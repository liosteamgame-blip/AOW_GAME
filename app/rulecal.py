"""📅 تقویم قوانین — سه حالت: خاموش / هشدار / مسدود (پیش‌فرض خاموش).

- هشدار: درخواست در روز غیرمجاز ثبت می‌شود؛ فقط در پیام/گزارش ادمین برچسب «⚠️ خارج از روز مجاز»
  می‌خورد و **هیچ چیز به بازیکن گفته نمی‌شود**.
- مسدود: بازیکن پیام مؤدبانه با روز مجاز بعدی می‌گیرد و درخواست ثبت نمی‌شود (ادمین مستثنا).
روزها قابل تنظیم‌اند (weekday پایتون: دوشنبه=0 … یکشنبه=6)؛ پیش‌فرض طبق _RULES_DIGEST.
"""
from datetime import datetime, timedelta

from app.config import TZ
from app.features import setting
from app.players import is_admin
from app.utils import _DAY_FA, format_days_setting, parse_days_setting

KINDS = {"upgrade": "⬆️ ارتقا", "trade": "🐪 تجارت با بازیکن", "merchant": "🛒 تجارت با تجار"}
MODES = ("off", "warn", "block")
MODE_TITLES = {"off": "❌ خاموش", "warn": "⚠️ هشدار", "block": "⛔️ مسدود"}


def mode() -> str:
    m = setting("rules_calendar")
    return m if m in MODES else "off"


def _now(now: datetime | None = None) -> datetime:
    return now or (datetime.now(TZ) if TZ else datetime.now())


def allowed_days(kind: str):
    """set از weekday یا None (= همه روزها)."""
    return parse_days_setting(setting(f"days_{kind}"))


def days_text(kind: str) -> str:
    return format_days_setting(setting(f"days_{kind}"))


def is_allowed(kind: str, now: datetime | None = None) -> bool:
    days = allowed_days(kind)
    return days is None or _now(now).weekday() in days


def next_allowed(kind: str, now: datetime | None = None) -> str:
    """نام روز مجاز بعدی (از فردا به بعد)."""
    days = allowed_days(kind)
    if not days:
        return "—"
    d = _now(now)
    for i in range(1, 8):
        wd = (d + timedelta(days=i)).weekday()
        if wd in days:
            return _DAY_FA[wd] + (" (فردا)" if i == 1 else "")
    return "—"


def admin_tag(kind: str, now: datetime | None = None) -> str:
    """برچسب برای پیام/گزارش ادمین (در حالت هشدار یا مسدودِ دورزده‌شده توسط ادمین)."""
    if mode() == "off" or is_allowed(kind, now):
        return ""
    return f"\n⚠️ <b>خارج از روز مجاز</b> — {KINDS[kind]} فقط {days_text(kind)}"


def block_message(kind: str, user_id: int, now: datetime | None = None) -> str:
    """'' = مجاز. فقط در حالت مسدود و برای غیرادمین متن مؤدبانه برمی‌گرداند."""
    if mode() != "block" or is_allowed(kind, now) or is_admin(user_id):
        return ""
    return (
        f"🗓 سرورم، {KINDS[kind]} طبق قوانین بازی فقط در روزهای <b>{days_text(kind)}</b> انجام می‌شود.\n"
        f"روز مجاز بعدی: <b>{next_allowed(kind, now)}</b>. در آن روز منتظر فرمان شما هستیم."
    )
