"""هندلرهای group_assets"""
import re

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import ADMIN_ID, DIV
from app.loader import bot, dp
from app.state import GROUPS, all_players, authenticated_users, pending_confirms
from app.utils import e, is_back_text, norm_cmd, send_chunks
from app.rulecal import admin_tag, block_message
from app.factions import _canonical_city_name, country_key
from app.states import GameStates
from app.players import (
    _players_of_city,
    city_from_message,
    is_admin,
    is_leader,
    is_player,
    mention,
    player_group_access,
    resolve_player_city,
)
from app.keyboards import (
    _btn,
    get_admin_inline_keyboard,
    get_back_keyboard,
    get_group_inquiry_keyboard,
)
from app.storage import save_data
from app.economy.rules import UPGRADE_TABLE
from app.economy.sheet import extract_asset_stats, set_city_asset
from app.economy.assets import apply_upgrade_levels, is_auto_city
from app.economy.views import format_city_asset_view, format_realm_view, format_stats_labeled
from app.handlers.groups import GROUP_INQUIRY_CMDS


# ---- ست دارایی در گروه شهر ----
SET_ASSET_CMDS = {
    "ستدارایی", "setasset", "setassets",
}
REGISTER_ASSET_CMDS = {
    "ثبتتغییردارایی", "ثبتدارایی", "registerasset", "updateasset",
}


async def _register_asset_now(message: types.Message, state: FSMContext, raw: str, city: str):
    """ثبت فوری دارایی برای شهر و نمایش خلاصه."""
    if not city:
        await state.update_data(asset_text=raw, asset_stats=extract_asset_stats(raw))
        await message.answer(
            "✅ متن دریافت شد.\nنام شهر را بنویسید (مثال: <code>oxford_monarchist</code>):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.adm_set_asset_city)
        return
    city = _canonical_city_name(city)
    stats = set_city_asset(city, raw)
    save_data(critical=True)
    side = country_key(city)
    body = (
        f"✅ دارایی <b>{e(city)}</b> مستقیم ثبت شد.\n"
        f"اعداد استخراج‌شده: <b>{len(stats)}</b> مورد\n\n"
        f"{format_stats_labeled(stats)}\n\n"
    )
    if side:
        body += format_realm_view(side)
    await state.clear()
    await message.answer(body[:4000], reply_markup=get_admin_inline_keyboard() if is_admin(message.from_user.id) else None)


@dp.message(F.text.regexp(r"(?i)^\s*اعمال\s*ارتقا"))
async def handle_apply_upgrade_cmd(message: types.Message):
    """اعمال ارتقا: بندر 2, خزانه 1 — فقط شهر اتو"""
    uid = message.from_user.id
    if not (is_player(uid) or is_admin(uid) or is_leader(uid)):
        return
    ok, city, err = city_from_message(message, uid)
    if not ok:
        return await message.answer(err or "❌ دسترسی ندارید.")
    if not city or city == "ناشناس":
        return await message.answer("❌ شهر مشخص نیست.")
    if not is_auto_city(city) and not is_admin(uid):
        return await message.answer(
            f"🔒 اتو برای <b>{e(city)}</b> فعال نیست. ادمین باید تیک بزند."
        )
    blocked = block_message("upgrade", uid)
    if blocked:
        return await message.answer(blocked)
    body = re.sub(r"(?i)^\s*اعمال\s*ارتقا\s*:?\s*", "", message.text or "").strip()
    if not body:
        return await message.answer(
            "مثال:\n<code>اعمال ارتقا: بندر 2, خزانه 1</code>"
        )
    results = []
    for chunk in re.split(r"[,،]\s*", body):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"(.+?)\s+(\d+)\s*$", chunk)
        if m:
            name, lv = m.group(1).strip(), int(m.group(2))
        else:
            name, lv = chunk, 1
        # تطبیق نام با جدول
        matched = None
        for k in UPGRADE_TABLE:
            if k == name or k in name or name in k:
                matched = k
                break
        if not matched:
            results.append(f"❌ ناشناخته: {e(name)}")
            continue
        ok, msg = apply_upgrade_levels(city, matched, lv, force=is_admin(uid))
        results.append(msg if ok else f"❌ {msg}")
    await message.answer(
        f"⬆️ <b>اعمال ارتقا — {e(city)}</b>\n{DIV}\n" + "\n\n".join(results)
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📝 ارتقا اتو توسط {mention(uid, city)}\n🏙 {e(city)}\n" + "\n".join(results)[:1500] + admin_tag("upgrade"),
        )
    except Exception:
        pass


