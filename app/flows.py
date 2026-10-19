"""مرحله‌ی نهایی فرمان‌ها بعد از تایید: پست کانال، گزارش و هشدار."""
import logging
import secrets
import time

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import state as app_state
from app.config import ADMIN_ID, CANCEL_WINDOW, CHANNEL_ID, DIV, ORDERS, TWEET_CHANNEL_ID
from app.loader import bot
from app.state import PENDING_TRADES, active_actions, spawn
from app.utils import e, fmt_num, format_goods, mtype_label, mtype_tag
from app.players import action_city, city_of, is_player, mention, user_fsm
from app.keyboards import (
    _btn,
    bot_open_url,
    get_back_keyboard,
    get_cancel_button,
    get_channel_buttons,
    get_open_bot_keyboard,
)
from app.storage import save_data
from app.channel import (
    channel_reply,
    channel_reply_art,
    expire_cancel_button,
    post_to_channel,
    send_report,
)
from app.menus import channel_failed, go_menu
from app.economy.assets import trade_house_remaining
from app.economy.merchants import _parse_goods_units, send_trade_reports
from app.threats import notify_target_threat
from app.arrivals import reschedule, schedule
from app.chronicle import record_event
from app.rulecal import admin_tag
from app.state import LAST_ORDERS


def remember_order(user_id: int, kind: str, data: dict) -> None:
    """برای «مثل دفعه قبل» — فقط فیلدهای فرم خود بازیکن."""
    keep = ("origin", "dest", "target", "stats", "mtype")
    LAST_ORDERS.setdefault(str(user_id), {})[kind] = {k: data.get(k) for k in keep if data.get(k)}


def _origin_chat(callback: types.CallbackQuery):
    msg = callback.message
    return msg.chat.id if msg and msg.chat.type in ("group", "supergroup") else None


async def _finish_campaign(callback: types.CallbackQuery, state: FSMContext, d: dict):
    user_id = callback.from_user.id
    city = action_city(callback, user_id)
    action_id = secrets.token_hex(4)
    text = (
        f"⚔️ <b>گزارش تحرکات ارتش({mtype_label(d)})</b> ⚔️\n\n"
        f"👑 {mention(user_id, 'فرمانده شهر')}\n"
        f"لشکریان خود را از <b>{e(d['origin'])}</b>📍 به مقصد <b>{e(d['dest'])}</b> اعزام نمود.\n\n"
        f"⏳ زمان رسیدن: <b>{e(d['time'])}</b>"
    )
    try:
        sent = await post_to_channel("campaign", text, get_channel_buttons(action_id), d.get("mtype"), city)
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پست لشکرکشی")

    active_actions[action_id] = {
        "owner_id": user_id, "type": "campaign", "time_created": time.time(), "msg_id": sent.message_id,
        "data": {"origin": d["origin"], "dest": d["dest"], "stats": d["stats"], "time": d["time"], "mtype": d.get("mtype")},
    }
    schedule(action_id, d["time"], text, bool(getattr(sent, "photo", None)),
             via="campaign", origin_chat=_origin_chat(callback), city=city)
    record_event("campaign", city=city, origin=d["origin"], dest=d["dest"], mtype=d.get("mtype"))
    remember_order(user_id, "campaign", d)
    save_data()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await go_menu(
        callback.message, state,
        f"✅ سرورم لشکریان <b>{mtype_tag(d)}</b> شما از مبدا <b>{e(d['origin'])}</b> 📍 به مقصد <b>{e(d['dest'])}</b> 🎯\n"
        f"با آمار:\n<blockquote>{e(d['stats'])}</blockquote>\n"
        f"و با زمان رسیدن <b>{e(d['time'])}</b> ⏳ به راه افتاد. 🚩",
    )
    await send_report(
        f"📬 <b>گزارش فنی لشکرکشی</b>\n{DIV}\n"
        f"👤 فرمانده: {mention(user_id, city)} (ID: <code>{user_id}</code>)\n"
        f"🏙 شهر: {e(city)}\n🧭 نوع: {mtype_tag(d)}\n"
        f"📍 مبدا: {e(d['origin'])}\n🎯 مقصد: {e(d['dest'])}\n⏳ زمان رسیدن: {e(d['time'])}\n"
        f"📊 آمار:\n<blockquote>{e(d['stats'])}</blockquote>"
    )
    # هشدار به مدافعان مقصد
    spawn(notify_target_threat(
        kind="campaign",
        attacker_id=user_id,
        attacker_city=city,
        target_raw=d.get("dest") or "",
        origin=d.get("origin") or "",
        extra=f"⏳ زمان رسیدن: <b>{e(d.get('time') or '—')}</b>\n🧭 نوع: {mtype_tag(d)}",
        action_id=action_id,
    ))


