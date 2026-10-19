"""🗓 آپ زمان‌بندی‌شده — پیش‌فرض طبق قوانین: چهارشنبه، ۱۵ دقیقه بعد از استاپ.

- یک ساعت قبل، پیش‌نمایش با دکمه‌ی «✅ تایید آپ امشب» برای مالک فرستاده می‌شود.
- **بدون تایید همان روز، آپ اجرا نمی‌شود**؛ فقط اطلاع داده می‌شود که اجرا نشد.
- اجرا با همان run_up_all دکمه‌ی ادمین (قفل دابل‌کلیک، کارنامه، بکاپ).
"""
import logging
from datetime import datetime, timedelta

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.audit import record
from app.castles import castle_trait_line
from app.config import ADMIN_ID, DIV, TZ
from app.events import active_events, ups_left
from app.features import enabled, setting
from app.keyboards import _btn
from app.loader import bot
from app.state import AUTO_CITIES, SETTINGS
from app.storage import save_data
from app.utils import _DAY_FA, _parse_hhmm, e, fmt_num
from app.economy.upflow import run_up_all

PREVIEW_BEFORE_MIN = 60


def _now() -> datetime:
    return datetime.now(TZ) if TZ else datetime.now()


def up_day() -> int:
    try:
        d = int(setting("up_day") or 2)
    except ValueError:
        d = 2
    return d if 0 <= d <= 6 else 2


def offset_min() -> int:
    try:
        return max(0, min(int(setting("up_offset_min") or 15), 360))
    except ValueError:
        return 15


def scheduled_on(day: datetime) -> datetime:
    """زمان آپ در تاریخِ day = ساعت استاپ + فاصله."""
    hm = _parse_hhmm(SETTINGS.get("time_stop") or "23:00") or (23, 0)
    base = day.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    return base + timedelta(minutes=offset_min())


def next_run(now: datetime | None = None) -> datetime:
    now = now or _now()
    for i in range(8):
        d = now + timedelta(days=i)
        if d.weekday() == up_day():
            t = scheduled_on(d)
            if t > now:
                return t
    return scheduled_on(now + timedelta(days=7))


def _key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def describe() -> str:
    hm = (SETTINGS.get("time_stop") or "23:00")
    return f"{_DAY_FA[up_day()]}ها، {fmt_num(offset_min())} دقیقه بعد از استاپ ({e(hm)})"


def preview_text(run_at: datetime) -> str:
    cities = sorted(c for c, on in AUTO_CITIES.items() if on)
    lines = [
        f"🗓 <b>پیش‌نمایش آپ زمان‌بندی‌شده</b>\n{DIV}",
        f"⏰ زمان اجرا: <b>{run_at.strftime('%H:%M')}</b> — {_DAY_FA[run_at.weekday()]} {run_at.strftime('%m/%d')}",
        f"🏙 شهرهای اتو: <b>{fmt_num(len(cities))}</b>" + (f"\n<i>{e('، '.join(cities[:30]))}</i>" if cities else ""),
    ]
    traits = [f"• {e(c)}: {castle_trait_line(c).replace('🏰 یادآوری ویژگی قلعه: ', '')}" for c in cities if castle_trait_line(c)]
    if traits:
        lines.append("🏰 <b>یادآوری ویژگی قلعه</b> <i>(فقط اطلاع؛ خودکار اعمال نمی‌شود)</i>\n" + "\n".join(traits))
    evs = active_events()
    if evs:
        lines.append("🌍 رویدادهای فعال: " + "، ".join(f"{ev['title']} ({fmt_num(ups_left(eid))} آپ)" for eid, ev in evs))
    lines.append(
        "\n⚠️ <b>بدون تایید شما آپ اجرا نمی‌شود.</b>\n"
        "قبل از اجرا از همه شهرها بکاپ گرفته می‌شود و بعد کارنامه‌ها فرستاده می‌شوند."
    )
    return "\n".join(lines)[:4000]


def preview_keyboard(run_at: datetime):
    b = InlineKeyboardBuilder()
    b.row(_btn("✅ تایید آپ امشب", f"upsch:ok:{_key(run_at)}", "success"),
          _btn("⏭ این هفته نه", f"upsch:no:{_key(run_at)}", "danger"))
    return b.as_markup()


def confirm(date_key: str, uid: int, yes: bool = True) -> str:
    if yes:
        SETTINGS["up_confirmed_for"] = date_key
        record("تایید آپ زمان‌بندی‌شده", "", date_key, admin_only=False)
        msg = f"✅ آپ {date_key} تایید شد و سر وقت اجرا می‌شود."
    else:
        if setting("up_confirmed_for") == date_key:
            SETTINGS["up_confirmed_for"] = ""
        SETTINGS["up_skip_notified"] = date_key   # پیام «اجرا نشد» لازم نیست؛ خودش رد کرد
        SETTINGS["up_last_run"] = date_key
        record("لغو آپ زمان‌بندی‌شده", "", date_key, admin_only=False)
        msg = f"⏭ آپ {date_key} اجرا نمی‌شود."
    save_data()
    return msg


async def tick(now: datetime | None = None) -> str:
    """یک دور بررسی. برمی‌گرداند: '' | 'preview' | 'ran' | 'skipped' (برای تست)."""
    if not enabled("scheduled_up"):
        return ""
    now = now or _now()
    if now.weekday() != up_day():
        return ""
    run_at = scheduled_on(now)
    key = _key(run_at)
    if setting("up_last_run") == key:
        return ""
    if now >= run_at - timedelta(minutes=PREVIEW_BEFORE_MIN) and setting("up_preview_sent") != key and now < run_at:
        SETTINGS["up_preview_sent"] = key
        save_data()
        try:
            await bot.send_message(ADMIN_ID, preview_text(run_at), reply_markup=preview_keyboard(run_at))
        except Exception:
            logging.exception("ارسال پیش‌نمایش آپ زمان‌بندی‌شده")
        return "preview"
    if now < run_at:
        return ""
    if setting("up_confirmed_for") == key:
        SETTINGS["up_last_run"] = key   # قبل از await — دوبار اجرا نمی‌شود
        save_data()
        body = await run_up_all(reason="scheduled_up")
        record("آپ زمان‌بندی‌شده اجرا شد", "", key, admin_only=False)
        try:
            await bot.send_message(ADMIN_ID, f"🗓 <b>آپ زمان‌بندی‌شده اجرا شد</b>\n{body or '⏳ آپ دیگری در حال اجرا بود.'}"[:4000])
        except Exception:
            logging.exception("گزارش آپ زمان‌بندی‌شده")
        return "ran"
    if setting("up_skip_notified") != key:
        SETTINGS["up_skip_notified"] = key
        save_data()
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⏸ <b>آپ زمان‌بندی‌شده اجرا نشد</b>\n{DIV}\nبرای {key} تاییدی ثبت نشده بود. "
                "در صورت نیاز از پنل «♻️ اجرای آپ» دستی بزنید.",
            )
        except Exception:
            logging.exception("اطلاع رد آپ زمان‌بندی‌شده")
        return "skipped"
    return ""
