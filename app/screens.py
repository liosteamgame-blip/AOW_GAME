"""صفحه‌های منوی اقتصادی، دارایی، ارتقا و مشاور."""

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV, ORDERS, XAI_API_KEY
from app.state import pending_confirms
from app.states import GameStates
from app.utils import e, fmt_num, mtype_tag, send_chunks
from app.factions import FACTIONS, FACTION_META
from app.players import (
    city_for_callback,
    city_of,
    is_admin,
    is_leader,
    is_player,
    leader_side,
    player_group_access,
    resolve_player_city,
    side_of_user,
)
from app.keyboards import _btn, get_back_keyboard, get_confirm_keyboard, get_economy_menu_keyboard, get_inline_back_row
from app.economy.rules import UPGRADE_SECTIONS
from app.economy.sheet import get_city_asset_stats, normalize_stats_keys
from app.economy.assets import is_auto_city
from app.economy.views import format_city_asset_view


async def open_economy_menu(callback: types.CallbackQuery, state: FSMContext):
    """نمایش خلاصه دارایی شهر + دکمه‌های اقتصادی."""
    uid = callback.from_user.id
    ok, city, err = city_for_callback(callback)
    if not ok or not city:
        city = resolve_player_city(uid) or city_of(uid)
    if city:
        await state.update_data(upg_city=city, active_city=city)
    lines = [f"💰 <b>منوی اقتصادی</b>\n{DIV}"]
    if city and city != "ناشناس":
        lines.append(f"🏙 شهر: <b>{e(city)}</b>")
        auto = is_auto_city(city)
        lines.append(f"🤖 اتو: {'✅ فعال (تست)' if auto else '❌ غیرفعال'}")
        bag = normalize_stats_keys(get_city_asset_stats(city))
        if bag:
            coins = bag.get("سکه") or 0
            food = bag.get("غذا") or 0
            pop = bag.get("جمعیت") or 0
            lines.append(f"💰 سکه: <b>{fmt_num(coins)}</b> · 🍽 غذا: <b>{fmt_num(food)}</b> · 👥 جمعیت: <b>{fmt_num(pop)}</b>")
        else:
            lines.append("📭 دارایی ثبت نشده — ادمین «ست دارایی» کند.")
    else:
        lines.append("شهر شما مشخص نیست.")
    lines.append("\nاز دکمه‌ها استفاده کنید:")
    text = "\n".join(lines)
    kb = get_economy_menu_keyboard(uid)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)

async def start_auto_upgrade(callback: types.CallbackQuery, state: FSMContext):
    """منوی بخش‌های ارتقا."""
    uid = callback.from_user.id
    data = await state.get_data()
    ok, city, err = city_for_callback(callback)
    if not ok or not city:
        city = data.get("upg_city") or data.get("active_city") or resolve_player_city(uid) or city_of(uid)
    if city:
        await state.update_data(upg_city=city, active_city=city)
    if not city or city == "ناشناس":
        return await callback.message.answer(
            "❌ شهر مشخص نیست.",
            reply_markup=get_inline_back_row("menu:economy"),
        )
    if not is_auto_city(city) and not is_admin(uid):
        return await callback.message.answer(
            f"🔒 حالت اتو برای <b>{e(city)}</b> فعال نیست.\n"
            "ادمین → «🤖 شهرهای اتو» را برای تست روشن کند.",
            reply_markup=get_inline_back_row("menu:economy"),
        )
    await state.update_data(upg_city=city)
    builder = InlineKeyboardBuilder()
    for key, (title, _items) in UPGRADE_SECTIONS.items():
        builder.row(_btn(title, f"upg:sec:{key}", "primary"))
    builder.row(_btn("✍️ دستور متنی", "upg:text", "success"))
    builder.row(_btn("🔙 بازگشت", "menu:economy"))
    text = (
        f"⬆️ <b>ارتقا — {e(city)}</b>\n{DIV}\n"
        "بخش را انتخاب کنید، سپس ساختمان و تعداد سطح.\n"
        "هزینه از قوانین محاسبه می‌شود و فقط بعد از زدن «✅ تایید ارتقا» از خزانه کسر می‌شود."
    )
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup())


