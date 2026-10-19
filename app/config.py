"""تنظیمات از متغیرهای محیطی Railway و ثابت‌های متنی بازی."""
import os
from zoneinfo import ZoneInfo


# ساعت تهران برای محاسبه تایم پلیر
try:
    TZ = ZoneInfo("Asia/Tehran")
except Exception:
    TZ = None


# ======================================================================
#                      تنظیمات (از Variables ریلوی)
# ======================================================================
def env_int(name, default=None):
    raw = (os.getenv(name) or "").strip().strip('"').strip("'")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"مقدار {name} باید فقط عدد باشد (مثلاً -1001234567890).")


TOKEN = (os.getenv("BOT_TOKEN") or "").strip().strip('"').strip("'")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است. آن را در Variables ریلوی وارد کنید.")

ADMIN_ID = env_int("ADMIN_ID", 7442300373)                    # آیدی عددی مالک/ادمین
CHANNEL_ID = env_int("CHANNEL_ID", -1001961681477)            # کانال اصلی (اعزام، محاصره، جنگ)
REPORT_CHANNEL_ID = env_int("REPORT_CHANNEL_ID", -1004391280733)  # کانال گزارش لشکرکشی (برای ادمین)
TWEET_CHANNEL_ID = env_int("TWEET_CHANNEL_ID", -1001892396783)    # کانال توییت (بیانیه‌ها)
BACKUP_CHAT_ID = env_int("BACKUP_CHAT_ID")                    # محل پشتیبان‌گیری داده‌ها (پیش‌فرض: پی‌وی ادمین)
ADMIN_CODE = os.getenv("ADMIN_CODE", "ADMIN").strip().upper()  # کد ورود ادمین
DATA_FILE = os.getenv("DATA_FILE", "data.json")               # فایل ذخیره‌ی داده‌ها
# کلید API هوش مصنوعی xAI/Grok برای مشاور ارتقا
# فقط از Variables ریلوی خوانده می‌شود — هرگز کلید را داخل کد ننویسید
XAI_API_KEY = (os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or "").strip().strip('"').strip("'")
XAI_MODEL = (os.getenv("XAI_MODEL") or "grok-3-mini").strip()
# مشاور ارتقا فقط خواندنی است — هرگز CITY_ASSETS / سکه / نیرو را تغییر نمی‌دهد

# فرم رسمی ارتقا (قوانین بازی)
UPGRADE_FORM_TEMPLATE = (
    "#فرم_ارتقا\n\n"
    "🏢نام ساختمان: {name}\n"
    "🔹از لول: {from_lv}\n"
    "🔹به لول: {to_lv}\n\n"
    "🧮هزینه ارتقا: {cost}\n"
    "◻️بازدهی نهایی: {yield_final}"
)

ADVISE_MODES = {
    "econ": ("💰", "اقتصادی"),
    "mil": ("⚔️", "نظامی"),
    "land": ("🛡", "زمینی"),
    "naval": ("⚓️", "دریایی"),
    "balance": ("⚖️", "ترکیبی / بالانس"),
    "chat": ("💬", "چت آزاد (سلیقه و پلن)"),
}

CODE_PREFIX = "AOW"          # کد ورود هر شهر با این شروع می‌شود
CANCEL_WINDOW = 600          # مهلت لغو محاصره/جنگ (ثانیه)
BACKUP_NAME = "aof_data.json"

CAMP_PHOTO = "https://i.ibb.co/Vp0g6W5/image.png"
WAR_PHOTO = "https://images.unsplash.com/photo-1618336753974-aae8e04506aa?q=80&w=600"
SIEGE_PHOTO = "https://images.unsplash.com/photo-1599740489246-0f33e7228f04?q=80&w=600"
DEFAULT_PHOTOS = {"campaign": CAMP_PHOTO, "war": WAR_PHOTO, "siege": SIEGE_PHOTO}
# ریشه پروژه (پوشه‌ای که main.py در آن است)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")