async def _finish_order(callback: types.CallbackQuery, state: FSMContext, d: dict):
    kind = d.get("kind", "siege")
    cfg = ORDERS[kind]
    user_id = callback.from_user.id
    city = action_city(callback, user_id)
    action_id = secrets.token_hex(4)
    text = cfg["channel"].format(who=mention(user_id, "فرمانده شهر"), city=e(city), target=e(d["target"]))
    text += f"\n\n🧭 نوع {cfg['noun']}: <b>{mtype_tag(d)}</b>"
    try:
        # همیشه کانال اصلی CHANNEL_ID
        sent = await post_to_channel(cfg["photo"], text, get_cancel_button(kind, action_id), d.get("mtype"), city)
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پست " + ("محاصره" if kind == "siege" else "اعلان جنگ"))

    active_actions[action_id] = {
        "owner_id": user_id, "type": kind, "time_created": time.time(), "msg_id": sent.message_id,
        "data": {"target": d["target"], "stats": d["stats"], "mtype": d.get("mtype")},
    }
    record_event(kind, city=city, target=d["target"], mtype=d.get("mtype"))
    remember_order(user_id, kind, d)
    save_data()
    spawn(expire_cancel_button(action_id))
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await go_menu(callback.message, state, cfg["done"])
    await send_report(
        f"{cfg['report_title']}\n{DIV}\n"
        f"👤 فرمانده: {mention(user_id, city)} (ID: <code>{user_id}</code>)\n"
        f"🏙 شهر: {e(city)}\n🧭 نوع: {mtype_tag(d)}\n🎯 هدف: {e(d['target'])}\n"
        f"📊 آمار:\n<blockquote>{e(d['stats'])}</blockquote>"
    )
    spawn(notify_target_threat(
        kind=kind,
        attacker_id=user_id,
        attacker_city=city,
        target_raw=d.get("target") or "",
        origin=city,
        extra=f"🧭 نوع: {mtype_tag(d)}",
        action_id=action_id,
    ))


async def cancel_order(callback: types.CallbackQuery, prefix, kind):
    uid = callback.from_user.id
    if not is_player(uid):
        return await callback.answer("❌ دسترسی شما لغو شده است یا وارد ربات نشده‌اید.", show_alert=True)
    action_id = callback.data[len(prefix):]
    action = active_actions.get(action_id)
    if not action or action.get("type") != kind:
        return await callback.answer("این دستور قدیمی شده یا یافت نشد.", show_alert=True)
    if uid != action["owner_id"]:
        return await callback.answer("❌ این دستور متعلق به شما نیست!", show_alert=True)
    if action.get("cancelled"):
        return await callback.answer("این دستور قبلاً لغو شده است.", show_alert=True)
    if time.time() - action.get("time_created", 0) > CANCEL_WINDOW:
        try:
            await bot.edit_message_reply_markup(chat_id=CHANNEL_ID, message_id=action["msg_id"], reply_markup=None)
        except Exception:
            pass
        return await callback.answer("⏳ مهلت ۱۰ دقیقه‌ای لغو این دستور تمام شده است.", show_alert=True)

    cfg = ORDERS[kind]
    action["cancelled"] = True
    record_event("cancel", city=city_of(uid), target=action["data"].get("target"))
    save_data()
    try:
        await bot.edit_message_reply_markup(chat_id=CHANNEL_ID, message_id=action["msg_id"], reply_markup=None)
    except Exception:
        pass
    target = action["data"]["target"]
    try:
        await channel_reply(cfg["cancel_post"].format(who=mention(uid), target=e(target)), action["msg_id"])
    except Exception:
        logging.exception("ارسال پیام لغو به کانال ناموفق بود.")
    await callback.answer("دستور شما لغو شد.")
    await send_report(f"{cfg['cancel_report']}\n{DIV}\n👤 فرمانده: {mention(uid, city_of(uid))}\n🎯 هدف: {e(target)}")