async def open_asset_edit_menu(callback: types.CallbackQuery):
    """منوی دکمه‌ای ویرایش دارایی — فقط ادمین."""
    builder = InlineKeyboardBuilder()
    builder.row(_btn("➕ اضافه منابع", "aedit:add_res", "success"))
    builder.row(_btn("➖ کسر منابع", "aedit:sub_res", "danger"))
    builder.row(_btn("💀 تلفات نیرو", "aedit:loss", "danger"))
    builder.row(_btn("📈 بازدهی آپ", "aedit:yield", "primary"))
    builder.row(_btn("🌟 نیروهای ویژه", "aedit:special", "primary"))
    builder.row(_btn("⌨️ ورود متنی سریع", "aedit:text", "success"))
    builder.row(_btn("🔙 بازگشت", "menu:economy"))
    await callback.message.answer(
        f"✏️ <b>ویرایش دارایی</b>\n{DIV}\n"
        "دکمه بزنید یا مستقیم بنویسید:\n"
        "<code>ویرایش دارایی +50 چوب -100 سکه</code>\n"
        "<code>ویرایش دارایی تلفات شبه نظامی 50</code>",
        reply_markup=builder.as_markup(),
    )


async def start_upgrade_advise(callback: types.CallbackQuery, state: FSMContext):
    """قدم ۱: انتخاب نوع مشاور."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return await callback.answer("❌ فقط فرمانده / لیدر / ادمین.", show_alert=True)
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("💰 اقتصادی", "advise_mode:econ", "success"),
        _btn("⚔️ نظامی", "advise_mode:mil", "danger"),
    )
    builder.row(
        _btn("🛡 زمینی", "advise_mode:land", "primary"),
        _btn("⚓️ دریایی", "advise_mode:naval", "primary"),
    )
    builder.row(_btn("⚖️ ترکیبی / بالانس", "advise_mode:balance", "success"))
    builder.row(_btn("💬 چت آزاد (پلن ۱–۲ پیام)", "advise_mode:chat", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    ai_note = "🤖 بعد از تحلیل محلی، «بازنگری گروک» با دکمه (سقف روزانه دارد)." if XAI_API_KEY else "💡 کلید Grok را در Variables ریلوی (<code>XAI_API_KEY</code>) بگذارید."
    await callback.message.answer(
        f"🧠 <b>مشاور ارتقا</b>\n{DIV}\n"
        "نوع مشاوره را انتخاب کنید:\n"
        "• اقتصادی / نظامی / زمینی / دریایی\n"
        "• ترکیبی برای حفظ بالانس\n"
        "• چت آزاد: ۱ یا ۲ پیام درباره سلیقه و پلن‌تان\n\n"
        f"{ai_note}",
        reply_markup=builder.as_markup(),
    )


async def start_asset_view(callback: types.CallbackQuery, state: FSMContext):
    """
    مشاهده دارایی:
    - پلیر عادی → فقط شیت شهر خودش
    - لیدر → شهرهای ساید + جمع قلمرو
    - ادمین → همه سایدها
    """
    uid = callback.from_user.id
    if not (is_player(uid) or is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    await callback.answer()

    # پلیر عادی (نه لیدر، نه ادمین) → شهر همین گپ (یا شهر اصلی در پی‌وی)
    if is_player(uid) and not is_leader(uid) and not is_admin(uid):
        ok, city, err = city_for_callback(callback, uid)
        if not ok or not city or city == "ناشناس":
            city = resolve_player_city(uid) or city_of(uid)
        if not city or city == "ناشناس":
            return await callback.message.answer(
                "❌ شهر شما مشخص نیست.",
                reply_markup=get_inline_back_row("menu:economy"),
            )
        text = format_city_asset_view(city)
        if len(text) > 3500:
            await send_chunks(callback.message, [text], reply_markup=None)
            return await callback.message.answer(
                "⬆️ شیت دارایی شما",
                reply_markup=get_inline_back_row("menu:economy"),
            )
        await callback.message.answer(text)
        return await callback.message.answer(
            "⬆️ شیت دارایی شما",
            reply_markup=get_inline_back_row("menu:economy"),
        )

    side = leader_side(uid)
    if is_admin(uid) and not side:
        builder = InlineKeyboardBuilder()
        for s in FACTIONS:
            flag, title = FACTION_META[s]
            builder.row(
                _btn(f"{flag} تکی", f"asset_view:cities:{s}", "success"),
                _btn(f"{flag} کل", f"asset_view:realm:{s}", "primary"),
            )
        builder.row(_btn("🔙 بازگشت", "menu:economy"))
        return await callback.message.answer(
            f"📦 <b>مشاهده دارایی</b>\n{DIV}\n"
            "• <b>تکی ساید</b> — انتخاب یک شهر از ساید\n"
            "• <b>کل ساید</b> — جمع کل قلمرو",
            reply_markup=builder.as_markup(),
        )
    if not side:
        side = side_of_user(uid)
    if not side or side not in FACTIONS:
        return await callback.message.answer(
            "❌ ساید شما مشخص نیست. لیدر باید با «ست لیدر» ثبت شود.",
            reply_markup=get_inline_back_row("menu:economy"),
        )
    flag, title = FACTION_META[side]
    okc, my_city, _ = city_for_callback(callback, uid)
    if not okc or not my_city:
        my_city = resolve_player_city(uid) or city_of(uid)
    builder = InlineKeyboardBuilder()
    # ۱ شخصی · ۲ تکی ساید · ۳ کل ساید
    builder.row(_btn("👤 دارایی شخصی (شهر همین گپ)", f"asset_view:mine:{side}", "primary"))
    builder.row(_btn("🏙 تکی ساید (انتخاب شهر)", f"asset_view:cities:{side}", "success"))
    builder.row(_btn("🌐 کل ساید (جمع قلمرو)", f"asset_view:realm:{side}", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:economy"))
    city_hint = f"\n🏙 شهر شما: <code>{e(my_city)}</code>" if my_city and my_city != "ناشناس" else ""
    await callback.message.answer(
        f"📦 <b>دارایی {flag}{title}</b>\n{DIV}\n"
        "1️⃣ <b>شخصی</b> — شیت شهر خودتان\n"
        "2️⃣ <b>تکی ساید</b> — یک شهر از ساید را انتخاب کنید\n"
        "3️⃣ <b>کل ساید</b> — فقط آمار جمع‌خورده قلمرو"
        f"{city_hint}",
        reply_markup=builder.as_markup(),
    )


# ---------------- مراحل مشترک فرم فرمان‌ها (فرم عادی + «مثل دفعه قبل») ----------------
CAMP_TIME_PROMPT = (
    "⏳ <b>زمان رسیدن</b> را بفرستید:\n"
    "• ساعت: <code>12:00</code>\n"
    "• یا دقیقه از الان: <code>45</code> (مثلاً ۹:۳۱ + ۴۵ → ۱۰:۱۶)\n"
    "• چند زمان: <code>12:00,14:30</code>\n↩️ ریپلای کنید."
)


async def ask_camp_time(message: types.Message, state: FSMContext):
    await message.answer(CAMP_TIME_PROMPT, reply_markup=get_back_keyboard())
    await state.set_state(GameStates.camp_time)


async def show_order_confirm(message: types.Message, state: FSMContext, uid: int):
    """کارت تایید محاصره/جنگ. uid جدا گرفته می‌شود چون message ممکن است پیام خود ربات باشد."""
    d = await state.get_data()
    pending_confirms[uid] = {"kind": d.get("kind", "siege"), "data": dict(d), "chat_id": message.chat.id}
    _ok, ctx_city, _err = player_group_access(uid, message.chat.id, message.chat.type)
    icon = "🔥" if d.get("kind") == "war" else "🏰"
    await message.answer(
        f"{icon} <b>پیش‌نویس فرمان {ORDERS[d['kind']]['noun']}</b>\n{DIV}\n"
        f"👑 فرمانده: <b>{e(ctx_city or city_of(uid))}</b>\n"
        f"🧭 نوع: <b>{mtype_tag(d)}</b>\n"
        f"🎯 شهر هدف: <b>{e(d['target'])}</b>\n\n"
        f"📊 <b>آمار ارتش:</b>\n<blockquote expandable>{e(d['stats'])}</blockquote>\n"
        "سرورم، فرمان صادر شود؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.order_confirm)