def _first_existing(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[0]


# همه‌ی آرت‌ها داخل یک فایل zip — جای قدیمی (کنار main.py) هم پشتیبانی می‌شود
ART_ZIP = _first_existing(os.path.join(ASSETS_DIR, "art.zip"), os.path.join(BASE_DIR, "art.zip"))
ART_DIR = _first_existing(os.path.join(ASSETS_DIR, "images"), os.path.join(BASE_DIR, "images"))  # (اختیاری) آرت‌های تکی
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")

MENU_TEXT = "🏰 <b>خوش آمدید سرورم</b>\nلطفا دستور خود را از میان دکمه ها انتخاب کنید. 👇"
PV_PLAYER_TEXT = (
    "🏰 سرورم، دستورات لشکرکشی / محاصره / جنگ / بیانیه فقط در <b>گروه شهر</b> شما انجام می‌شود.\n\n"
    "برای کمین، تغییر مسیر و بک از دکمه‌های کانال استفاده کنید؛ ربات شما را به پی‌وی هدایت می‌کند."
)
DIV = "━━━━━━━━━━━━━━"
BTN_YES = "✅ تایید"
BTN_NO = "❌ لغو"
BTN_BACK = "🔙 بازگشت"

# نوع لشکرکشی / محاصره / جنگ
MTYPES = {"sea": "دریایی", "land": "زمینی"}
MTYPE_BUTTONS = {"sea": "⚓ دریایی", "land": "🏕 زمینی"}
MTYPE_EMOJI = {"sea": "⚓", "land": "🏕"}
KIND_NOUN = {"campaign": "لشکرکشی", "siege": "محاصره", "war": "جنگ"}

CAMP_ORIGIN_PROMPT = (
    "⚔️ سرورم شما هم اکنون در حال دستور <b>اعزام لشکریان</b> خود هستید.\n\n"
    "📍 لطفا <b>مبدا و کشور</b> را وارد کنید "
    "(مثال: <code>آمیان_فرانسه</code> یا <code>york_england</code>).\n"
    "↩️ به این پیام <b>ریپلای</b> کنید (یا بنویسید بازگشت)."
)


# ======================================================================
#                    ۲. محاصره و ۳. اعلان جنگ (فرم مشترک)
# ======================================================================
ORDERS = {
    "siege": {
        "photo": "siege",
        "noun": "محاصره",
        "ask_target": "🏰 سرورم قصد <b>محاصره</b> کدام شهر از کشور ... دارید؟\n"
                      "لطفا به صورت (اسم شهر از کشور ...) وارد کنید.\n\n"
                      "📝 مثال: <code>آمیان از فرانسه</code>",
        "ask_stats": "📊 سرورم لطفا <b>آمار ارتش محاصره</b> را به صورت <b>تفکیک شده</b> وارد کنید.\n\n"
                     "⚠️ توجه کنید اگر به صورت <b>متحد</b> محاصره می‌کنید آمار هر شهر را تفکیک شده ارائه دهید.\n"
                     "📝 مانند: لندن ۱۰۰ سرباز، پمبورک ۲۰۰ سرباز.",
        "cancelled": "❌ سرورم دستور محاصره شما <b>لغو</b> شد.",
        "done": "✅ سرورم دستور محاصره شما ثبت شد و در کانال اعلام گردید. 🏰",
        "channel": "🏰 <b>فرمان محاصره</b> ⛓\n" + DIV + "\n\n"
                   "👑 {who} شهر <b>{city}</b>\n"
                   "دستور محاصره شهر <b>{target}</b> 🎯 را ارسال کرد.",
        "cancel_post": "🏳️ {who} دستور <b>محاصره</b> خود به شهر <b>{target}</b> را <b>لغو</b> کرد.",
        "report_title": "🏰 <b>گزارش فنی محاصره</b>",
        "cancel_report": "🏳️ <b>لغو محاصره</b>",
    },
    "war": {
        "photo": "war",
        "noun": "جنگ",
        "ask_target": "🛡️ سرورم قصد <b>اعلان جنگ</b> به کدام شهر از کشور ... دارید؟\n"
                      "لطفا به صورت (اسم شهر از کشور ...) وارد کنید.\n\n"
                      "📝 مثال: <code>آمیان از فرانسه</code>",
        "ask_stats": "📊 سرورم لطفا <b>آمار ارتش اعلان جنگ</b> را به صورت <b>تفکیک شده</b> وارد کنید.\n\n"
                     "⚠️ توجه کنید اگر به صورت <b>متحد</b> اعلان جنگ می‌دهید آمار هر شهر را تفکیک شده ارائه دهید.\n"
                     "📝 مانند: لندن ۱۰۰ سرباز، پمبورک ۲۰۰ سرباز.",
        "cancelled": "❌ سرورم اعلان جنگ شما <b>لغو</b> شد.",
        "done": "✅ سرورم اعلان جنگ شما ثبت شد و در کانال اعلام گردید. 🔥",
        "channel": "🔥 <b>طبل جنگ نواخته شد</b> 🔥\n" + DIV + "\n\n"
                   "👑 {who} شهر <b>{city}</b>\n"
                   "دستور حمله ارتش خود را به شهر <b>{target}</b> 🎯 ارسال نمود.",
        "cancel_post": "🕊 {who} دستور <b>حمله</b> خود به شهر <b>{target}</b> را <b>لغو</b> کرد.",
        "report_title": "🚨 <b>گزارش فنی اعلان جنگ</b>",
        "cancel_report": "🕊 <b>لغو اعلان جنگ</b>",
    },
}