@dp.message(F.text.func(lambda t: norm_cmd(t) in ("دارایی", "مشاهدهدارایی", "asset", "assets", "viewasset")))
async def handle_view_assets_in_chat(message: types.Message, state: FSMContext):
    """با نوشتن «دارایی» در گپ: شیت همان شهر + منوی ویرایش/شاپ/ارتقا."""
    uid = message.from_user.id
    chat_id = message.chat.id
    chat_type = message.chat.type
    ok, city, err = player_group_access(uid, chat_id, chat_type)
    if is_admin(uid):
        if chat_type in ("group", "supergroup") and GROUPS.get(chat_id):
            city = GROUPS[chat_id].get("city") or city
            ok = True
        elif not city:
            city = resolve_player_city(uid)
            ok = bool(city)
    if not ok or not city:
        return await message.answer(err or "❌ دسترسی یا شهر مشخص نیست.")
    text = format_city_asset_view(city, viewer=uid)
    chunks = []
    body = text
    while body:
        chunks.append(body[:3500])
        body = body[3500:]
    for i, ch in enumerate(chunks):
        if i == len(chunks) - 1:
            builder = InlineKeyboardBuilder()
            if is_admin(uid):
                builder.row(_btn("✏️ ویرایش / تلفات", f"gasset:edit:{city}", "danger"))
                builder.row(_btn("🛒 ست شاپ", f"gasset:shop:{city}", "primary"))
                builder.row(_btn("⬆️ افزایش سطح", f"gasset:lv:{city}", "success"))
                builder.row(_btn("📉 ثبت تلفات", f"gasset:loss:{city}", "danger"))
                builder.row(_btn("🎛 باف/نرف/رول", f"gasset:buff:{city}", "primary"))
            builder.row(_btn("🔄 تازه‌سازی", f"gasset:view:{city}"))
            await message.answer(ch[:4000], reply_markup=builder.as_markup())
        else:
            await message.answer(ch[:4000])


