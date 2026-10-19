"""ارسال به کانال اصلی، کانال گزارش و پیام‌های همگانی."""
import asyncio
import logging

from aiogram import types
from aiogram.types import ReplyParameters

from app.config import ADMIN_ID, CANCEL_WINDOW, CHANNEL_ID, DEFAULT_PHOTOS, DIV, REPORT_CHANNEL_ID
from app.loader import bot
from app.state import GROUPS, SETTINGS, active_actions, authenticated_users, spawn
from app.utils import e
from app.factions import country_key
from app.keyboards import get_main_menu_keyboard
from app.art import pick_art, send_art


async def _send_report_impl(text):
    chats = ([REPORT_CHANNEL_ID] if REPORT_CHANNEL_ID else []) + [ADMIN_ID]
    for chat in chats:
        try:
            await bot.send_message(chat_id=chat, text=text)
            return
        except Exception:
            logging.exception("ارسال گزارش به %s ناموفق بود.", chat)


async def send_report(text):
    """گزارش ادمین در پس‌زمینه — پاسخ به پلیر را معطل نمی‌کند."""
    spawn(_send_report_impl(text))


async def post_to_channel(kind, text, markup=None, mtype=None, city=None):
    """ارسال به کانال اصلی با آرت فکشن. در صورت خطا جزئیات به ادمین گزارش می‌شود."""
    if not CHANNEL_ID:
        await send_report("⚠️ <b>CHANNEL_ID تنظیم نشده</b> — پست کانال ارسال نشد.")
        raise RuntimeError("CHANNEL_ID is not set")
    faction = country_key(city) or "unknown"
    entry = pick_art(kind, mtype, city)
    logging.info("post_to_channel kind=%s mtype=%s city=%s faction=%s art=%s",
                 kind, mtype, city, faction, entry)
    try:
        if entry:
            return await send_art(CHANNEL_ID, entry, text, markup)
        # بدون آرت فکشن: عکس پیش‌فرض
        return await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=DEFAULT_PHOTOS.get(kind, DEFAULT_PHOTOS["campaign"]),
            caption=text,
            reply_markup=markup,
        )
    except Exception as ex:
        logging.exception("ارسال عکس به کانال ناموفق بود؛ تلاش بدون عکس. CHANNEL_ID=%s", CHANNEL_ID)
        try:
            return await bot.send_message(chat_id=CHANNEL_ID, text=text, reply_markup=markup)
        except Exception as ex2:
            await send_report(
                f"⚠️ <b>خطا در ارسال به کانال اصلی</b>\n{DIV}\n"
                f"🛠 kind: {e(kind)}\n🏙 شهر: {e(city)}\n🏴 فکشن: {e(faction)}\n"
                f"🆔 CHANNEL_ID: <code>{CHANNEL_ID}</code>\n"
                f"❗️ عکس: <code>{e(str(ex)[:200])}</code>\n"
                f"❗️ متن: <code>{e(str(ex2)[:200])}</code>\n\n"
                "ربات را در کانال ادمین کنید و CHANNEL_ID را چک کنید."
            )
            raise


async def channel_reply(text, msg_id):
    rp = ReplyParameters(message_id=msg_id, allow_sending_without_reply=True) if msg_id else None
    return await bot.send_message(chat_id=CHANNEL_ID, text=text, reply_parameters=rp)


async def channel_reply_art(kind, text, msg_id, mtype=None, city=None):
    """ریپلای روی پست کانال، همراه آرت (اگر آرتی باشد)."""
    entry = pick_art(kind, mtype, city)
    if entry:
        try:
            rp = ReplyParameters(message_id=msg_id, allow_sending_without_reply=True) if msg_id else None
            return await send_art(CHANNEL_ID, entry, text, None, rp)
        except Exception:
            logging.exception("ارسال ریپلای همراه آرت ناموفق بود؛ بدون آرت ارسال می‌شود.")
    return await channel_reply(text, msg_id)


