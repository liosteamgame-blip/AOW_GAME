"""هندلرهای trade"""
import logging
import secrets
import time

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import state as app_state
from app.config import DIV
from app.loader import bot, dp
from app.state import MERCHANT_LIMITS, PENDING_TRADES, active_actions, pending_confirms
from app.utils import (
    apply_buff,
    e,
    fmt_num,
    format_goods,
    need_text,
    normalize_digits,
    parse_goods_list,
)
from app.states import GameStates
from app.players import city_of, is_admin, is_player, mention
from app.gametime import parse_player_time
from app.keyboards import (
    _btn,
    get_back_keyboard,
    get_cities_keyboard,
    get_confirm_keyboard,
    get_main_menu_keyboard,
    get_trade_channel_buttons,
)
from app.storage import save_data
from app.channel import post_to_channel
from app.menus import go_menu
from app.economy.assets import consume_trade_house_cap, release_trade_house_cap
from app.economy.merchants import (
    apply_merchant_trade_to_city,
    format_merchant_catalog,
    item_buy_price,
    item_sell_price,
    validate_merchant_order,
)
from app.handlers.military import _set_city_field


@dp.callback_query(F.data.startswith("trade_kind:"))
async def trade_kind_pick(callback: types.CallbackQuery, state: FSMContext):
    if not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    kind = callback.data.split(":")[1]
    await callback.answer()
    if kind == "player":
        try:
            await callback.message.edit_text(
                "🐪 <b>فرم کاروان تجاری (بازیکن)</b>\n" + DIV + "\n\n"
                "📍 <b>مبدا تجارت</b> را از منو انتخاب کنید:",
                reply_markup=get_cities_keyboard("trade_origin"),
            )
        except Exception:
            await callback.message.answer(
                "📍 <b>مبدا تجارت</b> را انتخاب کنید:",
                reply_markup=get_cities_keyboard("trade_origin"),
            )
        await state.set_state(GameStates.trade_origin)
        return
    # تجارت با تجار — انتخاب خرید یا فروش
    if not app_state.MERCHANT_ENABLED:
        return await callback.message.answer(
            "❌ تجارت با تجار فعلاً توسط ادمین <b>غیرفعال</b> است.",
            reply_markup=get_main_menu_keyboard(callback.from_user.id),
        )
    # تجارت محدودیت زمانی ندارد — فقط فعال/غیرفعال ادمین
    if not MERCHANT_LIMITS:
        return await callback.message.answer(
            "❌ لیست تجار هنوز توسط ادمین تنظیم نشده است.",
            reply_markup=get_main_menu_keyboard(callback.from_user.id),
        )
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🛒 خرید از تجار", "mtrade_mode:buy", "success"))
    builder.row(_btn("💰 فروش به تجار", "mtrade_mode:sell", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    await callback.message.answer(
        f"🛒 <b>تجارت با تجار</b>\n{DIV}\n"
        f"{format_merchant_catalog()}\n\n"
        "می‌خواهید <b>بخرید</b> یا <b>بفروشید</b>؟",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(GameStates.mtrade_mode)


@dp.callback_query(F.data.startswith("mtrade_mode:"))
async def mtrade_mode_pick(callback: types.CallbackQuery, state: FSMContext):
    if not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    mode = callback.data.split(":")[1]
    if mode not in ("buy", "sell"):
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer()
    await state.update_data(mtrade_mode=mode)
    verb = "خرید" if mode == "buy" else "فروش"
    await callback.message.answer(
        f"📝 لیست کالاهای <b>{verb}</b> را بفرستید:\n"
        f"<code>|🪵|~| چوب | : 50</code>\nیا <code>چوب: 50</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.mtrade_list)


@dp.message(GameStates.mtrade_list)
async def process_mtrade_list(message: types.Message, state: FSMContext):
    if not is_player(message.from_user.id):
        return
    txt = await need_text(message, 2000)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    order, err = parse_goods_list(txt)
    if err:
        return await message.answer(
            f"❌ {err}\nمثال:\n<code>|🪵|~| چوب | : 50</code>\nیا <code>چوب: 50</code>"
        )
    d = await state.get_data()
    mode = d.get("mtrade_mode") or "buy"
    ok, errors, applied, cost = validate_merchant_order(order, mode=mode)
    if not ok:
        return await message.answer(
            "🚫 <b>درخواست غیرمجاز</b>\n" + DIV + "\n" + "\n".join(errors)
            + "\n\n" + format_merchant_catalog()
        )
    await state.update_data(mtrade_order=applied, mtrade_cost=cost, mtrade_mode=mode)
    # جزئیات قیمت هر کالا (فقط برای پلیر/ادمین — در کانال نمی‌آید)
    detail = []
    for k, q in applied.items():
        unit = item_buy_price(k) if mode == "buy" else item_sell_price(k)
        detail.append(f"• {k}: {fmt_num(q)} × {fmt_num(unit)} = <b>{fmt_num(q * unit)}</b>")
    verb = "هزینه خرید" if mode == "buy" else "درآمد فروش"
    await message.answer(
        f"✅ لیست مجاز ({'خرید' if mode == 'buy' else 'فروش'}):\n{format_goods(applied)}\n\n"
        + "\n".join(detail) + "\n"
        f"💰 {verb}: <b>{fmt_num(cost)}</b> سکه\n\n"
        f"🎚 باف پیش‌فرض: <b>{fmt_num(app_state.MERCHANT_BUFF_DEFAULT)}%</b>\n"
        "اگر باف دارید عدد بفرستید (مثلاً <code>15</code>).\n"
        "اگر ندارید: <code>0</code> یا <code>-</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.mtrade_buff)


@dp.message(GameStates.mtrade_buff)
async def process_mtrade_buff(message: types.Message, state: FSMContext):
    if not is_player(message.from_user.id):
        return
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    raw = normalize_digits(txt).strip().replace("%", "")
    if raw in ("-", "—", "هیچ", "ندارم", ""):
        buff = float(app_state.MERCHANT_BUFF_DEFAULT)
    else:
        try:
            buff = float(raw)
        except ValueError:
            return await message.answer("❌ عدد باف نامعتبر. مثال: <code>15</code>")
    d = await state.get_data()
    order = d.get("mtrade_order") or {}
    mode = d.get("mtrade_mode") or "buy"
    cost = d.get("mtrade_cost", 0)
    after = {k: round(apply_buff(v, buff), 2) for k, v in order.items()}
    await state.update_data(mtrade_buff=buff, mtrade_after=after)
    pending_confirms[message.from_user.id] = {
        "kind": "mtrade",
        "data": {
            "order": order, "buff": buff, "after": after,
            "cost": cost, "mode": mode,
        },
        "chat_id": message.chat.id,
    }
    verb = "خرید از" if mode == "buy" else "فروش به"
    money_lbl = "هزینه" if mode == "buy" else "درآمد"
    await message.answer(
        f"🛒 <b>پیش‌نمایش {verb} تجار</b>\n{DIV}\n"
        f"👑 {mention(message.from_user.id, 'فرمانده شهر')}\n"
        f"🏙 <b>{e(city_of(message.from_user.id))}</b>\n"
        f"🎚 باف: <b>{fmt_num(buff)}%</b>\n"
        f"💰 {money_lbl} (محرمانه): <b>{fmt_num(cost)}</b> سکه\n\n"
        f"📦 کالا:\n{format_goods(order)}\n\n"
        f"📦 پس از باف:\n{format_goods(after)}\n\n"
        "⚠️ سکه و جزئیات فقط برای شما/ادمین است — در کانال نمی‌آید.\n"
        "تایید می‌کنید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.mtrade_confirm)


@dp.callback_query(F.data.startswith("trade_ok:"))
async def admin_trade_approve(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ فقط ادمین اصلی.", show_alert=True)
    tid = callback.data.split(":", 1)[1]
    tr = PENDING_TRADES.get(tid)
    if not tr or tr.get("status") != "pending":
        return await callback.answer("یافت نشد / قبلاً رسیدگی شده.", show_alert=True)
    city = tr.get("city") or ""
    kind = tr.get("kind") or "merchant"

    if kind == "player":
        units = float(tr.get("units") or 0)
        ok_cap, cap_msg = consume_trade_house_cap(city, units)
        if not ok_cap:
            return await callback.answer(cap_msg[:180], show_alert=True)
        # قفل قبل از اولین await: کلیک دوم status=processing می‌بیند و رد می‌شود
        # (قبلاً دابل‌کلیک = دو پست کانال و دوبار کسر ظرفیت)
        tr["status"] = "processing"
        mtype = tr.get("mtype") if tr.get("mtype") in ("land", "sea") else "land"
        mlabel = "زمینی" if mtype == "land" else "دریایی"
        action_id = secrets.token_hex(4)
        public_text = (
            f"🐪 <b>کاروان تجاری به راه افتاد</b> 🐪\n{DIV}\n\n"
            f"👑 {mention(tr.get('user_id'), 'فرمانده شهر')}\n"
            f"🏙 شهر فرمانده: <b>{e(city)}</b>\n"
            f"🧭 مسیر: <b>{mlabel}</b>\n\n"
            f"📍 از: <b>{e(tr.get('origin'))}</b>\n"
            f"🎯 به: <b>{e(tr.get('dest'))}</b>\n"
            f"🗺️ مسیر حرکت: <b>{e(tr.get('route', '-'))}</b>\n"
            f"⏳ زمان رسیدن: <b>{e(tr.get('time', '-'))}</b>\n"
            f"🛡 نیروی حفاظتی: اعلام‌شده\n\n"
            f"🛤️ کاروانیان حرکت کردند…"
        )
        try:
            sent = await post_to_channel(
                "trade", public_text, get_trade_channel_buttons(action_id), mtype, city,
            )
        except Exception as ex:
            # پست نشد → برگرداندن وضعیت و ظرفیت تا ادمین بتواند دوباره تایید کند
            tr["status"] = "pending"
            release_trade_house_cap(city, units)
            return await callback.answer(f"خطای کانال: {ex}"[:180], show_alert=True)
        active_actions[action_id] = {
            "owner_id": tr.get("user_id"),
            "type": "trade",
            "time_created": time.time(),
            "msg_id": sent.message_id if sent else 0,
            "data": {
                "origin": tr.get("origin"),
                "dest": tr.get("dest"),
                "route": tr.get("route", "-"),
                "mtype": mtype,
                "guard": tr.get("guard", "-"),
                "recv": tr.get("recv", "-"),
                "send": tr.get("send", "-"),
                "time": tr.get("time", "-"),
            },
        }
        tr["status"] = "approved"
        PENDING_TRADES[tid] = tr
        save_data(critical=True)
        await callback.answer("✅ منتشر شد")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.answer(
            f"✅ تجارت بازیکن <code>{tid}</code> تأیید و منتشر شد.\n{cap_msg}"
        )
        try:
            await bot.send_message(
                tr.get("user_id"),
                f"✅ کاروان تجاری شما تأیید و در کانال منتشر شد.\n{cap_msg}",
            )
        except Exception:
            pass
        return

    # merchant
    log = apply_merchant_trade_to_city(
        city, tr.get("mode") or "buy", tr.get("after") or {}, float(tr.get("cost") or 0)
    )
    # ظرفیت تجارتخانه برای ارزش معامله (سکه)
    ok_cap, cap_msg = consume_trade_house_cap(city, float(tr.get("cost") or 0))
    tr["status"] = "approved"
    PENDING_TRADES[tid] = tr
    save_data(critical=True)
    verb_fa = "خرید کرد" if tr.get("mode") == "buy" else "فروخت"
    public_text = (
        f"🛒 <b>معامله با تجار</b>\n{DIV}\n\n"
        f"👑 {mention(tr.get('user_id'), 'فرمانده شهر')}\n"
        f"🏙 فرمانده قلعه <b>{e(city)}</b> با تجار {verb_fa}."
    )
    try:
        await post_to_channel("trade", public_text, None, "land", city)
    except Exception:
        logging.exception("پست کانال پس از تأیید تجارت")
    await callback.answer("✅ اعمال شد")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    extra = f"\n{cap_msg}" if cap_msg else ""
    await callback.message.answer(f"✅ معامله <code>{tid}</code> اعمال شد.\n{log}{extra}")
    try:
        await bot.send_message(
            tr.get("user_id"),
            f"✅ معامله تجار شما تأیید و روی دارایی <b>{e(city)}</b> اعمال شد.",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("trade_no:"))
async def admin_trade_reject(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ فقط ادمین اصلی.", show_alert=True)
    tid = callback.data.split(":", 1)[1]
    tr = PENDING_TRADES.get(tid)
    if not tr or tr.get("status") != "pending":
        return await callback.answer("یافت نشد.", show_alert=True)
    tr["status"] = "rejected"
    PENDING_TRADES[tid] = tr
    save_data(critical=True)
    await callback.answer("رد شد")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(f"❌ معامله <code>{tid}</code> رد شد.")
    try:
        await bot.send_message(tr.get("user_id"), "❌ معامله تجار شما توسط ادمین رد شد.")
    except Exception:
        pass


@dp.message(GameStates.trade_origin)
async def process_trade_origin(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "trade_origin", txt)


@dp.message(GameStates.trade_dest)
async def process_trade_dest(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "trade_dest", txt)


@dp.callback_query(F.data.startswith("trademtype:"))
async def process_trade_mtype(callback: types.CallbackQuery, state: FSMContext):
    if not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    mtype = callback.data.split(":", 1)[1]
    if mtype not in ("land", "sea"):
        return await callback.answer()
    await callback.answer()
    await state.update_data(mtype=mtype)
    try:
        await callback.message.edit_text(
            f"✅ مسیر: <b>{'🏕 زمینی' if mtype == 'land' else '⚓ دریایی'}</b>\n\n"
            "🗺️ <b>مسیر حرکت شهر به شهر</b> را بنویسید.\n"
            "مثال: <code>آمیان به پاریس به برست</code>\n↩️ ریپلای کنید.",
            reply_markup=None,
        )
    except Exception:
        await callback.message.answer(
            "🗺️ <b>مسیر حرکت شهر به شهر</b> را بنویسید.\nمثال: <code>آمیان به پاریس به برست</code>",
            reply_markup=get_back_keyboard(),
        )
    await callback.message.answer("↩️ مسیر را ریپلای کنید:", reply_markup=get_back_keyboard())
    await state.set_state(GameStates.trade_route)


@dp.message(GameStates.trade_route)
async def process_trade_route(message: types.Message, state: FSMContext):
    txt = await need_text(message, 400)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(route=txt)
    await message.answer(
        "🛡 <b>نوع و میزان نیروی حفاظتی</b> کاروان را بنویسید.\n"
        "مثال: <code>۵۰ شمشیرزن، ۲۰ کماندار</code>\n↩️ ریپلای کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.trade_guard)


@dp.message(GameStates.trade_guard)
async def process_trade_guard(message: types.Message, state: FSMContext):
    txt = await need_text(message, 500)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(guard=txt)
    await message.answer(
        "📥 <b>نوع و تعداد کالای دریافتی</b> (محرمانه — فقط گزارش ادمین):\n"
        "مثال: <code>۱۰۰ گندم</code>\n↩️ ریپلای کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.trade_recv)


@dp.message(GameStates.trade_recv)
async def process_trade_recv(message: types.Message, state: FSMContext):
    txt = await need_text(message, 500)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(recv=txt)
    await message.answer(
        "📤 <b>نوع و تعداد کالای ارسالی</b> (محرمانه — فقط گزارش ادمین):\n"
        "مثال: <code>۸۰ سنگ آهن</code>\n↩️ ریپلای کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.trade_send)


@dp.message(GameStates.trade_send)
async def process_trade_send(message: types.Message, state: FSMContext):
    txt = await need_text(message, 500)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(send=txt)
    await message.answer(
        "⏳ <b>زمان رسیدن کاروان</b> را بفرستید:\n"
        "• <code>12:00</code> یا <code>45</code> (دقیقه از الان)\n"
        "⚠️ <i>توجه: زمان تجارت آزاد است — حتی در تایم‌استاپ هم می‌توانید کاروان را حرکت دهید.</i>\n"
        "↩️ ریپلای کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.trade_time)


@dp.message(GameStates.trade_time)
async def process_trade_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    # تجارت آزاد است حتی در تایم‌استاپ
    parsed, err = parse_player_time(txt, respect_window=False)
    if err:
        return await message.answer(f"❌ {err}\nمثال: <code>12:00</code> یا <code>45</code>")
    await state.update_data(time=parsed)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {
        "kind": "trade",
        "data": dict(d),
        "chat_id": message.chat.id,
    }
    mlabel = "🏕 زمینی" if d.get("mtype") == "land" else "⚓ دریایی"
    await message.answer(
        f"🐪 <b>پیش‌نمایش کاروان</b>\n{DIV}\n\n"
        f"👑 {mention(message.from_user.id, 'فرمانده شهر')}\n"
        f"🏙 شهر: <b>{e(city_of(message.from_user.id))}</b>\n"
        f"🧭 نوع مسیر: <b>{mlabel}</b>\n\n"
        f"📍 مبدا: <b>{e(d['origin'])}</b>\n"
        f"🎯 مقصد: <b>{e(d['dest'])}</b>\n"
        f"🗺️ مسیر: <b>{e(d.get('route', '-'))}</b>\n"
        f"⏳ زمان رسیدن: <b>{e(d.get('time', '-'))}</b>\n"
        f"🛡 حفاظت: <blockquote>{e(d.get('guard', '-'))}</blockquote>\n"
        f"📥 دریافتی (محرمانه):\n<blockquote>{e(d['recv'])}</blockquote>\n"
        f"📤 ارسالی (محرمانه):\n<blockquote>{e(d['send'])}</blockquote>\n\n"
        "⚠️ محموله فقط در کانال گزارش ادمین ثبت می‌شود.\nآیا تایید می‌کنید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.trade_confirm)