@dp.callback_query(F.data.startswith("gasset:"))
async def handle_gasset_menu(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        return await callback.answer()
    action, city = parts[1], parts[2]
    # «تازه‌سازی» برای پلیر هم آزاد است؛ همه مسیرهای تغییر دارایی فقط ادمین
    allowed = is_admin(callback.from_user.id) or (action == "view" and is_player(callback.from_user.id))
    if not allowed:
        return await callback.answer("❌ فقط ادمین.", show_alert=True)
    await callback.answer()
    await state.update_data(gasset_city=city)
    if action == "view":
        body = format_city_asset_view(city, viewer=callback.from_user.id)
        return await send_chunks(callback.message, body.split("\n"))
    if action == "edit":
        await callback.message.answer(
            f"✏️ ویرایش دارایی <b>{e(city)}</b>\n"
            "مثال:\n<code>تلفات 50 شبه نظامی 30 شمشیرزن</code>\n"
            "<code>اضافه 100 چوب 50 آهن</code>\n"
            "<code>کسر 1000 سکه</code>",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.adm_set_timing)
        pending_confirms[callback.from_user.id] = {
            "kind": "gasset_edit", "data": {"city": city}, "chat_id": callback.message.chat.id,
        }
        return
    if action == "shop":
        await callback.message.answer(
            f"🛒 <b>ست شاپ — {e(city)}</b>\n" + DIV + "\n"
            "متن پک‌ها را بفرستید.\n"
            "مثال مزدوری:\n"
            "<code>مزدوری شمشیرزن 50 (10)</code>\n"
            "<code>گارد 20 (5)</code>\n"
            "عدد پرانتز = بازدهی هفتگی در آپ.",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.adm_shop_collect)
        await state.update_data(shop_city=city)
        return
    if action == "lv":
        await callback.message.answer(
            f"⬆️ افزایش سطح — <b>{e(city)}</b>\n"
            "فرمت:\n<code>افزایش لول ساختمان\nخزانه 1\nچوب بری 2\nشبه نظامی 3</code>",
            reply_markup=get_back_keyboard(),
        )
        pending_confirms[callback.from_user.id] = {
            "kind": "gasset_lv", "data": {"city": city}, "chat_id": callback.message.chat.id,
        }
        await state.set_state(GameStates.adm_set_timing)
        return
    if action == "loss":
        await callback.message.answer(
            f"📉 ثبت تلفات — <b>{e(city)}</b>\n"
            "فرمت:\n<code>ثبت تلفات\n500 شبه نظامی\n200 شمشیرزن</code>",
            reply_markup=get_back_keyboard(),
        )
        pending_confirms[callback.from_user.id] = {
            "kind": "gasset_loss", "data": {"city": city}, "chat_id": callback.message.chat.id,
        }
        await state.set_state(GameStates.adm_set_timing)
        return
    if action == "buff":
        await callback.message.answer(
            f"🎛 باف/نرف/رول — <b>{e(city)}</b>\n" + DIV + "\n"
            "فرم:\n<code>اعمال بازدهی رول و باف ونرف های شهر:\n"
            "بازدهی رول {سکه}: 500\n"
            "منبع(چوب) به تعداد(100)\n"
            "اعمال نرف بر روی دهکده به درصد(30)\n"
            "اعمال باف بر روی خزانه به درصد(50)</code>",
            reply_markup=get_back_keyboard(),
        )
        pending_confirms[callback.from_user.id] = {
            "kind": "gasset_buff", "data": {"city": city}, "chat_id": callback.message.chat.id,
        }
        await state.set_state(GameStates.adm_set_timing)
        return


@dp.message(F.text.func(lambda t: norm_cmd(t) in SET_ASSET_CMDS or norm_cmd(t) in REGISTER_ASSET_CMDS))
async def handle_set_assets_prompt(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    grp = GROUPS.get(message.chat.id) if message.chat.type in ("group", "supergroup") else None
    city_hint = grp["city"] if grp else None
    # ریپلای روی پیام شیت → ثبت مستقیم بدون ارسال مجدد
    replied = message.reply_to_message
    if replied and (replied.text or replied.caption):
        raw = (replied.text or replied.caption or "").strip()
        if raw:
            return await _register_asset_now(message, state, raw, city_hint)
    await state.update_data(asset_city_hint=city_hint)
    hint = f"شهر تشخیص‌داده‌شده: <b>{e(city_hint)}</b>\n" if city_hint else ""
    await message.answer(
        f"📦 <b>ثبت دارایی</b>\n{DIV}\n{hint}"
        "• روی پیام شیت دارایی <b>ریپلای</b> کنید و بنویسید <code>ست دارایی</code> "
        "تا همان پیام مستقیم ثبت شود.\n"
        "• یا متن کامل را همین‌جا بفرستید.\n\n"
        "ربات همان متن را ذخیره می‌کند و اعداد را برای جمع قلمرو استخراج می‌کند.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_asset_text)


@dp.message(GameStates.adm_set_asset_text)
async def handle_set_assets_text(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("❌ لغو شد.")
    # اگر ریپلای کرده باشد همان را بگیر
    raw = ""
    if message.reply_to_message and (message.reply_to_message.text or message.reply_to_message.caption):
        raw = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()
    if not raw:
        raw = (message.text or message.caption or "").strip()
    if not raw:
        return await message.answer("❌ متن خالی است. روی پیام شیت ریپلای کنید یا متن را بفرستید.")
    d = await state.get_data()
    hint = d.get("asset_city_hint")
    # اگر شهر مشخص است → ثبت مستقیم
    if hint:
        return await _register_asset_now(message, state, raw, hint)
    stats = extract_asset_stats(raw)
    await state.update_data(asset_text=raw, asset_stats=stats)
    preview_stats = (
        format_stats_labeled(stats)
        if stats
        else "— عددی برای جمع پیدا نشد (متن کامل ذخیره می‌شود) —"
    )
    if hint:
        builder = InlineKeyboardBuilder()
        builder.row(_btn(f"✅ ثبت برای {hint}", f"asset_confirm_city:{hint}", "success"))
        builder.row(_btn("✏️ شهر دیگر", "asset_pick_other"))
        builder.row(_btn("❌ انصراف", "menu:home", "danger"))
        await message.answer(
            f"✅ متن دریافت شد ({len(raw)} کاراکتر).\n"
            f"اعداد استخراج‌شده (بخش‌بندی‌شده):\n{DIV}\n{preview_stats}\n\n"
            f"برای کدام شهر ثبت شود؟",
            reply_markup=builder.as_markup(),
        )
    else:
        await message.answer(
            f"✅ متن دریافت شد.\nاعداد استخراج‌شده:\n{DIV}\n{preview_stats}\n\n"
            "نام شهر را بنویسید (مثال: <code>london_monarchist</code>):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.adm_set_asset_city)


@dp.callback_query(F.data.startswith("asset_confirm_city:"))
async def asset_confirm_city(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    city = callback.data.split(":", 1)[1]
    d = await state.get_data()
    raw = d.get("asset_text") or ""
    if not raw:
        return await callback.answer("متن خالی است.", show_alert=True)
    stats = set_city_asset(city, raw)
    save_data(critical=True)
    await callback.answer("ثبت شد")
    side = country_key(city)
    await state.clear()
    body = f"✅ دارایی <b>{e(city)}</b> ثبت شد.\nاعداد استخراج‌شده: {len(stats)} مورد\n\n"
    if side:
        body += format_realm_view(side)
    else:
        body += "⚠️ ساید شهر تشخیص داده نشد؛ در جمع قلمرو لحاظ نمی‌شود."
    await callback.message.answer(
        body[:4000],
        reply_markup=get_admin_inline_keyboard() if is_admin(callback.from_user.id) else None,
    )


@dp.callback_query(F.data == "asset_pick_other")
async def asset_pick_other(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "نام شهر را بنویسید (مثال: <code>کمبریج_انگلیس</code>):",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_asset_city)


@dp.message(GameStates.adm_set_asset_city)
async def handle_set_assets_city(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("❌ لغو شد.")
    city = (message.text or "").strip()
    d = await state.get_data()
    raw = d.get("asset_text") or ""
    if not raw:
        await state.clear()
        return await message.answer("❌ متن خالی است.")
    stats = set_city_asset(city, raw)
    save_data(critical=True)
    side = country_key(city)
    await state.clear()
    body = f"✅ دارایی <b>{e(city)}</b> ثبت شد.\nاعداد استخراج‌شده: {len(stats)} مورد\n\n"
    if side:
        body += format_realm_view(side)
    else:
        body += "⚠️ ساید شهر تشخیص داده نشد؛ در جمع قلمرو لحاظ نمی‌شود."
    await message.answer(body[:4000], reply_markup=get_admin_inline_keyboard())


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in GROUP_INQUIRY_CMDS))
async def handle_group_inquiry(message: types.Message):
    """استعلام گپ: نام شهر + آیدی پلیر + منوی حذف."""
    if not is_admin(message.from_user.id):
        return
    gid = message.chat.id
    grp = GROUPS.get(gid)
    if not grp:
        return await message.answer(
            "ℹ️ این گروه هنوز به شهری وصل نیست.\n"
            "با /start و «ست گپ» متصل کنید."
        )
    city = grp.get("city", "-")
    code = grp.get("code", "-")
    fac = country_key(city)
    flag = {
        "monarchist": "👑",
        "parliamentarian": "🏛",
        "england": "🇬🇧",
        "france": "🇫🇷",
        "ireland": "🇮🇪",
    }.get(fac, "🏙")
    players = _players_of_city(city)
    lines = [
        f"🔍 <b>استعلام گپ</b>\n{DIV}\n",
        f"{flag} شهر: <b>{e(city)}</b>",
        f"🔑 کد: <code>{e(code)}</code>",
        f"💬 گروه: <b>{e(message.chat.title or '')}</b>",
        f"🆔 آیدی گروه: <code>{gid}</code>",
        "",
    ]
    pids = []
    if players:
        lines.append("👤 <b>فرمانده(ها):</b>")
        for uid, u in players:
            pids.append(uid)
            uname = f" @{e(u['username'])}" if u.get("username") else ""
            lines.append(
                f"• {mention(uid, u.get('name') or 'فرمانده')}{uname}\n"
                f"  🆔 <code>{uid}</code>"
            )
    else:
        lines.append("👤 فرمانده: <i>هنوز تعیین نشده</i>")
    await message.answer(
        "\n".join(lines),
        reply_markup=get_group_inquiry_keyboard(gid, city, pids),
    )


@dp.callback_query(F.data.startswith("inq_delplayer:"))
async def inquiry_del_player(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ فقط ادمین.", show_alert=True)
    try:
        uid = int(callback.data.split(":")[1])
    except ValueError:
        return await callback.answer()
    u = authenticated_users.pop(uid, None)
    all_players.discard(uid)
    save_data(critical=True)
    await callback.answer("حذف شد", show_alert=True)
    city = (u or {}).get("country", "-")
    try:
        await callback.message.edit_text(
            f"✅ فرمانده <code>{uid}</code> از شهر <b>{e(city)}</b> حذف شد.\n"
            f"برای استعلام دوباره بنویسید: <code>استعلام گپ</code>",
            reply_markup=None,
        )
    except Exception:
        await callback.message.answer(f"✅ فرمانده <code>{uid}</code> حذف شد.")


@dp.callback_query(F.data.startswith("inq_unlink:"))
async def inquiry_unlink_group(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ فقط ادمین.", show_alert=True)
    try:
        gid = int(callback.data.split(":")[1])
    except ValueError:
        return await callback.answer()
    old = GROUPS.pop(gid, None)
    save_data(critical=True)
    await callback.answer("گروه قطع شد", show_alert=True)
    city = (old or {}).get("city", "-")
    try:
        await callback.message.edit_text(
            f"✅ اتصال گروه از شهر <b>{e(city)}</b> قطع شد.\n"
            f"گروه دیگر به این شهر وصل نیست.",
            reply_markup=None,
        )
    except Exception:
        await callback.message.answer("✅ اتصال گروه قطع شد.")


@dp.callback_query(F.data == "inq_close")
async def inquiry_close(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