async def _deliver_to_targets(message: types.Message, chat_ids):
    """ارسال و برگرداندن لیست موفق/ناموفق."""
    ok_list, fail_list = [], []
    header = f"📢 <b>اعلان رسمی</b>\n{DIV}\n\n"
    for cid in chat_ids:
        try:
            if message.photo:
                cap = (message.caption or "").strip()
                await bot.send_photo(
                    chat_id=cid, photo=message.photo[-1].file_id,
                    caption=(header + e(cap)) if cap else header.rstrip(),
                )
            elif message.video:
                cap = (message.caption or "").strip()
                await bot.send_video(
                    chat_id=cid, video=message.video.file_id,
                    caption=(header + e(cap)) if cap else header.rstrip(),
                )
            elif message.text:
                await bot.send_message(chat_id=cid, text=header + e(message.text))
            else:
                fail_list.append((cid, "فرمت"))
                continue
            ok_list.append(cid)
            await asyncio.sleep(0.04)
        except Exception as ex:
            fail_list.append((cid, str(ex)[:40]))
    return ok_list, fail_list


def _target_label(cid):
    if cid in authenticated_users:
        u = authenticated_users[cid]
        return f"{u.get('country') or u.get('name') or cid} (<code>{cid}</code>)"
    if cid in GROUPS:
        return f"گروه {GROUPS[cid].get('city', cid)} (<code>{cid}</code>)"
    return f"<code>{cid}</code>"


async def _broadcast_timing_to_groups(kind: str, to_channel: bool = True):
    """
    kind = start | stop
    پیام کامل (+عکس) به همه گروه‌ها با دکمه‌های منوی ربات،
    و در صورت نیاز به کانال اصلی.
    """
    text = SETTINGS.get("msg_start" if kind == "start" else "msg_stop", "") or "—"
    photo = SETTINGS.get("photo_start" if kind == "start" else "photo_stop", "") or ""
    menu = get_main_menu_keyboard()
    ok, fail = 0, 0
    for gid in list(GROUPS.keys()):
        try:
            if photo:
                await bot.send_photo(
                    chat_id=gid, photo=photo, caption=text[:1024], reply_markup=menu
                )
            else:
                await bot.send_message(chat_id=gid, text=text, reply_markup=menu)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    # کانال اصلی
    ch_ok = False
    if to_channel and CHANNEL_ID:
        try:
            if photo:
                await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=text[:1024])
            else:
                await bot.send_message(chat_id=CHANNEL_ID, text=text)
            ch_ok = True
        except Exception:
            logging.exception("ارسال استارت/استاپ به کانال اصلی ناموفق")
    return ok, fail, ch_ok


async def expire_cancel_button(action_id):
    """بعد از ۱۰ دقیقه دکمه‌ی لغو از پست کانال برداشته می‌شود."""
    await asyncio.sleep(CANCEL_WINDOW + 5)
    a = active_actions.get(action_id)
    if not a or a.get("cancelled"):
        return
    try:
        await bot.edit_message_reply_markup(chat_id=CHANNEL_ID, message_id=a["msg_id"], reply_markup=None)
    except Exception:
        pass


UPDATE_CHANGELOG = (
    "🔄 <b>به‌روزرسانی ربات</b>\n" + DIV + "\n\n"
    "✅ <b>چه چیزی اضافه/اصلاح شد:</b>\n"
    "• تایم استارت/استاپ + محاسبه هوشمند زمان لشکرکشی\n"
    "• تجارت با بازیکن و تجارت با تجار (سقف + باف)\n"
    "• گزارش کامل تجارت برای ادمین دارایی\n"
    "• لیدر ساید + مشاهده دارایی قلمرو/شهر\n"
    "• ست دارایی در گروه شهر + ثبت تغییر دارایی\n"
    "• ارسال پیام: همگانی / گروه‌ها / فرماندهان / انتخابی / خصوصی\n\n"
    "منوی فرماندهی: /start\n"
    "⚔️ لشکرکشی · 🛡️ جنگ · 🏰 محاصره · 🐪 تجارت · 📜 بیانیه · 📦 دارایی"
)


async def notify_groups_updated():
    """ارسال اعلان آپدیت به گروه‌ها — فقط بعد از تایید ادمین."""
    if not GROUPS:
        return
    ok, fail = 0, 0
    for gid in list(GROUPS.keys()):
        try:
            await bot.send_message(chat_id=gid, text=UPDATE_CHANGELOG, disable_notification=True)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    logging.info("اعلان آپدیت: موفق %s / ناموفق %s", ok, fail)
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ اعلان آپدیت ارسال شد.\nموفق: <b>{ok}</b> · ناموفق: <b>{fail}</b>",
            disable_notification=True,
        )
    except Exception:
        pass