async def _finish_ann(callback: types.CallbackQuery, state: FSMContext, d: dict):
    user_id = callback.from_user.id
    city = action_city(callback, user_id)
    media = d["ann"]
    # فقط بیانیه/توییت → کانال توییت؛ بقیه نظامی → کانال اصلی
    target = TWEET_CHANNEL_ID or CHANNEL_ID
    header = f"📜 <b>بیانیه رسمی</b> 📜\n{DIV}\n\n👑 {mention(user_id, 'فرمانده شهر')}\n🏙 شهر: <b>{e(city)}</b>\n\n"
    body = header + e(media["caption"])
    try:
        if media["kind"] == "photo":
            await bot.send_photo(chat_id=target, photo=media["file_id"], caption=body)
        elif media["kind"] == "video":
            await bot.send_video(chat_id=target, video=media["file_id"], caption=body)
        else:
            await bot.send_message(chat_id=target, text=body)
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "انتشار بیانیه")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    record_event("statement", city=city)
    await go_menu(callback.message, state, "✅ سرورم بیانیه شما با موفقیت <b>منتشر</b> شد. 📢")
    await send_report(f"📢 <b>بیانیه جدید منتشر شد</b>\n{DIV}\n👤 فرمانده: {mention(user_id, city)} (ID: <code>{user_id}</code>)\n🏙 شهر: {e(city)}")


async def _finish_mtrade(callback: types.CallbackQuery, state: FSMContext, d: dict):
    """ثبت درخواست معامله — پس از تأیید ادمین اصلی روی دارایی اعمال می‌شود."""
    user_id = callback.from_user.id
    city = action_city(callback, user_id)
    order = d.get("order") or {}
    buff = d.get("buff", 0)
    after = d.get("after") or order
    cost = float(d.get("cost") or 0)
    mode = d.get("mode") or "buy"
    trade_id = secrets.token_hex(4)
    PENDING_TRADES[trade_id] = {
        "user_id": user_id,
        "city": city,
        "order": order,
        "after": after,
        "buff": buff,
        "cost": cost,
        "mode": mode,
        "time": time.time(),
        "status": "pending",
    }
    save_data(critical=True)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(
        callback.message, state,
        "⏳ معامله ثبت شد و منتظر <b>تأیید ادمین اصلی</b> است.\n"
        "پس از تأیید، روی دارایی اعمال می‌شود.",
    )

    money_lbl = "هزینه خرید" if mode == "buy" else "درآمد فروش"
    tag = "#خرید" if mode == "buy" else "#فروش"
    full = (
        f"🛒 <b>معامله با تجار — نیاز به تأیید</b>\n#تجارت #تجار {tag}\n{DIV}\n"
        f"🆔 معامله: <code>{trade_id}</code>\n"
        f"👤 فرمانده: {mention(user_id, city)}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🏙 شهر: <b>{e(city)}</b>\n"
        f"🔀 نوع: <b>{'خرید' if mode == 'buy' else 'فروش'}</b>\n"
        f"🎚 باف: <b>{fmt_num(buff)}%</b>\n"
        f"💰 {money_lbl}: <b>{fmt_num(cost)}</b> سکه\n\n"
        f"📦 درخواست:\n{format_goods(order)}\n\n"
        f"📦 پس از باف:\n{format_goods(after)}\n\n"
        "پس از ✅ تأیید، سکه و کالا روی دارایی شهر اعمال می‌شود."
        + admin_tag("merchant")
    )
    await send_trade_reports(full, full)
    # دکمه‌های تأیید برای ادمین اصلی
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ تأیید و اعمال", f"trade_ok:{trade_id}", "success"),
        _btn("❌ رد", f"trade_no:{trade_id}", "danger"),
    )
    try:
        await bot.send_message(ADMIN_ID, full, reply_markup=builder.as_markup())
    except Exception:
        logging.exception("ارسال تأیید تجارت به ادمین")
    if app_state.ASSET_ADMIN_ID and app_state.ASSET_ADMIN_ID != ADMIN_ID:
        try:
            await bot.send_message(app_state.ASSET_ADMIN_ID, full + "\n\n<i>تأیید نهایی با ادمین اصلی است.</i>")
        except Exception:
            pass


