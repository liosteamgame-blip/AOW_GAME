"""حلقه‌های پس‌زمینه: ارسال خودکار استارت/استاپ و بکاپ دوره‌ای."""
import asyncio
import logging
from datetime import datetime

from app.config import ADMIN_ID, TZ
from app.loader import bot
from app.state import SETTINGS
from app.utils import _parse_hhmm
from app.gametime import is_game_day_open
from app.storage import push_backup
from app.channel import _broadcast_timing_to_groups


# آخرین تاریخ ارسال خودکار استارت/استاپ (YYYY-MM-DD) تا دوبار نفرستد
_auto_timing_sent = {"start": "", "stop": ""}


async def timing_scheduler_loop():
    """هر ۳۰ ثانیه چک می‌کند؛ در ساعت استارت/استاپ پیام را به گروه‌ها و کانال می‌فرستد."""
    while True:
        try:
            now = datetime.now(TZ) if TZ else datetime.now()
            today = now.strftime("%Y-%m-%d")
            hm = (now.hour, now.minute)
            # مقایسه عددی (نه رشته‌ای) تا «8:00» هم با «08:00» یکی باشد
            start = _parse_hhmm(SETTINGS.get("time_start", "08:00"))
            stop = _parse_hhmm(SETTINGS.get("time_stop", "23:00"))
            # فقط در روزهای مجاز بازی (days_start) — قبلاً هر روز ارسال می‌شد
            if not is_game_day_open():
                start = stop = None
            if start and hm == start and _auto_timing_sent.get("start") != today:
                _auto_timing_sent["start"] = today
                ok, fail, ch = await _broadcast_timing_to_groups("start", to_channel=True)
                logging.info("auto START sent groups=%s fail=%s channel=%s", ok, fail, ch)
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"⏰ ارسال خودکار <b>استارت</b>\nگروه ✅{ok} ❌{fail} · کانال {'✅' if ch else '❌'}",
                        disable_notification=True,
                    )
                except Exception:
                    pass
            if stop and hm == stop and _auto_timing_sent.get("stop") != today:
                _auto_timing_sent["stop"] = today
                ok, fail, ch = await _broadcast_timing_to_groups("stop", to_channel=True)
                logging.info("auto STOP sent groups=%s fail=%s channel=%s", ok, fail, ch)
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"⏰ ارسال خودکار <b>استاپ</b>\nگروه ✅{ok} ❌{fail} · کانال {'✅' if ch else '❌'}",
                        disable_notification=True,
                    )
                except Exception:
                    pass
        except Exception:
            logging.exception("timing_scheduler_loop")
        await asyncio.sleep(30)


async def periodic_backup_loop():
    """هر ۶ ساعت یک بکاپ اجباری به تلگرام می‌فرستد."""
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            await push_backup()
            logging.info("periodic backup pushed")
        except Exception:
            logging.exception("periodic_backup_loop")
