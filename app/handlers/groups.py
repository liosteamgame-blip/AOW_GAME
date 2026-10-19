"""هندلرهای groups"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app import state as app_state
from app.config import ADMIN_ID, MENU_TEXT
from app.loader import bot, dp
from app.state import GROUPS, PLAYER_CODES, all_players, authenticated_users
from app.utils import e, is_back_text, norm_cmd
from app.factions import gen_code, seed_default_cities
from app.states import GameStates
from app.players import (
    chat_fsm,
    is_admin,
    is_group_chat,
    is_player,
    link_player_to_group,
    mention,
    player_cities,
)
from app.keyboards import get_admin_inline_keyboard, get_country_keyboard, get_main_menu_keyboard
from app.storage import save_data


@dp.callback_query(F.data == "grp_setcity")
async def handle_group_setcity(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id) or not is_group_chat(callback.message):
        return await callback.answer()
    await callback.answer()
    if not PLAYER_CODES:
        seed_default_cities()
        save_data(critical=True)
    await state.set_state(GameStates.group_set_city)
    await callback.message.answer(
        "🏙 <b>ست گپ</b> — اول کشور را انتخاب کنید، بعد شهر:\n"
        "یا نام را دستی بنویسید مثل <code>آمیان_فرانسه</code>",
        reply_markup=get_country_keyboard("grp_city"),
    )


async def _link_group_to_city(message: types.Message, state: FSMContext, name: str):
    """اتصال گروه جاری به شهر (از منو یا ورودی دستی)."""
    name = (name or "").strip()
    if not name:
        return await message.answer("❌ نام شهر خالی است.")
    if len(name) > 60:
        return await message.answer("❌ نام خیلی طولانی است.")
    # اگر بدون _ بود و فقط از لیست انتخاب شده OK است
    existing = next((c for c, n in PLAYER_CODES.items() if n.lower() == name.lower()), None)
    if existing:
        code, canon_name = existing, PLAYER_CODES[existing]
    else:
        if "_" not in name:
            return await message.answer(
                "❌ فرمت دستی: <code>نامشهر_کشور</code>\nمثال: <code>کمبریج_انگلیس</code>"
            )
        code, canon_name = gen_code(), name
        PLAYER_CODES[code] = canon_name

    GROUPS[message.chat.id] = {"city": canon_name, "code": code}
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ این گروه به شهر <b>{e(canon_name)}</b> متصل شد.\n"
        f"🔑 کد ورود: <code>{e(code)}</code>\n\n"
        "👤 برای تعیین فرمانده، روی پیام او <b>ریپلای</b> و بنویسید: "
        "<code>ست پلیر</code> یا <code>/set player</code>"
    )


@dp.message(GameStates.group_set_city)
async def process_group_setcity(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("❌ لغو شد.")
    await _link_group_to_city(message, state, message.text or "")


SET_PLAYER_CMDS = {"ستپلیر", "setplayer"}
SET_ADMIN_CMDS = {"ستادمین", "setadmin"}
ADMIN_WORD = "admin"
GROUP_INQUIRY_CMDS = {
    "استعلامگپ", "استعلام", "estelamgap", "estelam", "inquiry", "groupinfo", "گپاینفو",
}


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in SET_PLAYER_CMDS))
async def handle_set_group_player(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    grp = GROUPS.get(message.chat.id)
    if not grp:
        return await message.answer("❌ اول باید این گروه را با «ست گپ» به یک شهر وصل کنید. /start را بزنید.")
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام فرمانده‌ی مورد نظر ریپلای کنید و دوباره «ست پلیر» یا «/set player» را بفرستید.")

    target = target_msg.from_user
    city_name = grp["city"]
    already = authenticated_users.get(target.id) or {}
    was_player = already.get("role") == "player" or is_player(target.id)
    link_player_to_group(target.id, message.chat.id, city_name, user_obj=target)
    # کد گپ را هم بنویس
    u = authenticated_users[target.id]
    if not u.get("code"):
        u["code"] = grp.get("code") or ""
        authenticated_users[target.id] = u
    cities_now = player_cities(target.id)
    note = ""
    if was_player:
        note = " (قبلاً ثبت — بدون کد مجدد · شهرها: " + "، ".join(cities_now) + ")"
    save_data(critical=True)

    tfsm = chat_fsm(message.chat.id, target.id)
    await tfsm.clear()
    await tfsm.set_state(GameStates.main_menu)

    await message.answer(
        f"✅ {mention(target.id, target.full_name)} فرمانده‌ی شهر <b>{e(grp['city'])}</b> در این گروه شد.{note}\n\n{MENU_TEXT}",
        reply_markup=get_main_menu_keyboard(),
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text=(
                f"👑 شما فرمانده‌ی شهر <b>{e(grp['city'])}</b> در گروه «{e(message.chat.title or '')}» شدید.\n"
                "در هر گپی که ست شده‌اید با همان شهر کار می‌کنید. نیازی به ثبت‌نام مجدد نیست."
            ),
        )
    except Exception:
        pass


SET_ASSIST_CMDS = {"ستکمکی", "setassistant", "sethelper", "ست‌کمکی"}


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in SET_ASSIST_CMDS))
async def handle_set_group_assistant(message: types.Message):
    """
    ست کمکی: ریپلای روی پیام پلیر + «ست کمکی»
    کمکی همان دسترسی فرمانده را فقط برای همین گپ/شهر دارد — با شهرهای دیگر قاطی نمی‌شود.
    """
    if not is_admin(message.from_user.id):
        return
    grp = GROUPS.get(message.chat.id)
    if not grp:
        return await message.answer("❌ اول «ست گپ» را برای این گروه بزنید.")
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام شخص کمکی ریپلای کنید و «ست کمکی» بفرستید.")
    target = target_msg.from_user
    city_name = grp.get("city") or ""
    # لینک پایدار به همین شهر/گپ
    link_player_to_group(target.id, message.chat.id, city_name, user_obj=target)
    g = dict(GROUPS.get(message.chat.id) or grp)
    asst = list(g.get("assistants") or [])
    if target.id not in asst:
        asst.append(target.id)
    g["assistants"] = asst
    # از commanders هم باشد تا دسترسی کامل همین گپ
    cmds = list(g.get("commanders") or [])
    if target.id not in cmds:
        cmds.append(target.id)
    g["commanders"] = cmds
    GROUPS[message.chat.id] = g
    u = dict(authenticated_users.get(target.id) or {})
    u["role"] = u.get("role") or "player"
    groups_map = dict(u.get("groups") or {})
    groups_map[str(message.chat.id)] = city_name
    u["groups"] = groups_map
    cities = list(u.get("cities") or [])
    if city_name and city_name not in cities:
        cities.append(city_name)
    u["cities"] = cities
    authenticated_users[target.id] = u
    all_players.add(target.id)
    save_data(critical=True)
    await message.answer(
        f"✅ {mention(target.id, target.full_name)} <b>کمکی</b> شهر <b>{e(city_name)}</b> شد.\n"
        f"در این گپ هر کاری با بات (لشکرکشی/ارتقا/تجارت/…) می‌تواند بکند.\n"
        f"در گپ دیگر فقط اگر آنجا هم ست شده باشد — دارایی‌ها قاطی نمی‌شوند."
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text=(
                f"🤝 شما کمکی شهر <b>{e(city_name)}</b> شدید.\n"
                f"فقط در گپ همان شهر به دارایی و دستورات دسترسی دارید."
            ),
        )
    except Exception:
        pass


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) == ADMIN_WORD))
async def handle_group_admin_word(message: types.Message):
    """در هر گروهی، تایپ کلمه‌ی ADMIN توسط یک ادمین، پنل مدیریت را همان‌جا باز می‌کند."""
    if not is_admin(message.from_user.id):
        return
    await message.answer("⚡️ پنل مدیریت شیشه‌ای:", reply_markup=get_admin_inline_keyboard())


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in SET_ADMIN_CMDS))
async def handle_set_group_admin(message: types.Message):
    """ادمین با ریپلای روی پیام یک عضو و فرستادن «ست ادمین» یا «/set admin»، به او دسترسی ادمین می‌دهد."""
    if not is_admin(message.from_user.id):
        return
    # فقط مالک (ADMIN_ID) می‌تواند ادمین جدید بسازد — ادمین فرعی نمی‌تواند زنجیره‌وار ادمین بسازد
    if message.from_user.id != ADMIN_ID:
        return await message.answer("❌ فقط مالک ربات می‌تواند ادمین جدید تعیین کند.")
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام عضو مورد نظر ریپلای کنید و دوباره «/set admin» را بفرستید.")

    target = target_msg.from_user
    if is_admin(target.id):
        return await message.answer(f"ℹ️ {mention(target.id, target.full_name)} از قبل ادمین است.")

    prev = dict(authenticated_users.get(target.id) or {})
    # شهر/گروه‌های قبلی (اگر پلیر بوده) حفظ می‌شود
    authenticated_users[target.id] = {**prev, "role": "admin", "country": prev.get("country") or "مدیریت کل"}
    save_data(critical=True)
    await message.answer(f"✅ {mention(target.id, target.full_name)} اکنون دسترسی ادمین دارد.")
    try:
        await bot.send_message(chat_id=target.id, text="⚡️ شما توسط ادمین کل، دسترسی ادمین دریافت کردید. برای ورود به پنل، عبارت ADMIN را بفرستید.")
    except Exception:
        pass


# ---- ست ادمین دارایی (ریپلای) ----
SET_ASSET_ADMIN_CMDS = {
    "ستادمیندارایی", "setassetadmin", "setadminasset", "ادمیندارایی",
}


@dp.message(F.text.func(lambda t: norm_cmd(t) in SET_ASSET_ADMIN_CMDS))
async def handle_set_asset_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام کاربر ریپلای کنید و «ست ادمین دارایی» بفرستید.")
    target = target_msg.from_user
    app_state.ASSET_ADMIN_ID = target.id
    save_data(critical=True)
    await message.answer(
        f"✅ {mention(target.id, target.full_name)} ادمین دارایی شد.\n"
        f"گزارش کامل تجارت برای ایشان هم ارسال می‌شود.\n🆔 <code>{target.id}</code>"
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text="📦 شما به‌عنوان <b>ادمین دارایی</b> تنظیم شدید. گزارش‌های کامل تجارت برایتان می‌آید.",
        )
    except Exception:
        pass