async def _finish_trade(callback: types.CallbackQuery, state: FSMContext, d: dict):
    """ثبت کاروان بازیکن — منتظر تأیید ادمین؛ بعد از تأیید کسر/گزارش خودکار."""
    user_id = callback.from_user.id
    city = action_city(callback, user_id)
    mtype = d.get("mtype") if d.get("mtype") in ("land", "sea") else "land"
    mlabel = "زمینی" if mtype == "land" else "دریایی"
    trade_id = secrets.token_hex(4)
    units = _parse_goods_units(d.get("send") or "") + _parse_goods_units(d.get("recv") or "")

    PENDING_TRADES[trade_id] = {
        "kind": "player",
        "user_id": user_id,
        "city": city,
        "origin": d.get("origin"),
        "dest": d.get("dest"),
        "route": d.get("route", "-"),
        "mtype": mtype,
        "guard": d.get("guard", "-"),
        "recv": d.get("recv", "-"),
        "send": d.get("send", "-"),
        "time": d.get("time", "-"),
        "units": units,
        "status": "pending",
        "time_created": time.time(),
    }
    save_data(critical=True)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(
        callback.message, state,
        "⏳ کاروان ثبت شد و منتظر <b>تأیید ادمین</b> است.\n"
        "پس از تأیید، در کانال گزارش می‌آید و ظرفیت تجارتخانه کسر می‌شود.",
    )

    full = (
        f"🐪 <b>تجارت بازیکن — نیاز به تأیید</b>\n"
        f"#تجارت #{mlabel}\n{DIV}\n"
        f"🆔 <code>{trade_id}</code>\n"
        f"👤 فرمانده: {mention(user_id, city)}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🏙 شهر: <b>{e(city)}</b>\n"
        f"📍 مبدا: <b>{e(d.get('origin'))}</b>\n"
        f"🎯 مقصد: <b>{e(d.get('dest'))}</b>\n"
        f"🗺️ مسیر: <b>{e(d.get('route', '-'))}</b>\n"
        f"🧭 نوع: <b>{mlabel}</b>\n"
        f"⏳ زمان: <b>{e(d.get('time', '-'))}</b>\n"
        f"📊 واحد تقریبی محموله: <b>{fmt_num(units)}</b>\n"
        f"📉 ظرفیت تجارتخانه باقی: <b>{trade_house_remaining(city)}</b>\n\n"
        f"🛡 حفاظتی:\n<blockquote>{e(d.get('guard', '-'))}</blockquote>\n"
        f"📦 ارسالی:\n<blockquote>{e(d.get('send', '-'))}</blockquote>\n"
        f"📦 دریافتی:\n<blockquote>{e(d.get('recv', '-'))}</blockquote>\n\n"
        "با ✅ تأیید → پست کانال + کسر ظرفیت تجارتخانه"
        + admin_tag("trade")
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ تأیید و انتشار", f"trade_ok:{trade_id}", "success"),
        _btn("❌ رد", f"trade_no:{trade_id}", "danger"),
    )
    try:
        await bot.send_message(ADMIN_ID, full, reply_markup=builder.as_markup())
    except Exception:
        logging.exception("ارسال تأیید تجارت بازیکن")
    await send_trade_reports(full, full)


# ======================================================================
#              دکمه‌های پست لشکرکشی در کانال (کمین، تغییر مسیر، بک)
# ======================================================================
def resolve_action(callback: types.CallbackQuery, prefix, owner, types_ok=("campaign",)):
    """(action_id, action, خطا) — owner=True فقط صاحب، owner=False هر بازیکن جز صاحب."""
    uid = callback.from_user.id
    if not is_player(uid):
        return None, None, "❌ دسترسی شما لغو شده است یا وارد ربات نشده‌اید (/start)."
    action_id = callback.data[len(prefix):]
    action = active_actions.get(action_id)
    if not action or action.get("type") not in types_ok:
        return None, None, "این عملیات قدیمی شده یا یافت نشد."
    if owner and uid != action["owner_id"]:
        return None, None, "❌ این عملیات متعلق به شما نیست!"
    if not owner and uid == action["owner_id"]:
        return None, None, "❌ شما نمی‌توانید به کاروان/ارتش خودتان کمین بزنید!"
    return action_id, action, None


