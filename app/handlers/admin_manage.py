"""هندلرهای admin_manage"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.loader import bot, dp
from app.state import CITY_ASSETS, GROUPS, PLAYER_CODES, all_players, authenticated_users
from app.utils import e
from app.factions import FACTIONS, FACTION_META, country_key, gen_code
from app.states import GameStates
from app.players import code_owner, is_admin, mention, user_fsm
from app.keyboards import (
    _btn,
    admin_help_text,
    get_admin_inline_keyboard,
    get_back_keyboard,
    get_manage_keyboard,
)
from app.storage import save_data
from app.economy.assets import realm_breakdown
from app.economy.views import format_assets_block, format_realm_view


# ---------------- دارایی در پنل ادمین ----------------
@dp.callback_query(F.data == "adm_assets")
async def admin_assets_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    for side in FACTIONS:
        flag, title = FACTION_META[side]
        n = sum(1 for c in CITY_ASSETS if country_key(c) == side)
        builder.row(_btn(f"{flag} {title} ({n} شهر)", f"adm_assets_side:{side}"))
    builder.row(_btn("🌐 جمع کل همه سایدها", "adm_assets_side:all"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"📦 <b>دارایی قلمروها</b>\n{DIV}\n"
        "ساید را برای مشاهده جمع انتخاب کنید.\n"
        "ثبت دارایی از گروه شهر با <code>ست دارایی</code> انجام می‌شود.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("adm_assets_side:"))
async def admin_assets_side(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    side = callback.data.split(":")[1]
    await callback.answer()
    if side == "all":
        parts = []
        for s in FACTIONS:
            parts.append(format_realm_view(s))
        text = "\n\n".join(parts)
    else:
        if side not in FACTIONS:
            return await callback.message.answer("❌ ساید نامعتبر.", reply_markup=get_admin_inline_keyboard())
        text = format_realm_view(side)
        # جزئیات عددی هر شهر همان ساید
        _, by_city, _ = realm_breakdown(side)
        if by_city:
            chunks = [text, ""]
            for city, st in by_city.items():
                chunks.append(format_assets_block(f"{city} (اعداد)", st))
            text = "\n".join(chunks)
    await callback.message.answer(text[:4000], reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_help")
async def admin_help(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(admin_help_text(), reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_manage")
async def admin_manage(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer("⚙️ <b>مدیریت شهرها و دسترسی‌ها</b>\n\nیکی از گزینه‌ها را انتخاب کنید:", reply_markup=get_manage_keyboard())


async def show_revoke_list(message: types.Message):
    players = [(uid, u) for uid, u in authenticated_users.items() if u.get("role") == "player"]
    if not players:
        return await message.answer("👥 هنوز هیچ فرماندهای وارد بازی نشده است.", reply_markup=get_manage_keyboard())
    builder = InlineKeyboardBuilder()
    for uid, u in players:
        builder.button(text=f"❌ {u.get('country', '؟')} | {uid}", callback_data=f"revoke:{uid}")
    builder.button(text="🔙 بازگشت", callback_data="adm_manage")
    builder.adjust(1)
    await message.answer("👤 روی هر شهر بزنید تا دسترسی فرمانده‌ی آن حذف شود:", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "adm_revoke_list")
async def admin_revoke_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await show_revoke_list(callback.message)


@dp.callback_query(F.data.startswith("revoke:"))
async def handle_revoke_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    p_id = int(callback.data.split(":")[1])
    u = authenticated_users.get(p_id)
    if not u:
        return await callback.answer("این فرمانده دیگر فعال نیست.", show_alert=True)
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ بله، حذف شود", callback_data=f"revoke_yes:{p_id}")
    builder.button(text="🔙 انصراف", callback_data="adm_revoke_list")
    builder.adjust(1)
    await callback.message.answer(
        f"⚠️ دسترسی فرمانده‌ی شهر <b>{e(u.get('country', '؟'))}</b> (آیدی <code>{p_id}</code>) حذف شود؟\n"
        f"کد این شهر (<code>{e(u.get('code', '-'))}</code>) باطل می‌شود و ربات دیگر او را نمی‌شناسد.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("revoke_yes:"))
async def handle_revoke_player(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    p_id = int(callback.data.split(":")[1])
    u = authenticated_users.pop(p_id, None)
    all_players.discard(p_id)
    if not u:
        await callback.answer("این فرمانده دیگر فعال نیست.", show_alert=True)
        return await show_revoke_list(callback.message)

    PLAYER_CODES.pop(u.get("code"), None)   # کد باطل می‌شود
    save_data()

    try:                                     # وضعیت گفتگوی بازیکن پاک می‌شود
        await user_fsm(p_id).clear()
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=p_id,
            text=f"⚠️ دسترسی شما به عنوان فرمانده‌ی شهر <b>{e(u.get('country', '؟'))}</b> توسط ادمین لغو شد و کد شما باطل گردید.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        pass

    await callback.answer("دسترسی فرمانده حذف شد.")
    await callback.message.answer(
        f"✅ دسترسی فرمانده‌ی شهر <b>{e(u.get('country', '؟'))}</b> حذف و کد <code>{e(u.get('code', '-'))}</code> باطل شد.\n"
        "برای این شهر کد تازه‌ای بخواهید، از «➕ افزودن شهر و ساخت کد» استفاده کنید.",
        reply_markup=get_manage_keyboard(),
    )


@dp.callback_query(F.data == "adm_del_city_list")
async def admin_del_city_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    if not PLAYER_CODES:
        return await callback.message.answer("شهری ثبت نشده.", reply_markup=get_manage_keyboard())
    builder = InlineKeyboardBuilder()
    for code, city in sorted(PLAYER_CODES.items(), key=lambda kv: str(kv[1]).lower()):
        uid = code_owner(code)
        tag = f" · ID:{uid}" if uid else ""
        label = f"🗑 {city} | {code}{tag}"
        if len(label) > 60:
            label = label[:58] + "…"
        builder.row(_btn(label, f"delcity:{code}", "danger"))
    builder.row(_btn("🔙 بازگشت", "adm_manage"))
    await callback.message.answer(
        f"🏙 <b>حذف شهر</b>\n{DIV}\nروی مورد اضافی بزنید تا حذف شود:\n"
        f"(کد + آیدی فرمانده اگر باشد نمایش داده می‌شود)",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("delcity:"))
async def admin_del_city_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    code = callback.data.split(":", 1)[1]
    city = PLAYER_CODES.get(code)
    if not city:
        return await callback.answer("این شهر دیگر نیست.", show_alert=True)
    await callback.answer()
    uid = code_owner(code)
    builder = InlineKeyboardBuilder()
    builder.row(_btn("✅ بله حذف شود", f"delcityyes:{code}", "danger"))
    builder.row(_btn("🔙 انصراف", "adm_del_city_list"))
    extra = f"\n👤 فرمانده: {mention(uid)} · <code>{uid}</code>" if uid else "\n👤 فرمانده: —"
    await callback.message.answer(
        f"⚠️ حذف شهر <b>{e(city)}</b>\n🔑 کد: <code>{e(code)}</code>{extra}\n\n"
        "کد باطل و فرمانده (در صورت وجود) هم حذف می‌شود.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("delcityyes:"))
async def admin_del_city_yes(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    code = callback.data.split(":", 1)[1]
    city = PLAYER_CODES.pop(code, None)
    if not city:
        await callback.answer("از قبل حذف شده.", show_alert=True)
        return
    # حذف فرمانده مرتبط
    uid = None
    for u_id, u in list(authenticated_users.items()):
        if u.get("role") == "player" and u.get("code") == code:
            uid = u_id
            authenticated_users.pop(u_id, None)
            all_players.discard(u_id)
            break
    # قطع گروه‌های این شهر
    for gid, g in list(GROUPS.items()):
        if (g.get("code") == code) or (g.get("city") or "").lower() == str(city).lower():
            GROUPS.pop(gid, None)
    save_data(critical=True)
    await callback.answer("حذف شد")
    msg = f"✅ شهر <b>{e(city)}</b> حذف شد.\n🔑 کد باطل: <code>{e(code)}</code>"
    if uid:
        msg += f"\n👤 فرمانده <code>{uid}</code> هم حذف شد."
    await callback.message.answer(msg, reply_markup=get_manage_keyboard())


@dp.callback_query(F.data == "adm_add_city")
async def admin_add_city_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "👑 <b>مالک محترم</b> لطفا <b>نام شهر و کشور</b> پلیر را مانند فرمت (<code>آمیان_فرانسه</code> یا <code>york_england</code>) وارد کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.admin_add_city)


@dp.message(GameStates.admin_add_city)
async def admin_add_city_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name:
        return await message.answer("❌ نام شهر را به صورت متن ارسال کنید:")
    parts = name.split("_")
    if len(parts) < 2 or not parts[0].strip() or not parts[-1].strip():
        return await message.answer("❌ فرمت درست نیست. مانند (آمیان_فرانسه) یا (york_england) وارد کنید:")
    if len(name) > 60:
        return await message.answer("❌ نام خیلی طولانی است. کوتاه‌تر بنویسید:")
    if any(n.strip().lower() == name.lower() for n in PLAYER_CODES.values()):
        return await message.answer("❌ این شهر از قبل ثبت شده است. نام دیگری بفرستید:")

    code = gen_code()
    PLAYER_CODES[code] = name
    save_data()
    await message.answer(
        f"✅ شهر <b>{e(name)}</b> اضافه شد.\n🔑 کد ورود: <code>{e(code)}</code>\n\n"
        "این کد را برای فرمانده‌ی همان شهر بفرستید.",
        reply_markup=get_manage_keyboard(),
    )
    await state.clear()


@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer("⚡️ منوی اصلی مدیریت:", reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_logout")
async def admin_logout(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    # فقط پنل بسته می‌شود — قبلاً رکورد کاربر حذف می‌شد و ادمین فرعی/داده‌ی پلیرِ او برای همیشه از دست می‌رفت
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("🚪 پنل مدیریت بسته شد. برای باز کردن دوباره /start یا ADMIN بزنید.", reply_markup=ReplyKeyboardRemove())
    await state.clear()
