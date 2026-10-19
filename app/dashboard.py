"""📊 داشبورد زنده برای ادمین‌ها — یک پیام پین‌شده که هر ۵ دقیقه ویرایش می‌شود.

فقط در چتی نصب می‌شود که ادمین انتخاب کند (پی‌وی یا گروه ادمین‌ها). هیچ کار xAI ندارد.
"""
import logging
import time
from datetime import datetime

from app.ai import daily_limit, used_today
from app.approvals import pending_list
from app.config import DIV, TZ
from app.errorlog import recent_count
from app.events import active_events, ups_left
from app.features import enabled, setting
from app.gametime import game_time_status
from app.loader import bot
from app.state import AUTO_CITIES, GROUPS, PENDING_TRADES, PLAYER_CODES, SETTINGS, UP_SNAPSHOTS, active_actions, all_players
from app.storage import save_data
from app.utils import e, fmt_num
from app.upschedule import describe as up_describe, next_run

REFRESH_SECONDS = 300
_last = {"text": ""}


def _moving(now: float) -> tuple:
    """(تعداد لشکر/کاروان در راه، نزدیک‌ترین رسیدن به دقیقه یا None)"""
    n, nearest = 0, None
    for act in active_actions.values():
        arr = act.get("arrival")
        if not isinstance(arr, dict) or arr.get("done") or act.get("cancelled"):
            continue
        times = arr.get("times") or []
        i = int(arr.get("next") or 0)
        if i >= len(times):
            continue
        n += 1
        rem = (times[i] - now) / 60
        nearest = rem if nearest is None else min(nearest, rem)
    return n, nearest


def build_text(now: float | None = None) -> str:
    now = time.time() if now is None else now
    stamp = (datetime.fromtimestamp(now, TZ) if TZ else datetime.fromtimestamp(now)).strftime("%H:%M")
    moving, nearest = _moving(now)
    pend_trades = sum(1 for t in PENDING_TRADES.values() if t.get("status") == "pending")
    meta = UP_SNAPSHOTS.get("__meta__") or {}
    lines = [
        f"📊 <b>داشبورد زنده خاکستر جنگ</b>  <i>({stamp})</i>",
        DIV,
        game_time_status(),
        f"🏙 شهر: <b>{fmt_num(len(PLAYER_CODES))}</b> · 👥 گروه: <b>{fmt_num(len(GROUPS))}</b>"
        f" · 👤 فرمانده: <b>{fmt_num(len(all_players))}</b> · 🤖 اتو: <b>{fmt_num(sum(1 for v in AUTO_CITIES.values() if v))}</b>",
        f"⚔️ در راه: <b>{fmt_num(moving)}</b>"
        + (f" · نزدیک‌ترین رسیدن: <b>{fmt_num(max(0, round(nearest)))}</b> دقیقه" if nearest is not None else ""),
        f"🛒 تجارت معلق: <b>{fmt_num(pend_trades)}</b> · 🔐 تایید مالک: <b>{fmt_num(len(pending_list()))}</b>",
    ]
    evs = active_events()
    if evs:
        lines.append("🌍 رویداد: " + "، ".join(f"{ev['title']} ({fmt_num(ups_left(eid))} آپ)" for eid, ev in evs))
    lines.append(f"🤖 گروک امروز: <b>{fmt_num(used_today())}</b> از {fmt_num(daily_limit())}")
    if meta.get("ts"):
        lines.append(f"♻️ آخرین آپ کلی: <b>{e(meta.get('ts'))}</b>")
    if enabled("scheduled_up"):
        lines.append(f"🗓 آپ بعدی: <b>{next_run().strftime('%m/%d %H:%M')}</b> ({up_describe()})")
    errs = recent_count(3600, now)
    lines.append(f"🚨 خطای یک ساعت اخیر: <b>{fmt_num(errs)}</b>" if errs else "✅ خطای اخیر: ندارد")
    lines.append("\n<i>هر ۵ دقیقه به‌روز می‌شود.</i>")
    return "\n".join(lines)


def installed() -> tuple:
    try:
        return int(setting("dash_chat")), int(setting("dash_mid"))
    except ValueError:
        return None, None


async def install(chat_id: int) -> bool:
    text = build_text()
    sent = await bot.send_message(chat_id, text, disable_notification=True)
    old_chat, old_mid = installed()
    SETTINGS["dash_chat"] = str(chat_id)
    SETTINGS["dash_mid"] = str(sent.message_id)
    _last["text"] = text
    save_data()
    try:
        await bot.pin_chat_message(chat_id, sent.message_id, disable_notification=True)
    except Exception:
        logging.warning("پین داشبورد ناموفق (ربات در این چت اجازه‌ی پین ندارد؟)")
    if old_chat and old_mid and (old_chat, old_mid) != (chat_id, sent.message_id):
        try:
            await bot.unpin_chat_message(old_chat, message_id=old_mid)
        except Exception:
            pass
    return True


def uninstall():
    SETTINGS["dash_chat"] = ""
    SETTINGS["dash_mid"] = ""
    _last["text"] = ""
    save_data()


async def refresh(now: float | None = None) -> bool:
    """True = پیام ویرایش شد."""
    if not enabled("live_dashboard"):
        return False
    chat, mid = installed()
    if not chat or not mid:
        return False
    text = build_text(now)
    if text == _last["text"]:
        return False
    try:
        await bot.edit_message_text(chat_id=chat, message_id=mid, text=text, disable_web_page_preview=True)
    except Exception as ex:
        msg = str(ex).lower()
        if "not modified" in msg:
            _last["text"] = text
            return False
        if "not found" in msg or "can't be edited" in msg:
            logging.warning("پیام داشبورد پیدا نشد؛ داشبورد غیرفعال شد")
            uninstall()
            return False
        logging.warning("ویرایش داشبورد ناموفق: %s", ex)
        return False
    _last["text"] = text
    return True