async def start_dm_flow(callback: types.CallbackQuery, action_id, new_state, text):
    """هدایت بازیکن به پی‌وی ربات (کمین / تغییر مسیر / بک) با لینک مستقیم."""
    uid = callback.from_user.id
    open_url = bot_open_url()
    try:
        await bot.send_message(chat_id=uid, text=text, reply_markup=get_back_keyboard())
    except Exception:
        alert = "❌ ابتدا ربات را استارت کنید."
        if open_url:
            alert = f"❌ اول ربات را باز کنید:\n{open_url}"
        return await callback.answer(alert, show_alert=True)
    fsm = user_fsm(uid)                 # وضعیت پی‌وی بازیکن (نه وضعیت کانال)
    await fsm.clear()
    await fsm.update_data(action_id=action_id)
    await fsm.set_state(new_state)
    # در کانال هم لینک می‌دهیم تا با یک کلیک وارد پی‌وی شود
    if open_url:
        try:
            await callback.message.answer(
                f"📩 {mention(uid)} به <b>پی‌وی ربات</b> بروید و دستور را ادامه دهید:",
                reply_markup=get_open_bot_keyboard(),
            )
        except Exception:
            pass
        await callback.answer("به پی‌وی ربات بروید 👇", show_alert=False)
    else:
        await callback.answer("به پی‌وی ربات بروید.")


async def _finish_ambush(callback: types.CallbackQuery, state: FSMContext, d: dict):
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(callback.message, state, "این عملیات دیگر معتبر نیست.")
    attacker_id, defender_id = callback.from_user.id, action["owner_id"]
    attacker, defender = city_of(attacker_id), city_of(defender_id)
    # کانال اصلی: بدون آمار مهاجم
    try:
        await channel_reply_art(
            "ambush",
            f"🪓 <b>کمین!</b> 💥\n{DIV}\n\n"
            f"لشکر شهر <b>{e(defender)}</b> توسط {mention(attacker_id, 'فرمانده شهر')} "
            f"از شهر <b>{e(attacker)}</b> مورد <b>کمین</b> قرار گرفت.\n\n"
            f"⏳ هر دو طرف <b>۳۰ دقیقه</b> فرصت دارند سناریوی خود را به ادمین بفرستند.",
            action["msg_id"],
        )
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پیام کمین")
    record_event("ambush", city=attacker, defender=defender, via="campaign")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(callback.message, state, "✅ کمین ثبت شد. سناریوی خود را به ادمین بفرستید. ⏳")
    notice = (
        "🚨 <b>وضعیت اضطراری — کمین</b> 🚨\n" + DIV + "\n\n"
        "⚔️ شما درگیر نبرد کمین هستید!\n"
        "⏳ <b>۳۰ دقیقه</b> فرصت دارید «سناریوی دفاع یا تهاجم» را به پی‌وی ادمین بفرستید.\n"
        "در غیر این صورت عواقب سختی در انتظار پادشاهی شماست. ☠️"
    )
    for uid in (defender_id, attacker_id):
        try:
            await bot.send_message(chat_id=uid, text=notice)
        except Exception:
            pass
    # گزارش ادمین: آمار فقط برای ادمین
    await send_report(
        f"🪓 <b>گزارش کمین نظامی</b>\n{DIV}\n"
        f"🛡 مدافع: {mention(defender_id, defender)} (<code>{defender_id}</code>)\n"
        f"⚔️ مهاجم: {mention(attacker_id, attacker)} (<code>{attacker_id}</code>)\n"
        f"📊 آمار مهاجم (محرمانه):\n<blockquote>{e(d.get('stats', '-'))}</blockquote>"
    )


