"""📘 راهنمای بازیکن — متن کوتاه (حداکثر ۱۵ خط) برای فرمانده و لیدر.

متن پیش‌فرض از قوانین (_RULES_DIGEST) و تنظیمات زنده‌ی روزها ساخته می‌شود؛ ادمین می‌تواند از پنل
متن جایگزین بگذارد (SETTINGS["guide_commander"] / ["guide_leader"]). هیچ اطلاعات مخفی (آمار ارتش،
دارایی شهرها، …) در راهنما نیست — فقط قوانین عمومی و طرز کار منوها.
"""
from app.config import DIV, RULE_DAYS
from app.state import SETTINGS, authenticated_users
from app.utils import e, format_days_setting
from app.players import is_player, leader_side
from app.storage import save_data

MAX_LINES = 15
ROLES = {"commander": "👑 فرمانده", "leader": "🏴 لیدر جناح"}


def rule_days(kind: str) -> str:
    """روزهای قانونی (قابل تنظیم در تقویم قوانین؛ پیش‌فرض طبق قوانین بازی)."""
    raw = SETTINGS.get(f"days_{kind}")
    return format_days_setting(raw if raw is not None and str(raw).strip() else RULE_DAYS[kind])


def default_text(role: str) -> str:
    lines = [
        f"📘 <b>راهنمای {ROLES[role]}</b>",
        DIV,
        f"🗓 روزهای بازی: <b>{format_days_setting(SETTINGS.get('days_start') or '')}</b>"
        f" · تایم <code>{e(SETTINGS.get('time_start', ''))}</code> تا <code>{e(SETTINGS.get('time_stop', ''))}</code>",
        "⚔️ لشکرکشی، جنگ و محاصره فقط در تایم استارت؛ از «منوی نظامی» در گروه شهر.",
        f"⬆️ ارتقا: <b>{rule_days('upgrade')}</b> — منوی اقتصادی ← ارتقا (پیش‌نویس، بعد تایید).",
        f"🐪 تجارت با بازیکن: <b>{rule_days('trade')}</b> — منو ← تجارت.",
        f"🛒 خرید و فروش با تجار: <b>{rule_days('merchant')}</b>.",
        "♻️ آپ هفتگی بعد از استاپ چهارشنبه؛ کارنامه‌ی شهر در گروه می‌آید.",
        "📦 دارایی شهر: «دارایی» را در گروه شهر بنویسید.",
        "🔒 آمار لشکر فقط برای ادمین می‌رود و در کانال اعلام نمی‌شود.",
    ]
    if role == "leader":
        lines.append("🏴 پنل جناح (پی‌وی ربات): خلاصه‌ی شهرهای جناح، پیام به گروه‌ها و نظرسنجی.")
        lines.append("🤫 اطلاعات جناح محرمانه است؛ آن را در گروه‌ها پخش نکنید.")
    lines.append("❓ دوباره دیدن این راهنما: «راهنما» یا دکمه‌ی 📘.")
    return "\n".join(lines)


def role_of(user_id: int) -> str:
    return "leader" if user_id and leader_side(user_id) else "commander"


def guide_text(user_id: int = 0, role: str | None = None) -> str:
    role = role or role_of(user_id)
    custom = (SETTINGS.get(f"guide_{role}") or "").strip()
    if custom:
        return f"📘 <b>راهنمای {ROLES[role]}</b>\n{DIV}\n{e(custom)}"
    return default_text(role)


def validate_custom(text: str) -> str:
    """'' = معتبر؛ در غیر این صورت پیام خطا."""
    lines = [ln for ln in (text or "").splitlines()]
    if not (text or "").strip():
        return "متن خالی است."
    if len(lines) > MAX_LINES - 2:   # دو خط عنوان و جداکننده
        return f"حداکثر {MAX_LINES - 2} خط (به‌علاوه‌ی عنوان)؛ الان {len(lines)} خط است."
    if len(text) > 1500:
        return "حداکثر ۱۵۰۰ کاراکتر."
    return ""


def should_auto_show(user_id: int) -> bool:
    """اولین باری که فرمانده منو را باز می‌کند (یک‌بار برای همیشه)."""
    if not user_id or not is_player(user_id):
        return False
    u = authenticated_users.get(user_id)
    return bool(u) and not u.get("guide_seen")


def mark_seen(user_id: int) -> None:
    u = authenticated_users.get(user_id)
    if u is not None and not u.get("guide_seen"):
        u["guide_seen"] = True
        save_data()
