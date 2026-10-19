"""تایم استارت/استاپ، روزهای مجاز و محاسبه زمان رسیدن."""
import re
from datetime import datetime, timedelta

from app.config import TZ
from app.state import SETTINGS
from app.utils import (
    _mins_of_day,
    _parse_hhmm,
    e,
    format_days_setting,
    normalize_digits,
    parse_days_setting,
)
from app.players import is_admin


def game_time_status() -> str:
    """یک خط وضعیت تایم بازی برای هدر منوها."""
    if is_game_time_open():
        return f"🟢 <b>تایم استارت</b> · تا <code>{e(SETTINGS.get('time_stop', ''))}</code>"
    return (
        f"🔴 <b>تایم استاپ</b> · استارت بعدی <code>{e(SETTINGS.get('time_start', ''))}</code>"
        f" ({e(format_days_setting(SETTINGS.get('days_start') or ''))})"
    )


MILITARY_KINDS = ("campaign", "siege", "war")


def military_closed_text(user_id) -> str:
    """اگر الان تایم استاپ است متن خطا (متن ساده، مناسب پاپ‌آپ)؛ در غیر این صورت ''.
    ادمین محدود نمی‌شود. تجارت/بیانیه این محدودیت را ندارند."""
    if is_admin(user_id) or is_game_time_open():
        return ""
    days = format_days_setting(SETTINGS.get("days_start") or "")
    return (
        "🔴 تایم استاپ است — لشکرکشی، محاصره و اعلان جنگ بسته است.\n"
        f"⏰ بازه مجاز: {SETTINGS.get('time_start', '')} تا {SETTINGS.get('time_stop', '')}\n"
        f"📅 روزها: {days}\n"
        "🐪 تجارت و 📜 بیانیه آزاد است."
    )


def is_game_day_open():
    """آیا امروز روز مجاز بازی است؟"""
    days = parse_days_setting(SETTINGS.get("days_start") or "")
    if days is None:
        return True
    now = datetime.now(TZ) if TZ else datetime.now()
    return now.weekday() in days


def is_game_time_open():
    """آیا الان داخل بازه استارت–استاپ و روز مجاز هستیم؟"""
    if not is_game_day_open():
        return False
    start_hm = _parse_hhmm(SETTINGS.get("time_start", "08:00"))
    stop_hm = _parse_hhmm(SETTINGS.get("time_stop", "23:00"))
    if not start_hm or not stop_hm:
        return True
    now = datetime.now(TZ) if TZ else datetime.now()
    now_m = _mins_of_day(now.hour, now.minute)
    start_m = _mins_of_day(*start_hm)
    stop_m = _mins_of_day(*stop_hm)
    if stop_m >= start_m:
        return start_m <= now_m <= stop_m
    return now_m >= start_m or now_m <= stop_m


def parse_player_time(raw: str, respect_window: bool = True):
    """
    ورودی زمان پلیر:
    - ساعت مطلق: 12:00 یا 12:00,14:30
    - عدد دقیقه: 45 → الان + 45 دقیقه
    اگر respect_window و بازه استارت/استاپ فعال باشد:
      • دقیقه اگر از استاپ رد شود → باقی از استارت بعدی به‌صورت ساعت واقعی (مثلاً ۲۰:۰۴)
      • ساعت مطلق خارج از بازه رد می‌شود
    """
    raw = normalize_digits((raw or "").strip())
    if not raw:
        return None, "زمان خالی است."

    now = datetime.now(TZ) if TZ else datetime.now()
    start_hm = _parse_hhmm(SETTINGS.get("time_start", "08:00"))
    stop_hm = _parse_hhmm(SETTINGS.get("time_stop", "23:00"))
    parts = [p.strip() for p in raw.replace("،", ",").split(",") if p.strip()]
    out = []

    def _at_start_plus(overflow_mins: int, sh: int, sm: int) -> str:
        total = int(sm) + max(0, int(overflow_mins))
        hh = int(sh) + total // 60
        mm = total % 60
        return f"{hh % 24:02d}:{mm:02d}"

    def _remain_to_stop(now_m: int, start_m: int, stop_m: int) -> int:
        if stop_m >= start_m:
            if now_m < start_m:
                return -1
            if now_m >= stop_m:
                return 0
            return stop_m - now_m
        if now_m >= start_m:
            return (24 * 60 - now_m) + stop_m
        if now_m <= stop_m:
            return stop_m - now_m
        return 0

    def _in_window(m: int, start_m: int, stop_m: int) -> bool:
        if stop_m >= start_m:
            return start_m <= m <= stop_m
        return m >= start_m or m <= stop_m

    for p in parts:
        if re.fullmatch(r"\d{1,4}", p):
            mins = int(p)
            if mins > 24 * 60:
                return None, f"عدد «{p}» خیلی بزرگ است (حداکثر ۱۴۴۰ دقیقه)."
            if mins < 0:
                return None, "دقیقه منفی مجاز نیست."
            if respect_window and stop_hm and start_hm:
                now_m = _mins_of_day(now.hour, now.minute)
                stop_m = _mins_of_day(*stop_hm)
                start_m = _mins_of_day(*start_hm)
                sh, sm = start_hm
                remain = _remain_to_stop(now_m, start_m, stop_m)
                if remain < 0:
                    out.append(_at_start_plus(mins, sh, sm))
                elif mins <= remain:
                    tnow = now + timedelta(minutes=mins)
                    out.append(tnow.strftime("%H:%M"))
                else:
                    out.append(_at_start_plus(mins - remain, sh, sm))
            else:
                tnow = now + timedelta(minutes=mins)
                out.append(tnow.strftime("%H:%M"))
            continue
        hm = _parse_hhmm(p)
        if hm:
            h, mi = hm
            if respect_window and stop_hm and start_hm:
                target_m = _mins_of_day(h, mi)
                stop_m = _mins_of_day(*stop_hm)
                start_m = _mins_of_day(*start_hm)
                if not _in_window(target_m, start_m, stop_m):
                    return None, (
                        f"ساعت <b>{h:02d}:{mi:02d}</b> خارج از بازه مجاز است "
                        f"(استارت <code>{SETTINGS.get('time_start')}</code> — "
                        f"استاپ <code>{SETTINGS.get('time_stop')}</code>)."
                    )
            out.append(f"{h:02d}:{mi:02d}")
            continue
        return None, f"فرمت «{p}» درست نیست. مثال: <code>12:00</code> یا <code>45</code>"
    return ", ".join(out), None