async def _finish_trade_ambush(callback: types.CallbackQuery, state: FSMContext, d: dict):
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(callback.message, state, "این کاروان دیگر معتبر نیست.")
    attacker_id, defender_id = callback.from_user.id, action["owner_id"]
    attacker, defender = city_of(attacker_id), city_of(defender_id)
    try:
        await channel_reply_art(
            "ambush",
            f"🪓 <b>کمین به کاروان تجاری!</b> 💥\n{DIV}\n\n"
            f"کاروان شهر <b>{e(defender)}</b> توسط {mention(attacker_id, 'فرمانده شهر')} "
            f"از شهر <b>{e(attacker)}</b> مورد <b>کمین</b> قرار گرفت.\n\n"
            f"⏳ هر دو طرف سناریوی خود را ظرف <b>۳۰ دقیقه</b> به ادمین بفرستند.",
            action["msg_id"],
        )
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "کمین کاروان")
    record_event("ambush", city=attacker, defender=defender, via="caravan")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(callback.message, state, "✅ کمین کاروان ثبت شد. سناریو را به ادمین بفرستید.")
    notice = (
        "🚨 <b>کمین به کاروان</b>\n" + DIV + "\n\n"
        "⏳ ۳۰ دقیقه برای ارسال سناریو به ادمین فرصت دارید."
    )
    for uid in (defender_id, attacker_id):
        try:
            await bot.send_message(chat_id=uid, text=notice)
        except Exception:
            pass
    await send_report(
        f"🪓 <b>کمین کاروان</b> #تجارت\n{DIV}\n"
        f"🛡 صاحب کاروان: {mention(defender_id, defender)} (<code>{defender_id}</code>)\n"
        f"⚔️ مهاجم: {mention(attacker_id, attacker)} (<code>{attacker_id}</code>)\n"
        f"📊 آمار مهاجم (محرمانه):\n<blockquote>{e(d.get('stats', '-'))}</blockquote>"
    )


async def _finish_redirect(callback: types.CallbackQuery, state: FSMContext, d: dict):
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(callback.message, state, "این عملیات دیگر معتبر نیست.")
    user_id = callback.from_user.id
    city = action_city(callback, user_id)
    try:
        await channel_reply(
            f"🔄 <b>تغییر مسیر ناگهانی</b> 🚨\n{DIV}\n\n"
            f"لشکریان <b>{e(city)}</b> به مقصد <b>{e(d['new_dest'])}</b> 🎯 تغییر مسیر دادند.\n\n"
            f"⏳ زمان رسیدن: <b>{e(d['new_time'])}</b>",
            action["msg_id"],
        )
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پیام تغییر مسیر")

    old_dest = action["data"].get("dest", "-")
    action["data"]["dest"] = d["new_dest"]
    action["data"]["time"] = d["new_time"]
    # شمارش معکوس و هشدار رسیدن با مقصد/زمان جدید
    reschedule(d.get("action_id"), d["new_time"], mode="go", dest=d["new_dest"])
    record_event("redirect", city=city, dest=d["new_dest"])
    save_data()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await go_menu(callback.message, state, "✅ سرورم تغییر مسیر لشکریان شما ثبت شد. 🔄")
    await send_report(
        f"🔄 <b>گزارش تغییر مسیر</b>\n{DIV}\n👤 فرمانده: {mention(user_id, city)} (ID: <code>{user_id}</code>)\n"
        f"📍 از مقصد: {e(old_dest)}\n🎯 به مقصد جدید: {e(d['new_dest'])}\n⏳ زمان رسیدن: {e(d['new_time'])}"
    )


async def _finish_back(callback: types.CallbackQuery, state: FSMContext, d: dict):
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(callback.message, state, "این عملیات دیگر معتبر نیست.")
    user_id = callback.from_user.id
    city = action_city(callback, user_id)
    try:
        await channel_reply(
            f"🔙 <b>بازگشت لشکر</b> 🏳️\n{DIV}\n\n"
            f"👑 {mention(user_id)} شهر <b>{e(city)}</b> دستور بازگشت ارسال کرد.\n\n"
            f"⏳ زمان رسیدن به مبدا: <b>{e(d['back_time'])}</b>",
            action["msg_id"],
        )
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پیام بازگشت")

    # قبلاً زمان بازگشت روی اکشن ثبت نمی‌شد؛ حالا شمارش معکوس بازگشت به مبدأ
    action["data"]["back_time"] = d["back_time"]
    reschedule(d.get("action_id"), d["back_time"], mode="back")
    record_event("back", city=city)
    save_data()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(callback.message, state, "✅ سرورم دستور بازگشت لشکریان شما ثبت شد. 🔙")
    await send_report(
        f"🔙 <b>گزارش بازگشت لشکر</b>\n{DIV}\n👤 فرمانده: {mention(user_id, city)} (ID: <code>{user_id}</code>)\n"
        f"⏳ زمان رسیدن به مبدا: {e(d['back_time'])}"
    )
