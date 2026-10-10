import asyncio
import html
import io
import json
import logging
import os
import random
import re
import secrets
import time
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ساعت تهران برای محاسبه تایم پلیر
try:
    TZ = ZoneInfo("Asia/Tehran")
except Exception:
    TZ = None

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    ForceReply,
    FSInputFile,
    InputMediaDocument,
    ReplyKeyboardRemove,
    ReplyParameters,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


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
# اگر ریلوی متغیر نمی‌گیرد، همین‌جا بین کوتیشن بگذار (مثال: "xai-xxxx")
XAI_API_KEY_IN_CODE = "xai-bl7px1npdHjfZz1bnfnJ0ugK02TovFwoEEaZO1ocO8xNpTXVE1zS6aHRLxZPgw5xOH0S7XYWsqnMeq5Q"
XAI_API_KEY = (
    XAI_API_KEY_IN_CODE.strip()
    or (os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or "").strip()
)
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

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

BOT_USERNAME = None  # بعد از استارت از get_me پر می‌شود

CAMP_PHOTO = "https://i.ibb.co/Vp0g6W5/image.png"
WAR_PHOTO = "https://images.unsplash.com/photo-1618336753974-aae8e04506aa?q=80&w=600"
SIEGE_PHOTO = "https://images.unsplash.com/photo-1599740489246-0f33e7228f04?q=80&w=600"
DEFAULT_PHOTOS = {"campaign": CAMP_PHOTO, "war": WAR_PHOTO, "siege": SIEGE_PHOTO}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ART_ZIP = os.path.join(BASE_DIR, "art.zip")     # همه‌ی آرت‌ها داخل یک فایل zip
ART_DIR = os.path.join(BASE_DIR, "images")      # (اختیاری) آرت‌های تکی

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
#                              ذخیره‌سازی
# ======================================================================
# PLAYER_CODES:        کد ورود -> نام شهر (مثل آمیان_فرانسه)
# authenticated_users: آیدی کاربر -> {"role", "country"(نام شهر), "code", "username", "name"}
# active_actions:      شناسه عملیات -> اطلاعات لشکرکشی/محاصره/جنگ (برای دکمه‌های کانال)
PLAYER_CODES = {}
authenticated_users = {}
active_actions = {}
all_players = set()
GROUPS = {}   # آیدی گروه -> {"city": نام شهر, "code": کد شهر} — گروه‌هایی که با «ست گپ» ثبت شده‌اند

# تنظیمات بازی (تایم استارت/استاپ، پیام‌ها، موارد مجاز)
# SETTINGS: {
#   "time_start": "08:00", "time_stop": "23:00",
#   "msg_start": "...", "msg_stop": "...",
#   "allowed": "لشکرکشی،محاصره،جنگ،تجارت"  # متن آزاد برای ادمین
# }
SETTINGS = {
    "time_start": "08:00",
    "time_stop": "23:00",
    # روزهای مجاز (۰=دوشنبه … ۶=یکشنبه مطابق datetime.weekday) — خالی = همه روزها
    # مثال: "0,1,2,3" = دوشنبه تا پنجشنبه | فارسی: "شنبه,یکشنبه,دوشنبه"
    "days_start": "0,1,2,3",  # شنبه تا چهارشنبه ≈ بازی؛ قابل تنظیم
    "days_stop": "",          # خالی = همان days_start
    "msg_start": "⏰ تایم استارت فعال شد. دستورات نظامی آزاد است.",
    "msg_stop": "🛑 تایم استاپ فعال شد. دستورات نظامی تا استارت بعدی محدود است.",
    "allowed": "لشکرکشی، محاصره، جنگ، تجارت، بیانیه",
    # file_id عکس‌ها
    "photo_start": "",
    "photo_stop": "",
    "photo_menu": "",  # عکس منوی کاربری (اختیاری)
    # قالب‌های لیدربورد اعلامیه (ادمین می‌تواند عوض کند؛ {rank} {name} {flag})
    "lb_intro_all": "",
    "lb_intro_econ": "",
    "lb_intro_mil": "",
    "lb_intro_nav": "",
    "lb_place_1": "در صدر ایستاده است",
    "lb_place_2": "پس از او می‌درخشد",
    "lb_place_3": "رتبهٔ سوم را از آن خود کرده",
    "lb_place_mid": "در ردیف‌های میانی قدرت جای گرفته",
    "lb_place_low": "هنوز در سایهٔ بزرگان می‌جنگد",
    "lb_footer": "جنگ داخلی انگلیس آینهٔ قدرت است؛ رتبه امروز، سرنوشت فرداست.",
}

# شهرهایی که حالت فول‌اتو فعال است (تست) — فقط روی این‌ها ارتقا/آپ/تلفات از بات اعمال می‌شود
# city_name -> True
AUTO_CITIES = {}

# ادمین دارایی — گزارش کامل تجارت برای او هم می‌رود
ASSET_ADMIN_ID = None  # int یا None؛ با ریپلای + «ست ادمین دارایی» تنظیم می‌شود

# کاتالوگ تجار: نام کالا -> سقف مجاز خرید (عدد)
# فرمت ورودی ادمین مثل:
# |🪵|~| چوب | : 300
DEFAULT_MERCHANT_LIMITS = {
    "چوب": 300,
    "آهن": 300,
    "اهن": 300,
    "سنگ": 300,
    "پوشاک": 200,
    "باروت": 200,
    "جمعیت": 250,
}
MERCHANT_LIMITS = dict(DEFAULT_MERCHANT_LIMITS)
# متن خام لیست (برای نمایش به پلیر) — ادمین می‌تواند جایگزین کند
MERCHANT_LIST_TEXT = (
    "⚜️ لیست قیمت خرید از تجار — به ازای هر ۱ عدد باید X مقدار بپردازید\n\n"
    "|🪵|~| چوب | : 300\n"
    "|🔩|~| آهن | : 300\n"
    "|🪨|~| سنگ | : 300\n"
    "|🧥|~| پوشاک | : 200\n"
    "|💥|~| باروت | : 200\n"
    "|👨‍👩‍👧‍👦|-| جمعیت | : 250\n\n"
    "محدودیت خرید و فروش به صورت بالاست.\n"
    "قیمت خرید هر عدد: ۵ سکه\n"
    "قیمت فروش هر عدد: ۲ سکه"
)
# قیمت پیش‌فرض واحد (سکه) — اگر برای کالا قیمت جدا نباشد
MERCHANT_BUY_PRICE = 5
MERCHANT_SELL_PRICE = 2
# قیمت جداگانه هر کالا: {"چوب": {"buy": 5, "sell": 2}, ...}
MERCHANT_PRICES = {}
# فعال/غیرفعال بودن تجارت با تجار
MERCHANT_ENABLED = True
# باف پیش‌فرض تجارت با تجار (درصد)
MERCHANT_BUFF_DEFAULT = 0

# لیدرهای هر ساید — حداکثر ۳ نفر
# monarchist / parliamentarian = دو جناح انگلیس
LEADERS = {
    "monarchist": [],
    "parliamentarian": [],
    "france": [],
    "ireland": [],
}

# دارایی هر شهر:
# {"آمیان_فرانسه": {"text": "متن کامل شیت…", "stats": {"خزانه": 9700, "چوب": 380}}}
# text = همان چیزی که ادمین ست می‌کند؛ stats = اعداد استخراج‌شده برای جمع قلمرو
CITY_ASSETS = {}

# تاییدهای در انتظار — مستقل از FSM تا بعد از ری‌استارت یا باگ state هم کار کند
# user_id -> {"kind": "campaign"|"siege"|"war"|"ann"|..., "data": {...}, "chat_id": int}
pending_confirms = {}

backup_state = {"mid": None}
_backup_flags = {"dirty": False, "running": False}
_tasks = set()


def spawn(coro):
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def snapshot():
    recent = sorted(active_actions.items(), key=lambda kv: kv[1].get("time_created", 0), reverse=True)[:300]
    return {
        "codes": PLAYER_CODES,
        "users": {str(uid): u for uid, u in authenticated_users.items() if u.get("role") in ("player", "admin")},
        "actions": dict(recent),
        "groups": {str(cid): g for cid, g in GROUPS.items()},
        "settings": dict(SETTINGS),
        "asset_admin_id": ASSET_ADMIN_ID,
        "merchant_limits": dict(MERCHANT_LIMITS),
        "merchant_buff_default": MERCHANT_BUFF_DEFAULT,
        "merchant_list_text": MERCHANT_LIST_TEXT,
        "merchant_buy_price": MERCHANT_BUY_PRICE,
        "merchant_sell_price": MERCHANT_SELL_PRICE,
        "merchant_prices": {k: dict(v) for k, v in MERCHANT_PRICES.items()},
        "merchant_enabled": bool(MERCHANT_ENABLED),
        "leaders": {k: list(v) for k, v in LEADERS.items()},
        "city_assets": {k: dict(v) for k, v in CITY_ASSETS.items()},
        "auto_cities": {str(k): bool(v) for k, v in AUTO_CITIES.items()},
    }


def apply_data(raw):
    codes = {str(k).upper(): str(v) for k, v in (raw.get("codes") or {}).items()}
    users = {}
    for k, u in (raw.get("users") or {}).items():
        try:
            uid = int(k)
        except ValueError:
            continue
        if not isinstance(u, dict):
            continue
        if u.get("role") == "admin":
            users[uid] = u
        elif u.get("role") == "player" and u.get("code") in codes:   # کاربری که کدش باطل شده حذف می‌شود
            users[uid] = u
    actions = {str(k): v for k, v in (raw.get("actions") or {}).items() if isinstance(v, dict) and "owner_id" in v}
    groups = {}
    for k, g in (raw.get("groups") or {}).items():
        try:
            cid = int(k)
        except ValueError:
            continue
        if isinstance(g, dict) and g.get("city"):
            groups[cid] = g

    PLAYER_CODES.clear()
    PLAYER_CODES.update(codes)
    authenticated_users.clear()
    authenticated_users.update(users)
    active_actions.clear()
    active_actions.update(actions)
    all_players.clear()
    all_players.update(uid for uid, u in users.items() if u.get("role") == "player")
    GROUPS.clear()
    GROUPS.update(groups)

    # تنظیمات و داده‌های تکمیلی
    global ASSET_ADMIN_ID, MERCHANT_BUFF_DEFAULT, MERCHANT_LIST_TEXT
    global MERCHANT_BUY_PRICE, MERCHANT_SELL_PRICE, MERCHANT_ENABLED
    st = raw.get("settings") or {}
    if isinstance(st, dict):
        for k in (
            "time_start", "time_stop", "days_start", "days_stop",
            "msg_start", "msg_stop", "allowed",
            "photo_start", "photo_stop", "photo_menu",
            "lb_intro_all", "lb_intro_econ", "lb_intro_mil", "lb_intro_nav",
            "lb_place_1", "lb_place_2", "lb_place_3", "lb_place_mid", "lb_place_low", "lb_footer",
        ):
            if st.get(k) is not None:
                SETTINGS[k] = str(st[k])
    AUTO_CITIES.clear()
    ac = raw.get("auto_cities") or {}
    if isinstance(ac, dict):
        for ck, cv in ac.items():
            if cv:
                AUTO_CITIES[str(ck)] = True
    try:
        ASSET_ADMIN_ID = int(raw["asset_admin_id"]) if raw.get("asset_admin_id") else None
    except (TypeError, ValueError):
        ASSET_ADMIN_ID = None
    ml = raw.get("merchant_limits") or {}
    MERCHANT_LIMITS.clear()
    if isinstance(ml, dict) and ml:
        for name, lim in ml.items():
            try:
                MERCHANT_LIMITS[str(name).strip()] = float(lim)
            except (TypeError, ValueError):
                continue
    if not MERCHANT_LIMITS:
        MERCHANT_LIMITS.update(DEFAULT_MERCHANT_LIMITS)
    try:
        MERCHANT_BUFF_DEFAULT = float(raw.get("merchant_buff_default") or 0)
    except (TypeError, ValueError):
        MERCHANT_BUFF_DEFAULT = 0
    if raw.get("merchant_list_text"):
        MERCHANT_LIST_TEXT = str(raw["merchant_list_text"])
    try:
        MERCHANT_BUY_PRICE = float(raw.get("merchant_buy_price", MERCHANT_BUY_PRICE))
    except (TypeError, ValueError):
        pass
    try:
        MERCHANT_SELL_PRICE = float(raw.get("merchant_sell_price", MERCHANT_SELL_PRICE))
    except (TypeError, ValueError):
        pass
    MERCHANT_PRICES.clear()
    for name, pr in (raw.get("merchant_prices") or {}).items():
        if not isinstance(pr, dict):
            continue
        try:
            MERCHANT_PRICES[str(name).strip()] = {
                "buy": float(pr.get("buy", MERCHANT_BUY_PRICE)),
                "sell": float(pr.get("sell", MERCHANT_SELL_PRICE)),
            }
        except (TypeError, ValueError):
            continue
    MERCHANT_ENABLED = bool(raw.get("merchant_enabled", True))
    LEADERS.clear()
    LEADERS.update({
        "monarchist": [],
        "parliamentarian": [],
        "france": [],
        "ireland": [],
    })
    raw_leaders = dict(raw.get("leaders") or {})
    # مهاجرت: england قدیمی → monarchist
    if "england" in raw_leaders and "monarchist" not in raw_leaders:
        raw_leaders["monarchist"] = raw_leaders.pop("england")
    for side, ids in raw_leaders.items():
        key = str(side).lower()
        if key not in LEADERS:
            continue
        cleaned = []
        for x in (ids or []):
            try:
                cleaned.append(int(x))
            except (TypeError, ValueError):
                continue
        LEADERS[key] = cleaned[:3]
    CITY_ASSETS.clear()
    for city, items in (raw.get("city_assets") or {}).items():
        if not isinstance(items, dict):
            continue
        # فرمت جدید: {text, stats}
        if "text" in items or "stats" in items:
            text = str(items.get("text") or "")
            stats = {}
            for n, v in (items.get("stats") or {}).items():
                try:
                    stats[str(n).strip()] = float(v)
                except (TypeError, ValueError):
                    continue
            if text or stats:
                CITY_ASSETS[str(city)] = {"text": text, "stats": stats}
            continue
        # فرمت قدیمی: فقط اعداد
        bag = {}
        for n, v in items.items():
            try:
                bag[str(n).strip()] = float(v)
            except (TypeError, ValueError):
                continue
        if bag:
            CITY_ASSETS[str(city)] = {
                "text": "\n".join(f"{k}: {int(v) if float(v)==int(v) else v}" for k, v in bag.items()),
                "stats": bag,
            }


def read_local():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        logging.exception("خواندن فایل داده ناموفق بود.")
        return None


def write_local():
    try:
        folder = os.path.dirname(DATA_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        # بدون indent = سریع‌تر و فایل کوچک‌تر
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot(), f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, DATA_FILE)
    except Exception:
        logging.exception("ذخیره‌ی فایل داده ناموفق بود.")


def has_data():
    return bool(PLAYER_CODES or authenticated_users or active_actions or GROUPS)


def backup_chat():
    return BACKUP_CHAT_ID or ADMIN_ID


def _mid_file():
    """فایل کوچک برای نگه داشتن message_id پشتیبان بین ری‌استارت‌های کوتاه."""
    return DATA_FILE + ".mid"


def _save_mid(mid):
    try:
        with open(_mid_file(), "w", encoding="utf-8") as f:
            f.write(str(int(mid)))
    except Exception:
        pass


def _load_mid():
    try:
        with open(_mid_file(), encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


async def find_backup_message():
    """
    ترتیب جستجو:
    1) پیام پین‌شده با نام aof_data.json
    2) message_id ذخیره‌شده — با forward سند را می‌گیریم (کپی موقت)
    """
    chat_id = backup_chat()
    # 1) پین
    try:
        chat = await bot.get_chat(chat_id)
        pm = getattr(chat, "pinned_message", None)
        if pm and getattr(pm, "document", None):
            fname = (pm.document.file_name or "").lower()
            if fname == BACKUP_NAME.lower() or fname.endswith(".json"):
                return pm
            logging.warning("پین هست ولی نام فایل %s است (انتظار: %s)",
                            pm.document.file_name, BACKUP_NAME)
    except Exception:
        logging.exception("خواندن پین پشتیبان از چت %s ناموفق بود.", chat_id)

    # 2) mid محلی — فوروارد موقت برای دسترسی به document
    mid = backup_state.get("mid") or _load_mid()
    if mid:
        try:
            fwd = await bot.forward_message(
                chat_id=chat_id, from_chat_id=chat_id, message_id=mid, disable_notification=True,
            )
            if fwd and getattr(fwd, "document", None):
                backup_state["mid"] = mid
                # علامت می‌زنیم که این پیام موقت است تا بعد از دانلود پاک شود
                try:
                    fwd._aof_temp_fwd = True  # noqa: SLF001
                except Exception:
                    pass
                return fwd
        except Exception:
            logging.warning("forward mid=%s برای بازیابی ناموفق بود", mid)
            backup_state["mid"] = mid
    return None


async def _download_backup_doc(document) -> dict:
    buf = io.BytesIO()
    await bot.download(document, destination=buf)
    return json.loads(buf.getvalue().decode("utf-8"))


async def push_backup():
    """داده‌ها را به‌صورت فایل داخل تلگرام (پیام پین‌شده) نگه می‌دارد تا با Deploy مجدد از بین نرود."""
    chat = backup_chat()
    payload = json.dumps(snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    caption = (
        f"🗄 پشتیبان داده‌های ربات — این پیام را <b>حذف/آن‌پین نکنید</b>\n"
        f"🏙 شهر: {len(PLAYER_CODES)} | 👤 فرمانده: {len(all_players)} | 👥 گروه: {len(GROUPS)}\n"
        f"🕒 {datetime.now(TZ).strftime('%Y-%m-%d %H:%M') if TZ else datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    mid = backup_state.get("mid") or _load_mid()
    if mid:
        try:
            doc = BufferedInputFile(payload, filename=BACKUP_NAME)
            await bot.edit_message_media(
                media=InputMediaDocument(media=doc, caption=caption),
                chat_id=chat, message_id=mid,
            )
            backup_state["mid"] = mid
            _save_mid(mid)
            return
        except TelegramBadRequest as ex:
            if "not modified" in str(ex).lower():
                return
            logging.warning("ویرایش پیام پشتیبان ناموفق بود؛ پیام جدید ساخته می‌شود: %s", ex)
            backup_state["mid"] = None
        except Exception as ex:
            logging.warning("ویرایش پشتیبان ناموفق: %s", ex)
            backup_state["mid"] = None

    doc = BufferedInputFile(payload, filename=BACKUP_NAME)
    sent = await bot.send_document(chat_id=chat, document=doc, caption=caption, disable_notification=True)
    backup_state["mid"] = sent.message_id
    _save_mid(sent.message_id)
    try:
        await bot.pin_chat_message(chat_id=chat, message_id=sent.message_id, disable_notification=True)
    except Exception:
        logging.exception(
            "پین کردن پیام پشتیبان ناموفق بود. mid=%s — پیام را دستی در پی‌وی ربات پین کنید!",
            sent.message_id,
        )
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "⚠️ <b>پین پشتیبان ناموفق بود</b>\n"
                    "لطفاً در پی‌وی ربات، آخرین فایل <code>aof_data.json</code> را "
                    "<b>پین</b> کنید تا بعد از ری‌استارت داده از بین نرود."
                ),
                disable_notification=True,
            )
        except Exception:
            pass


async def _backup_worker():
    try:
        await asyncio.sleep(1.5)
        while _backup_flags["dirty"]:
            _backup_flags["dirty"] = False
            try:
                await push_backup()
            except Exception:
                logging.exception("پشتیبان‌گیری در تلگرام ناموفق بود.")
            if _backup_flags["dirty"]:
                await asyncio.sleep(2)
    finally:
        _backup_flags["running"] = False


def save_data(critical=False):
    """
    ذخیره محلی فوری + پشتیبان تلگرام در پس‌زمینه.
    critical=True → آپلود تلگرام را فوری هم صف می‌کند (برای ست پلیر/گپ).
    """
    try:
        write_local()
    except Exception:
        logging.exception("write_local در save_data ناموفق بود.")
    _backup_flags["dirty"] = True
    if not _backup_flags["running"]:
        try:
            _backup_flags["running"] = True
            spawn(_backup_worker())
        except RuntimeError:
            _backup_flags["running"] = False
    if critical:
        # تلاش فوری اضافه (بدون بلاک کردن event loop طولانی)
        try:
            spawn(push_backup())
        except RuntimeError:
            pass


async def restore_from_document(document) -> tuple:
    """بازیابی از یک Document تلگرام. برمی‌گرداند (ok, msg)."""
    try:
        fname = (document.file_name or "").lower()
        if not (fname.endswith(".json") or fname == BACKUP_NAME.lower()):
            return False, "فایل باید json باشد (aof_data.json)."
        raw = await _download_backup_doc(document)
        if not isinstance(raw, dict):
            return False, "محتوای فایل نامعتبر است."
        apply_data(raw)
        write_local()
        try:
            await push_backup()
        except Exception:
            logging.exception("پس از بازیابی، پشتیبان جدید ناموفق بود.")
        return True, (
            f"✅ بازیابی شد.\n"
            f"🏙 شهر: <b>{len(PLAYER_CODES)}</b>\n"
            f"👤 فرمانده: <b>{len(all_players)}</b>\n"
            f"👥 گروه: <b>{len(GROUPS)}</b>"
        )
    except Exception as ex:
        logging.exception("restore_from_document")
        return False, f"❌ خطا در بازیابی: <code>{e(str(ex)[:200])}</code>"


async def init_storage():
    """
    روی Railway رایگان دیسک پاک می‌شود → منبع حقیقت = پیام پین‌شده تلگرام.
    همیشه اول از تلگرام بازیابی می‌کنیم (اگر باشد).
    """
    restored = False
    try:
        pm = await find_backup_message()
        if pm and getattr(pm, "document", None):
            # اگر از پین آمده mid همان پین است؛ اگر فوروارد موقت باشد mid اصلی را نگه می‌داریم
            is_temp = bool(getattr(pm, "_aof_temp_fwd", False))
            if not is_temp:
                backup_state["mid"] = pm.message_id
                _save_mid(pm.message_id)
            raw = await _download_backup_doc(pm.document)
            apply_data(raw)
            write_local()
            restored = True
            if is_temp:
                try:
                    await bot.delete_message(chat_id=backup_chat(), message_id=pm.message_id)
                except Exception:
                    pass
            logging.info(
                "✅ بازیابی از پشتیبان تلگرام: %s شهر، %s فرمانده، %s گروه",
                len(PLAYER_CODES), len(all_players), len(GROUPS),
            )
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"✅ ربات روشن شد و داده بازیابی شد.\n"
                        f"🏙 شهر: <b>{len(PLAYER_CODES)}</b>\n"
                        f"👤 فرمانده: <b>{len(all_players)}</b>\n"
                        f"👥 گروه: <b>{len(GROUPS)}</b>"
                    ),
                    disable_notification=True,
                )
            except Exception:
                pass
        else:
            logging.warning("⚠️ پشتیبان پین‌شده پیدا نشد.")
            if has_data():
                logging.info("داده محلی موجود است: %s شهر — آپلود پشتیبان…", len(PLAYER_CODES))
                try:
                    await push_backup()
                except Exception:
                    logging.exception("آپلود پشتیبان اولیه ناموفق")
            else:
                # هیچ داده‌ای نیست — هشدار جدی به ادمین
                try:
                    await bot.send_message(
                        chat_id=ADMIN_ID,
                        text=(
                            "⚠️ <b>هشدار: داده پیدا نشد</b>\n"
                            f"{DIV}\n"
                            "پشتیبان پین‌شده در تلگرام یافت نشد و دیسک هم خالی است.\n\n"
                            "<b>بازیابی دستی:</b>\n"
                            "۱) در پی‌وی ربات فایل <code>aof_data.json</code> قدیمی را پیدا کنید "
                            "(یا از فوروارد/سیو شده)\n"
                            "۲) همان فایل را برای ربات بفرستید\n"
                            "۳) یا بنویسید <code>/restore</code> و فایل را ضمیمه کنید\n\n"
                            "بعد از ست دوباره پلیر/گپ، پیام پشتیبان را <b>پین</b> نگه دارید."
                        ),
                        disable_notification=True,
                    )
                except Exception:
                    pass
    except Exception:
        logging.exception("بازیابی از پشتیبان تلگرام ناموفق بود.")
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text="❌ بازیابی خودکار ناموفق بود. فایل <code>aof_data.json</code> را برای ربات بفرستید.",
            )
        except Exception:
            pass
    return restored


_raw = read_local()
if _raw:
    apply_data(_raw)
mid0 = _load_mid()
if mid0:
    backup_state["mid"] = mid0


# ======================================================================
#                              ابزارها
# ======================================================================
def e(value):
    """متن کاربر را برای HTML امن می‌کند."""
    return html.escape(str(value), quote=False)


def norm_cmd(text):
    """چند نوشتار مختلف یک دستور را یکسان می‌کند: «ست پلیر»، «/set player»، «/setplayer» و ... ."""
    return re.sub(r"[\s/_-]+", "", (text or "").strip()).lower()


def is_player(user_id):
    u = authenticated_users.get(user_id)
    return bool(u and u.get("role") == "player")


def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    u = authenticated_users.get(user_id)
    return bool(u and u.get("role") == "admin")


def city_of(user_id):
    return authenticated_users.get(user_id, {}).get("country", "ناشناس")


def mention(user_id, label="فرمانده"):
    """کلمه‌ای که روی آن لینک پروفایل بازیکن قرار می‌گیرد."""
    return f'<a href="tg://user?id={user_id}">{e(label)}</a>'


def code_owner(code):
    for uid, u in authenticated_users.items():
        if u.get("role") == "player" and u.get("code") == code:
            return uid
    return None


def gen_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = CODE_PREFIX + "".join(secrets.choice(alphabet) for _ in range(5))
        if code not in PLAYER_CODES and code != ADMIN_CODE:
            return code


def user_fsm(user_id):
    """وضعیت گفتگوی پی‌وی یک بازیکن (برای دکمه‌های کانال لازم است)."""
    return FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))


def chat_fsm(chat_id, user_id):
    """وضعیت گفتگوی یک کاربر مشخص در یک چت مشخص (برای فرمانده‌ی گروه لازم است)."""
    return FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id))


def is_group_chat(message):
    return message.chat.type in ("group", "supergroup")


# ---------------- آرت پست‌ها ----------------
# نام فایل‌ها:  art_<نوع>_<land|sea|all>_<کشور|all>_<شماره>.jpg
#   نوع = campaign | war | siege | ambush | trade
#   کشور = england | france | ireland | all
#   مثال:
#     art_campaign_land_england_1.jpg
#     art_campaign_sea_france_2.jpg
#     art_war_land_ireland_1.jpg
#     art_trade_land_all_1.jpg
#     art_campaign_land_all_1.jpg   ← عمومی (فقط اگر فکشن پیدا نشد)
ART_RE = re.compile(
    r"^(?:.*/)?art_(campaign|siege|war|ambush|trade)_(land|sea|all)_([a-z]+)_\d+\.(?:jpe?g|png)$",
    re.I,
)
COUNTRY_ALIASES = {
    # دو جناح انگلیس
    "monarchist": {
        "مونارشیست", "مونارش", "پادشاهی", "پادشاهیخواه", "رویالیست",
        "monarchist", "monarch", "royal", "royalist", "king",
    },
    "parliamentarian": {
        "پارلمانری", "پارلمان", "پارلمانتاریان", "جمهوریخواه",
        "parliamentarian", "parliament", "parliamentary", "roundhead",
    },
    # سازگاری با نام قدیمی england در شهر/آرت
    "england": {
        "انگلستان", "انگلیس", "بریتانیا", "بریتانیایکبیر", "انگلند",
        "england", "engeland", "englend", "britain", "greatbritain", "uk", "eng",
    },
    "france": {
        "فرانسه", "فرانسوی", "france", "franse", "fransa", "fran",
    },
    "ireland": {
        "ایرلند", "ایرلندی", "ireland", "ire", "eire", "éire",
    },
}
# چهار ساید رسمی (انگلیس = مونارشیست + پارلمانری)
FACTIONS = ("monarchist", "parliamentarian", "france", "ireland")

# آرت فایل‌ها هنوز با england برچسب خورده‌اند
ART_FACTION_MAP = {
    "monarchist": "england",
    "parliamentarian": "england",
    "england": "england",
    "france": "france",
    "ireland": "ireland",
}

# پارلمانری: ۱۰ شهر مشخص — بقیه انگلیس = مونارشیست
DEFAULT_CITIES = [
    # Parliamentarian
    "norwich_parliamentarian",
    "leeds_parliamentarian",
    "dover_parliamentarian",
    "winchester_parliamentarian",
    "bridgwater_parliamentarian",
    "exeter_parliamentarian",
    "york_parliamentarian",
    "gloucester_parliamentarian",
    "newcastle_parliamentarian",
    "manchester_parliamentarian",
    # Monarchist (بقیه انگلیس)
    "london_monarchist",
    "cambridge_monarchist",
    "leicester_monarchist",
    "bristol_monarchist",
    "edinburgh_monarchist",
    "oxford_monarchist",
    "colchester_monarchist",
    "pembroke_monarchist",
    "liverpool_monarchist",
    "nottingham_monarchist",
    # Ireland
    "dublin_ireland",
    "armagh_ireland",
    "limerick_ireland",
    "waterford_ireland",
    "cork_ireland",
    # France
    "amiens_france",
    "nantes_france",
    "brest_france",
    "paris_france",
    "caen_france",
]

ART = {}            # (نوع، land/sea/all) -> {کشور: [آرت‌ها]}
_file_ids = {}      # آرت -> file_id تلگرام (بعد از اولین ارسال دیگر آپلود نمی‌شود)


def seed_default_cities():
    """شهرهای پیش‌فرضِ گمشده را اضافه می‌کند (نام تکراری را رد می‌کند)."""
    existing = {str(v).lower() for v in PLAYER_CODES.values()}
    n = 0
    for name in DEFAULT_CITIES:
        if name.lower() in existing:
            continue
        code = gen_code()
        while code in PLAYER_CODES:
            code = gen_code()
        PLAYER_CODES[code] = name
        existing.add(name.lower())
        n += 1
    return n


def _canonical_city_name(name: str) -> str:
    """
    نام شهر را به فرم رسمی می‌برد:
    oxford_england / آکسفورد_انگلیس → oxford_monarchist
    norwich_england → norwich_parliamentarian
    اگر از قبل monarchist/parliamentarian/france/ireland باشد همان می‌ماند.
    """
    if not name:
        return name
    raw = str(name).strip()
    # اگر از قبل پسوند درست دارد
    ck = country_key(raw)
    if ck in ("monarchist", "parliamentarian", "france", "ireland"):
        # اگر پسوند england قدیمی بود، country_key درست برمی‌گرداند ولی نام را عوض کن
        low = raw.lower().replace("ي", "ی")
        if low.endswith("_england") or low.endswith("_انگلیس") or low.endswith("_انگلستان"):
            base = raw.rsplit("_", 1)[0]
            base_l = _norm_country_token(base)
            parl = {_norm_country_token(x) for x in PARLIAMENT_CITY_BASES}
            suffix = "parliamentarian" if base_l in parl else "monarchist"
            # نام پایه را انگلیسی نگه دار اگر در DEFAULT هست
            eng_base = None
            for c in DEFAULT_CITIES:
                if c.endswith(f"_{suffix}") and _norm_country_token(c.rsplit("_", 1)[0]) == base_l:
                    eng_base = c.rsplit("_", 1)[0]
                    break
            return f"{eng_base or base}_{suffix}"
        return raw
    # بدون پسوند شناخته‌شده
    base_l = _norm_country_token(raw.split("_")[0] if "_" in raw else raw)
    for c in DEFAULT_CITIES:
        if _norm_country_token(c.rsplit("_", 1)[0]) == base_l:
            return c
    return raw


def migrate_city_names():
    """
    شهرهای قدیمی *_england را به monarchist/parliamentarian تبدیل می‌کند.
    داده (کد، گروه، دارایی، بازیکن) حفظ می‌شود؛ فقط نام شهر عوض می‌شود.
    """
    changed = 0

    # PLAYER_CODES: code -> city
    for code, city in list(PLAYER_CODES.items()):
        new = _canonical_city_name(city)
        if new != city:
            PLAYER_CODES[code] = new
            changed += 1

    # CITY_ASSETS keys
    for city in list(CITY_ASSETS.keys()):
        new = _canonical_city_name(city)
        if new != city:
            if new in CITY_ASSETS:
                # ادغام: متن جدیدتر ترجیح / نگه داشتن هر دو اگر متفاوت
                old_e = CITY_ASSETS.pop(city)
                if not CITY_ASSETS[new].get("text") and old_e.get("text"):
                    CITY_ASSETS[new] = old_e
            else:
                CITY_ASSETS[new] = CITY_ASSETS.pop(city)
            changed += 1

    # GROUPS
    for gid, g in list(GROUPS.items()):
        city = g.get("city")
        if city:
            new = _canonical_city_name(city)
            if new != city:
                g["city"] = new
                changed += 1

    # authenticated_users
    for uid, u in list(authenticated_users.items()):
        city = u.get("country") or u.get("city") or u.get("name")
        if city:
            new = _canonical_city_name(str(city))
            if new != city:
                if "country" in u:
                    u["country"] = new
                if "city" in u:
                    u["city"] = new
                if "name" in u and u["name"] == city:
                    u["name"] = new
                changed += 1

    # حذف شهرهای تکراری هم‌نام در PLAYER_CODES (همان نام با کدهای مختلف)
    seen = {}
    for code, city in list(PLAYER_CODES.items()):
        key = city.lower()
        if key in seen:
            # کد قدیمی‌تر را نگه دار؛ این را حذف نکن اگر به بازیکن وصل است
            pass
        else:
            seen[key] = code

    return changed


def _add_art(name, entry):
    base = os.path.basename(name)
    m = ART_RE.match(name) or ART_RE.match(base)
    if m:
        kind, typ, country = (x.lower() for x in m.groups())
        ART.setdefault((kind, typ), {}).setdefault(country, []).append(entry)


def load_art():
    ART.clear()
    if os.path.isfile(ART_ZIP):
        try:
            with zipfile.ZipFile(ART_ZIP) as z:
                for n in z.namelist():
                    if n.endswith("/") or n.startswith("__"):
                        continue
                    _add_art(n, ("zip", n))
        except Exception:
            logging.exception("خواندن art.zip ناموفق بود.")
    if os.path.isdir(ART_DIR):
        for n in sorted(os.listdir(ART_DIR)):
            _add_art(n, ("file", os.path.join(ART_DIR, n)))
    total = sum(len(v) for g in ART.values() for v in g.values())
    eng = sum(len(group.get("england", [])) for group in ART.values())
    fra = sum(len(group.get("france", [])) for group in ART.values())
    ire = sum(len(group.get("ireland", [])) for group in ART.values())
    logging.info("آرت‌های بارگذاری‌شده: %s | england=%s france=%s ireland=%s",
                 total, eng, fra, ire)


def _norm_country_token(s):
    return (
        str(s or "")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", "")
        .replace(" ", "")
        .replace("-", "")
        .lower()
    )


# شهرهای پایهٔ پارلمانری (برای تشخیص پسوند england قدیمی)
PARLIAMENT_CITY_BASES = {
    "norwich", "leeds", "dover", "winchester", "bridgwater", "bridgewater",
    "exeter", "york", "gloucester", "newcastle", "manchester",
    "نورویچ", "لیدز", "دوور", "وینچستر", "بریجواتر", "بریجوایتر",
    "اکستر", "یورک", "گلاستر", "نیوکاسل", "نیوکسل", "منچستر",
}


def country_key(city):
    """
    از نام شهر (مثل london_monarchist / norwich_parliamentarian / dublin_ireland)
    ساید را برمی‌گرداند: monarchist | parliamentarian | france | ireland
    فقط پسوند/کلید دقیق — نه substring کوتاه مثل ire/fran/king
    """
    if not city:
        return None
    raw = _norm_country_token(city)
    parts = raw.split("_") if "_" in raw else [raw]
    suffix = parts[-1]
    base = parts[0]

    # ۱) پسوند دقیق
    for key in ("monarchist", "parliamentarian", "france", "ireland"):
        norm_names = {_norm_country_token(n) for n in COUNTRY_ALIASES[key]}
        if suffix == key or suffix in norm_names:
            return key

    # ۲) نام کامل کلید داخل نام شهر (حداقل طول ۴ تا اشتباه نشود)
    for key in ("parliamentarian", "monarchist", "ireland", "france"):
        if key in raw:
            return key
        for n in COUNTRY_ALIASES[key]:
            nn = _norm_country_token(n)
            if len(nn) >= 5 and nn in raw:
                return key

    # ۳) پسوند england قدیمی
    eng_names = {_norm_country_token(n) for n in COUNTRY_ALIASES.get("england", [])}
    if suffix in eng_names or suffix == "england":
        base_n = _norm_country_token(base)
        if base_n in {_norm_country_token(x) for x in PARLIAMENT_CITY_BASES}:
            return "parliamentarian"
        return "monarchist"
    return None


def art_country_key(city):
    """برای انتخاب آرت: هر دو جناح انگلیس → england."""
    side = country_key(city)
    return ART_FACTION_MAP.get(side, side)


def faction_of_user(user_id):
    """فکشن بازیکن از روی شهر ثبت‌شده‌اش."""
    return country_key(city_of(user_id))


def _pool(kind, typ, country=None):
    group = ART.get((kind, typ), {})
    if country is None:
        return [x for arts in group.values() for x in arts]
    return list(group.get(country, []))


def pick_art(kind, mtype=None, city=None):
    """
    آرت فکشن‌محور:
    1) آرت مخصوص همان فکشن + همان نوع (land/sea)
    2) آرت مخصوص فکشن با typ=all
    3) آرت عمومی all
    هرگز آرت فکشن دیگر را جایگزین نمی‌کند.
    دو جناح انگلیس هر دو از آرت england استفاده می‌کنند.
    """
    country = art_country_key(city)
    typ = mtype if mtype in ("land", "sea") else "all"

    if kind == "ambush":
        chains = [("ambush", "all"), ("ambush", typ)]
    elif kind == "trade":
        # تجارت فقط آرت مخصوص خودش — fallback به campaign همان نوع
        chains = [("trade", typ), ("trade", "all"), ("campaign", typ), ("campaign", "all")]
    else:
        chains = [(kind, typ)]
        if typ != "all":
            chains.append((kind, "all"))
        if kind == "siege":
            chains.append(("war", typ))
            chains.append(("war", "all"))
        if typ == "sea" and kind != "campaign":
            chains.append(("campaign", "sea"))

    for k, t in chains:
        if country:
            pool = _pool(k, t, country)
            if pool:
                return secrets.choice(pool)
        pool = _pool(k, t, "all")
        if pool:
            return secrets.choice(pool)
    return None


def _art_media(entry):
    cached = _file_ids.get(entry)
    if cached:
        return cached
    src, path = entry
    if src == "zip":
        with zipfile.ZipFile(ART_ZIP) as z:
            return BufferedInputFile(z.read(path), filename=os.path.basename(path))
    return FSInputFile(path)


async def send_art(chat_id, entry, caption, markup=None, reply_parameters=None):
    try:
        sent = await bot.send_photo(chat_id=chat_id, photo=_art_media(entry), caption=caption,
                                    reply_markup=markup, reply_parameters=reply_parameters)
    except Exception:
        if entry not in _file_ids:
            raise
        _file_ids.pop(entry, None)           # file_id قدیمی بود؛ دوباره آپلود می‌شود
        sent = await bot.send_photo(chat_id=chat_id, photo=_art_media(entry), caption=caption,
                                    reply_markup=markup, reply_parameters=reply_parameters)
    try:
        _file_ids[entry] = sent.photo[-1].file_id
    except Exception:
        pass
    return sent


async def send_chunks(target: types.Message, blocks, reply_markup=None, limit=3800):
    parts, chunk = [], ""
    for b in blocks:
        if chunk and len(chunk) + len(b) + 1 > limit:
            parts.append(chunk)
            chunk = ""
        chunk += b + "\n"
    if chunk:
        parts.append(chunk)
    for i, p in enumerate(parts):
        await target.answer(p, reply_markup=reply_markup if i == len(parts) - 1 else None)


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


async def need_text(message: types.Message, max_len=100):
    txt = (message.text or "").strip()
    if not txt:
        await message.answer("❌ لطفاً فقط متن ارسال کنید (به پیام ربات ریپلای کنید).")
        return None
    if is_back_text(txt):
        return "__BACK__"
    if len(txt) > max_len:
        await message.answer(f"❌ متن خیلی طولانی است (حداکثر {max_len} کاراکتر). کوتاه‌تر بنویسید.")
        return None
    return txt


def mtype_label(data):
    return MTYPES.get((data or {}).get("mtype"), "-")


def mtype_tag(data):
    k = (data or {}).get("mtype")
    return f"{MTYPE_EMOJI[k]} {MTYPES[k]}" if k in MTYPES else "-"


def choice(text):
    if text == BTN_YES:
        return True
    if text == BTN_NO:
        return False
    return None


def is_back_text(text):
    t = (text or "").strip()
    return t in (BTN_BACK, "بازگشت", "back", "/back")


async def go_menu(message: types.Message, state: FSMContext, text=MENU_TEXT, user_id=None):
    """
    منوی اصلی — ترجیحاً همان پیام قبلی ویرایش می‌شود تا منو تکرار نشود.
    اگر photo_menu تنظیم شده باشد، با عکس ارسال می‌شود.
    """
    uid = user_id or (message.from_user.id if message.from_user and not getattr(message.from_user, "is_bot", False) else None)
    if uid:
        pending_confirms.pop(uid, None)
    await state.clear()
    if message.chat.type == "private":
        await message.answer(text if text != MENU_TEXT else PV_PLAYER_TEXT, reply_markup=ReplyKeyboardRemove())
        return
    await state.set_state(GameStates.main_menu)
    body = text if text != MENU_TEXT else MENU_TEXT
    markup = get_main_menu_keyboard(uid)
    photo_id = (SETTINGS.get("photo_menu") or "").strip()

    # اگر پیام از خود ربات است (مثلاً callback.message) → ویرایش همان پیام
    is_bot_msg = bool(message.from_user and getattr(message.from_user, "is_bot", False))
    if is_bot_msg and not photo_id:
        try:
            await message.edit_text(body, reply_markup=markup)
            return
        except Exception:
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            try:
                await message.delete()
            except Exception:
                pass

    if photo_id:
        try:
            await message.answer_photo(photo=photo_id, caption=body, reply_markup=markup)
            return
        except Exception:
            logging.exception("ارسال عکس منو ناموفق")
    await message.answer(body, reply_markup=markup)


async def channel_failed(message: types.Message, state: FSMContext, ex, what):
    logging.exception("خطا در ارسال به کانال (%s)", what)
    await send_report(f"⚠️ <b>خطا در ارسال به کانال</b>\n{DIV}\n🛠 عملیات: {e(what)}\n❗️ خطا: <code>{e(str(ex)[:300])}</code>")
    await go_menu(message, state, "❌ ارسال به کانال ناموفق بود. ادمین مطلع شد؛ کمی بعد دوباره تلاش کنید.")


class GameStates(StatesGroup):
    waiting_for_code = State()
    main_menu = State()
    admin_broadcast = State()
    admin_broadcast_target = State()
    admin_dm = State()
    admin_add_city = State()
    admin_transfer = State()
    group_set_city = State()

    # تنظیمات ادمین
    adm_set_timing = State()       # ورودی کلید=مقدار برای تایم/پیام
    adm_set_photo = State()        # دریافت عکس استارت یا استاپ | menu
    adm_set_merchant = State()     # لیست سقف تجار
    adm_set_buff = State()         # باف پیش‌فرض
    adm_set_price = State()        # قیمت خرید/فروش تجار
    adm_set_asset_text = State()   # متن دارایی شهر
    adm_set_asset_city = State()   # تایید شهر برای دارایی
    adm_set_leader_side = State()  # انتخاب ساید برای لیدر

    # لشکرکشی
    camp_origin = State()
    camp_dest = State()
    camp_stats = State()
    camp_time = State()
    camp_confirm = State()

    # محاصره و اعلان جنگ (فرم مشترک)
    order_target = State()
    order_stats = State()
    order_confirm = State()

    # بیانیه
    ann_media = State()
    ann_confirm = State()

    # تجارت با بازیکن
    trade_origin = State()
    trade_dest = State()
    trade_mtype = State()
    trade_route = State()
    trade_guard = State()
    trade_recv = State()
    trade_send = State()
    trade_time = State()
    trade_confirm = State()
    # کمین کاروان
    trade_ambush_stats = State()
    trade_ambush_confirm = State()

    # تجارت با تجار
    mtrade_mode = State()   # buy | sell
    mtrade_list = State()
    mtrade_buff = State()
    mtrade_confirm = State()

    # مشاهده دارایی لیدر
    asset_view_menu = State()

    # مشاور ارتقا — چت کوتاه سلیقه/پلن (حداکثر ۲ پیام)
    advise_pref = State()

    # دکمه‌های پست لشکرکشی در کانال
    ambush_stats = State()
    ambush_confirm = State()
    redirect_target = State()
    redirect_time = State()
    redirect_confirm = State()
    back_time = State()
    back_confirm = State()


# ======================================================================
#                              کیبوردها (شیشه‌ای / رنگی)
# ======================================================================
def _btn(text, callback_data, style=None):
    """دکمه اینلاین؛ در صورت پشتیبانی API، style رنگی (primary/success/danger)."""
    kwargs = {"text": text, "callback_data": callback_data}
    if style:
        try:
            return types.InlineKeyboardButton(**kwargs, style=style)
        except TypeError:
            pass
    return types.InlineKeyboardButton(**kwargs)


def get_main_menu_keyboard(user_id=None):
    """منوی اصلی — ۴ بخش: نظامی · اقتصادی · تجارت · بیانیه"""
    builder = InlineKeyboardBuilder()
    builder.row(_btn("⚔️ منوی نظامی", "menu:military", "danger"))
    builder.row(_btn("💰 منوی اقتصادی", "menu:economy", "success"))
    builder.row(
        _btn("🐪 تجارت", "menu:trade", "primary"),
        _btn("📜 بیانیه", "menu:statement", "primary"),
    )
    builder.row(_btn("🔙 بستن منو", "menu:close"))
    return builder.as_markup()


def get_military_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(_btn("⚔️ لشکرکشی", "menu:campaign", "danger"))
    builder.row(
        _btn("🛡️ اعلان جنگ", "menu:war", "danger"),
        _btn("🏰 محاصره", "menu:siege", "primary"),
    )
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    return builder.as_markup()


def get_economy_menu_keyboard(user_id=None):
    """منوی اقتصادی کامل — دارایی · ارتقا · مشاور · قفل · ویرایش · راهنما"""
    builder = InlineKeyboardBuilder()
    builder.row(_btn("📦 مشاهده دارایی", "menu:assets", "primary"))
    if user_id and (is_leader(user_id) or is_admin(user_id) or is_player(user_id)):
        builder.row(
            _btn("⬆️ ارتقا", "menu:upgrade", "success"),
            _btn("🧠 مشاور", "menu:advise", "success"),
        )
        builder.row(
            _btn("🔓 بازکردن قفل", "eco:unlock", "primary"),
            _btn("📜 تغییرات اخیر", "eco:changes"),
        )
        builder.row(
            _btn("🗡 اقتدار / مشروعیت", "eco:politics", "primary"),
            _btn("🎛 باف/نرف آپ", "eco:buffpick", "primary"),
        )
    if user_id and is_admin(user_id):
        builder.row(_btn("✏️ ویرایش دارایی", "menu:asset_edit", "danger"))
    builder.row(_btn("❓ راهنما", "eco:help"), _btn("🔙 بازگشت", "menu:home"))
    return builder.as_markup()


# بخش‌های ارتقا برای منوی سلسله‌مراتبی
UPGRADE_SECTIONS = {
    "econ": ("💰 اقتصادی", ["خزانه", "تجارتخانه", "بندر", "آشپزخانه", "دهکده", "انبار"]),
    "prod": ("🏗 تولیدی", ["چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی"]),
    "edu": ("📚 آموزشی", ["دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی", "اصطبل"]),
    "inf": ("🛡 کمپ پیاده", ["شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر"]),
    "cav": ("🐴 کمپ سواره", ["سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار"]),
    "spec": ("🌟 ویژه / توپ", ["ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین"]),
    "nav": ("⚓️ کشتی‌سازی", ["قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی"]),
}

# یونیت‌هایی که معمولاً قفل‌اند تا فناوری/هزینه
LOCKED_DEFAULT = {
    "افسر", "سواره‌نظام تفنگدار", "ویژه", "توپ سنگین", "کشتی سلطنتی",
}
# هزینه فناوری نظامی برای آنلاک (طبق قوانین)
TECH_UNLOCK_COST = {
    "افسر": 1,
    "ویژه": 2,
    "توپ سنگین": 3,
    "کشتی سلطنتی": 4,
}


def _tier_label(val, tiers):
    """از بالا به پایین؛ مرز مشترک (مثل ۴۰) به پلهٔ بالاتر می‌رود."""
    if val is None:
        return "—"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "—"
    for lo, hi, name in tiers:
        if lo <= v <= hi:
            return name
    return "—"


AUTHORITY_TIERS = [
    (80, 100, "اوج — +۲۵۰ سکه هفتگی از مردم · کاهش اثر جاسوسی"),
    (60, 80, "بالا — جان‌فشانی در جنگ"),
    (40, 60, "متوسط — حاکم قابل‌قبول"),
    (20, 40, "ضعیف — مردم منتظر جرقه شورش"),
    (0, 20, "بی‌اعتبار — خطر برکناری و شورش ارتش"),
]
LEGITIMACY_TIERS = [
    (80, 100, "مشروعیت مطلق — حمایت گسترده · خطر کودتا حداقلی"),
    (60, 80, "مشروعیت بالا — ثبات و وفاداری نیروها"),
    (40, 60, "مشروعیت متوسط — قابل قبول با ریسک بحران"),
    (20, 40, "مشروعیت ضعیف — پایه‌ها متزلزل"),
    (0, 20, "بحران مشروعیت — خطر شورش/کودتا/تجزیه"),
]


def get_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(_btn(BTN_YES, "confirm:yes", "success"), _btn(BTN_NO, "confirm:no", "danger"))
    builder.row(_btn(BTN_BACK, "confirm:back"))
    return builder.as_markup()


def get_back_keyboard():
    """ForceReply برای دریافت متن در گروه (Privacy Mode)."""
    return ForceReply(selective=True, input_field_placeholder="اینجا بنویسید… یا از منوی شهر انتخاب کنید")


def get_inline_back_row(callback_data="menu:home"):
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🔙 بازگشت", callback_data))
    return builder.as_markup()


def _city_label(name: str) -> str:
    """برچسب زیباتر شهر با ایموجی فکشن."""
    fac = country_key(name)
    flag = {
        "monarchist": "👑",
        "parliamentarian": "🏛",
        "england": "🇬🇧",
        "france": "🇫🇷",
        "ireland": "🇮🇪",
    }.get(fac, "🏙")
    # جدا کردن شهر و کشور اگر با _ باشد
    if "_" in name:
        city, country = name.rsplit("_", 1)
        city_show = city.replace("_", " ").title() if city.isascii() else city
        country_show = country.replace("_", " ").title() if country.isascii() else country
        label = f"{flag} {city_show} · {country_show}"
    else:
        label = f"{flag} {name}"
    return label if len(label) <= 40 else label[:38] + "…"


FACTION_META = {
    "monarchist": ("👑", "مونارشیست"),
    "parliamentarian": ("🏛", "پارلمانری"),
    "france": ("🇫🇷", "فرانسه"),
    "ireland": ("🇮🇪", "ایرلند"),
}


def cities_by_faction(faction=None):
    """لیست شهرها؛ اگر faction داده شود فقط همان فکشن."""
    all_c = sorted({str(v) for v in PLAYER_CODES.values()}, key=lambda s: s.lower())
    if not faction:
        return all_c
    return [c for c in all_c if country_key(c) == faction]


def get_country_keyboard(field: str):
    """مرحله ۱: انتخاب کشور برای مبدا/مقصد."""
    builder = InlineKeyboardBuilder()
    for key, (flag, title) in FACTION_META.items():
        n = len(cities_by_faction(key))
        builder.row(_btn(f"{flag} {title} ({n})", f"cityfac:{field}:{key}"))
    # شهرهای بدون فکشن شناخته‌شده
    other = [c for c in cities_by_faction() if country_key(c) not in FACTION_META]
    if other:
        builder.row(_btn(f"🏙 سایر ({len(other)})", f"cityfac:{field}:other"))
    builder.row(_btn("✍️ ورود دستی", f"citymanual:{field}", "primary"))
    builder.row(_btn("🔙 بازگشت به منو", "menu:home"))
    return builder.as_markup()


def get_cities_keyboard(field: str, faction: str = None, page: int = 0, per_page: int = 8):
    """
    منوی شهرها — اول کشور، بعد شهر همان کشور.
    اگر faction=None باشد کیبورد کشورها برمی‌گردد.
    """
    if faction is None:
        return get_country_keyboard(field)

    if faction == "other":
        cities = [c for c in cities_by_faction() if country_key(c) not in FACTION_META]
    else:
        cities = cities_by_faction(faction)

    builder = InlineKeyboardBuilder()
    if not cities:
        builder.row(_btn("❗️ شهری در این کشور نیست", "noop"))
        builder.row(_btn("🔙 انتخاب کشور", f"cityfacback:{field}"))
        return builder.as_markup()

    start = page * per_page
    chunk = cities[start:start + per_page]
    for i, name in enumerate(chunk):
        idx = start + i
        # فقط نام شهر (بدون تکرار کشور)
        if "_" in name:
            short = name.rsplit("_", 1)[0].replace("_", " ")
            short = short.title() if short.isascii() else short
        else:
            short = name
        if len(short) > 32:
            short = short[:30] + "…"
        builder.row(_btn(f"🏙 {short}", f"citypick:{field}:{faction}:{idx}"))
    nav = []
    if page > 0:
        nav.append(_btn("◀️", f"citypage:{field}:{faction}:{page - 1}"))
    total_pages = max(1, (len(cities) + per_page - 1) // per_page)
    if total_pages > 1:
        nav.append(_btn(f"{page + 1}/{total_pages}", "noop"))
    if start + per_page < len(cities):
        nav.append(_btn("▶️", f"citypage:{field}:{faction}:{page + 1}"))
    if nav:
        builder.row(*nav)
    builder.row(_btn("🔙 انتخاب کشور", f"cityfacback:{field}"))
    builder.row(_btn("✍️ ورود دستی", f"citymanual:{field}", "primary"))
    builder.row(_btn("🏠 منوی اصلی", "menu:home"))
    return builder.as_markup()


def city_by_index(idx: int, faction: str = None):
    if faction == "other":
        cities = [c for c in cities_by_faction() if country_key(c) not in FACTION_META]
    elif faction:
        cities = cities_by_faction(faction)
    else:
        cities = cities_by_faction()
    if 0 <= idx < len(cities):
        return cities[idx]
    return None


def _parse_hhmm(s: str):
    """برگرداندن (h, m) یا None."""
    m = re.fullmatch(r"(\d{1,2})[:\.](\d{1,2})", (s or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h, mi


def _mins_of_day(h, mi):
    return h * 60 + mi


_DAY_ALIASES = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "mon": 0, "monday": 0, "دوشنبه": 0,
    "tue": 1, "tuesday": 1, "سهشنبه": 1, "سه‌شنبه": 1,
    "wed": 2, "wednesday": 2, "چهارشنبه": 2,
    "thu": 3, "thursday": 3, "پنجشنبه": 3, "پنج‌شنبه": 3,
    "fri": 4, "friday": 4, "جمعه": 4,
    "sat": 5, "saturday": 5, "شنبه": 5,
    "sun": 6, "sunday": 6, "یکشنبه": 6, "یک‌شنبه": 6,
}
_DAY_FA = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")


def parse_days_setting(raw: str):
    """رشته روزها → set از weekday (۰=دوشنبه … ۶=یکشنبه). خالی = همه."""
    raw = (raw or "").strip()
    if not raw or raw in ("*", "all", "همه"):
        return None  # همه روزها
    out = set()
    for part in re.split(r"[,،/\s]+", raw):
        p = part.strip().lower().replace("‌", "")
        if not p:
            continue
        if p in _DAY_ALIASES:
            out.add(_DAY_ALIASES[p])
            continue
        # عدد مستقیم
        if p.isdigit() and 0 <= int(p) <= 6:
            out.add(int(p))
    return out or None


def format_days_setting(raw: str) -> str:
    days = parse_days_setting(raw)
    if days is None:
        return "همه روزها"
    return "، ".join(_DAY_FA[d] for d in sorted(days))


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


def is_auto_city(city: str) -> bool:
    """آیا این شهر حالت فول‌اتو (تست) دارد؟"""
    if not city:
        return False
    if AUTO_CITIES.get(city):
        return True
    cn = _norm_country_token(city)
    for k, v in AUTO_CITIES.items():
        if v and _norm_country_token(k) == cn:
            return True
    return False


def parse_player_time(raw: str, respect_window: bool = True):
    """
    ورودی زمان پلیر:
    - ساعت مطلق: 12:00 یا 12:00,14:30
    - عدد دقیقه: 45 → الان + 45 دقیقه
    اگر respect_window=True و تایم‌استاپ تنظیم شده:
      • زمان مطلق بعد از استاپ رد می‌شود
      • عدد دقیقه اگر از استاپ رد شود: تا استاپ حساب، باقی به استارت فردا به‌صورت +HH:MM
    خروجی: رشته‌ی فرمت‌شده (مثلاً 10:16 یا +20:20) یا لیست جدا با ویرگول.
    """
    raw = (raw or "").strip()
    if not raw:
        return None, "زمان خالی است."

    now = datetime.now(TZ) if TZ else datetime.now()
    start_hm = _parse_hhmm(SETTINGS.get("time_start", "08:00"))
    stop_hm = _parse_hhmm(SETTINGS.get("time_stop", "23:00"))
    parts = [p.strip() for p in raw.replace("،", ",").split(",") if p.strip()]
    out = []
    for p in parts:
        # فقط عدد = دقیقه از الان
        if re.fullmatch(r"\d{1,4}", p):
            mins = int(p)
            if mins > 24 * 60:
                return None, f"عدد «{p}» خیلی بزرگ است (حداکثر ۱۴۴۰ دقیقه)."
            if respect_window and stop_hm and start_hm:
                now_m = _mins_of_day(now.hour, now.minute)
                stop_m = _mins_of_day(*stop_hm)
                start_m = _mins_of_day(*start_hm)
                # فاصله تا استاپ (اگر الان قبل از استاپ باشیم)
                if now_m < stop_m:
                    remain_to_stop = stop_m - now_m
                    if mins <= remain_to_stop:
                        t = now + timedelta(minutes=mins)
                        out.append(t.strftime("%H:%M"))
                    else:
                        overflow = mins - remain_to_stop
                        # باقی‌مانده بعد از استارت بعدی
                        oh, om = divmod(overflow, 60)
                        out.append(f"+{oh:02d}:{om:02d}")
                else:
                    # الان بعد/مساوی استاپ → همه به استارت فردا
                    oh, om = divmod(mins, 60)
                    out.append(f"+{oh:02d}:{om:02d}")
            else:
                t = now + timedelta(minutes=mins)
                out.append(t.strftime("%H:%M"))
            continue
        # HH:MM مطلق
        hm = _parse_hhmm(p)
        if hm:
            h, mi = hm
            if respect_window and stop_hm and start_hm:
                target_m = _mins_of_day(h, mi)
                stop_m = _mins_of_day(*stop_hm)
                start_m = _mins_of_day(*start_hm)
                # رد کردن زمان‌های بعد از استاپ و قبل از استارت (خارج پنجره)
                if stop_m > start_m:
                    # پنجره معمولی: مثلاً 08:00 تا 23:00
                    if target_m > stop_m or target_m < start_m:
                        return None, (
                            f"ساعت <b>{h:02d}:{mi:02d}</b> خارج از بازه مجاز است "
                            f"(استارت <code>{SETTINGS.get('time_start')}</code> — "
                            f"استاپ <code>{SETTINGS.get('time_stop')}</code>)."
                        )
            out.append(f"{h:02d}:{mi:02d}")
            continue
        return None, f"فرمت «{p}» درست نیست. مثال: <code>12:00</code> یا <code>45</code>"
    return ", ".join(out), None


# ---------------- ارقام و لیست کالا ----------------
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(s: str) -> str:
    return (s or "").translate(_PERSIAN_DIGITS)


def _clean_item_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip(" |-~•·*_/:：")
    # نرمال املای رایج
    repl = {"اهن": "آهن", "اهَن": "آهن"}
    return repl.get(name, name)


def parse_goods_list(text: str):
    """
    پارس لیست کالا به dict نام→عدد.
    فرمتهای مجاز:
      سکه: 300
      |🪵|~| چوب | : 300
      چوب 300
    خطوط بدون عدد (تیتر) نادیده گرفته می‌شوند.
    """
    text = normalize_digits(text or "").strip()
    if not text:
        return None, "لیست خالی است."
    bag = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # رد کردن تیترهای بدون عدد خالص در انتها
        qty = None
        name = None
        # |…| نام | : عدد
        m = re.search(
            r"\|[^|\n]*\|\s*[~\-•·]?\s*\|?\s*([^|\n:：]+?)\s*\|\s*[:=：]?\s*([\d]+(?:\.\d+)?)\s*$",
            line,
        )
        if m:
            name, qty = m.group(1), m.group(2)
        if name is None:
            m = re.search(r"([^|\n:：=]{1,40}?)\s*[:=：]\s*([\d]+(?:\.\d+)?)\s*$", line)
            if m:
                name, qty = m.group(1), m.group(2)
        if name is None:
            m = re.match(r"^(.+?)\s+([\d]+(?:\.\d+)?)\s*$", line)
            if m:
                name, qty = m.group(1), m.group(2)
        if name is None or qty is None:
            # تیتر یا خط تزئینی — رد
            continue
        name = _clean_item_name(name)
        if not name or len(name) > 40:
            continue
        if re.fullmatch(r"[\W\d_]+", name):
            continue
        try:
            val = float(qty)
        except ValueError:
            continue
        if val < 0:
            return None, f"مقدار منفی برای «{e(name)}» مجاز نیست."
        bag[name] = bag.get(name, 0) + val
    if not bag:
        return None, (
            "هیچ کالایی پیدا نشد.\n"
            "مثال:\n<code>|🪵|~| چوب | : 50</code>\nیا <code>چوب: 50</code>"
        )
    return bag, None


def format_goods(bag: dict) -> str:
    if not bag:
        return "—"
    lines = []
    for k, v in bag.items():
        num = int(v) if float(v) == int(v) else v
        lines.append(f"• {k}: <b>{num}</b>")
    return "\n".join(lines)


def item_buy_price(name: str) -> float:
    pr = MERCHANT_PRICES.get(name) or MERCHANT_PRICES.get(_clean_item_name(name)) or {}
    try:
        return float(pr.get("buy", MERCHANT_BUY_PRICE))
    except (TypeError, ValueError):
        return float(MERCHANT_BUY_PRICE)


def item_sell_price(name: str) -> float:
    pr = MERCHANT_PRICES.get(name) or MERCHANT_PRICES.get(_clean_item_name(name)) or {}
    try:
        return float(pr.get("sell", MERCHANT_SELL_PRICE))
    except (TypeError, ValueError):
        return float(MERCHANT_SELL_PRICE)


def format_merchant_catalog() -> str:
    """نمایش لیست تجار با سقف و قیمت هر کالا."""
    if not MERCHANT_LIMITS:
        return "— لیست خالی —"
    lines = ["⚜️ <b>لیست تجار</b>", DIV]
    for name, lim in MERCHANT_LIMITS.items():
        buy = item_buy_price(name)
        sell = item_sell_price(name)
        lim_s = int(lim) if float(lim) == int(lim) else lim
        lines.append(
            f"• <b>{e(name)}</b> — سقف <b>{lim_s}</b> | "
            f"خرید <b>{buy:g}</b>🪙 | فروش <b>{sell:g}</b>🪙"
        )
    return "\n".join(lines)


def validate_merchant_order(order: dict, mode: str = "buy"):
    """
    چک سقف + محاسبه هزینه/درآمد با قیمت هر کالا.
    mode: buy | sell
    برمی‌گرداند (ok, errors, applied, cost)
    """
    if not MERCHANT_ENABLED:
        return False, ["تجارت با تجار فعلاً غیرفعال است."], {}, 0
    if not MERCHANT_LIMITS:
        return False, ["لیست تجار هنوز توسط ادمین تنظیم نشده است."], {}, 0
    errors = []
    applied = {}
    limit_map = {_clean_item_name(str(k)): float(v) for k, v in MERCHANT_LIMITS.items()}
    limit_lower = {k.lower(): k for k in limit_map}
    if "آهن" in limit_map and "اهن" not in limit_lower:
        limit_lower["اهن"] = "آهن"
    for name, qty in order.items():
        clean = _clean_item_name(name)
        key = limit_lower.get(clean.lower())
        if key is None:
            errors.append(f"❌ «{e(name)}» در لیست تجار نیست.")
            continue
        lim = limit_map[key]
        if qty > lim:
            errors.append(
                f"❌ «{e(key)}»: درخواست <b>{qty:g}</b> بیش از سقف <b>{lim:g}</b> "
                f"(اضافه: {(qty - lim):g})."
            )
            continue
        applied[key] = applied.get(key, 0) + qty
    if errors:
        return False, errors, applied, 0
    if not applied:
        return False, ["هیچ کالای مجازی انتخاب نشد."], {}, 0
    cost = 0.0
    for k, q in applied.items():
        unit = item_buy_price(k) if mode == "buy" else item_sell_price(k)
        cost += float(q) * unit
    cost = int(cost) if abs(cost - int(cost)) < 1e-9 else round(cost, 2)
    return True, [], applied, cost


def apply_buff(amount: float, buff_pct: float) -> float:
    """باف مثبت = افزایش مقدار دریافتی؛ منفی = کاهش."""
    return amount * (1.0 + (buff_pct or 0) / 100.0)


def apply_buff_to_order(order: dict, buff_pct: float) -> dict:
    return {k: round(apply_buff(v, buff_pct), 2) for k, v in order.items()}


def side_of_user(user_id):
    """فکشن بازیکن از روی شهر ثبت‌شده."""
    return country_key(city_of(user_id))


def is_leader(user_id):
    if is_admin(user_id):
        return True
    for ids in LEADERS.values():
        if user_id in ids:
            return True
    return False


def leader_side(user_id):
    """ساید لیدر؛ None اگر لیدر نباشد."""
    for side, ids in LEADERS.items():
        if user_id in ids:
            return side
    return None


def is_plain_player(user_id):
    """فرمانده عادی — نه ادمین، نه لیدر ساید."""
    return is_player(user_id) and not is_admin(user_id) and leader_side(user_id) is None


def resolve_player_city(user_id) -> str | None:
    """
    شهر ثبت‌شده پلیر را به کلید CITY_ASSETS / PLAYER_CODES منطبق می‌کند.
    """
    my = city_of(user_id)
    if not my or my == "ناشناس":
        return None
    mn = _norm_country_token(my)
    mb = mn.split("_")[0] if "_" in mn else mn
    # تطبیق دقیق
    for c in all_known_cities():
        cn = _norm_country_token(c)
        if cn == mn:
            return c
    # تطبیق پایه نام شهر
    for c in all_known_cities():
        cn = _norm_country_token(c)
        cb = cn.split("_")[0] if "_" in cn else cn
        if cb == mb or mb in cn or cn in mn:
            return c
    return my


def cities_of_side(side: str):
    return cities_by_faction(side)


def cities_for_side_assets(side: str):
    """
    شهرهای یک ساید برای دارایی/جمع:
    ترکیب شهرهای ثبت‌شده در PLAYER_CODES + کلیدهای CITY_ASSETS همان ساید.
    هرگز شهر ساید دیگر را برنمی‌گرداند.
    """
    if not side:
        return []
    names = set(cities_by_faction(side))
    for c in CITY_ASSETS:
        if country_key(c) == side:
            names.add(c)
    return sorted(names, key=lambda s: str(s).lower())


# ======================================================================
#                    سیستم هشدار تهدید + مشاور ارتقا
# ======================================================================
def all_known_cities():
    names = set(str(v) for v in PLAYER_CODES.values())
    names |= set(CITY_ASSETS.keys())
    for g in GROUPS.values():
        if g.get("city"):
            names.add(str(g["city"]))
    return names


def match_registered_cities(raw: str) -> list:
    """تطبیق متن مقصد/هدف با شهرهای ثبت‌شده (انگلیسی/فارسی)."""
    if not raw:
        return []
    text = str(raw).strip()
    # «آمیان از فرانسه» / «amiens from france»
    text = re.sub(r"\s+از\s+", "_", text)
    text = re.sub(r"\s+from\s+", "_", text, flags=re.I)
    norm = _norm_country_token(text)
    hits = []
    for city in all_known_cities():
        cn = _norm_country_token(city)
        base = cn.split("_")[0] if "_" in cn else cn
        if not base:
            continue
        if cn == norm or base == norm:
            hits.append(city)
            continue
        if base in norm or cn in norm:
            hits.append(city)
            continue
        # تطبیق سست روی بخش اول مقصد
        dest_base = norm.split("_")[0] if "_" in norm else norm
        if dest_base and len(dest_base) >= 3 and (dest_base in base or base in dest_base):
            hits.append(city)
    # یکتا
    seen, out = set(), []
    for c in hits:
        k = c.lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def players_of_city(city: str) -> list:
    """فرمانده‌های متصل به یک شهر."""
    if not city:
        return []
    cn = _norm_country_token(city)
    base = cn.split("_")[0] if "_" in cn else cn
    uids = []
    for uid, u in authenticated_users.items():
        if u.get("role") not in ("player", "admin"):
            continue
        uc = _norm_country_token(u.get("country") or "")
        if not uc:
            continue
        ub = uc.split("_")[0] if "_" in uc else uc
        if uc == cn or ub == base or city.lower() == (u.get("country") or "").lower():
            uids.append(uid)
    return uids


def groups_of_city(city: str) -> list:
    if not city:
        return []
    cn = _norm_country_token(city)
    base = cn.split("_")[0] if "_" in cn else cn
    gids = []
    for gid, g in GROUPS.items():
        gc = _norm_country_token(g.get("city") or "")
        gb = gc.split("_")[0] if "_" in gc else gc
        if gc == cn or gb == base:
            gids.append(gid)
    return gids


def _threat_title(kind: str) -> str:
    return {
        "campaign": "🚨 هشدار لشکرکشی به سوی شما",
        "siege": "🚨 هشدار محاصره",
        "war": "🚨 هشدار اعلان جنگ",
    }.get(kind, "🚨 هشدار نظامی")


async def notify_target_threat(
    kind: str,
    attacker_id: int,
    attacker_city: str,
    target_raw: str,
    origin: str = "",
    extra: str = "",
    action_id: str = "",
):
    """
    پس از ثبت لشکرکشی/محاصره/جنگ، به فرمانده و گروه شهر هدف هشدار می‌دهد.
    """
    matched = match_registered_cities(target_raw)
    if not matched:
        logging.info("threat: no city match for %r", target_raw)
        return
    title = _threat_title(kind)
    who = mention(attacker_id, attacker_city or "فرمانده")
    notified_uids, notified_gids = set(), set()
    for city in matched:
        body = (
            f"{title}\n{DIV}\n"
            f"🏙 شهر هدف: <b>{e(city)}</b>\n"
            f"📝 مقصد ثبت‌شده: <code>{e(target_raw)}</code>\n"
            f"👑 مهاجم: {who}\n"
            f"📍 مبدأ: <b>{e(origin or attacker_city or '—')}</b>\n"
        )
        if extra:
            body += f"{extra}\n"
        body += (
            f"\n⚠️ آماده دفاع شوید. آمار مهاجم در کانال اصلی اعلام شده است."
            + (f"\n🆔 اکشن: <code>{action_id}</code>" if action_id else "")
        )
        builder = InlineKeyboardBuilder()
        builder.row(_btn("✅ دریافت شد", f"alert_ack:{action_id or 'x'}", "success"))
        builder.row(_btn("📦 دارایی شهر", "menu:assets", "primary"))
        markup = builder.as_markup()

        for uid in players_of_city(city):
            if uid == attacker_id or uid in notified_uids:
                continue
            notified_uids.add(uid)
            try:
                await bot.send_message(chat_id=uid, text=body, reply_markup=markup)
                await asyncio.sleep(0.04)
            except Exception:
                logging.exception("threat dm to %s failed", uid)

        for gid in groups_of_city(city):
            if gid in notified_gids:
                continue
            notified_gids.add(gid)
            try:
                await bot.send_message(chat_id=gid, text=body, reply_markup=markup)
                await asyncio.sleep(0.05)
            except Exception:
                logging.exception("threat group %s failed", gid)

    if notified_uids or notified_gids:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 هشدار تهدید ارسال شد.\n"
                f"🎯 {e(target_raw)} → {', '.join(e(c) for c in matched)}\n"
                f"👤 DM: {len(notified_uids)} · 👥 گروه: {len(notified_gids)}",
                disable_notification=True,
            )
        except Exception:
            pass


@dp.callback_query(F.data.startswith("alert_ack:"))
async def handle_alert_ack(callback: types.CallbackQuery):
    await callback.answer("ثبت شد — هوشیار بمانید.", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ---- مشاور ارتقا (محلی + xAI) — هزینه‌ها از قوانین رسمی خاکستر جنگ ----
# هر مورد: هزینه سکه + مواد + بازدهی هر سطح
UPGRADE_TABLE = {
    "خزانه": {"coin": 1500, "wood": 25, "stone": 50, "iron": 25, "pop": 50, "yield": 1000, "yunit": "سکه", "max": 20},
    "تجارتخانه": {"coin": 700, "wood": 50, "pop": 25, "yield": 150, "yunit": "سکه", "max": 15, "limit": "۳۰۰۰ سکه / ۳۰۰ منبع"},
    "بندر": {"coin": 1000, "wood": 50, "iron": 50, "pop": 50, "yield": 500, "yunit": "سکه", "max": 20, "limit": "۱۵ کشتی"},
    "آشپزخانه": {"coin": 600, "stone": 50, "pop": 50, "yield": 500, "yunit": "غذا", "max": 25},
    "دهکده": {"coin": 400, "wood": 25, "stone": 25, "yield": 100, "yunit": "نفر", "max": 40},
    "چوب بری": {"coin": 500, "stone": 50, "pop": 25, "yield": 100, "yunit": "چوب", "max": 10},
    "معدن سنگ": {"coin": 600, "wood": 50, "pop": 25, "yield": 100, "yunit": "سنگ", "max": 10},
    "معدن آهن": {"coin": 600, "wood": 25, "stone": 25, "pop": 25, "yield": 100, "yunit": "آهن", "max": 10},
    "پوشاک سازی": {"coin": 700, "wood": 25, "pop": 50, "yield": 100, "yunit": "پوشاک", "max": 10},
    "باروت سازی": {"coin": 800, "stone": 50, "iron": 25, "pop": 50, "yield": 100, "yunit": "باروت", "max": 10},
    "انبار": {"coin": 500, "stone": 25, "pop": 25, "yield": 500, "yunit": "ظرفیت", "max": 99},
    "دانشکده افسری": {"coin": 600, "yield": 5, "yunit": "فناوری نظامی"},
    "مجمع نخبگان": {"coin": 700, "yield": 2, "yunit": "فناوری اقتصادی"},
    "دانشگاه پزشکی": {"coin": 800, "yield": 3, "yunit": "فناوری پزشکی"},
    "اصطبل": {"coin": 400, "wood": 50, "yield": 100, "yunit": "اسب"},
    "شبه نظامی": {"coin": 500, "wood": 50, "pop": 50, "cloth": 25, "yield": 150, "yunit": "نفر", "max": 10},
    "شمشیرزن": {"coin": 600, "iron": 60, "pop": 60, "cloth": 50, "yield": 100, "yunit": "نفر", "max": 10},
    "نیزه دار": {"coin": 700, "wood": 70, "pop": 70, "cloth": 50, "yield": 75, "yunit": "نفر", "max": 10},
    "رایفلدار": {"coin": 800, "powder": 80, "pop": 80, "cloth": 50, "yield": 50, "yunit": "نفر", "max": 10},
    "افسر": {"coin": 600, "wood": 60, "pop": 60, "cloth": 25, "yield": 25, "yunit": "نفر", "max": 10},
    "سواره نظام شمشیرزن": {"coin": 500, "wood": 50, "pop": 50, "horse": 100, "yield": 150, "yunit": "نفر", "max": 10},
    "سواره‌نظام زره پوش": {"coin": 600, "iron": 60, "pop": 60, "cloth": 50, "horse": 100, "yield": 100, "yunit": "نفر", "max": 10},
    "سواره‌نظام تفنگدار": {"coin": 700, "powder": 70, "pop": 70, "cloth": 50, "horse": 100, "yield": 50, "yunit": "نفر", "max": 10},
    "ویژه": {"coin": 900, "wood": 100, "pop": 100, "cloth": 50, "powder": 100, "yield": 50, "yunit": "نفر", "max": 10},
    "توپ سبک": {"coin": 700, "powder": 70, "iron": 50, "pop": 50, "yield": 8, "yunit": "عراده", "max": 10},
    "توپ محاصره": {"coin": 800, "powder": 80, "iron": 60, "pop": 60, "yield": 4, "yunit": "عراده", "max": 10},
    "توپ سنگین": {"coin": 900, "powder": 90, "iron": 70, "pop": 70, "yield": 2, "yunit": "عراده", "max": 10},
    "قایق": {"coin": 500, "pop": 60, "cloth": 25, "iron": 40, "yield": 5, "yunit": "فروند", "max": 10},
    "کشتی جنگی": {"coin": 600, "pop": 60, "cloth": 25, "iron": 40, "powder": 50, "yield": 3, "yunit": "فروند", "max": 10},
    "ناو جنگی": {"coin": 700, "pop": 70, "cloth": 50, "iron": 40, "powder": 60, "yield": 2, "yunit": "فروند", "max": 10},
    "کشتی سلطنتی": {"coin": 800, "pop": 80, "cloth": 50, "iron": 60, "powder": 80, "yield": 1, "yunit": "فروند", "max": 10},
}

# مصرف غذا (قوانین)
# جمعیت/کارگر/مهندس: مبنا · پیاده ۱ · سواره ۲ · ویژه ۳
FOOD_PER = {"inf": 1, "cav": 2, "elite": 3}


def _fmt_upgrade_cost(name: str) -> str:
    t = UPGRADE_TABLE.get(name) or {}
    if not t:
        return "—"
    parts = [f"{t.get('coin', 0)} سکه"]
    for k, lab in (
        ("wood", "چوب"), ("stone", "سنگ"), ("iron", "آهن"),
        ("pop", "نفر"), ("cloth", "پوشاک"), ("powder", "باروت"), ("horse", "اسب"),
    ):
        if t.get(k):
            parts.append(f"{t[k]} {lab}")
    y = t.get("yield")
    yu = t.get("yunit", "")
    out = " + ".join(parts)
    if y is not None:
        out += f" → بازده +{y} {yu}/سطح"
    if t.get("max"):
        out += f" (مکس {t['max']})"
    return out


def _can_afford(bag: dict, name: str) -> bool:
    t = UPGRADE_TABLE.get(name) or {}
    if not t:
        return False
    coins = float(bag.get("سکه") or 0)
    if coins < t.get("coin", 0):
        return False
    checks = [
        ("wood", "چوب"), ("stone", "سنگ"), ("iron", "آهن"),
        ("cloth", "پوشاک"), ("powder", "باروت"),
    ]
    for key, lab in checks:
        need = t.get(key, 0)
        if not need:
            continue
        have = float(bag.get(lab) or bag.get("اهن" if lab == "آهن" else lab) or 0)
        if have < need:
            return False
    return True


def local_upgrade_advice(city: str, bag: dict) -> str:
    """تحلیل هزینه/بازده طبق قوانین رسمی خاکستر جنگ."""
    bag = normalize_stats_keys(bag or {})
    coins = float(bag.get("سکه") or 0)
    food = float(bag.get("غذا") or 0)
    pop = float(bag.get("جمعیت") or 0)
    wood = float(bag.get("چوب") or 0)
    iron = float(bag.get("آهن") or bag.get("اهن") or 0)
    stone = float(bag.get("سنگ") or 0)
    powder = float(bag.get("باروت") or 0)
    cloth = float(bag.get("پوشاک") or 0)
    authority = float(bag.get("اقتدار") or 40)

    prod = {
        "چوب بری": float(bag.get("چوب بری") or 0),
        "معدن سنگ": float(bag.get("معدن سنگ") or 0),
        "معدن آهن": float(bag.get("معدن آهن") or 0),
        "باروت سازی": float(bag.get("باروت سازی") or 0),
        "پوشاک سازی": float(bag.get("پوشاک سازی") or 0),
    }
    inf_units = {
        "شبه نظامی": float(bag.get("شبه نظامی") or 0),
        "شمشیرزن": float(bag.get("شمشیرزن") or 0),
        "نیزه دار": float(bag.get("نیزه دار") or bag.get("نیزه‌دار") or 0),
        "رایفلدار": float(bag.get("رایفلدار") or 0),
        "افسر": float(bag.get("افسر") or 0),
    }
    cav_units = {
        "سواره نظام شمشیرزن": float(bag.get("سواره نظام شمشیرزن") or bag.get("سواره‌نظام شمشیرزن") or 0),
        "سواره‌نظام زره پوش": float(bag.get("سواره‌نظام زره پوش") or bag.get("سواره نظام زره پوش") or 0),
        "سواره‌نظام تفنگدار": float(bag.get("سواره‌نظام تفنگدار") or bag.get("سواره نظام تفنگدار") or 0),
    }
    infantry = sum(inf_units.values()) + float(bag.get("سربازان") or 0)
    cavalry = sum(cav_units.values()) + float(bag.get("کیوراسیرها") or 0)
    elite = float(bag.get("کیوراسیرها") or 0) + float(bag.get("رایفلداران مدرن") or 0)
    arty = sum(float(bag.get(k) or 0) for k in ("توپ سبک", "توپ سنگین", "توپ محاصره", "توپ خمپاره ای"))
    navy = sum(float(bag.get(k) or 0) for k in ("قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی", "کشتی خط شکن"))

    # مصرف غذا تقریبی هفته‌ای (قوانین)
    food_need = pop + infantry * FOOD_PER["inf"] + cavalry * FOOD_PER["cav"] + elite * FOOD_PER["elite"]

    tips = []

    # اقتدار
    if authority < 20:
        tips.append((
            "👑 اقتدار بحرانی (۰–۲۰)",
            "مردم خواهان برکناری‌اند و در ارتش شورش محتمل است.",
            "اولویت: رول مردمی/پاداش نظامی · پیروزی کوچک · جلوگیری از باخت پی‌درپی",
        ))
    elif authority < 40:
        tips.append((
            "👑 اقتدار شکننده (۲۰–۴۰)",
            "مردم منتظر جرقه شورش‌اند؛ روحیه ارتش پایین.",
            "پاداش مردم‌پسند + رول اجتماعی · هزینه کم · بازده ثبات داخلی",
        ))

    # خزانه
    if coins < UPGRADE_TABLE["خزانه"]["coin"]:
        tips.append((
            "💰 نقدینگی برای ارتقای خزانه کافی نیست",
            f"برای ۱ سطح خزانه نیاز به {_fmt_upgrade_cost('خزانه')}.",
            "فروش مازاد به تجار (دوشنبه) یا تمرکز بازدهی بندر/تجارتخانه",
        ))
    elif coins >= 1500 and float(bag.get("بازدهی خزانه") or 0) < 2000:
        ok = "✅" if _can_afford(bag, "خزانه") else "⚠️ مواد کم"
        tips.append((
            f"🏦 ارتقای خزانه {ok}",
            f"هزینه: {_fmt_upgrade_cost('خزانه')}",
            "بازده پایدار سکه — اولویت اقتصادی بلندمدت",
        ))

    # غذا
    if food_need > 0 and food < food_need * 1.5:
        ok = "✅" if _can_afford(bag, "آشپزخانه") else "⚠️"
        tips.append((
            f"🍽 فشار غذایی {ok}",
            f"مصرف تقریبی نیرو+جمعیت ≈ {food_need:g} · موجودی غذا: {food:g}",
            f"ارتقای آشپزخانه: {_fmt_upgrade_cost('آشپزخانه')} · در محاصره مصرف×۲ است",
        ))

    # تولید ضعیف
    for pname, pval in sorted(prod.items(), key=lambda x: x[1]):
        if pval >= 200:
            continue
        t = UPGRADE_TABLE.get(pname, {})
        if not t:
            continue
        afford = _can_afford(bag, pname)
        tips.append((
            f"🏗 {pname} ضعیف (≈{pval:g})",
            f"هزینه ۱ سطح: {_fmt_upgrade_cost(pname)} · {'موجودی کافی' if afford else 'کمبود منابع/سکه'}",
            f"بازده +{t.get('yield', 100)} {t.get('yunit', '')}/سطح · مکس لول {t.get('max', 10)}",
        ))
        break  # فقط ضعیف‌ترین

    if iron < 150 and (infantry > 400 or arty > 0):
        tips.append((
            "🔩 کمبود آهن",
            f"موجودی آهن {iron:g} — ارتش/توپ وابسته به آهن است.",
            f"معدن آهن: {_fmt_upgrade_cost('معدن آهن')}",
        ))
    if powder < 80 and (arty > 0 or inf_units.get("رایفلدار", 0) > 50):
        tips.append((
            "💥 کمبود باروت",
            f"باروت {powder:g} برای رایفل/توپ کافی نیست.",
            f"باروت‌سازی: {_fmt_upgrade_cost('باروت سازی')}",
        ))

    # نظامی — نسبت‌ها
    if infantry > 300 and cavalry < max(50, infantry * 0.12):
        tips.append((
            "🐴 کمبود سواره",
            f"پیاده≈{infantry:g} · سواره≈{cavalry:g}",
            f"کمپ سواره شمشیرزن: {_fmt_upgrade_cost('سواره نظام شمشیرزن')}",
        ))
    if arty == 0 and infantry >= 500:
        tips.append((
            "🧨 نبود توپخانه",
            "برای محاصره حداقل ۵۰۰ نیرو + ۵ ادوات لازم است (قوانین).",
            f"توپ سبک: {_fmt_upgrade_cost('توپ سبک')} · یا توپ محاصره: {_fmt_upgrade_cost('توپ محاصره')}",
        ))
    if navy == 0:
        tips.append((
            "⚓️ ناوگان خالی",
            "بدون کشتی، لشکرکشی/تجارت دریایی محدود است. ظرفیت بندر: ۱۵ کشتی.",
            f"قایق: {_fmt_upgrade_cost('قایق')} · کشتی جنگی: {_fmt_upgrade_cost('کشتی جنگی')}",
        ))

    # تقویم بازی
    tips.append((
        "📅 یادآوری تقویم",
        "تجارت پلیر: شنبه–یکشنبه · تجار: دوشنبه · ارتقا/ساخت: سه‌شنبه–چهارشنبه · آپ: پنجشنبه–جمعه (ممنوع نظامی).",
        "فرم ارتقا را فقط در روز مجاز بفرستید.",
    ))

    if not any(t[0].startswith(("💰", "🏦", "🍽", "🏗", "🔩", "💥", "🐴", "🧨", "⚓️", "👑")) for t in tips[:-1]):
        tips.insert(0, (
            "✅ وضعیت نسبتاً پایدار",
            "کمبود بحرانی دیده نشد.",
            "تمرکز: فناوری (دانشکده/نخبگان) و ذخیره باروت–آهن",
        ))

    lines = [
        f"🧠 <b>مشاور ارتقا — {e(city)}</b>",
        f"<i>طبق قوانین رسمی خاکستر جنگ · هزینه و بازده واقعی</i>",
        DIV,
        f"💰 سکه <b>{coins:g}</b> · 🍽 غذا <b>{food:g}</b> · 👥 جمعیت <b>{pop:g}</b>",
        f"🛡 پیاده≈<b>{infantry:g}</b> · 🐴 سواره≈<b>{cavalry:g}</b> · 🧨 توپ≈<b>{arty:g}</b> · ⚓️ ناو≈<b>{navy:g}</b>",
        f"👑 اقتدار: <b>{authority:g}</b> · مصرف‌غذای تقریبی: <b>{food_need:g}</b>",
        "",
    ]
    for i, (title, why, advise) in enumerate(tips[:7], 1):
        lines.append(f"<b>{i}. {title}</b>\n{why}\n➡️ {advise}\n")
    lines.append(
        f"{DIV}\n"
        "<i>تحلیل محلی بر اساس جدول ارتقای رسمی. با XAI_API_KEY تحلیل Grok هم اضافه می‌شود.</i>"
    )
    return "\n".join(lines)


_RULES_DIGEST = (
    "بازی خاکستر جنگ (۱۶۴۰). بازی شنبه تا چهارشنبه. ارتقا سه‌شنبه و چهارشنبه. "
    "تجارت پلیر شنبه‌یکشنبه، تجار دوشنبه. آپ بعد استاپ چهارشنبه. "
    "محاصره: حداقل ۵۰۰ نیرو + ۵ ادوات؛ مصرف غله ×۲. نبرد حداقل ۳۰۰ نفر. "
    "کمین ۱۰۰–۲۰۰ نیرو و ۳–۶ ادوات. پیش‌قراول ۱۵۰–۳۰۰ نیرو و ۴–۸ ادوات. "
    "اقتدار پیش‌فرض ۴۰؛ ۰–۲۰ بی‌اعتبار، ۸۰–۱۰۰ مالیات مردمی ۲۵۰س. "
    "مشروعیت: ۰–۲۰ بحران، ۸۰–۱۰۰ مطلق. غذا: پیاده۱ سواره۲ ویژه۳. "
    "فناوری نظامی آنلاک: افسر۱ ویژه۲ توپ‌سنگین۳ کشتی‌سلطنتی۴. "
    "خزانه ۱۵۰۰س → +۱۰۰۰ سکه. تولیدی‌ها لول‌مکس ۱۰."
)


# منابع قابل‌مصرف برای محاسبه هزینه چندسطحی
_RES_MAP = (
    ("coin", "سکه"),
    ("wood", "چوب"),
    ("stone", "سنگ"),
    ("iron", "آهن"),
    ("pop", "جمعیت"),
    ("cloth", "پوشاک"),
    ("powder", "باروت"),
    ("horse", "اسب"),
)


def _bag_stock(bag: dict) -> dict:
    bag = normalize_stats_keys(bag or {})
    return {
        "coin": float(bag.get("سکه") or 0),
        "wood": float(bag.get("چوب") or 0),
        "stone": float(bag.get("سنگ") or 0),
        "iron": float(bag.get("آهن") or bag.get("اهن") or 0),
        "pop": float(bag.get("جمعیت") or 0),
        "cloth": float(bag.get("پوشاک") or 0),
        "powder": float(bag.get("باروت") or 0),
        "horse": float(bag.get("اسب") or 0),
    }


def cost_for_levels(name: str, levels: int) -> dict:
    """هزینه N سطح (هر سطح همان هزینه ثابت جدول قوانین)."""
    t = UPGRADE_TABLE.get(name) or {}
    levels = max(1, min(int(levels or 1), int(t.get("max") or 10)))
    out = {}
    for key, _lab in _RES_MAP:
        v = int(t.get(key) or 0) * levels
        if v:
            out[key] = v
    out["_levels"] = levels
    out["_yield_total"] = (t.get("yield") or 0) * levels
    out["_yunit"] = t.get("yunit", "")
    out["_max"] = t.get("max") or 10
    return out


def format_cost_dict(cd: dict) -> str:
    parts = []
    for key, lab in _RES_MAP:
        if cd.get(key):
            parts.append(f"{cd[key]} {lab}")
    return " + ".join(parts) if parts else "—"


def max_affordable_levels(name: str, stock: dict) -> int:
    """حداکثر سطحی که با موجودی فعلی قابل پرداخت است."""
    t = UPGRADE_TABLE.get(name) or {}
    if not t:
        return 0
    mx = int(t.get("max") or 10)
    lim = mx
    for key, _lab in _RES_MAP:
        unit = int(t.get(key) or 0)
        if unit <= 0:
            continue
        have = float(stock.get(key) or 0)
        lim = min(lim, int(have // unit))
    return max(0, lim)


def guess_current_level(name: str, bag: dict, sheet: str = "") -> int | None:
    """حدس لول فعلی از شیت یا از بازده نسبی."""
    t = UPGRADE_TABLE.get(name) or {}
    y_unit = t.get("yield") or 0
    if sheet:
        # الگو: چوب بری | (3) : 300
        pat = re.compile(
            re.escape(name).replace("\\ ", r"\s*") + r"[^\n]{0,40}?\((\d+)\)",
            re.I,
        )
        m = pat.search(sheet)
        if m:
            return int(m.group(1))
    if y_unit and name in (bag or {}):
        val = float(bag.get(name) or 0)
        if val > 0:
            return max(1, int(round(val / y_unit)))
    return None


def parse_upgrade_requests(notes: str) -> list:
    """
    از متن پلیر درخواست‌ها را می‌خواند.
    مثال: «بندر ۳ لول»، «خزانه را ۲ تا ببر»، «چوب بری و معدن آهن»
    """
    if not notes:
        return []
    text = notes
    found = []
    # نام‌ها از طولانی به کوتاه تا تداخل کمتر شود
    names = sorted(UPGRADE_TABLE.keys(), key=len, reverse=True)
    for name in names:
        if name not in text and name.replace("‌", "") not in text.replace("‌", ""):
            # جستجوی ساده‌تر بدون نیم‌فاصله
            if name.replace(" ", "") not in text.replace(" ", "").replace("‌", ""):
                continue
        # سطح خواسته‌شده کنار نام
        levels = 1
        m = re.search(
            rf"{re.escape(name)}[^\d]{{0,12}}(\d+)\s*(?:لول|سطح|تا|level)?",
            text,
            re.I,
        )
        if not m:
            m = re.search(
                rf"(\d+)\s*(?:لول|سطح)?[^\n]{{0,12}}{re.escape(name)}",
                text,
                re.I,
            )
        if m:
            try:
                levels = max(1, min(10, int(m.group(1))))
            except ValueError:
                levels = 1
        found.append({"name": name, "levels": levels})
    # یکتا
    seen, out = set(), []
    for f in found:
        if f["name"] in seen:
            continue
        seen.add(f["name"])
        out.append(f)
    return out


def _mode_candidates(mode: str, bag: dict) -> list:
    """لیست نام ساختمان‌های مرتبط با نوع مشاور + اولویت."""
    bag = normalize_stats_keys(bag or {})
    cand = []
    prod = ["چوب بری", "معدن سنگ", "معدن آهن", "باروت سازی", "پوشاک سازی"]
    weak = sorted(prod, key=lambda n: float(bag.get(n) or 0))

    if mode in ("econ", "balance", "chat"):
        cand += ["خزانه", "تجارتخانه", "آشپزخانه", "دهکده", "انبار"] + weak
    if mode in ("mil", "land", "balance", "chat"):
        cand += ["شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
                 "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "توپ سبک", "توپ محاصره"]
    if mode in ("naval", "balance", "chat"):
        cand += ["بندر", "قایق", "کشتی جنگی", "ناو جنگی"]
    if mode == "land":
        cand += ["نیزه دار", "توپ محاصره", "توپ سنگین"]
    # یکتا با حفظ ترتیب
    seen, out = set(), []
    for n in cand:
        if n in UPGRADE_TABLE and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _roi_score(name: str, levels: int, mode: str) -> float:
    """امتیاز بازده تقریبی برای اولویت‌بندی."""
    t = UPGRADE_TABLE.get(name) or {}
    y = float(t.get("yield") or 1) * levels
    coin_cost = max(1, int(t.get("coin") or 1) * levels)
    base = y / coin_cost * 1000
    boost = {
        "econ": {"خزانه": 1.4, "چوب بری": 1.2, "معدن آهن": 1.25, "آشپزخانه": 1.15, "تجارتخانه": 1.1},
        "mil": {"توپ سبک": 1.4, "شمشیرزن": 1.2, "رایفلدار": 1.25, "سواره نظام شمشیرزن": 1.2},
        "land": {"توپ محاصره": 1.5, "نیزه دار": 1.2, "شمشیرزن": 1.15},
        "naval": {"کشتی جنگی": 1.4, "بندر": 1.3, "ناو جنگی": 1.35, "قایق": 1.1},
        "balance": {"خزانه": 1.2, "بندر": 1.15, "توپ سبک": 1.15, "معدن آهن": 1.1},
        "chat": {},
    }.get(mode, {})
    return base * boost.get(name, 1.0)


def build_optimal_plan(
    bag: dict,
    mode: str = "balance",
    notes: str = "",
    sheet: str = "",
    city: str = "",
    seed: int = 0,
) -> list:
    """
    بهترین پلن با منابع محدود.
    - درخواست صریح پلیر را اولویت می‌دهد
    - تا ۳ لول روی یک ساختمان اگر بودجه اجازه دهد
    - برای هر شهر/پلیر کمی متنوع (seed)
    دارایی را تغییر نمی‌دهد — فقط محاسبه.
    """
    stock = _bag_stock(bag)
    requests = parse_upgrade_requests(notes)
    plan = []

    def try_add(name, levels, forced=False):
        nonlocal stock
        t = UPGRADE_TABLE.get(name)
        if not t:
            return False
        mx = int(t.get("max") or 10)
        cur = guess_current_level(name, bag, sheet)
        # سقف تا مکس لول
        if cur is not None:
            levels = min(levels, max(0, mx - cur))
        levels = max(0, min(levels, mx))
        if levels <= 0:
            return False
        # اگر forced نیست، تا حد قابل‌پرداخت کم کن
        aff = max_affordable_levels(name, stock)
        if aff <= 0:
            return False
        if not forced:
            levels = min(levels, aff)
        else:
            # forced: اگر کامل نمی‌شود، حداکثر ممکن
            levels = min(levels, aff) if aff else 0
        if levels <= 0:
            return False
        cd = cost_for_levels(name, levels)
        # کم کردن از موجودی مجازی
        for key, _ in _RES_MAP:
            need = cd.get(key, 0)
            if need:
                stock[key] = float(stock.get(key) or 0) - need
        from_lv = cur if cur is not None else "?"
        to_lv = (cur + levels) if cur is not None else f"?+{levels}"
        y_each = t.get("yield") or 0
        y_final = f"+{y_each * levels} {t.get('yunit', '')} (هر سطح +{y_each})"
        plan.append({
            "name": name,
            "from_lv": from_lv,
            "to_lv": to_lv,
            "levels": levels,
            "cost": format_cost_dict(cd),
            "cost_dict": cd,
            "yield_final": y_final,
            "reason": "درخواست شما" if forced else "بهینه منابع",
            "score": _roi_score(name, levels, mode),
        })
        return True

    # ۱) درخواست‌های صریح پلیر
    for req in requests:
        try_add(req["name"], req.get("levels") or 1, forced=True)

    # ۲) پیشنهاد خودکار تا پر شدن بودجه معنادار
    cands = _mode_candidates(mode, bag)
    # تنوع بر اساس seed (شهر + حالت)
    if seed:
        cands = cands[seed % max(1, len(cands)):] + cands[: seed % max(1, len(cands))]
    already = {p["name"] for p in plan}
    for name in cands:
        if name in already:
            continue
        if len(plan) >= 4:
            break
        aff = max_affordable_levels(name, stock)
        if aff <= 0:
            continue
        # چند سطح؟ ۱ تا ۳ بر اساس ROI و موجودی
        best_l, best_s = 1, -1
        for L in range(1, min(3, aff) + 1):
            sc = _roi_score(name, L, mode)
            # جریمه جزئی برای قفل کردن بودجه زیاد
            sc -= L * 0.02
            if sc > best_s:
                best_s, best_l = sc, L
        # ساختمان‌های حیاتی ضعیف → تا ۳ لول
        if name in ("چوب بری", "معدن آهن", "باروت سازی", "خزانه", "بندر") and aff >= 2:
            if float(bag.get(name) or 0) < 200 or name in ("خزانه", "بندر"):
                best_l = min(3, aff)
        try_add(name, best_l, forced=False)
        already.add(name)

    # اگر هیچی نتوانست: حداقل ۱ سطح ارزان‌ترین
    if not plan:
        cheap = sorted(
            UPGRADE_TABLE.items(),
            key=lambda kv: int(kv[1].get("coin") or 9999),
        )
        for name, _t in cheap:
            if try_add(name, 1):
                break
    return plan


def format_plan_summary(plan: list, bag: dict) -> str:
    stock = _bag_stock(bag)
    lines = [
        "📊 <b>موجودی قابل‌مصرف (قبل از ارتقا)</b>",
        f"💰 {stock['coin']:g} · 🪵 {stock['wood']:g} · 🪨 {stock['stone']:g} · 🔩 {stock['iron']:g}",
        f"🧥 {stock['cloth']:g} · 💥 {stock['powder']:g} · 👥 {stock['pop']:g}",
        "",
        "🧩 <b>بهترین پلن با منابع محدود</b> <i>(فقط پیشنهاد — دارایی تغییر نمی‌کند)</i>",
        DIV,
    ]
    total = {k: 0 for k, _ in _RES_MAP}
    for i, p in enumerate(plan, 1):
        lines.append(
            f"<b>{i}. {e(p['name'])}</b> · {p['from_lv']} → <b>{p['to_lv']}</b> "
            f"({p['levels']} سطح)\n"
            f"   🧮 {e(p['cost'])}\n"
            f"   ◻️ {e(p['yield_final'])}\n"
            f"   <i>{e(p.get('reason') or '')}</i>"
        )
        for k, _ in _RES_MAP:
            total[k] += int((p.get("cost_dict") or {}).get(k) or 0)
    cost_txt = format_cost_dict({k: v for k, v in total.items() if v})
    lines.append(f"\n{DIV}\nΣ هزینه کل پلن: <b>{e(cost_txt)}</b>")
    remain = []
    for key, lab in _RES_MAP:
        left = float(stock.get(key) or 0) - total.get(key, 0)
        if stock.get(key) or total.get(key):
            remain.append(f"{lab} {left:g}")
    if remain:
        lines.append("پس از اجرا (فرضی): " + " · ".join(remain))
    return "\n".join(lines)


def build_upgrade_forms(suggestions: list) -> str:
    if not suggestions:
        return ""
    blocks = [
        "📋 <b>فرم‌های ارتقا</b> — از لول = <i>لول کنونی</i> · به لول = <i>لول دلخواه</i>",
        DIV,
    ]
    for s in suggestions:
        form = UPGRADE_FORM_TEMPLATE.format(
            name=s.get("name", "—"),
            from_lv=s.get("from_lv", "?"),
            to_lv=s.get("to_lv", "?"),
            cost=s.get("cost", "—"),
            yield_final=s.get("yield_final", "—"),
        )
        blocks.append(f"<pre>{e(form)}</pre>")
    return "\n\n".join(blocks)


def local_upgrade_advice_mode(
    city: str,
    bag: dict,
    mode: str = "balance",
    notes: str = "",
    sheet: str = "",
    user_id: int = 0,
) -> str:
    """تحلیل + پلن بهینه منابع + فرم‌های چندسطحی."""
    mode_meta = ADVISE_MODES.get(mode, ADVISE_MODES["balance"])
    seed = (hash((city or "") + mode) + int(user_id or 0)) % 97
    plan = build_optimal_plan(bag, mode=mode, notes=notes, sheet=sheet, city=city, seed=seed)

    header = (
        f"🧠 <b>مشاور حرفه‌ای ارتقا — {e(city)}</b>\n"
        f"🎯 نوع: {mode_meta[0]} <b>{mode_meta[1]}</b>\n"
    )
    if notes:
        header += f"📝 درخواست/پلن: <i>{e(notes[:450])}</i>\n"
    header += (
        f"{DIV}\n"
        f"<i>از لول = لول کنونی · به لول = لول هدف · هزینه = مجموع سطوح</i>\n\n"
    )

    # نکات کلی (کوتاه)
    tips = local_upgrade_advice(city, bag)
    # فقط ۳ خط اول آمار از tips
    tip_lines = tips.split("\n")[:8]
    summary = format_plan_summary(plan, bag)
    forms = build_upgrade_forms(plan)

    extras = []
    if plan:
        max_one = max(plan, key=lambda p: p.get("levels", 1))
        if max_one.get("levels", 1) >= 2:
            extras.append(
                f"💡 روی <b>{e(max_one['name'])}</b> ارتقای "
                f"<b>{max_one['levels']}</b> سطحی پیشنهاد شد (بودجه اجازه داد)."
            )
    if notes and not parse_upgrade_requests(notes):
        extras.append(
            "ℹ️ در پیام‌تان نام ساختمان مشخص نبود؛ پلن خودکار چیده شد. "
            "مثال: «بندر را ۳ لول ببر و خزانه ۲ لول»"
        )

    return (
        header
        + "\n".join(tip_lines)
        + "\n\n"
        + summary
        + ("\n" + "\n".join(extras) if extras else "")
        + "\n\n"
        + forms
    )


async def xai_upgrade_advice(
    city: str,
    bag: dict,
    sheet_excerpt: str = "",
    mode: str = "balance",
    notes: str = "",
    plan: list | None = None,
) -> str | None:
    if not XAI_API_KEY:
        return None
    stats_txt = format_stats_labeled(bag) if bag else "—"
    mode_fa = ADVISE_MODES.get(mode, ADVISE_MODES["balance"])[1]
    plan_txt = ""
    if plan:
        for p in plan:
            plan_txt += (
                f"- {p['name']}: از {p['from_lv']} به {p['to_lv']} | "
                f"هزینه {p['cost']} | بازده {p['yield_final']}\n"
            )
    prompt = (
        "تو مشاور ارشد ارتقای بازی «خاکستر جنگ» هستی. "
        f"تمرکز: {mode_fa}. "
        "پلن محاسبه‌شده زیر را بررسی کن، اگر بهتر می‌شود اصلاح کن، و برای هر مورد "
        "فرم را با قالب زیر بده. از لول=لول کنونی، به لول=لول هدف. "
        "می‌توانی ۲ یا ۳ سطح یکجا پیشنهاد بدهی اگر بودجه برسد. "
        "دارایی را تغییر نده — فقط پیشنهاد. فارسی رسمی مختصر.\n\n"
        "قالب:\n#فرم_ارتقا\n🏢نام ساختمان:\n🔹از لول:\n🔹به لول:\n🧮هزینه ارتقا:\n◻️بازدهی نهایی:\n\n"
        f"قوانین:\n{_RULES_DIGEST}\n\n"
        f"شهر: {city}\nآمار:\n{stats_txt}\n\n"
        f"پلن موتور محلی:\n{plan_txt or '—'}\n"
    )
    if notes:
        prompt += f"\nدرخواست بازیکن:\n{notes[:600]}\n"
    if sheet_excerpt:
        prompt += f"\nگزیده شیت:\n{sheet_excerpt[:800]}"
    body = {
        "model": XAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ashes of War senior upgrade planner. "
                    "Output optimized multi-level plans and filled #فرم_ارتقا. "
                    "Never invent costs; use provided table. Persian."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 1200,
    }
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.x.ai/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {XAI_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=55) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = (data["choices"][0]["message"]["content"] or "").strip()
        return f"🤖 <b>بازنگری Grok — {e(city)}</b> · {e(mode_fa)}\n{DIV}\n{e(content)}"
    except Exception:
        logging.exception("xAI upgrade advice failed")
        return None


async def build_upgrade_advice(
    city: str,
    mode: str = "balance",
    notes: str = "",
    user_id: int = 0,
) -> str:
    bag = normalize_stats_keys(get_city_asset_stats(city))
    sheet = get_city_asset_text(city) or ""
    seed = (hash((city or "") + mode) + int(user_id or 0)) % 97
    plan = build_optimal_plan(bag, mode=mode, notes=notes, sheet=sheet, city=city, seed=seed)
    local = local_upgrade_advice_mode(
        city, bag, mode=mode, notes=notes, sheet=sheet, user_id=user_id,
    )
    ai = await xai_upgrade_advice(city, bag, sheet, mode=mode, notes=notes, plan=plan)
    if ai:
        return f"{local}\n\n{DIV}\n{ai}"
    return local


# برچسب‌هایی که در جمع قلمرو نباید بیایند (توضیحی / غیرعددی)
_ASSET_SKIP_LABELS = {
    "", "-", "—", "0", "ظرفیت", "محدودیت", "باف", "نرف", "باف ویژه",
    "نام شخصیت", "نام جناج", "نام جناح",
}
_ASSET_SKIP_SUBSTR = ("باف", "نرف", "ظرفیت", "محدودیت")


# تشخیص بخش شیت VIP برای نام‌گذاری درست موجودی/بازدهی
_SECTION_RULES = [
    # (کلمات کلیدی در خط عنوان، نام بخش)
    (("خزانه",), "treasury"),
    (("آشپزخانه", "اشپزخانه"), "kitchen"),
    (("دهکده",), "village"),
    (("بندر",), "port"),
    (("انبار",), "warehouse"),
    (("کارگاه تولیدی", "چوب بری", "معدن"), "workshop"),
    (("پادگان", "پیاده‌نظام", "سواره‌نظام", "توپخانه", "ناوگان"), "army"),
    (("قلعه",), "castle"),
    (("تجارت خانه", "تجارتخانه"), "tradehouse"),
]


def _detect_section(line: str, current: str) -> str:
    low = line.replace(" ", "").replace("\u200c", "")
    for keys, sec in _SECTION_RULES:
        if any(k in low or k in line for k in keys):
            return sec
    return current


def _contextual_label(label: str, section: str) -> str | None:
    """
    موجودی/بازدهی عمومی را بر اساس بخش شیت نام‌گذاری می‌کند:
      خزانه → سکه / بازدهی خزانه
      آشپزخانه → غذا
      دهکده → رعیت
      بندر → بازدهی بندر
    بقیه برچسب‌ها (چوب، سرباز، …) همان‌اند.
    """
    lab = label.strip()
    lab_n = lab.replace(" ", "").replace("\u200c", "")
    if lab_n in ("موجودی", "موجودیخزانه"):
        if section == "treasury":
            return "سکه"
        if section == "kitchen":
            return "غذا"
        if section == "warehouse":
            return "موجودی انبار"
        return f"موجودی ({section or '?'})"
    if lab_n in ("بازدهی",):
        if section == "treasury":
            return "بازدهی خزانه"
        if section == "village":
            return "جمعیت"  # دهکده = همان جمعیت/رعیت
        if section == "port":
            return "بازدهی بندر"
        if section == "kitchen":
            return "بازدهی آشپزخانه"
        if section == "tradehouse":
            return "بازدهی تجارت‌خانه"
        return f"بازدهی ({section or '?'})"
    # جمعیت و رعیت یکی هستند
    if lab_n in ("جمعیت", "رعیت"):
        return "جمعیت"
    if lab_n.startswith("تعدادسرباز") or lab_n in ("تعدادسربازان", "سربازان"):
        return "سربازان"
    return lab


def normalize_stats_keys(bag: dict) -> dict:
    """ادغام کلیدهای هم‌معنی (مثل جمعیت+رعیت) قبل از نمایش/جمع."""
    if not bag:
        return {}
    out = {}
    merge = {"رعیت": "جمعیت", "اهن": "آهن"}
    for k, v in bag.items():
        key = merge.get(k, k)
        out[key] = out.get(key, 0) + float(v)
    return {k: (int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)) for k, v in out.items()}


def extract_asset_stats(text: str) -> dict:
    """
    استخراج اعداد از شیت VIP با درک بخش‌ها.
    متن خام را تغییر نمی‌دهد.
    """
    text = normalize_digits(text or "")
    stats = {}
    section = ""
    line_pat = re.compile(
        r"\|\s*([^|%{}]+?)\s*\|\s*(?:\([^)]*\))?\s*[:=：]\s*([\d]+(?:\.\d+)?)\s*$"
    )
    plain_pat = re.compile(
        r"^\s*([^\n|:=：%{}]{1,40}?)\s*[:=：]\s*([\d]+(?:\.\d+)?)\s*$"
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # عنوان بخش (بدون عدد خالص در انتها)
        if not line_pat.search(line) and ("﴿" in line or "🏦" in line or "🍽" in line
                                          or "🛖" in line or "⚓️" in line or "🏗" in line
                                          or "📦" in line or "🏰" in line or "🛡" in line
                                          or "خزانه" in line or "آشپزخانه" in line
                                          or "دهکده" in line or "بندر" in line
                                          or "انبار" in line):
            section = _detect_section(line, section)
            continue
        section = _detect_section(line, section)

        if "%" in line:
            continue
        # ظرفیت 1500/1500
        if re.search(r"\d+\s*/\s*\d+", line):
            continue

        m = line_pat.search(line)
        if not m:
            m = plain_pat.match(line)
        if not m:
            continue
        label = re.sub(r"\s+", " ", m.group(1)).strip(" |-~•·*_/:：")
        label = _clean_item_name(label) if label else ""
        if not label or len(label) > 40:
            continue
        if label in _ASSET_SKIP_LABELS:
            continue
        if any(s in label for s in _ASSET_SKIP_SUBSTR):
            continue
        if re.fullmatch(r"[\W\d_]+", label):
            continue
        try:
            qty = float(m.group(2))
        except ValueError:
            continue
        final = _contextual_label(label, section)
        if not final:
            continue
        stats[final] = stats.get(final, 0) + qty
    return {k: (int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)) for k, v in stats.items()}


def get_city_asset_text(city: str) -> str:
    """متن کامل شیت — بدون هیچ ویرایش."""
    entry = CITY_ASSETS.get(city) or {}
    if isinstance(entry, dict) and "text" in entry:
        return entry.get("text") or ""
    if isinstance(entry, dict):
        return format_goods(entry)
    return ""


def get_city_asset_stats(city: str) -> dict:
    entry = CITY_ASSETS.get(city) or {}
    if isinstance(entry, dict) and "stats" in entry:
        return dict(entry.get("stats") or {})
    if isinstance(entry, dict) and "text" not in entry:
        out = {}
        for k, v in entry.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    return {}


def set_city_asset(city: str, text: str):
    """
    متن کامل را عیناً ذخیره می‌کند (هیچ کاراکتری عوض نمی‌شود).
    فقط یک دیکشنری stats جدا برای جمع قلمرو ساخته می‌شود.
    """
    text = text if text is not None else ""
    # فقط trim ابتدا/انتهای کل پیام — داخل شیت دست نمی‌زنیم
    if text.startswith("\n"):
        text = text.lstrip("\n")
    text = text.rstrip()
    stats = extract_asset_stats(text)
    prev = CITY_ASSETS.get(city) or {}
    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "unlocked": list(prev.get("unlocked") or []),
        "changes": list(prev.get("changes") or []),
    }
    return stats


def sum_realm_assets(side: str = None):
    """
    جمع عددی دارایی فقط همان ساید (اگر side داده شود).
    شهرهای ساید دیگر هرگز وارد جمع نمی‌شوند.
    """
    total = {}
    for city in list(CITY_ASSETS.keys()):
        ck = country_key(city)
        if side:
            if ck != side:
                continue
        elif not ck:
            continue
        for name, qty in normalize_stats_keys(get_city_asset_stats(city)).items():
            total[name] = total.get(name, 0) + float(qty)
    return normalize_stats_keys(total)


def realm_breakdown(side: str):
    """
    (total, by_city, city_list) — فقط شهرهای همان ساید.
    by_city: فقط شهرهایی که دارایی ثبت‌شده دارند.
    """
    by_city = {}
    total = {}
    city_list = cities_for_side_assets(side) if side else []
    for city in city_list:
        if country_key(city) != side:
            continue
        if city not in CITY_ASSETS:
            continue
        st = normalize_stats_keys(get_city_asset_stats(city))
        by_city[city] = st
        for name, qty in st.items():
            total[name] = total.get(name, 0) + float(qty)
    return normalize_stats_keys(total), by_city, city_list


# گروه‌بندی نمایش اعداد استخراج‌شده — جلوی هر بخش معنی مشخص است
_STATS_SECTIONS = [
    ("👤 شخصیت / جمعیت", (
        "اقتدار", "مشروعیت", "جمعیت", "رعیت", "سربازان", "پوینت", "پوئن",
    )),
    ("🏦 خزانه (سکه)", (
        "سکه", "بازدهی خزانه",
    )),
    ("🍽 آشپزخانه (غذا)", (
        "غذا", "بازدهی آشپزخانه",
    )),
    ("⚓️ بندر", (
        "بازدهی بندر",
    )),
    ("🏬 تجارت‌خانه", (
        "بازدهی تجارت‌خانه",
    )),
    ("📦 انبار منابع", (
        "چوب", "آهن", "اهن", "سنگ", "پوشاک", "باروت", "موجودی انبار",
    )),
    ("🏗 تولید / کارگاه", (
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
    )),
    ("🛡 پیاده‌نظام", (
        "شبه نظامی", "شمشیرزن", "نیزه دار", "نیزه‌دار", "رایفلدار", "افسر",
    )),
    ("🐴 سواره‌نظام", (
        "سواره نظام شمشیرزن", "سواره‌نظام شمشیرزن",
        "سواره‌نظام زره پوش", "سواره نظام زره پوش",
        "سواره‌نظام تفنگدار", "سواره نظام تفنگدار",
    )),
    ("🌟 ویژه", (
        "کشتی خط شکن", "کیوراسیرها", "رایفلداران مدرن",
    )),
    ("🧨 توپخانه", (
        "توپ سبک", "توپ سنگین", "توپ محاصره", "توپ خمپاره ای",
    )),
    ("⚓️ ناوگان", (
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
    )),
]


# کلیدهای امتیازدهی لیدربورد — مطابق شیت VIP
# اقتصادی: موجودی خزانه ×۵ · تولید کارگاه ×۲ · منابع/غذا/جمعیت
# نظامی: پیاده / سواره / ویژه / توپ (با ضریب)
# دریایی: ناوگان
_LB_ECON = (
    "سکه", "بازدهی خزانه", "غذا", "بازدهی آشپزخانه", "جمعیت",
    "بازدهی بندر", "بازدهی تجارت‌خانه",
    "چوب", "آهن", "اهن", "سنگ", "پوشاک", "باروت", "موجودی انبار",
    "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
)
_LB_MIL = (
    "سربازان", "شبه نظامی", "شمشیرزن", "نیزه دار", "نیزه‌دار", "رایفلدار", "افسر",
    "سواره نظام شمشیرزن", "سواره‌نظام شمشیرزن",
    "سواره‌نظام زره پوش", "سواره نظام زره پوش",
    "سواره‌نظام تفنگدار", "سواره نظام تفنگدار",
    "کیوراسیرها", "رایفلداران مدرن",
    "توپ سبک", "توپ سنگین", "توپ محاصره", "توپ خمپاره ای",
)
_LB_NAV = (
    "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی", "کشتی خط شکن",
)
# ضرایب: خزانه×۵ · تولید×۲ · پیاده/سواره/توپ/ناوگان
_LB_WEIGHT = {
    # اقتصادی
    "سکه": 5,              # موجودی خزانه
    "بازدهی خزانه": 2,
    "غذا": 1, "بازدهی آشپزخانه": 1, "جمعیت": 1,
    "بازدهی بندر": 1, "بازدهی تجارت‌خانه": 1,
    "چوب": 1, "آهن": 1, "اهن": 1, "سنگ": 1, "پوشاک": 1, "باروت": 1, "موجودی انبار": 1,
    "چوب بری": 2, "معدن سنگ": 2, "معدن آهن": 2, "پوشاک سازی": 2, "باروت سازی": 2,  # لول/خروجی تولید
    # نظامی — پیاده‌نظام
    "شبه نظامی": 1, "شمشیرزن": 1.5, "نیزه دار": 1.5, "نیزه‌دار": 1.5,
    "رایفلدار": 2, "افسر": 5, "سربازان": 0.5,
    # نظامی — سواره‌نظام
    "سواره نظام شمشیرزن": 3, "سواره‌نظام شمشیرزن": 3,
    "سواره‌نظام زره پوش": 4, "سواره نظام زره پوش": 4,
    "سواره‌نظام تفنگدار": 4, "سواره نظام تفنگدار": 4,
    "کیوراسیرها": 5, "رایفلداران مدرن": 3,
    # نظامی — توپخانه
    "توپ سبک": 10, "توپ سنگین": 15, "توپ محاصره": 20, "توپ خمپاره ای": 12,
    # دریایی — ناوگان
    "قایق": 5, "کشتی جنگی": 15, "ناو جنگی": 25, "کشتی سلطنتی": 40, "کشتی خط شکن": 20,
}


def _score_bag(bag: dict, keys: tuple) -> float:
    total = 0.0
    for k in keys:
        if k not in bag:
            continue
        w = _LB_WEIGHT.get(k, 1.0)
        total += float(bag[k]) * w
    return total


def city_power_scores(city: str) -> dict:
    """امتیاز اقتصادی / نظامی / دریایی یک شهر."""
    bag = normalize_stats_keys(get_city_asset_stats(city))
    return {
        "econ": round(_score_bag(bag, _LB_ECON), 1),
        "mil": round(_score_bag(bag, _LB_MIL), 1),
        "nav": round(_score_bag(bag, _LB_NAV), 1),
        "bag": bag,
    }


def _lb_rows(scope: str, category: str):
    """لیست رتبه‌بندی‌شده [(label, flag, scores_dict), ...]"""
    if scope == "side":
        rows = []
        for side in FACTIONS:
            total, _, _ = realm_breakdown(side)
            scores = {
                "econ": round(_score_bag(total, _LB_ECON), 1),
                "mil": round(_score_bag(total, _LB_MIL), 1),
                "nav": round(_score_bag(total, _LB_NAV), 1),
            }
            scores["total"] = scores["econ"] + scores["mil"] + scores["nav"]
            flag, title = FACTION_META.get(side, ("", side))
            rows.append((title, flag, scores))
    else:
        rows = []
        for city in list(CITY_ASSETS.keys()):
            sc = city_power_scores(city)
            sc["total"] = sc["econ"] + sc["mil"] + sc["nav"]
            flag = FACTION_META.get(country_key(city) or "", ("", ""))[0]
            rows.append((city, flag, sc))
    key = "total" if category == "all" else category
    rows.sort(key=lambda r: r[2].get(key, 0), reverse=True)
    return rows


def format_leaderboard(scope: str = "city", category: str = "all", announce: bool = False) -> str:
    """
    scope: city | side
    category: all | econ | mil | nav
    announce: متن رسمی برای کانال
    """
    medals = ("🥇", "🥈", "🥉")
    cat_fa = {"all": "کل قدرت", "econ": "اقتصادی", "mil": "نظامی", "nav": "دریایی"}[category]
    scope_fa = "سایدها" if scope == "side" else "شهرها"
    rows = _lb_rows(scope, category)
    if not rows:
        return "📭 هنوز دارایی ثبت نشده."

    if announce:
        # متن‌های قابل تنظیم از SETTINGS (ادمین می‌نویسد)
        default_intros = {
            "all": (
                "⚔️ در سایهٔ جنگ داخلی، ترازوی قدرت دوباره سنجیده شد.\n"
                "نه با فریاد میدان، که با سنگینی خزانه، صف نیرو و بادبان‌ها."
            ),
            "econ": "💰 در عصر آشوب، ثروت همان تیغی‌ست که بی‌صدا می‌برد.",
            "mil": "🛡 آهن سخن می‌گوید؛ پیاده، سواره و توپخانه رتبه می‌سازند.",
            "nav": "⚓️ دریا پادشاهی بی‌تاج است؛ هر بادبان پیامی از قدرت.",
        }
        intro_key = {"all": "lb_intro_all", "econ": "lb_intro_econ", "mil": "lb_intro_mil", "nav": "lb_intro_nav"}
        intro = (SETTINGS.get(intro_key.get(category, "lb_intro_all")) or "").strip() or default_intros.get(category, default_intros["all"])
        place_words = (
            SETTINGS.get("lb_place_1") or "در صدر ایستاده است",
            SETTINGS.get("lb_place_2") or "پس از او می‌درخشد",
            SETTINGS.get("lb_place_3") or "رتبهٔ سوم را از آن خود کرده",
            SETTINGS.get("lb_place_mid") or "در ردیف‌های میانی قدرت جای گرفته",
            SETTINGS.get("lb_place_low") or "هنوز در سایهٔ بزرگان می‌جنگد",
        )
        footer = (SETTINGS.get("lb_footer") or "").strip() or (
            "جنگ داخلی انگلیس آینهٔ قدرت است؛ رتبه امروز، سرنوشت فرداست."
        )
        lines = [
            f"🏆 <b>اعلامیهٔ لیدربورد — {scope_fa}</b>",
            f"📜 محور: <b>{cat_fa}</b>",
            DIV,
            intro,
            "",
        ]
        limit = 8 if scope == "city" else len(rows)
        for i, (name, flag, sc) in enumerate(rows[:limit]):
            m = medals[i] if i < 3 else f"▫️ {i + 1}."
            if i < 3:
                verb = place_words[i]
            elif i < 5:
                verb = place_words[3]
            else:
                verb = place_words[4]
            # پشتیبانی {rank} {name} در متن جایگاه
            verb = verb.replace("{rank}", str(i + 1)).replace("{name}", name)
            lines.append(f"{m} {flag}<b>{e(name)}</b> — {verb}.")
        if scope == "city" and len(rows) > limit:
            lines.append("\n… و دیگر شهرها در پردهٔ تاریخ انتظار می‌کشند.")
        lines.append(f"\n{DIV}\n<i>{e(footer)}</i>\n#لیدربورد")
        return "\n".join(lines)

    lines = [f"🏆 <b>لیدربورد {scope_fa}</b> — {cat_fa}", DIV]
    limit = 15 if scope == "city" else len(rows)
    for i, (name, flag, sc) in enumerate(rows[:limit]):
        m = medals[i] if i < 3 else f"{i+1}."
        lines.append(
            f"{m} {flag}<b>{e(name)}</b>\n"
            f"   💰 {sc['econ']:g} · ⚔️ {sc['mil']:g} · ⚓️ {sc['nav']:g}"
            + (f" · Σ {sc['total']:g}" if category == "all" else "")
        )
    if scope == "city" and len(rows) > limit:
        lines.append(f"\n… و {len(rows) - limit} شهر دیگر")
    return "\n".join(lines)


def format_stats_labeled(bag: dict) -> str:
    """
    اعداد استخراج‌شده را بخش‌بندی می‌کند و جلوی هر بخش معنی می‌نویسد.
    اقلام ناشناس در انتها زیر «سایر» می‌آیند.
    """
    bag = normalize_stats_keys(bag or {})
    if not bag:
        return "— عددی نیست —"
    used = set()
    lines = []
    for title, keys in _STATS_SECTIONS:
        rows = []
        for k in keys:
            if k in bag:
                v = bag[k]
                num = int(v) if float(v) == int(float(v)) else v
                rows.append(f"  • {k}: <b>{num}</b>")
                used.add(k)
        # تطبیق بدون حساسیت به فاصله/ی
        for k, v in bag.items():
            if k in used:
                continue
            kn = k.replace("\u200c", "").replace(" ", "")
            for key in keys:
                if kn == key.replace("\u200c", "").replace(" ", ""):
                    num = int(v) if float(v) == int(float(v)) else v
                    rows.append(f"  • {k}: <b>{num}</b>")
                    used.add(k)
                    break
        if rows:
            lines.append(f"<b>{title}</b>")
            lines.extend(rows)
    other = []
    for k, v in bag.items():
        if k in used:
            continue
        num = int(v) if float(v) == int(float(v)) else v
        other.append(f"  • {k}: <b>{num}</b>")
    if other:
        lines.append("<b>📋 سایر</b>")
        lines.extend(other)
    return "\n".join(lines) if lines else "— عددی نیست —"


def format_assets_block(title: str, bag: dict) -> str:
    body = format_stats_labeled(bag) if bag else "— خالی —"
    return f"📦 <b>{e(title)}</b>\n{DIV}\n{body}"


def format_realm_view(side: str) -> str:
    """
    دارایی کل قلمرو — فقط یک پیام جمع‌زده (بدون شیت تک‌تک شهرها).
    """
    flag, title = FACTION_META.get(side, ("", side or "?"))
    total, by_city, city_list = realm_breakdown(side)
    n_reg = len(by_city)
    n_all = len(city_list)
    lines = [
        f"🌐 <b>دارایی کل قلمرو {flag}{title}</b>",
        f"<i>جمع تخمینی از {n_reg} شهر ثبت‌شده (از {n_all} شهر ساید)</i>",
        DIV,
        format_stats_labeled(total) if total else "— هنوز دارایی‌ای برای جمع ثبت نشده —",
    ]
    return "\n".join(lines)


def format_city_asset_view(city: str) -> str:
    """دارایی شخصی یک شهر: متن کامل شیت ثبت‌شده."""
    side = country_key(city)
    flag, title = FACTION_META.get(side, ("", side or "؟")) if side else ("", "؟")
    text = get_city_asset_text(city)
    header = f"📦 <b>دارایی شخصی — {e(city)}</b>\n🏴 ساید: {flag}{title}\n{DIV}\n"
    if not text:
        return header + "— برای این شهر هنوز دارایی ثبت نشده —"
    return header + text


async def send_trade_reports(public_report: str, full_report: str):
    """
    گزارش تجارت:
    - کانال گزارش + ادمین اصلی ← public_report یا full
    - ادمین دارایی ← full_report کامل
    """
    await send_report(full_report)
    if ASSET_ADMIN_ID and ASSET_ADMIN_ID != ADMIN_ID:
        try:
            await bot.send_message(chat_id=ASSET_ADMIN_ID, text=full_report)
        except Exception:
            logging.exception("ارسال گزارش تجارت به ادمین دارایی ناموفق بود.")


def get_admin_inline_keyboard():
    """منوی ادمین فشرده."""
    builder = InlineKeyboardBuilder()
    builder.row(_btn("📨 ارسال پیام", "adm_msg", "primary"))
    builder.row(
        _btn("⏰ تایم‌استارت/استاپ", "adm_timing", "success"),
        _btn("🛒 لیست تجار", "adm_merchant", "primary"),
    )
    builder.row(
        _btn("👑 لیدرها", "adm_leaders"),
        _btn("📦 دارایی", "adm_assets"),
    )
    builder.row(
        _btn("🏆 لیدربورد", "adm_leaderboard", "success"),
        _btn("📊 آمار شهرها", "adm_stats"),
    )
    builder.row(
        _btn("🤖 شهرهای اتو", "adm_auto", "success"),
        _btn("♻️ اجرای آپ", "adm_run_up", "primary"),
    )
    builder.row(
        _btn("🏙 واگذاری شهر", "adm_transfer", "danger"),
        _btn("🖼 عکس منو", "adm_photo:menu", "primary"),
    )
    builder.row(_btn("⚙️ مدیریت", "adm_manage"), _btn("📢 پیام آپدیت گروه‌ها", "adm_send_update"))
    builder.row(_btn("📋 وضعیت", "adm_report"), _btn("❓ راهنما", "adm_help"))
    builder.row(_btn("🚪 خروج", "adm_logout", "danger"))
    return builder.as_markup()


ADMIN_HELP_TEXT = (
    f"⚡️ <b>راهنمای پنل ادمین</b>\n{DIV}\n\n"
    "<b>در گروه ادمینی / پی‌وی:</b>\n"
    "• <code>ADMIN</code> — باز کردن پنل\n"
    "• <code>/set admin</code> یا <code>ست ادمین</code> — دادن ادمین (ریپلای)\n"
    "• <code>ست ادمین دارایی</code> — ریپلای روی کاربر برای گزارش تجارت\n"
    "• <code>ست لیدر انگلیس</code> / <code>/set leader france</code> — ریپلای\n\n"
    "<b>در گروه شهر:</b>\n"
    "• <code>/start</code> — ست گپ / اتصال شهر\n"
    "• <code>/set player</code> یا <code>ست پلیر</code> — تعیین فرمانده (ریپلای)\n"
    "• <code>ست دارایی</code> — ثبت دارایی همین شهر (ادمین)\n"
    "• <code>/ثبت تغییر دارایی</code> — بروزرسانی دارایی + جمع قلمرو\n"
    "• <code>استعلام گپ</code> — شهر + آیدی پلیر + حذف\n\n"
    "<b>پنل شیشه‌ای:</b>\n"
    "• 📨 پیام — همگانی / ترتیبی / انتخابی / خصوصی\n"
    "• ⏰ تایم استارت/استاپ + پیام‌ها + موارد مجاز\n"
    "• 🛒 لیست تجار + سقف هر کالا + باف\n"
    "• 👑 لیدر ساید (حداکثر ۳ نفر)\n"
    "• 📦 مشاهده/مدیریت دارایی\n\n"
    f"🆔 کانال اصلی: <code>{CHANNEL_ID}</code>\n"
    f"🆔 کانال گزارش: <code>{REPORT_CHANNEL_ID or '—'}</code>\n"
    f"🆔 کانال توییت: <code>{TWEET_CHANNEL_ID or '—'}</code>\n"
    f"👤 ادمین دارایی: <code>{ASSET_ADMIN_ID or '—'}</code>"
)


def get_manage_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🏙 حذف شهر / کد", "adm_del_city_list", "danger"))
    builder.row(_btn("❌ حذف دسترسی بازیکن", "adm_revoke_list", "danger"))
    builder.row(_btn("➕ افزودن شهر و ساخت کد", "adm_add_city", "success"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    return builder.as_markup()


def get_channel_buttons(action_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="🪓 کمین", callback_data=f"chan_ambush:{action_id}")
    builder.button(text="🔄 تغییر مسیر", callback_data=f"chan_redir:{action_id}")
    builder.button(text="🔙 بک", callback_data=f"chan_back:{action_id}")
    builder.adjust(3)
    return builder.as_markup()


def get_trade_channel_buttons(action_id):
    """دکمه کمین مخصوص کاروان تجاری."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🪓 کمین به کاروان", callback_data=f"chan_trade_ambush:{action_id}")
    return builder.as_markup()


def get_trade_mtype_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("🏕 زمینی", "trademtype:land", "success"),
        _btn("⚓ دریایی", "trademtype:sea", "primary"),
    )
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    return builder.as_markup()


def get_cancel_button(kind, action_id):
    builder = InlineKeyboardBuilder()
    prefix = "chan_cancelsiege" if kind == "siege" else "chan_cancelwar"
    builder.button(text="❌ لغو دستور (۱۰ دقیقه)", callback_data=f"{prefix}:{action_id}")
    return builder.as_markup()


def get_type_keyboard(kind):
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn(MTYPE_BUTTONS["sea"], f"mtype:{kind}:sea", "primary"),
        _btn(MTYPE_BUTTONS["land"], f"mtype:{kind}:land", "success"),
    )
    builder.row(_btn("🔙 بازگشت", "mtype:back"))
    return builder.as_markup()


# ======================================================================
#                          هسته احراز هویت
# ======================================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    if is_group_chat(message):
        return await group_start(message, state)
    await state.clear()
    user_id = message.from_user.id
    user_data = authenticated_users.get(user_id)
    if user_data:
        if user_data["role"] == "admin":
            await message.answer("⚡️ سلام رئیس! به پنل مدیریت شیشه‌ای خوش آمدید.", reply_markup=get_admin_inline_keyboard())
        else:
            await go_menu(message, state)
    else:
        await message.answer("⚔️ سلام فرمانده! به بازی <b>خاکستر جنگ</b> خوش آمدید.\n\n🔑 لطفاً <b>کد ورود اختصاصی</b> شهر خود را ارسال کنید:")
        await state.set_state(GameStates.waiting_for_code)


@dp.message(Command("backup"))
async def cmd_backup(message: types.Message):
    """ادمین: پشتیبان فوری بگیر و پین کن."""
    if not is_admin(message.from_user.id):
        return
    try:
        await push_backup()
        await message.answer(
            f"✅ پشتیبان گرفته شد و در چت پشتیبان ارسال/به‌روز شد.\n"
            f"🏙 {len(PLAYER_CODES)} · 👤 {len(all_players)} · 👥 {len(GROUPS)}\n"
            f"پیام <code>{BACKUP_NAME}</code> را <b>پین</b> نگه دارید."
        )
    except Exception as ex:
        logging.exception("cmd_backup")
        await message.answer(f"❌ پشتیبان ناموفق: <code>{e(str(ex)[:200])}</code>")


@dp.message(Command("restore"))
async def cmd_restore(message: types.Message):
    """ادمین: /restore را با فایل aof_data.json بفرست یا ریپلای روی فایل."""
    if not is_admin(message.from_user.id):
        return
    doc = None
    if message.document:
        doc = message.document
    elif message.reply_to_message and message.reply_to_message.document:
        doc = message.reply_to_message.document
    if not doc:
        return await message.answer(
            "📥 فایل <code>aof_data.json</code> را ضمیمه کنید یا روی همان فایل ریپلای کنید و "
            "<code>/restore</code> بزنید.\n"
            "همچنین می‌توانید فقط فایل را بدون دستور برای ربات بفرستید."
        )
    ok, info = await restore_from_document(doc)
    if ok:
        await message.answer(f"✅ بازیابی موفق.\n{info}")
    else:
        await message.answer(f"❌ بازیابی ناموفق.\n{info}")


@dp.message(F.document, F.chat.type == "private")
async def admin_document_restore(message: types.Message, state: FSMContext):
    """اگر ادمین در پی‌وی فایل json پشتیبان بفرستد → بازیابی."""
    if not is_admin(message.from_user.id):
        return
    if not message.document:
        return
    fname = (message.document.file_name or "").lower()
    if not (fname.endswith(".json") or fname == BACKUP_NAME.lower()):
        return
    # اگر وسط فرم دیگری است دست نزن
    st = await state.get_state()
    if st and st not in (None, GameStates.main_menu.state):
        return
    ok, info = await restore_from_document(message.document)
    if ok:
        await message.answer(
            f"✅ داده از فایل بازیابی شد.\n{info}\n"
            f"برای اطمینان <code>/backup</code> بزنید تا پین به‌روز شود.",
            reply_markup=get_admin_inline_keyboard(),
        )
    else:
        await message.answer(f"❌ {info}")


# ---------------- ثبت گروه به‌جای پی‌وی («ست گپ» / «ست پلیر») ----------------
async def group_start(message: types.Message, state: FSMContext):
    if is_player(message.from_user.id):
        return await go_menu(message, state)
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    grp = GROUPS.get(message.chat.id)
    builder = InlineKeyboardBuilder()
    if grp:
        builder.button(text="🔄 تغییر شهر گروه", callback_data="grp_setcity")
        text = (
            f"🏙 این گروه به شهر <b>{e(grp['city'])}</b> متصل است.\n\n"
            "برای تعیین یا تغییر فرمانده‌ی این گروه، روی پیام او ریپلای کرده و بنویسید: <code>ست پلیر</code> یا <code>/set player</code>"
        )
    else:
        builder.button(text="🏙 ست گپ", callback_data="grp_setcity")
        text = "این گروه هنوز به هیچ شهری متصل نیست."
    await message.answer(text, reply_markup=builder.as_markup())


@dp.callback_query(F.data == "grp_setcity")
async def handle_group_setcity(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id) or not is_group_chat(callback.message):
        return await callback.answer()
    await callback.answer()
    if not PLAYER_CODES:
        seed_default_cities()
        save_data(critical=True)
    await state.set_state(GameStates.group_set_city)
    await callback.message.answer(
        "🏙 <b>ست گپ</b> — اول کشور را انتخاب کنید، بعد شهر:\n"
        "یا نام را دستی بنویسید مثل <code>آمیان_فرانسه</code>",
        reply_markup=get_country_keyboard("grp_city"),
    )


async def _link_group_to_city(message: types.Message, state: FSMContext, name: str):
    """اتصال گروه جاری به شهر (از منو یا ورودی دستی)."""
    name = (name or "").strip()
    if not name:
        return await message.answer("❌ نام شهر خالی است.")
    if len(name) > 60:
        return await message.answer("❌ نام خیلی طولانی است.")
    # اگر بدون _ بود و فقط از لیست انتخاب شده OK است
    existing = next((c for c, n in PLAYER_CODES.items() if n.lower() == name.lower()), None)
    if existing:
        code, canon_name = existing, PLAYER_CODES[existing]
    else:
        if "_" not in name:
            return await message.answer(
                "❌ فرمت دستی: <code>نامشهر_کشور</code>\nمثال: <code>کمبریج_انگلیس</code>"
            )
        code, canon_name = gen_code(), name
        PLAYER_CODES[code] = canon_name

    GROUPS[message.chat.id] = {"city": canon_name, "code": code}
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ این گروه به شهر <b>{e(canon_name)}</b> متصل شد.\n"
        f"🔑 کد ورود: <code>{e(code)}</code>\n\n"
        "👤 برای تعیین فرمانده، روی پیام او <b>ریپلای</b> و بنویسید: "
        "<code>ست پلیر</code> یا <code>/set player</code>"
    )


@dp.message(GameStates.group_set_city)
async def process_group_setcity(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("❌ لغو شد.")
    await _link_group_to_city(message, state, message.text or "")


SET_PLAYER_CMDS = {"ستپلیر", "setplayer"}
SET_ADMIN_CMDS = {"ستادمین", "setadmin"}
ADMIN_WORD = "admin"
GROUP_INQUIRY_CMDS = {
    "استعلامگپ", "استعلام", "estelamgap", "estelam", "inquiry", "groupinfo", "گپاینفو",
}


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in SET_PLAYER_CMDS))
async def handle_set_group_player(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    grp = GROUPS.get(message.chat.id)
    if not grp:
        return await message.answer("❌ اول باید این گروه را با «ست گپ» به یک شهر وصل کنید. /start را بزنید.")
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام فرمانده‌ی مورد نظر ریپلای کنید و دوباره «ست پلیر» یا «/set player» را بفرستید.")

    target = target_msg.from_user
    authenticated_users[target.id] = {
        "role": "player",
        "country": grp["city"],
        "code": grp["code"],
        "username": target.username or "",
        "name": target.full_name,
    }
    all_players.add(target.id)
    save_data(critical=True)

    tfsm = chat_fsm(message.chat.id, target.id)
    await tfsm.clear()
    await tfsm.set_state(GameStates.main_menu)

    await message.answer(
        f"✅ {mention(target.id, target.full_name)} فرمانده‌ی شهر <b>{e(grp['city'])}</b> در این گروه شد.\n\n{MENU_TEXT}",
        reply_markup=get_main_menu_keyboard(),
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text=f"👑 شما فرمانده‌ی شهر <b>{e(grp['city'])}</b> در گروه «{e(message.chat.title or '')}» شدید.",
        )
    except Exception:
        pass


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) == ADMIN_WORD))
async def handle_group_admin_word(message: types.Message):
    """در هر گروهی، تایپ کلمه‌ی ADMIN توسط یک ادمین، پنل مدیریت را همان‌جا باز می‌کند."""
    if not is_admin(message.from_user.id):
        return
    await message.answer("⚡️ پنل مدیریت شیشه‌ای:", reply_markup=get_admin_inline_keyboard())


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in SET_ADMIN_CMDS))
async def handle_set_group_admin(message: types.Message):
    """ادمین با ریپلای روی پیام یک عضو و فرستادن «ست ادمین» یا «/set admin»، به او دسترسی ادمین می‌دهد."""
    if not is_admin(message.from_user.id):
        return
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام عضو مورد نظر ریپلای کنید و دوباره «/set admin» را بفرستید.")

    target = target_msg.from_user
    if is_admin(target.id):
        return await message.answer(f"ℹ️ {mention(target.id, target.full_name)} از قبل ادمین است.")

    authenticated_users[target.id] = {"role": "admin", "country": "مدیریت کل"}
    save_data(critical=True)
    await message.answer(f"✅ {mention(target.id, target.full_name)} اکنون دسترسی ادمین دارد.")
    try:
        await bot.send_message(chat_id=target.id, text="⚡️ شما توسط ادمین کل، دسترسی ادمین دریافت کردید. برای ورود به پنل، عبارت ADMIN را بفرستید.")
    except Exception:
        pass


# ---- ست ادمین دارایی (ریپلای) ----
SET_ASSET_ADMIN_CMDS = {
    "ستادمیندارایی", "setassetadmin", "setadminasset", "ادمیندارایی",
}


@dp.message(F.text.func(lambda t: norm_cmd(t) in SET_ASSET_ADMIN_CMDS))
async def handle_set_asset_admin(message: types.Message):
    global ASSET_ADMIN_ID
    if not is_admin(message.from_user.id):
        return
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام کاربر ریپلای کنید و «ست ادمین دارایی» بفرستید.")
    target = target_msg.from_user
    ASSET_ADMIN_ID = target.id
    save_data(critical=True)
    await message.answer(
        f"✅ {mention(target.id, target.full_name)} ادمین دارایی شد.\n"
        f"گزارش کامل تجارت برای ایشان هم ارسال می‌شود.\n🆔 <code>{target.id}</code>"
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text="📦 شما به‌عنوان <b>ادمین دارایی</b> تنظیم شدید. گزارش‌های کامل تجارت برایتان می‌آید.",
        )
    except Exception:
        pass


# ---- ست / حذف لیدر ساید ----
_SIDE_ALIASES = {
    # مونارشیست
    "monarchist": "monarchist", "monarch": "monarchist", "royal": "monarchist",
    "royalist": "monarchist", "king": "monarchist",
    "مونارشیست": "monarchist", "مونارش": "monarchist",
    "پادشاهی": "monarchist", "پادشاهیخواه": "monarchist", "رویالیست": "monarchist",
    # پارلمانری
    "parliamentarian": "parliamentarian", "parliament": "parliamentarian",
    "parliamentary": "parliamentarian", "roundhead": "parliamentarian",
    "پارلمانری": "parliamentarian", "پارلمان": "parliamentarian",
    "پارلمانتاریان": "parliamentarian",
    # فرانسه / ایرلند
    "france": "france", "فرانسه": "france",
    "ireland": "ireland", "ایرلند": "ireland",
}


def _resolve_side_token(tok: str):
    if not tok:
        return None
    t = tok.strip().lower().replace("ي", "ی").replace("ك", "ک")
    # انگلیس مبهم است → باید مونارشیست یا پارلمانری مشخص شود
    if re.search(r"(انگلیس|انگلستان|\bengland\b)", t):
        if not re.search(r"(مونارش|پارلمان|monarch|parliament|royal)", t):
            return None
    if t in _SIDE_ALIASES:
        return _SIDE_ALIASES[t]
    for alias, side in sorted(_SIDE_ALIASES.items(), key=lambda x: -len(x[0])):
        a = alias.lower().replace("ي", "ی")
        if len(a) >= 3 and a in t:
            return side
    return None


def _parse_leader_cmd(text: str):
    """برمی‌گرداند ('set'|'del', side|None) یا (None, None)."""
    raw = (text or "").strip()
    n = norm_cmd(raw)
    if n in ("حذف‌لیدر", "حذفلیدر", "removeleader", "delleader", "unsetleader", "حذف لیدر"):
        return "del", None
    # فقط دستورهای ست لیدر
    if not re.match(
        r"^[/\\]?\s*(ست\s*لیدر|ستلیدر|set\s*leader|setleader)\b",
        raw,
        re.I | re.U,
    ):
        return None, None
    # ساید از کل متن
    side = _resolve_side_token(raw)
    if side:
        return "set", side
    # توکن‌به‌توکن
    parts = re.split(r"[\s/_-]+", re.sub(r"^[/\\]", "", raw))
    for tok in reversed(parts):
        side = _resolve_side_token(tok)
        if side and side in FACTIONS:
            return "set", side
    return "set", None


@dp.message(F.text.func(lambda t: _parse_leader_cmd(t)[0] is not None))
async def handle_set_leader(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    action, side = _parse_leader_cmd(message.text or "")
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام کاربر ریپلای کنید.")
    target = target_msg.from_user
    if action == "del":
        removed_from = []
        for s, ids in LEADERS.items():
            if target.id in ids:
                ids.remove(target.id)
                removed_from.append(s)
        save_data(critical=True)
        if not removed_from:
            return await message.answer("ℹ️ این کاربر لیدر هیچ سایدی نبود.")
        return await message.answer(
            f"✅ {mention(target.id, target.full_name)} از لیدری "
            f"{', '.join(FACTION_META.get(s, ('', s))[1] for s in removed_from)} حذف شد."
        )
    # set — اگر ساید نبود از شهر کاربر، وگرنه دکمه‌های انتخاب
    if not side or side not in FACTIONS:
        side = side_of_user(target.id)
    if not side or side not in FACTIONS:
        builder = InlineKeyboardBuilder()
        for s in FACTIONS:
            flag, title = FACTION_META[s]
            builder.row(_btn(f"{flag} {title}", f"set_leader_side:{s}:{target.id}"))
        return await message.answer(
            f"❌ ساید مشخص نیست برای {mention(target.id, target.full_name)}.\n"
            "یکی را انتخاب کنید یا این‌ها را بزنید:\n"
            "<code>ست لیدر مونارشیست</code>\n"
            "<code>ست لیدر پارلمانری</code>\n"
            "<code>ست لیدر فرانسه</code>\n"
            "<code>ست لیدر ایرلند</code>",
            reply_markup=builder.as_markup(),
        )
    ids = LEADERS.setdefault(side, [])
    if target.id in ids:
        return await message.answer(f"ℹ️ از قبل لیدر {FACTION_META[side][1]} است.")
    if len(ids) >= 3:
        return await message.answer(f"❌ ظرفیت لیدر {FACTION_META[side][1]} پر است (حداکثر ۳ نفر).")
    ids.append(target.id)
    save_data(critical=True)
    flag, title = FACTION_META[side]
    await message.answer(
        f"✅ {mention(target.id, target.full_name)} لیدر {flag}<b>{title}</b> شد "
        f"({len(ids)}/3).\nمشاهده دارایی از منوی اصلی در دسترس است."
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text=f"👑 شما لیدر ساید {flag}<b>{title}</b> شدید.\nاز منوی ربات «📦 مشاهده دارایی» را بزنید.",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("set_leader_side:"))
async def handle_set_leader_side_btn(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    side, uid_s = parts[1], parts[2]
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر", show_alert=True)
    try:
        uid = int(uid_s)
    except ValueError:
        return await callback.answer("آیدی نامعتبر", show_alert=True)
    ids = LEADERS.setdefault(side, [])
    if uid in ids:
        return await callback.answer("از قبل لیدر است.", show_alert=True)
    if len(ids) >= 3:
        return await callback.answer("ظرفیت پر است (۳/۳).", show_alert=True)
    ids.append(uid)
    save_data(critical=True)
    flag, title = FACTION_META[side]
    await callback.answer("ثبت شد")
    await callback.message.answer(
        f"✅ کاربر <code>{uid}</code> لیدر {flag}<b>{title}</b> شد ({len(ids)}/3)."
    )
    try:
        await bot.send_message(
            chat_id=uid,
            text=f"👑 شما لیدر ساید {flag}<b>{title}</b> شدید.\nاز منوی ربات «📦 مشاهده دارایی» را بزنید.",
        )
    except Exception:
        pass


# ---- ست دارایی در گروه شهر ----
SET_ASSET_CMDS = {
    "ستدارایی", "setasset", "setassets", "دارایی",
}
REGISTER_ASSET_CMDS = {
    "ثبتتغییردارایی", "ثبتدارایی", "registerasset", "updateasset",
}


async def _register_asset_now(message: types.Message, state: FSMContext, raw: str, city: str):
    """ثبت فوری دارایی برای شهر و نمایش خلاصه."""
    if not city:
        await state.update_data(asset_text=raw, asset_stats=extract_asset_stats(raw))
        await message.answer(
            "✅ متن دریافت شد.\nنام شهر را بنویسید (مثال: <code>oxford_monarchist</code>):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.adm_set_asset_city)
        return
    city = _canonical_city_name(city)
    stats = set_city_asset(city, raw)
    save_data(critical=True)
    side = country_key(city)
    body = (
        f"✅ دارایی <b>{e(city)}</b> مستقیم ثبت شد.\n"
        f"اعداد استخراج‌شده: <b>{len(stats)}</b> مورد\n\n"
        f"{format_stats_labeled(stats)}\n\n"
    )
    if side:
        body += format_realm_view(side)
    await state.clear()
    await message.answer(body[:4000], reply_markup=get_admin_inline_keyboard() if is_admin(message.from_user.id) else None)


@dp.message(F.text.regexp(r"(?i)^\s*اعمال\s*ارتقا"))
async def handle_apply_upgrade_cmd(message: types.Message):
    """اعمال ارتقا: بندر 2, خزانه 1 — فقط شهر اتو"""
    uid = message.from_user.id
    if not (is_player(uid) or is_admin(uid) or is_leader(uid)):
        return
    city = resolve_player_city(uid) or city_of(uid)
    if message.chat.type in ("group", "supergroup"):
        grp = GROUPS.get(message.chat.id)
        if grp and grp.get("city"):
            city = grp["city"]
    if not city or city == "ناشناس":
        return await message.answer("❌ شهر مشخص نیست.")
    if not is_auto_city(city) and not is_admin(uid):
        return await message.answer(
            f"🔒 اتو برای <b>{e(city)}</b> فعال نیست. ادمین باید تیک بزند."
        )
    body = re.sub(r"(?i)^\s*اعمال\s*ارتقا\s*:?\s*", "", message.text or "").strip()
    if not body:
        return await message.answer(
            "مثال:\n<code>اعمال ارتقا: بندر 2, خزانه 1</code>"
        )
    results = []
    for chunk in re.split(r"[,،]\s*", body):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(r"(.+?)\s+(\d+)\s*$", chunk)
        if m:
            name, lv = m.group(1).strip(), int(m.group(2))
        else:
            name, lv = chunk, 1
        # تطبیق نام با جدول
        matched = None
        for k in UPGRADE_TABLE:
            if k == name or k in name or name in k:
                matched = k
                break
        if not matched:
            results.append(f"❌ ناشناخته: {e(name)}")
            continue
        ok, msg = apply_upgrade_levels(city, matched, lv)
        results.append(msg if ok else f"❌ {msg}")
    await message.answer(
        f"⬆️ <b>اعمال ارتقا — {e(city)}</b>\n{DIV}\n" + "\n\n".join(results)
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📝 ارتقا اتو توسط {mention(uid, city)}\n🏙 {e(city)}\n" + "\n".join(results)[:1500],
        )
    except Exception:
        pass


@dp.message(F.text.func(lambda t: norm_cmd(t) in SET_ASSET_CMDS or norm_cmd(t) in REGISTER_ASSET_CMDS))
async def handle_set_assets_prompt(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    grp = GROUPS.get(message.chat.id) if message.chat.type in ("group", "supergroup") else None
    city_hint = grp["city"] if grp else None
    # ریپلای روی پیام شیت → ثبت مستقیم بدون ارسال مجدد
    replied = message.reply_to_message
    if replied and (replied.text or replied.caption):
        raw = (replied.text or replied.caption or "").strip()
        if raw:
            return await _register_asset_now(message, state, raw, city_hint)
    await state.update_data(asset_city_hint=city_hint)
    hint = f"شهر تشخیص‌داده‌شده: <b>{e(city_hint)}</b>\n" if city_hint else ""
    await message.answer(
        f"📦 <b>ثبت دارایی</b>\n{DIV}\n{hint}"
        "• روی پیام شیت دارایی <b>ریپلای</b> کنید و بنویسید <code>ست دارایی</code> "
        "تا همان پیام مستقیم ثبت شود.\n"
        "• یا متن کامل را همین‌جا بفرستید.\n\n"
        "ربات همان متن را ذخیره می‌کند و اعداد را برای جمع قلمرو استخراج می‌کند.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_asset_text)


@dp.message(GameStates.adm_set_asset_text)
async def handle_set_assets_text(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("❌ لغو شد.")
    # اگر ریپلای کرده باشد همان را بگیر
    raw = ""
    if message.reply_to_message and (message.reply_to_message.text or message.reply_to_message.caption):
        raw = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()
    if not raw:
        raw = (message.text or message.caption or "").strip()
    if not raw:
        return await message.answer("❌ متن خالی است. روی پیام شیت ریپلای کنید یا متن را بفرستید.")
    d = await state.get_data()
    hint = d.get("asset_city_hint")
    # اگر شهر مشخص است → ثبت مستقیم
    if hint:
        return await _register_asset_now(message, state, raw, hint)
    stats = extract_asset_stats(raw)
    await state.update_data(asset_text=raw, asset_stats=stats)
    preview_stats = (
        format_stats_labeled(stats)
        if stats
        else "— عددی برای جمع پیدا نشد (متن کامل ذخیره می‌شود) —"
    )
    if hint:
        builder = InlineKeyboardBuilder()
        builder.row(_btn(f"✅ ثبت برای {hint}", f"asset_confirm_city:{hint}", "success"))
        builder.row(_btn("✏️ شهر دیگر", "asset_pick_other"))
        builder.row(_btn("❌ انصراف", "menu:home", "danger"))
        await message.answer(
            f"✅ متن دریافت شد ({len(raw)} کاراکتر).\n"
            f"اعداد استخراج‌شده (بخش‌بندی‌شده):\n{DIV}\n{preview_stats}\n\n"
            f"برای کدام شهر ثبت شود؟",
            reply_markup=builder.as_markup(),
        )
    else:
        await message.answer(
            f"✅ متن دریافت شد.\nاعداد استخراج‌شده:\n{DIV}\n{preview_stats}\n\n"
            "نام شهر را بنویسید (مثال: <code>london_monarchist</code>):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.adm_set_asset_city)


@dp.callback_query(F.data.startswith("asset_confirm_city:"))
async def asset_confirm_city(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    city = callback.data.split(":", 1)[1]
    d = await state.get_data()
    raw = d.get("asset_text") or ""
    if not raw:
        return await callback.answer("متن خالی است.", show_alert=True)
    stats = set_city_asset(city, raw)
    save_data(critical=True)
    await callback.answer("ثبت شد")
    side = country_key(city)
    await state.clear()
    body = f"✅ دارایی <b>{e(city)}</b> ثبت شد.\nاعداد استخراج‌شده: {len(stats)} مورد\n\n"
    if side:
        body += format_realm_view(side)
    else:
        body += "⚠️ ساید شهر تشخیص داده نشد؛ در جمع قلمرو لحاظ نمی‌شود."
    await callback.message.answer(
        body[:4000],
        reply_markup=get_admin_inline_keyboard() if is_admin(callback.from_user.id) else None,
    )


@dp.callback_query(F.data == "asset_pick_other")
async def asset_pick_other(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "نام شهر را بنویسید (مثال: <code>کمبریج_انگلیس</code>):",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_asset_city)


@dp.message(GameStates.adm_set_asset_city)
async def handle_set_assets_city(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("❌ لغو شد.")
    city = (message.text or "").strip()
    d = await state.get_data()
    raw = d.get("asset_text") or ""
    if not raw:
        await state.clear()
        return await message.answer("❌ متن خالی است.")
    stats = set_city_asset(city, raw)
    save_data(critical=True)
    side = country_key(city)
    await state.clear()
    body = f"✅ دارایی <b>{e(city)}</b> ثبت شد.\nاعداد استخراج‌شده: {len(stats)} مورد\n\n"
    if side:
        body += format_realm_view(side)
    else:
        body += "⚠️ ساید شهر تشخیص داده نشد؛ در جمع قلمرو لحاظ نمی‌شود."
    await message.answer(body[:4000], reply_markup=get_admin_inline_keyboard())


def _players_of_city(city_name: str):
    """فرمانده(های) یک شهر."""
    out = []
    for uid, u in authenticated_users.items():
        if u.get("role") == "player" and (u.get("country") or "").lower() == (city_name or "").lower():
            out.append((uid, u))
    return out


def get_group_inquiry_keyboard(chat_id: int, city: str, player_ids: list):
    builder = InlineKeyboardBuilder()
    for uid in player_ids:
        builder.row(_btn(f"❌ حذف فرمانده {uid}", f"inq_delplayer:{uid}", "danger"))
    builder.row(_btn("🗑 قطع اتصال گروه از شهر", f"inq_unlink:{chat_id}", "danger"))
    builder.row(_btn("🔙 بستن", "inq_close"))
    return builder.as_markup()


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in GROUP_INQUIRY_CMDS))
async def handle_group_inquiry(message: types.Message):
    """استعلام گپ: نام شهر + آیدی پلیر + منوی حذف."""
    if not is_admin(message.from_user.id):
        return
    gid = message.chat.id
    grp = GROUPS.get(gid)
    if not grp:
        return await message.answer(
            "ℹ️ این گروه هنوز به شهری وصل نیست.\n"
            "با /start و «ست گپ» متصل کنید."
        )
    city = grp.get("city", "-")
    code = grp.get("code", "-")
    fac = country_key(city)
    flag = {
        "monarchist": "👑",
        "parliamentarian": "🏛",
        "england": "🇬🇧",
        "france": "🇫🇷",
        "ireland": "🇮🇪",
    }.get(fac, "🏙")
    players = _players_of_city(city)
    lines = [
        f"🔍 <b>استعلام گپ</b>\n{DIV}\n",
        f"{flag} شهر: <b>{e(city)}</b>",
        f"🔑 کد: <code>{e(code)}</code>",
        f"💬 گروه: <b>{e(message.chat.title or '')}</b>",
        f"🆔 آیدی گروه: <code>{gid}</code>",
        "",
    ]
    pids = []
    if players:
        lines.append("👤 <b>فرمانده(ها):</b>")
        for uid, u in players:
            pids.append(uid)
            uname = f" @{e(u['username'])}" if u.get("username") else ""
            lines.append(
                f"• {mention(uid, u.get('name') or 'فرمانده')}{uname}\n"
                f"  🆔 <code>{uid}</code>"
            )
    else:
        lines.append("👤 فرمانده: <i>هنوز تعیین نشده</i>")
    await message.answer(
        "\n".join(lines),
        reply_markup=get_group_inquiry_keyboard(gid, city, pids),
    )


@dp.callback_query(F.data.startswith("inq_delplayer:"))
async def inquiry_del_player(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ فقط ادمین.", show_alert=True)
    try:
        uid = int(callback.data.split(":")[1])
    except ValueError:
        return await callback.answer()
    u = authenticated_users.pop(uid, None)
    all_players.discard(uid)
    save_data(critical=True)
    await callback.answer("حذف شد", show_alert=True)
    city = (u or {}).get("country", "-")
    try:
        await callback.message.edit_text(
            f"✅ فرمانده <code>{uid}</code> از شهر <b>{e(city)}</b> حذف شد.\n"
            f"برای استعلام دوباره بنویسید: <code>استعلام گپ</code>",
            reply_markup=None,
        )
    except Exception:
        await callback.message.answer(f"✅ فرمانده <code>{uid}</code> حذف شد.")


@dp.callback_query(F.data.startswith("inq_unlink:"))
async def inquiry_unlink_group(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ فقط ادمین.", show_alert=True)
    try:
        gid = int(callback.data.split(":")[1])
    except ValueError:
        return await callback.answer()
    old = GROUPS.pop(gid, None)
    save_data(critical=True)
    await callback.answer("گروه قطع شد", show_alert=True)
    city = (old or {}).get("city", "-")
    try:
        await callback.message.edit_text(
            f"✅ اتصال گروه از شهر <b>{e(city)}</b> قطع شد.\n"
            f"گروه دیگر به این شهر وصل نیست.",
            reply_markup=None,
        )
    except Exception:
        await callback.message.answer("✅ اتصال گروه قطع شد.")


@dp.callback_query(F.data == "inq_close")
async def inquiry_close(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@dp.message(StateFilter(None), F.chat.type.in_({"group", "supergroup"}), F.text == BTN_BACK)
async def group_fallback_handler(message: types.Message, state: FSMContext):
    """بعد از ری‌استارت ربات، وضعیت فرمانده‌ی گروه را دوباره برقرار می‌کند."""
    if is_player(message.from_user.id):
        await go_menu(message, state)


@dp.message(GameStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    code = (message.text or "").strip().upper()
    if not code:
        return await message.answer("❌ لطفاً کد را به صورت متن ارسال کنید:")

    if code == ADMIN_CODE and is_admin(user_id):
        authenticated_users[user_id] = {"role": "admin", "country": "مدیریت کل"}
        await message.answer("⚡️ سلام رئیس! پنل مدیریت ادمین فعال شد.", reply_markup=get_admin_inline_keyboard())
        await state.clear()
    elif code in PLAYER_CODES:
        owner = code_owner(code)
        if owner and owner != user_id:
            return await message.answer("🚫 این کد قبلاً توسط فرمانده دیگری فعال شده است.\nبا ادمین تماس بگیرید:")
        city = PLAYER_CODES[code]
        authenticated_users[user_id] = {
            "role": "player",
            "country": city,
            "code": code,
            "username": message.from_user.username or "",
            "name": message.from_user.full_name,
        }
        all_players.add(user_id)
        save_data(critical=True)
        await go_menu(message, state, f"✅ <b>کد شما تایید شد!</b>\n👑 مدیریت شهر <b>{e(city)}</b> به شما واگذار گردید.\n\n{MENU_TEXT}")
    else:
        await message.answer("🚫 این کد معتبر نیست یا باطل شده است!\nمجدداً تلاش کنید:")


@dp.message(F.text == BTN_BACK)
async def global_back(message: types.Message, state: FSMContext):
    user_data = authenticated_users.get(message.from_user.id)
    if not user_data:
        return
    if user_data["role"] == "admin":
        await state.clear()
        await message.answer("⚡️ منوی اصلی مدیریت:", reply_markup=get_admin_inline_keyboard())
    else:
        await go_menu(message, state)


# ======================================================================
#                         عملیات‌های پنل ادمین
# ======================================================================
@dp.callback_query(F.data == "adm_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()

    if not PLAYER_CODES:
        return await callback.message.answer(
            "📊 هنوز هیچ شهری ثبت نشده است.\nاز «⚙️ مدیریت» گزینه‌ی «➕ افزودن شهر» را بزنید.",
            reply_markup=get_admin_inline_keyboard(),
        )

    # گروه‌های وصل‌شده به هر شهر
    groups_by_city = {}
    for gid, g in GROUPS.items():
        c = (g.get("city") or "").lower()
        groups_by_city.setdefault(c, []).append(gid)

    blocks = [f"📊 <b>آمار شهرها</b>\n{DIV}\n"]
    # مرتب بر اساس نام شهر
    items = sorted(PLAYER_CODES.items(), key=lambda kv: str(kv[1]).lower())
    for code, city in items:
        fac = country_key(city)
        flag = {
        "monarchist": "👑",
        "parliamentarian": "🏛",
        "england": "🇬🇧",
        "france": "🇫🇷",
        "ireland": "🇮🇪",
    }.get(fac, "🏙")
        uid = code_owner(code)
        if uid:
            u = authenticated_users[uid]
            uname = f" @{e(u['username'])}" if u.get("username") else ""
            player_line = f"✅ {mention(uid, u.get('name') or 'فرمانده')}{uname}\n   🆔 <code>{uid}</code>"
        else:
            player_line = "❌ فرمانده تعیین نشده"
        n_grp = len(groups_by_city.get(str(city).lower(), []))
        grp_line = f"👥 گروه متصل: <b>{n_grp}</b>" if n_grp else "👥 گروه: —"
        blocks.append(
            f"{flag} <b>{e(city)}</b>\n"
            f"🔑 <code>{e(code)}</code>\n"
            f"👤 {player_line}\n"
            f"{grp_line}\n"
        )
    blocks.append(
        f"{DIV}\n"
        f"📈 فعال: <b>{len(all_players)}</b> / {len(PLAYER_CODES)} شهر · "
        f"گروه: <b>{len(GROUPS)}</b>"
    )
    await send_chunks(callback.message, blocks, reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_msg")
async def admin_msg_start(callback: types.CallbackQuery, state: FSMContext):
    """ارسال پیام: همگانی / فقط گروه‌ها / فقط فرماندهان / انتخابی / خصوصی."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("📢 همگانی (فرماندهان + گروه‌ها)", "adm_msg_scope:all", "primary"))
    builder.row(_btn("👥 فقط گروه‌ها", "adm_msg_scope:groups", "success"))
    builder.row(_btn("👑 فقط فرماندهان", "adm_msg_scope:players"))
    builder.row(_btn("📋 انتخابی (چند نفر)", "adm_msg_scope:select", "primary"))
    builder.row(_btn("🔒 خصوصی (یک نفر)", "adm_msg_scope:private", "success"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"📨 <b>ارسال پیام</b>\n{DIV}\nنوع ارسال را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


def _player_pick_keyboard(selected=None, prefix="adm_msg_pick"):
    selected = set(selected or [])
    players = [(uid, u) for uid, u in authenticated_users.items() if u.get("role") == "player"]
    builder = InlineKeyboardBuilder()
    for uid, u in sorted(players, key=lambda x: str(x[1].get("country", "")).lower())[:50]:
        city = u.get("country") or "?"
        mark = "✅ " if uid in selected else ""
        builder.row(_btn(f"{mark}{city} · {uid}", f"{prefix}:{uid}"))
    if selected:
        builder.row(_btn(f"📨 ارسال به {len(selected)} نفر", f"{prefix}_done", "success"))
    builder.row(_btn("🔙 بازگشت", "adm_msg"))
    return builder.as_markup()


@dp.callback_query(F.data.startswith("adm_msg_scope:"))
async def admin_msg_scope(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    scope = callback.data.split(":")[1]
    await callback.answer()
    if scope in ("all", "groups", "players"):
        await state.update_data(msg_scope=scope, msg_targets=None)
        labels = {
            "all": "همگانی (فرماندهان + گروه‌ها)",
            "groups": "فقط گروه‌ها",
            "players": "فقط فرماندهان",
        }
        await callback.message.answer(
            f"📢 محتوای پیام «{labels[scope]}» را بفرستید (متن / عکس / ویدیو):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.admin_broadcast)
        return
    if scope == "select":
        await state.update_data(msg_scope="select", msg_targets=[])
        await callback.message.answer(
            "📋 فرماندهان مورد نظر را انتخاب کنید (چندتایی):",
            reply_markup=_player_pick_keyboard([]),
        )
        return
    # خصوصی: یک فرمانده
    players = [(uid, u) for uid, u in authenticated_users.items() if u.get("role") == "player"]
    if not players:
        return await callback.message.answer("فرماندهی نیست.", reply_markup=get_admin_inline_keyboard())
    builder = InlineKeyboardBuilder()
    for uid, u in sorted(players, key=lambda x: str(x[1].get("country", "")).lower())[:50]:
        city = u.get("country") or "?"
        builder.row(_btn(f"👤 {city} · {uid}", f"adm_msg_to:{uid}"))
    builder.row(_btn("🔙 بازگشت", "adm_msg"))
    await callback.message.answer("🔒 گیرنده خصوصی را انتخاب کنید:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("adm_msg_pick:"))
async def admin_msg_pick_toggle(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[1])
    d = await state.get_data()
    selected = list(d.get("msg_targets") or [])
    if uid in selected:
        selected.remove(uid)
    else:
        selected.append(uid)
    await state.update_data(msg_targets=selected)
    await callback.answer(f"{'حذف' if uid not in selected else 'اضافه'} شد")
    try:
        await callback.message.edit_reply_markup(reply_markup=_player_pick_keyboard(selected))
    except Exception:
        pass


@dp.callback_query(F.data == "adm_msg_pick_done")
async def admin_msg_pick_done(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    d = await state.get_data()
    targets = d.get("msg_targets") or []
    if not targets:
        return await callback.answer("حداقل یک نفر انتخاب کنید.", show_alert=True)
    await callback.answer()
    await state.update_data(msg_scope="select")
    await callback.message.answer(
        f"✉️ پیام برای <b>{len(targets)}</b> فرمانده را بفرستید (متن/عکس/ویدیو):",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.admin_broadcast)


@dp.callback_query(F.data.startswith("adm_msg_to:"))
async def admin_msg_to(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[1])
    await callback.answer()
    await state.update_data(msg_scope="private", msg_targets=[uid])
    await callback.message.answer(
        f"✉️ پیام برای {mention(uid, city_of(uid))} (<code>{uid}</code>)\nمتن/عکس/ویدیو بفرستید:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.admin_broadcast)


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
                body = header + e(message.text) if message.chat.type != "private" or True else e(message.text)
                # برای خصوصی هم قالب اعلان
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


@dp.message(GameStates.admin_broadcast)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل مدیریت:", reply_markup=get_admin_inline_keyboard())
    if not (message.text or message.photo or message.video):
        return await message.answer("❌ فقط متن، عکس یا ویدیو:")
    d = await state.get_data()
    scope = d.get("msg_scope", "all")
    if scope in ("private", "select") and d.get("msg_targets"):
        targets = list(d["msg_targets"])
    elif scope == "groups":
        targets = list(GROUPS.keys())
    elif scope == "players":
        targets = list(all_players)
    else:
        targets = list(set(list(all_players) + list(GROUPS.keys())))
    if not targets:
        await state.clear()
        return await message.answer("❗️ گیرنده‌ای نیست.", reply_markup=get_admin_inline_keyboard())

    ok_list, fail_list = await _deliver_to_targets(message, targets)
    lines = [f"📬 <b>نتیجه ارسال</b>\n{DIV}\n"]
    lines.append(f"✅ موفق: <b>{len(ok_list)}</b>")
    for cid in ok_list[:30]:
        lines.append(f"  • {_target_label(cid)}")
    if len(ok_list) > 30:
        lines.append(f"  … و {len(ok_list) - 30} مورد دیگر")
    lines.append(f"\n❌ ناموفق: <b>{len(fail_list)}</b>")
    for cid, err in fail_list[:20]:
        lines.append(f"  • {_target_label(cid)} — <i>{e(err)}</i>")
    await message.answer("\n".join(lines), reply_markup=get_admin_inline_keyboard())
    await state.clear()


@dp.callback_query(F.data == "adm_report")
async def admin_report(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    leaders_line = " · ".join(
        f"{FACTION_META.get(s, ('', s))[0]}{len(LEADERS.get(s, []))}" for s in FACTIONS
    )
    text = (
        f"📋 <b>گزارش وضعیت ربات</b>\n{DIV}\n"
        f"🏙 شهرها: <b>{len(PLAYER_CODES)}</b>\n"
        f"👤 فرماندهان: <b>{len(all_players)}</b>\n"
        f"👥 گروه‌ها: <b>{len(GROUPS)}</b>\n"
        f"⚔️ اکشن فعال: <b>{len(active_actions)}</b>\n"
        f"👑 لیدرها: {leaders_line}\n"
        f"📦 شهر دارای دارایی: <b>{len(CITY_ASSETS)}</b>\n"
        f"🛒 کالاهای تجار: <b>{len(MERCHANT_LIMITS)}</b>\n"
        f"⏰ استارت: <code>{SETTINGS.get('time_start')}</code> · "
        f"استاپ: <code>{SETTINGS.get('time_stop')}</code>\n"
        f"🆔 کانال اصلی: <code>{CHANNEL_ID}</code>\n"
        f"🆔 کانال گزارش: <code>{REPORT_CHANNEL_ID or '—'}</code>\n"
        f"🆔 کانال توییت: <code>{TWEET_CHANNEL_ID or '—'}</code>\n"
        f"👤 ادمین دارایی: <code>{ASSET_ADMIN_ID or '—'}</code>"
    )
    await callback.message.answer(text, reply_markup=get_admin_inline_keyboard())


# ---------------- تایم استارت / استاپ ----------------
def _timing_menu_keyboard():
    builder = InlineKeyboardBuilder()
    has_ps = "✅" if SETTINGS.get("photo_start") else "➕"
    has_pe = "✅" if SETTINGS.get("photo_stop") else "➕"
    builder.row(_btn(f"{has_ps} عکس استارت", "adm_photo:start", "primary"))
    builder.row(_btn(f"{has_pe} عکس استاپ", "adm_photo:stop", "primary"))
    builder.row(_btn("📝 ویرایش متن/ساعت", "adm_timing_edit", "success"))
    builder.row(
        _btn("📢 ارسال استارت به گروه‌ها", "adm_broadcast_ts:start", "success"),
        _btn("📢 ارسال استاپ به گروه‌ها", "adm_broadcast_ts:stop", "danger"),
    )
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    return builder.as_markup()


@dp.callback_query(F.data == "adm_timing")
async def admin_timing_menu(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await state.clear()
    text = (
        f"⏰ <b>تایم استارت / استاپ</b>\n{DIV}\n"
        f"▶️ استارت: <code>{SETTINGS.get('time_start')}</code>\n"
        f"⏹ استاپ: <code>{SETTINGS.get('time_stop')}</code>\n"
        f"📅 روزهای مجاز: <b>{e(format_days_setting(SETTINGS.get('days_start', '')))}</b>\n"
        f"💬 پیام استارت:\n<blockquote>{e(SETTINGS.get('msg_start', ''))}</blockquote>\n"
        f"💬 پیام استاپ:\n<blockquote>{e(SETTINGS.get('msg_stop', ''))}</blockquote>\n"
        f"✅ موارد مجاز:\n<blockquote>{e(SETTINGS.get('allowed', ''))}</blockquote>\n"
        f"🖼 عکس استارت: {'✅' if SETTINGS.get('photo_start') else '—'}\n"
        f"🖼 عکس استاپ: {'✅' if SETTINGS.get('photo_stop') else '—'}\n"
        f"🖼 عکس منو: {'✅' if SETTINGS.get('photo_menu') else '—'}"
    )
    await callback.message.answer(text, reply_markup=_timing_menu_keyboard())


@dp.callback_query(F.data == "adm_timing_edit")
async def admin_timing_edit(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "برای تغییر، یک یا چند خط بفرستید:\n"
        "<code>time_start=08:00</code>\n"
        "<code>time_stop=23:00</code>\n"
        "<code>days_start=شنبه,یکشنبه,دوشنبه,سه‌شنبه,چهارشنبه</code>\n"
        "<code>days_start=5,6,0,1,2</code> (۰=دوشنبه … ۶=یکشنبه)\n"
        "<code>msg_start=متن پیام</code>\n"
        "<code>msg_stop=متن پیام</code>\n"
        "<code>allowed=لشکرکشی،محاصره،جنگ،تجارت</code>\n\n"
        "خالی گذاشتن days_start = همه روزها",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_timing)


@dp.message(GameStates.adm_set_timing)
async def admin_set_timing(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    txt = (message.text or "").strip()
    changed = []
    mapping = {
        "time_start": "time_start", "timestart": "time_start", "استارت": "time_start",
        "time_stop": "time_stop", "timestop": "time_stop", "استاپ": "time_stop",
        "days_start": "days_start", "days": "days_start", "روزها": "days_start", "روز": "days_start",
        "days_stop": "days_stop",
        "msg_start": "msg_start", "msgstart": "msg_start", "پیام_استارت": "msg_start",
        "msg_stop": "msg_stop", "msgstop": "msg_stop", "پیام_استاپ": "msg_stop",
        "allowed": "allowed", "مجاز": "allowed",
    }
    # پشتیبانی پیام چندخطی: msg_start=خط اول\nادامه متن...
    # یا فقط کلید در خط اول و بقیه متن پیام
    lines = txt.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or "=" not in line:
            i += 1
            continue
        key, _, val = line.partition("=")
        key = key.strip().lower().replace(" ", "_")
        sk = mapping.get(key)
        if not sk:
            i += 1
            continue
        val = val.strip()
        # برای پیام استارت/استاپ بقیه خطوط تا کلید بعدی را هم بگیر
        if sk in ("msg_start", "msg_stop", "allowed"):
            extra = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if "=" in nxt:
                    k2 = nxt.split("=", 1)[0].strip().lower().replace(" ", "_")
                    if k2 in mapping:
                        break
                extra.append(nxt)
                j += 1
            if extra:
                val = (val + "\n" + "\n".join(extra)).strip()
            i = j
        else:
            i += 1
        if sk in ("time_start", "time_stop") and not _parse_hhmm(val):
            await message.answer(f"❌ ساعت «{e(val)}» برای {sk} نامعتبر است.")
            continue
        SETTINGS[sk] = val
        changed.append(sk)
    if not changed:
        return await message.answer(
            "❌ چیزی تغییر نکرد.\n"
            "مثال:\n<code>time_start=08:00\ntime_stop=23:00\n"
            "msg_start=پیام کامل استارت\nخط دوم پیام\n"
            "msg_stop=پیام کامل استاپ</code>"
        )
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ ذخیره شد: <b>{', '.join(changed)}</b>\n"
        f"استارت <code>{SETTINGS['time_start']}</code> · استاپ <code>{SETTINGS['time_stop']}</code>\n\n"
        f"💬 استارت:\n<blockquote>{e(SETTINGS.get('msg_start', ''))[:500]}</blockquote>\n"
        f"💬 استاپ:\n<blockquote>{e(SETTINGS.get('msg_stop', ''))[:500]}</blockquote>",
        reply_markup=_timing_menu_keyboard(),
    )


@dp.callback_query(F.data.startswith("adm_photo:"))
async def admin_photo_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    which = callback.data.split(":")[1]  # start | stop | menu
    await callback.answer()
    await state.update_data(photo_which=which)
    label = {"start": "استارت", "stop": "استاپ", "menu": "منوی کاربری"}.get(which, which)
    await callback.message.answer(
        f"🖼 عکس <b>{label}</b> را همین الان بفرستید (یک عکس).\n"
        "برای حذف عکس فعلی بنویسید: <code>-</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_photo)


@dp.message(GameStates.adm_set_photo)
async def admin_set_photo(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    d = await state.get_data()
    which = d.get("photo_which", "start")
    key = {"start": "photo_start", "stop": "photo_stop", "menu": "photo_menu"}.get(which, "photo_start")
    label = {"start": "استارت", "stop": "استاپ", "menu": "منوی کاربری"}.get(which, which)
    back_kb = _timing_menu_keyboard() if which in ("start", "stop") else get_admin_inline_keyboard()
    if message.text and message.text.strip() in ("-", "—", "حذف", "delete", "none"):
        SETTINGS[key] = ""
        save_data(critical=True)
        await state.clear()
        return await message.answer(f"🗑 عکس {label} حذف شد.", reply_markup=back_kb)
    if not message.photo:
        return await message.answer("❌ لطفاً یک <b>عکس</b> بفرستید یا <code>-</code> برای حذف.")
    file_id = message.photo[-1].file_id
    SETTINGS[key] = file_id
    save_data(critical=True)
    await state.clear()
    await message.answer(f"✅ عکس {label} ذخیره شد.", reply_markup=back_kb)
    try:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=file_id,
            caption=f"🖼 پیش‌نمایش عکس {label}",
        )
    except Exception:
        pass


# ---------------- شهرهای اتو / آپ / واگذاری ----------------
def apply_stat_delta(city: str, deltas: dict, note: str = "") -> str:
    """
    اعمال تغییر روی stats شهر — فقط برای اتو/ادمین.
    متن کامل شیت حفظ می‌شود؛ فقط اعداد stats و یک لاگ در انتها اضافه می‌شود.
    دارایی را «بازنویسی کامل» نمی‌کند.
    """
    entry = CITY_ASSETS.get(city) or {"text": "", "stats": {}}
    stats = dict(entry.get("stats") or {})
    stats = normalize_stats_keys(stats)
    lines_log = []
    for k, delta in deltas.items():
        try:
            dlt = float(delta)
        except (TypeError, ValueError):
            continue
        old = float(stats.get(k) or 0)
        new = old + dlt
        if new < 0:
            new = 0
        stats[k] = new
        lines_log.append(f"{k}: {old:g} → {new:g} ({dlt:+g})")
    text = entry.get("text") or ""
    if note or lines_log:
        stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M") if TZ else datetime.now().strftime("%Y-%m-%d %H:%M")
        text = (
            text.rstrip()
            + f"\n\n———\n📝 تغییر اتو [{stamp}]\n"
            + (note + "\n" if note else "")
            + "\n".join(lines_log)
        )
    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "unlocked": list(entry.get("unlocked") or []),
        "changes": list(entry.get("changes") or []),
    }
    save_data(critical=True)
    return "\n".join(lines_log) or "—"


def apply_upgrade_levels(city: str, name: str, levels: int) -> tuple[bool, str]:
    """اعمال ارتقا روی stats اگر اتو باشد. هزینه از موجودی کم می‌شود، بازده اضافه می‌شود."""
    if not is_auto_city(city):
        return False, "اتو برای این شهر فعال نیست."
    t = UPGRADE_TABLE.get(name)
    if not t:
        return False, f"ساختمان «{name}» در جدول نیست."
    levels = max(1, min(int(levels or 1), int(t.get("max") or 10)))
    bag = normalize_stats_keys(get_city_asset_stats(city))
    stock = _bag_stock(bag)
    aff = max_affordable_levels(name, stock)
    if aff < levels:
        if aff <= 0:
            return False, "موجودی برای حتی ۱ سطح کافی نیست."
        levels = aff
    cd = cost_for_levels(name, levels)
    deltas = {}
    for key, lab in _RES_MAP:
        need = cd.get(key, 0)
        if need:
            # کم کردن هزینه
            if lab == "سکه":
                deltas["سکه"] = deltas.get("سکه", 0) - need
            elif lab == "جمعیت":
                pass  # نفر برای ساخت معمولاً از جمعیت کم نمی‌شود در این نسخه
            else:
                deltas[lab] = deltas.get(lab, 0) - need
    # بازده: به کلید ساختمان یا واحد بازده
    y = (t.get("yield") or 0) * levels
    yu = t.get("yunit") or ""
    if name in bag or name in UPGRADE_TABLE:
        # سطح تولید: افزایش عدد بازده ساختمان
        deltas[name] = deltas.get(name, 0) + y
    if yu in ("سکه",) and name in ("خزانه", "بندر", "تجارتخانه"):
        pass  # بازده هفتگی در آپ اعمال می‌شود نه فوری
    log = apply_stat_delta(city, deltas, note=f"ارتقا {name} ×{levels} سطح")
    return True, f"✅ {name}: {levels} سطح\n{log}"


def run_weekly_up_for_city(city: str) -> str:
    """اعمال بازدهی ساختمان‌ها (آپ) — فقط اتو."""
    if not is_auto_city(city):
        return f"⏭ {city}: اتو نیست"
    bag = normalize_stats_keys(get_city_asset_stats(city))
    deltas = {}
    # بازده خزانه/بندر/آشپزخانه/تولیدی‌ها از جدول
    for name, t in UPGRADE_TABLE.items():
        y = t.get("yield")
        yu = t.get("yunit") or ""
        if not y:
            continue
        # اگر ساختمان در stats هست یا بازده ثبت شده
        level_hint = float(bag.get(name) or 0)
        if level_hint <= 0 and name not in ("خزانه", "بندر", "آشپزخانه", "دهکده"):
            continue
        # فرض: مقدار ثبت‌شده ≈ بازده فعلی؛ آپ = افزودن همان بازده یک‌بار
        add = float(y)
        if level_hint > 0 and yu not in ("نفر", "فروند", "عراده"):
            add = level_hint  # استفاده از بازده فعلی شیت
        if yu == "سکه":
            deltas["سکه"] = deltas.get("سکه", 0) + add
        elif yu == "غذا":
            deltas["غذا"] = deltas.get("غذا", 0) + add
        elif yu in ("چوب", "سنگ", "آهن", "پوشاک", "باروت"):
            deltas[yu] = deltas.get(yu, 0) + add
        elif yu == "نفر" and name == "دهکده":
            deltas["جمعیت"] = deltas.get("جمعیت", 0) + add
    if not deltas:
        return f"ℹ️ {city}: بازده قابل‌اعمال نبود"
    log = apply_stat_delta(city, deltas, note="آپ هفتگی — بازدهی ساختمان‌ها")
    return f"✅ آپ {city}\n{log}"


@dp.callback_query(F.data == "adm_auto")
async def admin_auto_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    cities = sorted(all_known_cities(), key=lambda s: s.lower())
    builder = InlineKeyboardBuilder()
    for i, city in enumerate(cities[:40]):
        on = is_auto_city(city)
        mark = "✅" if on else "❌"
        short = city.rsplit("_", 1)[0] if "_" in city else city
        builder.row(_btn(f"{mark} {short}", f"auto_tog:{i}"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    n_on = sum(1 for c in cities if is_auto_city(c))
    await callback.message.answer(
        f"🤖 <b>شهرهای فول‌اتو (تست)</b>\n{DIV}\n"
        f"فعال: <b>{n_on}</b> / {len(cities)}\n"
        "فقط روی شهرهای ✅ ارتقا/آپ/تلفات از بات اعمال می‌شود.\n"
        "برای تولید روی تیک بزنید:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("auto_tog:"))
async def admin_auto_toggle(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    try:
        idx = int(callback.data.split(":")[1])
    except ValueError:
        return await callback.answer()
    cities = sorted(all_known_cities(), key=lambda s: s.lower())
    if idx < 0 or idx >= len(cities):
        return await callback.answer("نامعتبر", show_alert=True)
    city = cities[idx]
    if is_auto_city(city):
        # خاموش
        for k in list(AUTO_CITIES.keys()):
            if _norm_country_token(k) == _norm_country_token(city):
                AUTO_CITIES.pop(k, None)
        AUTO_CITIES.pop(city, None)
        save_data(critical=True)
        await callback.answer(f"خاموش: {city}")
    else:
        AUTO_CITIES[city] = True
        save_data(critical=True)
        await callback.answer(f"روشن: {city}")
    # رفرش منو
    return await admin_auto_menu(callback)


@dp.callback_query(F.data == "adm_run_up")
async def admin_run_up(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer("در حال آپ…")
    results = []
    for city in list(AUTO_CITIES.keys()):
        if AUTO_CITIES.get(city):
            results.append(run_weekly_up_for_city(city))
    if not results:
        return await callback.message.answer(
            "📭 هیچ شهر اتویی فعال نیست.",
            reply_markup=get_admin_inline_keyboard(),
        )
    body = f"♻️ <b>نتیجه آپ</b>\n{DIV}\n" + "\n\n".join(results[:20])
    await callback.message.answer(body[:4000], reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_transfer")
async def admin_transfer_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "🏙 <b>واگذاری شهر</b>\n{DIV}\n"
        "فرمت:\n"
        "<code>واگذاری از_شهر به_شهر</code>\n"
        "یا\n"
        "<code>transfer london_monarchist york_parliamentarian</code>\n\n"
        " fort از دارایی و گروه شهر مبدأ به مقصد منتقل می‌شود و ساید مقصد لحاظ می‌گردد.\n"
        "مثال: پس از فتح، شهر فتح‌شده را به نام فاتح ثبت کنید."
        .replace("{DIV}", DIV),
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.admin_transfer)


@dp.message(GameStates.admin_transfer)
async def admin_transfer_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    txt = (message.text or "").strip()
    txt = re.sub(r"^(واگذاری|transfer)\s*", "", txt, flags=re.I).strip()
    parts = re.split(r"\s+به\s+|\s+->\s+|\s+→\s+|\s+", txt)
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return await message.answer("❌ فرمت: <code>شهر_مبدا شهر_مقصد</code>")
    src, dst = parts[0], parts[1]
    msg = transfer_city(src, dst)
    await state.clear()
    await message.answer(msg, reply_markup=get_admin_inline_keyboard())


def transfer_city(src: str, dst: str) -> str:
    """انتقال دارایی و بازیکنان از src به dst (نام شهر مقصد)."""
    src_n = None
    for c in all_known_cities():
        if _norm_country_token(c) == _norm_country_token(src) or c.lower() == src.lower():
            src_n = c
            break
    if not src_n:
        src_n = src
    # دارایی
    if src_n in CITY_ASSETS:
        CITY_ASSETS[dst] = CITY_ASSETS.pop(src_n)
    # کدها
    for code, name in list(PLAYER_CODES.items()):
        if _norm_country_token(name) == _norm_country_token(src_n):
            PLAYER_CODES[code] = dst
    # کاربران
    for uid, u in authenticated_users.items():
        if _norm_country_token(u.get("country") or "") == _norm_country_token(src_n):
            u["country"] = dst
    # گروه‌ها
    for gid, g in GROUPS.items():
        if _norm_country_token(g.get("city") or "") == _norm_country_token(src_n):
            g["city"] = dst
    # اتو
    if is_auto_city(src_n):
        AUTO_CITIES.pop(src_n, None)
        AUTO_CITIES[dst] = True
    save_data(critical=True)
    return f"✅ واگذاری: <b>{e(src_n)}</b> → <b>{e(dst)}</b>"


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


@dp.callback_query(F.data.startswith("adm_broadcast_ts:"))
async def admin_broadcast_timing(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    kind = callback.data.split(":")[1]
    await callback.answer("در حال ارسال…")
    ok, fail, ch_ok = await _broadcast_timing_to_groups(kind, to_channel=True)
    label = "استارت" if kind == "start" else "استاپ"
    await callback.message.answer(
        f"📢 پیام {label} ارسال شد.\n"
        f"✅ گروه موفق: <b>{ok}</b> · ❌ ناموفق: <b>{fail}</b>\n"
        f"📣 کانال اصلی: {'✅' if ch_ok else '❌'}",
        reply_markup=_timing_menu_keyboard(),
    )


# ---------------- لیست تجار ----------------
@dp.callback_query(F.data == "adm_merchant")
async def admin_merchant_menu(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    body = format_merchant_catalog()
    en_lbl = "✅ فعال" if MERCHANT_ENABLED else "❌ غیرفعال"
    builder = InlineKeyboardBuilder()
    builder.row(_btn(f"🔌 تجارت با تجار: {en_lbl}", "adm_merchant_toggle"))
    builder.row(_btn("📝 تنظیم لیست سقف", "adm_merchant_set", "primary"))
    builder.row(_btn("🏷 قیمت هر کالا جداگانه", "adm_merchant_item_prices", "success"))
    builder.row(
        _btn(f"💰 خرید پیش‌فرض {MERCHANT_BUY_PRICE:g}", "adm_merchant_price:buy"),
        _btn(f"💰 فروش پیش‌فرض {MERCHANT_SELL_PRICE:g}", "adm_merchant_price:sell"),
    )
    builder.row(_btn(f"🎚 باف پیش‌فرض ({MERCHANT_BUFF_DEFAULT:g}%)", "adm_merchant_buff"))
    builder.row(_btn("🗑 پاک کردن لیست", "adm_merchant_clear", "danger"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"🛒 <b>لیست تجار</b>\n{DIV}\n{body}\n\n"
        f"وضعیت: <b>{en_lbl}</b>\n"
        f"پیش‌فرض خرید/فروش: <b>{MERCHANT_BUY_PRICE:g}</b> / <b>{MERCHANT_SELL_PRICE:g}</b>\n"
        f"🎚 باف: <b>{MERCHANT_BUFF_DEFAULT:g}%</b>",
        reply_markup=builder.as_markup(),
    )


MERCHANT_ARRIVE_LINES = [
    "🛒 کاروان تجار از راه‌های دوردست رسید.\nبازار گشوده شد؛ معامله آزاد است.",
    "⚜️ تجار با بارِ کالا به شهر درآمدند.\nساعتِ خرید و فروش فرا رسیده است.",
    "🌊 کشتی‌های بازرگانی لنگر انداختند.\nتجار حاضرند؛ بازار آمادهٔ معامله است.",
    "🔔 ناقوس بازار نواخته شد.\nکاروان تجار در شهر ایستاده است.",
]
MERCHANT_LEAVE_LINES = [
    "🌙 کاروان تجار بار بست و راه گرفت.\nبازار تا بازگشت بعدی بسته است.",
    "🕊 تجار آخرین معامله را بستند و رفتند.\nتجارت با تجار تا اطلاع بعدی متوقف است.",
    "🌊 بادبان‌ها بالا رفت؛ تجار بندر را ترک کردند.\nبازار بازرگانی خاموش شد.",
    "🔕 چادرهای بازار جمع شد.\nتجار رفتند؛ معامله تا دیدار بعد بسته است.",
]


def merchant_guide_text() -> str:
    cat = format_merchant_catalog()
    return (
        f"{cat}\n\n"
        f"📖 <b>راهنما</b>\n"
        "منو → 🐪 تجارت → تجارت با تجار → خرید یا فروش\n"
        "لیست کالا: <code>چوب: 50</code> سپس باف و تایید."
    )


async def announce_merchants_to_channel(enabled: bool):
    """اعلان رسمی و کوتاه در کانال اصلی هنگام فعال/غیرفعال شدن تجار."""
    if not CHANNEL_ID:
        return
    if enabled:
        line = random.choice(MERCHANT_ARRIVE_LINES)
        text = f"{line}\n\n{merchant_guide_text()}"
    else:
        line = random.choice(MERCHANT_LEAVE_LINES)
        text = line
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text[:4000])
    except Exception:
        logging.exception("اعلان تجار در کانال ناموفق")


@dp.callback_query(F.data == "adm_merchant_toggle")
async def admin_merchant_toggle(callback: types.CallbackQuery):
    global MERCHANT_ENABLED
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    MERCHANT_ENABLED = not MERCHANT_ENABLED
    save_data(critical=True)
    await callback.answer("✅ فعال شد" if MERCHANT_ENABLED else "❌ غیرفعال شد")
    # اعلان کانال اصلی
    try:
        await announce_merchants_to_channel(MERCHANT_ENABLED)
    except Exception:
        pass
    return await admin_merchant_menu(callback, None)


@dp.callback_query(F.data == "adm_merchant_item_prices")
async def admin_merchant_item_prices(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    if not MERCHANT_LIMITS:
        return await callback.message.answer("❌ اول لیست سقف را تنظیم کنید.")
    builder = InlineKeyboardBuilder()
    for name in MERCHANT_LIMITS:
        buy = item_buy_price(name)
        sell = item_sell_price(name)
        builder.row(_btn(f"{name} 🛒{buy:g}/💰{sell:g}", f"adm_item_price:{name}"))
    builder.row(_btn("🔙 بازگشت", "adm_merchant"))
    await callback.message.answer(
        "🏷 کالا را انتخاب کنید تا قیمت خرید/فروش جداگانه ست شود:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("adm_item_price:"))
async def admin_item_price_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    name = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(price_item=name)
    buy = item_buy_price(name)
    sell = item_sell_price(name)
    await callback.message.answer(
        f"🏷 قیمت <b>{e(name)}</b>\n"
        f"فعلی — خرید: <b>{buy:g}</b> · فروش: <b>{sell:g}</b>\n\n"
        "بفرستید به صورت:\n<code>خرید فروش</code>\n"
        "مثال: <code>5 2</code> یا <code>خرید:5 فروش:2</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_price)
    await state.update_data(price_which="item")


@dp.callback_query(F.data == "adm_merchant_set")
async def admin_merchant_set(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "📝 کل لیست تجار را بفرستید (همان فرمت بازی):\n"
        "<code>⚜️ لیست …\n|🪵|~| چوب | : 300\n|🔩|~| آهن | : 300</code>\n\n"
        "اعداد = سقف مجاز خرید.\nمتن کامل برای نمایش به پلیر ذخیره می‌شود.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_merchant)


@dp.message(GameStates.adm_set_merchant)
async def admin_merchant_save(message: types.Message, state: FSMContext):
    global MERCHANT_LIST_TEXT
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    raw = (message.text or "").strip()
    bag, err = parse_goods_list(raw)
    if err:
        return await message.answer(f"❌ {err}")
    MERCHANT_LIMITS.clear()
    MERCHANT_LIMITS.update(bag)
    MERCHANT_LIST_TEXT = raw
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ لیست تجار ذخیره شد ({len(MERCHANT_LIMITS)} کالا):\n{format_goods(MERCHANT_LIMITS)}\n\n"
        f"💰 خرید: {MERCHANT_BUY_PRICE:g} · فروش: {MERCHANT_SELL_PRICE:g}",
        reply_markup=get_admin_inline_keyboard(),
    )


@dp.callback_query(F.data.startswith("adm_merchant_price:"))
async def admin_merchant_price_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    which = callback.data.split(":")[1]  # buy | sell
    await callback.answer()
    await state.update_data(price_which=which)
    label = "خرید" if which == "buy" else "فروش"
    cur = MERCHANT_BUY_PRICE if which == "buy" else MERCHANT_SELL_PRICE
    await callback.message.answer(
        f"💰 قیمت <b>{label}</b> هر عدد کالا (سکه) — فعلی: <b>{cur:g}</b>\n"
        "عدد جدید را بفرستید:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_price)


@dp.message(GameStates.adm_set_price)
async def admin_merchant_price_save(message: types.Message, state: FSMContext):
    global MERCHANT_BUY_PRICE, MERCHANT_SELL_PRICE
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    raw = normalize_digits(message.text or "").strip()
    d = await state.get_data()
    which = d.get("price_which", "buy")

    # قیمت جداگانه یک کالا: "5 2" یا "خرید:5 فروش:2"
    if which == "item":
        name = d.get("price_item") or ""
        nums = re.findall(r"[\d.]+", raw)
        if len(nums) < 2:
            return await message.answer("❌ دو عدد بفرستید: <code>خرید فروش</code> مثال <code>5 2</code>")
        try:
            buy_v, sell_v = float(nums[0]), float(nums[1])
        except ValueError:
            return await message.answer("❌ عدد نامعتبر.")
        if buy_v < 0 or sell_v < 0:
            return await message.answer("❌ قیمت منفی مجاز نیست.")
        MERCHANT_PRICES[name] = {"buy": buy_v, "sell": sell_v}
        save_data(critical=True)
        await state.clear()
        return await message.answer(
            f"✅ {e(name)} — خرید <b>{buy_v:g}</b> · فروش <b>{sell_v:g}</b>",
            reply_markup=get_admin_inline_keyboard(),
        )

    try:
        val = float(raw)
    except ValueError:
        return await message.answer("❌ عدد نامعتبر.")
    if val < 0:
        return await message.answer("❌ قیمت منفی مجاز نیست.")
    if which == "sell":
        MERCHANT_SELL_PRICE = val
        label = "فروش پیش‌فرض"
    else:
        MERCHANT_BUY_PRICE = val
        label = "خرید پیش‌فرض"
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ قیمت {label}: <b>{val:g}</b> سکه",
        reply_markup=get_admin_inline_keyboard(),
    )


@dp.callback_query(F.data == "adm_merchant_buff")
async def admin_merchant_buff(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        f"🎚 باف پیش‌فرض فعلی: <b>{MERCHANT_BUFF_DEFAULT:g}%</b>\n"
        "عدد جدید را بفرستید (مثلاً <code>15</code> یا <code>-10</code>):",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_buff)


@dp.message(GameStates.adm_set_buff)
async def admin_merchant_buff_save(message: types.Message, state: FSMContext):
    global MERCHANT_BUFF_DEFAULT
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    raw = normalize_digits(message.text or "").strip().replace("%", "")
    try:
        MERCHANT_BUFF_DEFAULT = float(raw)
    except ValueError:
        return await message.answer("❌ عدد نامعتبر.")
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ باف پیش‌فرض: <b>{MERCHANT_BUFF_DEFAULT:g}%</b>",
        reply_markup=get_admin_inline_keyboard(),
    )


@dp.callback_query(F.data == "adm_merchant_clear")
async def admin_merchant_clear(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    MERCHANT_LIMITS.clear()
    save_data(critical=True)
    await callback.answer("پاک شد")
    await callback.message.answer("🗑 لیست تجار خالی شد.", reply_markup=get_admin_inline_keyboard())


# ---------------- لیدربورد قدرت ----------------
def _leaderboard_keyboard(scope: str = "city", category: str = "all"):
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("🏙 شهرها", "lb:city:all", "primary" if scope == "city" else None),
        _btn("🏴 سایدها", "lb:side:all", "primary" if scope == "side" else None),
    )
    builder.row(
        _btn("💰 اقتصادی", f"lb:{scope}:econ", "success" if category == "econ" else None),
        _btn("⚔️ نظامی", f"lb:{scope}:mil", "danger" if category == "mil" else None),
        _btn("⚓️ دریایی", f"lb:{scope}:nav", "primary" if category == "nav" else None),
    )
    builder.row(_btn("📊 کل قدرت", f"lb:{scope}:all", "success" if category == "all" else None))
    builder.row(
        _btn("📢 اعلام در کانال", f"lb_announce:{scope}:{category}", "success"),
    )
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    return builder.as_markup()


@dp.callback_query(F.data == "adm_leaderboard")
async def admin_leaderboard_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    text = format_leaderboard("city", "all")
    await callback.message.answer(
        text[:4000],
        reply_markup=_leaderboard_keyboard("city", "all"),
    )


@dp.callback_query(F.data.startswith("lb:"))
async def admin_leaderboard_filter(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer()
    scope, category = parts[1], parts[2]
    if scope not in ("city", "side") or category not in ("all", "econ", "mil", "nav"):
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer()
    text = format_leaderboard(scope, category)
    try:
        await callback.message.edit_text(text[:4000], reply_markup=_leaderboard_keyboard(scope, category))
    except Exception:
        await callback.message.answer(text[:4000], reply_markup=_leaderboard_keyboard(scope, category))


@dp.callback_query(F.data.startswith("lb_announce:"))
async def admin_leaderboard_announce(callback: types.CallbackQuery):
    """ارسال رسمی لیدربورد به کانال اصلی (+ عکس تصادفی در صورت وجود آرت)."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer()
    scope, category = parts[1], parts[2]
    if scope not in ("city", "side") or category not in ("all", "econ", "mil", "nav"):
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer("در حال ارسال…")
    text = format_leaderboard(scope, category, announce=True)
    if not CHANNEL_ID:
        return await callback.message.answer("❌ CHANNEL_ID تنظیم نشده.")
    sent = False
    # تلاش برای عکس مرتبط (جنگ/لشکرکشی عمومی)
    try:
        art_kind = "war" if category == "mil" else ("campaign" if category == "nav" else "siege")
        entry = pick_art(art_kind, "all", None) if "pick_art" in dir() else None
        if entry is None:
            # fallback از ART dict
            for k, v in (ART or {}).items():
                if isinstance(v, dict):
                    for lst in v.values():
                        if lst:
                            entry = random.choice(lst)
                            break
                if entry:
                    break
        if entry:
            await send_art(CHANNEL_ID, entry, text, None)
            sent = True
    except Exception:
        logging.exception("ارسال آرت لیدربورد")
    if not sent:
        try:
            await bot.send_message(chat_id=CHANNEL_ID, text=text[:4000])
            sent = True
        except Exception:
            logging.exception("ارسال متن لیدربورد به کانال")
    if sent:
        await callback.message.answer(
            f"✅ لیدربورد در کانال اصلی اعلام شد.\n"
            f"🏙/🏴 {scope} · 📊 {category}",
            reply_markup=_leaderboard_keyboard(scope, category),
        )
    else:
        await callback.message.answer(
            "❌ ارسال به کانال ناموفق بود. دسترسی ربات به کانال را چک کنید.",
            reply_markup=_leaderboard_keyboard(scope, category),
        )


# ---------------- لیدرها ----------------
@dp.callback_query(F.data == "adm_leaders")
async def admin_leaders_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    lines = [f"👑 <b>لیدرهای ساید</b>\n{DIV}\n"]
    for side in FACTIONS:
        flag, title = FACTION_META[side]
        ids = LEADERS.get(side) or []
        lines.append(f"{flag} <b>{title}</b> ({len(ids)}/3)")
        if not ids:
            lines.append("  — خالی —")
        for uid in ids:
            lines.append(f"  • {mention(uid, city_of(uid))} <code>{uid}</code>")
        lines.append("")
    lines.append(
        "برای افزودن: روی پیام کاربر <b>ریپلای</b> کنید و بنویسید:\n"
        "<code>ست لیدر مونارشیست</code> / <code>ست لیدر پارلمانری</code>\n"
        "<code>/set leader france</code>\n"
        "برای حذف: <code>حذف لیدر</code> (ریپلای)"
    )
    await callback.message.answer("\n".join(lines), reply_markup=get_admin_inline_keyboard())


# ---------------- دارایی در پنل ادمین ----------------
@dp.callback_query(F.data == "adm_assets")
async def admin_assets_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    for side in FACTIONS:
        flag, title = FACTION_META[side]
        n = sum(1 for c in CITY_ASSETS if country_key(c) == side)
        builder.row(_btn(f"{flag} {title} ({n} شهر)", f"adm_assets_side:{side}"))
    builder.row(_btn("🌐 جمع کل همه سایدها", "adm_assets_side:all"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"📦 <b>دارایی قلمروها</b>\n{DIV}\n"
        "ساید را برای مشاهده جمع انتخاب کنید.\n"
        "ثبت دارایی از گروه شهر با <code>ست دارایی</code> انجام می‌شود.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("adm_assets_side:"))
async def admin_assets_side(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    side = callback.data.split(":")[1]
    await callback.answer()
    if side == "all":
        parts = []
        for s in FACTIONS:
            parts.append(format_realm_view(s))
        text = "\n\n".join(parts)
    else:
        if side not in FACTIONS:
            return await callback.message.answer("❌ ساید نامعتبر.", reply_markup=get_admin_inline_keyboard())
        text = format_realm_view(side)
        # جزئیات عددی هر شهر همان ساید
        _, by_city, _ = realm_breakdown(side)
        if by_city:
            chunks = [text, ""]
            for city, st in by_city.items():
                chunks.append(format_assets_block(f"{city} (اعداد)", st))
            text = "\n".join(chunks)
    await callback.message.answer(text[:4000], reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_help")
async def admin_help(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(ADMIN_HELP_TEXT, reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_manage")
async def admin_manage(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer("⚙️ <b>مدیریت شهرها و دسترسی‌ها</b>\n\nیکی از گزینه‌ها را انتخاب کنید:", reply_markup=get_manage_keyboard())


async def show_revoke_list(message: types.Message):
    players = [(uid, u) for uid, u in authenticated_users.items() if u.get("role") == "player"]
    if not players:
        return await message.answer("👥 هنوز هیچ فرماندهای وارد بازی نشده است.", reply_markup=get_manage_keyboard())
    builder = InlineKeyboardBuilder()
    for uid, u in players:
        builder.button(text=f"❌ {u.get('country', '؟')} | {uid}", callback_data=f"revoke:{uid}")
    builder.button(text="🔙 بازگشت", callback_data="adm_manage")
    builder.adjust(1)
    await message.answer("👤 روی هر شهر بزنید تا دسترسی فرمانده‌ی آن حذف شود:", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "adm_revoke_list")
async def admin_revoke_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await show_revoke_list(callback.message)


@dp.callback_query(F.data.startswith("revoke:"))
async def handle_revoke_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    p_id = int(callback.data.split(":")[1])
    u = authenticated_users.get(p_id)
    if not u:
        return await callback.answer("این فرمانده دیگر فعال نیست.", show_alert=True)
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ بله، حذف شود", callback_data=f"revoke_yes:{p_id}")
    builder.button(text="🔙 انصراف", callback_data="adm_revoke_list")
    builder.adjust(1)
    await callback.message.answer(
        f"⚠️ دسترسی فرمانده‌ی شهر <b>{e(u.get('country', '؟'))}</b> (آیدی <code>{p_id}</code>) حذف شود؟\n"
        f"کد این شهر (<code>{e(u.get('code', '-'))}</code>) باطل می‌شود و ربات دیگر او را نمی‌شناسد.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("revoke_yes:"))
async def handle_revoke_player(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    p_id = int(callback.data.split(":")[1])
    u = authenticated_users.pop(p_id, None)
    all_players.discard(p_id)
    if not u:
        await callback.answer("این فرمانده دیگر فعال نیست.", show_alert=True)
        return await show_revoke_list(callback.message)

    PLAYER_CODES.pop(u.get("code"), None)   # کد باطل می‌شود
    save_data()

    try:                                     # وضعیت گفتگوی بازیکن پاک می‌شود
        await user_fsm(p_id).clear()
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=p_id,
            text=f"⚠️ دسترسی شما به عنوان فرمانده‌ی شهر <b>{e(u.get('country', '؟'))}</b> توسط ادمین لغو شد و کد شما باطل گردید.",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        pass

    await callback.answer("دسترسی فرمانده حذف شد.")
    await callback.message.answer(
        f"✅ دسترسی فرمانده‌ی شهر <b>{e(u.get('country', '؟'))}</b> حذف و کد <code>{e(u.get('code', '-'))}</code> باطل شد.\n"
        "برای این شهر کد تازه‌ای بخواهید، از «➕ افزودن شهر و ساخت کد» استفاده کنید.",
        reply_markup=get_manage_keyboard(),
    )


@dp.callback_query(F.data == "adm_del_city_list")
async def admin_del_city_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    if not PLAYER_CODES:
        return await callback.message.answer("شهری ثبت نشده.", reply_markup=get_manage_keyboard())
    builder = InlineKeyboardBuilder()
    for code, city in sorted(PLAYER_CODES.items(), key=lambda kv: str(kv[1]).lower()):
        uid = code_owner(code)
        tag = f" · ID:{uid}" if uid else ""
        label = f"🗑 {city} | {code}{tag}"
        if len(label) > 60:
            label = label[:58] + "…"
        builder.row(_btn(label, f"delcity:{code}", "danger"))
    builder.row(_btn("🔙 بازگشت", "adm_manage"))
    await callback.message.answer(
        f"🏙 <b>حذف شهر</b>\n{DIV}\nروی مورد اضافی بزنید تا حذف شود:\n"
        f"(کد + آیدی فرمانده اگر باشد نمایش داده می‌شود)",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("delcity:"))
async def admin_del_city_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    code = callback.data.split(":", 1)[1]
    city = PLAYER_CODES.get(code)
    if not city:
        return await callback.answer("این شهر دیگر نیست.", show_alert=True)
    await callback.answer()
    uid = code_owner(code)
    builder = InlineKeyboardBuilder()
    builder.row(_btn("✅ بله حذف شود", f"delcityyes:{code}", "danger"))
    builder.row(_btn("🔙 انصراف", "adm_del_city_list"))
    extra = f"\n👤 فرمانده: {mention(uid)} · <code>{uid}</code>" if uid else "\n👤 فرمانده: —"
    await callback.message.answer(
        f"⚠️ حذف شهر <b>{e(city)}</b>\n🔑 کد: <code>{e(code)}</code>{extra}\n\n"
        "کد باطل و فرمانده (در صورت وجود) هم حذف می‌شود.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("delcityyes:"))
async def admin_del_city_yes(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    code = callback.data.split(":", 1)[1]
    city = PLAYER_CODES.pop(code, None)
    if not city:
        await callback.answer("از قبل حذف شده.", show_alert=True)
        return
    # حذف فرمانده مرتبط
    uid = None
    for u_id, u in list(authenticated_users.items()):
        if u.get("role") == "player" and u.get("code") == code:
            uid = u_id
            authenticated_users.pop(u_id, None)
            all_players.discard(u_id)
            break
    # قطع گروه‌های این شهر
    for gid, g in list(GROUPS.items()):
        if (g.get("code") == code) or (g.get("city") or "").lower() == str(city).lower():
            GROUPS.pop(gid, None)
    save_data(critical=True)
    await callback.answer("حذف شد")
    msg = f"✅ شهر <b>{e(city)}</b> حذف شد.\n🔑 کد باطل: <code>{e(code)}</code>"
    if uid:
        msg += f"\n👤 فرمانده <code>{uid}</code> هم حذف شد."
    await callback.message.answer(msg, reply_markup=get_manage_keyboard())


@dp.callback_query(F.data == "adm_add_city")
async def admin_add_city_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "👑 <b>مالک محترم</b> لطفا <b>نام شهر و کشور</b> پلیر را مانند فرمت (<code>آمیان_فرانسه</code> یا <code>york_england</code>) وارد کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.admin_add_city)


@dp.message(GameStates.admin_add_city)
async def admin_add_city_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name:
        return await message.answer("❌ نام شهر را به صورت متن ارسال کنید:")
    parts = name.split("_")
    if len(parts) < 2 or not parts[0].strip() or not parts[-1].strip():
        return await message.answer("❌ فرمت درست نیست. مانند (آمیان_فرانسه) یا (york_england) وارد کنید:")
    if len(name) > 60:
        return await message.answer("❌ نام خیلی طولانی است. کوتاه‌تر بنویسید:")
    if any(n.strip().lower() == name.lower() for n in PLAYER_CODES.values()):
        return await message.answer("❌ این شهر از قبل ثبت شده است. نام دیگری بفرستید:")

    code = gen_code()
    PLAYER_CODES[code] = name
    save_data()
    await message.answer(
        f"✅ شهر <b>{e(name)}</b> اضافه شد.\n🔑 کد ورود: <code>{e(code)}</code>\n\n"
        "این کد را برای فرمانده‌ی همان شهر بفرستید.",
        reply_markup=get_manage_keyboard(),
    )
    await state.clear()


@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer("⚡️ منوی اصلی مدیریت:", reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_logout")
async def admin_logout(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    authenticated_users.pop(callback.from_user.id, None)
    await callback.message.answer("از پنل مدیریت خارج شدید. برای ورود دوباره /start بزنید.", reply_markup=ReplyKeyboardRemove())
    await state.clear()


# ======================================================================
#                           ۱. لشکرکشی
# ======================================================================
async def ask_type(message: types.Message, kind):
    await message.answer(f"🧭 سرورم لطفا <b>نوع {KIND_NOUN[kind]}</b> خود را تعیین کنید. 👇", reply_markup=get_type_keyboard(kind))


async def start_campaign(message: types.Message, state: FSMContext):
    await ask_type(message, "campaign")


@dp.callback_query(F.data.startswith("mtype:"))
async def handle_type_pick(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not is_player(uid):
        return await callback.answer("❌ دسترسی شما لغو شده است یا وارد ربات نشده‌اید (/start).", show_alert=True)
    if callback.message and callback.message.chat.type == "private":
        return await callback.answer("❌ این دستور فقط در گروه شهر شما قابل اجراست.", show_alert=True)
    parts = callback.data.split(":")
    if parts[1] == "back":
        await callback.answer()
        try:
            await callback.message.delete()
        except Exception:
            pass
        return await go_menu(callback.message, state)
    if len(parts) != 3 or parts[1] not in KIND_NOUN or parts[2] not in MTYPES:
        return await callback.answer()
    kind, mtype = parts[1], parts[2]
    await callback.answer()
    try:                                     # دکمه‌ها برداشته می‌شوند و انتخاب نمایش داده می‌شود
        await callback.message.edit_text(f"✅ نوع {KIND_NOUN[kind]}: <b>{MTYPE_EMOJI[mtype]} {MTYPES[mtype]}</b>")
    except Exception:
        pass
    await state.clear()
    await state.update_data(kind=kind, mtype=mtype)
    if kind == "campaign":
        await callback.message.answer(
            CAMP_ORIGIN_PROMPT + "\n\n📋 از منوی شهر انتخاب کنید یا ورود دستی:",
            reply_markup=get_cities_keyboard("camp_origin"),
        )
        await state.set_state(GameStates.camp_origin)
    else:
        await callback.message.answer(
            ORDERS[kind]["ask_target"] + "\n\n📋 از منوی شهر انتخاب کنید یا ورود دستی:",
            reply_markup=get_cities_keyboard("order_target"),
        )
        await state.set_state(GameStates.order_target)


async def _set_city_field(message: types.Message, state: FSMContext, field: str, value: str):
    """اعمال شهر انتخاب‌شده/دستی در فلوی لشکرکشی، هدف، تجارت، ست‌گپ."""
    if field == "grp_city":
        return await _link_group_to_city(message, state, value)
    if field == "camp_origin":
        await state.update_data(origin=value)
        await message.answer(
            f"✅ مبدا: <b>{e(value)}</b>\n\n🎯 حالا <b>مقصد</b> را انتخاب کنید:",
            reply_markup=get_cities_keyboard("camp_dest"),
        )
        await state.set_state(GameStates.camp_dest)
    elif field == "camp_dest":
        await state.update_data(dest=value)
        await message.answer(
            f"✅ مقصد: <b>{e(value)}</b>\n\n📊 آمار لشکریان را <b>تفکیک‌شده</b> بنویسید "
            "(ریپلای به این پیام):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.camp_stats)
    elif field == "order_target":
        await state.update_data(target=value)
        d = await state.get_data()
        await message.answer(
            f"✅ هدف: <b>{e(value)}</b>\n\n" + ORDERS[d["kind"]]["ask_stats"] + "\n\n↩️ ریپلای کنید.",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.order_stats)
    elif field == "trade_origin":
        await state.update_data(origin=value)
        await message.answer(
            f"✅ مبدا تجارت: <b>{e(value)}</b>\n\n🎯 <b>مقصد تجارت</b> را انتخاب کنید:",
            reply_markup=get_cities_keyboard("trade_dest"),
        )
        await state.set_state(GameStates.trade_dest)
    elif field == "trade_dest":
        await state.update_data(dest=value)
        await message.answer(
            f"✅ مقصد: <b>{e(value)}</b>\n\n"
            "🧭 مسیر حرکت کاروان <b>زمینی</b> است یا <b>دریایی</b>؟",
            reply_markup=get_trade_mtype_keyboard(),
        )
        await state.set_state(GameStates.trade_mtype)


@dp.callback_query(F.data.startswith("cityfac:"))
async def handle_city_faction(callback: types.CallbackQuery, state: FSMContext):
    """انتخاب کشور → نمایش شهرهای همان کشور (ویرایش همان پیام)."""
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer()
    field, faction = parts[1], parts[2]
    # ست‌گپ فقط ادمین؛ بقیه فقط پلیر
    if field == "grp_city":
        if not is_admin(callback.from_user.id):
            return await callback.answer("❌ فقط ادمین.", show_alert=True)
    elif not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    await callback.answer()
    titles = {
        "camp_origin": "📍 مبدا — شهر را انتخاب کنید",
        "camp_dest": "🎯 مقصد — شهر را انتخاب کنید",
        "order_target": "🎯 هدف — شهر را انتخاب کنید",
        "trade_origin": "📍 مبدا تجارت — شهر را انتخاب کنید",
        "trade_dest": "🎯 مقصد تجارت — شهر را انتخاب کنید",
        "grp_city": "🏙 شهر این گروه را انتخاب کنید",
    }
    try:
        await callback.message.edit_text(
            titles.get(field, "شهر را انتخاب کنید:"),
            reply_markup=get_cities_keyboard(field, faction=faction, page=0),
        )
    except Exception:
        await callback.message.answer(
            titles.get(field, "شهر را انتخاب کنید:"),
            reply_markup=get_cities_keyboard(field, faction=faction, page=0),
        )


@dp.callback_query(F.data.startswith("cityfacback:"))
async def handle_city_fac_back(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    await callback.answer()
    try:
        await callback.message.edit_text(
            "🌍 ابتدا <b>کشور</b> را انتخاب کنید:",
            reply_markup=get_country_keyboard(field),
        )
    except Exception:
        await callback.message.answer("🌍 کشور را انتخاب کنید:", reply_markup=get_country_keyboard(field))


@dp.callback_query(F.data.startswith("citypick:"))
async def handle_city_pick(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    # citypick:field:faction:idx
    if len(parts) != 4:
        return await callback.answer()
    field, faction, idx_s = parts[1], parts[2], parts[3]
    if field == "grp_city":
        if not is_admin(callback.from_user.id):
            return await callback.answer("❌ فقط ادمین.", show_alert=True)
    elif not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    try:
        idx = int(idx_s)
    except ValueError:
        return await callback.answer()
    name = city_by_index(idx, faction)
    if not name:
        return await callback.answer("شهر پیدا نشد.", show_alert=True)
    await callback.answer(f"✅ {name}")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _set_city_field(callback.message, state, field, name)


@dp.callback_query(F.data.startswith("citypage:"))
async def handle_city_page(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    # citypage:field:faction:page
    if len(parts) != 4:
        return await callback.answer()
    field, faction, page_s = parts[1], parts[2], parts[3]
    try:
        page = int(page_s)
    except ValueError:
        return await callback.answer()
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_cities_keyboard(field, faction=faction, page=page)
        )
    except Exception:
        await callback.message.answer(
            "📋 انتخاب شهر:",
            reply_markup=get_cities_keyboard(field, faction=faction, page=page),
        )


@dp.callback_query(F.data.startswith("citymanual:"))
async def handle_city_manual(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    await callback.answer()
    prompts = {
        "camp_origin": "📍 مبدا را دستی بنویسید (مثال: <code>london_england</code>) — ریپلای کنید:",
        "camp_dest": "🎯 مقصد را دستی بنویسید — ریپلای کنید:",
        "order_target": "🎯 شهر هدف را دستی بنویسید — ریپلای کنید:",
        "trade_origin": "📍 مبدا تجارت را دستی بنویسید — ریپلای کنید:",
        "trade_dest": "🎯 مقصد تجارت را دستی بنویسید — ریپلای کنید:",
        "grp_city": "🏙 نام شهر را دستی بنویسید (مثال: <code>کمبریج_انگلیس</code>) — ریپلای کنید:",
    }
    try:
        await callback.message.edit_text(prompts.get(field, "متن را بنویسید:"))
    except Exception:
        pass
    await callback.message.answer(prompts.get(field, "متن را بنویسید:"), reply_markup=get_back_keyboard())


@dp.callback_query(F.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer()


@dp.message(GameStates.camp_origin)
async def process_camp_origin(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "camp_origin", txt)


@dp.message(GameStates.camp_dest)
async def process_camp_dest(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "camp_dest", txt)


@dp.message(GameStates.camp_stats)
async def process_camp_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(stats=txt)
    await message.answer(
        "⏳ <b>زمان رسیدن</b> را بفرستید:\n"
        "• ساعت: <code>12:00</code>\n"
        "• یا دقیقه از الان: <code>45</code> (مثلاً ۹:۳۱ + ۴۵ → ۱۰:۱۶)\n"
        "• چند زمان: <code>12:00,14:30</code>\n↩️ ریپلای کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.camp_time)


@dp.message(GameStates.camp_time)
async def process_camp_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    parsed, err = parse_player_time(txt)
    if err:
        return await message.answer(
            f"❌ {err}\n\nمثال: <code>12:00</code> یا <code>45</code> (یعنی ۴۵ دقیقه دیگر)\n"
            "چند زمان: <code>12:00,14:30</code>"
        )
    await state.update_data(time=parsed)
    d = await state.get_data()
    # ذخیره مستقل از FSM تا دکمه تایید حتماً کار کند
    pending_confirms[message.from_user.id] = {
        "kind": "campaign",
        "data": dict(d),
        "chat_id": message.chat.id,
    }
    await message.answer(
        f"🧭 نوع لشکرکشی: <b>{mtype_tag(d)}</b>\n{DIV}\n\n"
        f"👑 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از اعزام لشکریان خود از مبدا <b>{e(d['origin'])}</b> 📍 "
        f"به مقصد <b>{e(d['dest'])}</b> 🎯 با آمار:\n<blockquote>{e(d['stats'])}</blockquote>\n"
        f"⏳ و زمان رسیدن <b>{e(d['time'])}</b> موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.camp_confirm)


async def _finish_campaign(callback: types.CallbackQuery, state: FSMContext, d: dict):
    user_id = callback.from_user.id
    city = city_of(user_id)
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


async def start_siege(message: types.Message, state: FSMContext):
    await ask_type(message, "siege")


async def start_war(message: types.Message, state: FSMContext):
    await ask_type(message, "war")


@dp.callback_query(F.data.startswith("menu:"))
async def handle_menu_click(callback: types.CallbackQuery, state: FSMContext):
    kind = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    if kind == "close":
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    if kind == "home":
        await callback.answer()
        return await go_menu(callback.message, state, user_id=uid)
    # منوی نظامی
    if kind == "military":
        await callback.answer()
        try:
            await callback.message.edit_text(
                f"⚔️ <b>منوی نظامی</b>\n{DIV}\nلشکرکشی · جنگ · محاصره",
                reply_markup=get_military_menu_keyboard(),
            )
        except Exception:
            await callback.message.answer(
                f"⚔️ <b>منوی نظامی</b>\n{DIV}\nلشکرکشی · جنگ · محاصره",
                reply_markup=get_military_menu_keyboard(),
            )
        return
    # منوی اقتصادی — دارایی + دکمه‌ها
    if kind == "economy":
        await callback.answer()
        return await open_economy_menu(callback, state)
    if kind == "assets":
        await callback.answer()
        return await start_asset_view(callback, state)
    if kind == "advise":
        await callback.answer()
        return await start_upgrade_advise(callback, state)
    if kind == "upgrade":
        await callback.answer()
        return await start_auto_upgrade(callback, state)
    if kind == "asset_edit":
        if not is_admin(uid):
            return await callback.answer("❌ فقط ادمین.", show_alert=True)
        await callback.answer()
        await callback.message.answer(
            "✏️ <b>تغییر دارایی</b>\n"
            "در گروه شهر بنویسید:\n"
            "<code>ست دارایی</code> (ریپلای روی شیت)\n"
            "یا <code>/ثبت تغییر دارایی</code>\n\n"
            "برای تلفات/رول: متن کامل شیت جدید را بفرستید.",
            reply_markup=get_inline_back_row("menu:economy"),
        )
        return
    if not is_player(uid):
        return await callback.answer("❌ این دستور برای شما نیست.", show_alert=True)
    if callback.message and callback.message.chat.type == "private":
        return await callback.answer("❌ این دستور فقط در گروه شهر شما قابل اجراست.", show_alert=True)
    await callback.answer()
    handlers = {
        "campaign": start_campaign,
        "siege": start_siege,
        "war": start_war,
        "statement": start_announcement,
        "trade": start_trade,
    }
    fn = handlers.get(kind)
    if fn:
        await fn(callback.message, state)


def _city_change_log(city: str) -> list:
    entry = CITY_ASSETS.get(city) or {}
    return list(entry.get("changes") or [])[-15:]


def _append_change(city: str, line: str):
    entry = CITY_ASSETS.setdefault(city, {"text": "", "stats": {}, "changes": []})
    ch = list(entry.get("changes") or [])
    stamp = datetime.now(TZ).strftime("%m-%d %H:%M") if TZ else datetime.now().strftime("%m-%d %H:%M")
    ch.append(f"[{stamp}] {line}")
    entry["changes"] = ch[-40:]
    CITY_ASSETS[city] = entry


def is_building_locked(city: str, name: str) -> bool:
    """قفل از شیت (🔒) یا لیست پیش‌فرض تا آنلاک نشود."""
    entry = CITY_ASSETS.get(city) or {}
    unlocked = set(entry.get("unlocked") or [])
    if name in unlocked:
        return False
    text = entry.get("text") or ""
    # اگر در متن کنار نام قفل باشد
    if name and "🔒" in text:
        for ln in text.splitlines():
            if name in ln and "🔒" in ln:
                return True
    return name in LOCKED_DEFAULT and name not in unlocked


async def open_economy_menu(callback: types.CallbackQuery, state: FSMContext):
    """نمایش خلاصه دارایی شهر + دکمه‌های اقتصادی."""
    uid = callback.from_user.id
    city = resolve_player_city(uid) or city_of(uid)
    lines = [f"💰 <b>منوی اقتصادی</b>\n{DIV}"]
    if city and city != "ناشناس":
        lines.append(f"🏙 شهر: <b>{e(city)}</b>")
        auto = is_auto_city(city)
        lines.append(f"🤖 اتو: {'✅ فعال (تست)' if auto else '❌ غیرفعال'}")
        bag = normalize_stats_keys(get_city_asset_stats(city))
        if bag:
            coins = bag.get("سکه") or 0
            food = bag.get("غذا") or 0
            pop = bag.get("جمعیت") or 0
            lines.append(f"💰 سکه: <b>{coins:g}</b> · 🍽 غذا: <b>{food:g}</b> · 👥 جمعیت: <b>{pop:g}</b>")
        else:
            lines.append("📭 دارایی ثبت نشده — ادمین «ست دارایی» کند.")
    else:
        lines.append("شهر شما مشخص نیست.")
    lines.append("\nاز دکمه‌ها استفاده کنید:")
    text = "\n".join(lines)
    kb = get_economy_menu_keyboard(uid)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


async def start_auto_upgrade(callback: types.CallbackQuery, state: FSMContext):
    """منوی بخش‌های ارتقا."""
    uid = callback.from_user.id
    city = resolve_player_city(uid) or city_of(uid)
    if not city or city == "ناشناس":
        return await callback.message.answer(
            "❌ شهر مشخص نیست.",
            reply_markup=get_inline_back_row("menu:economy"),
        )
    if not is_auto_city(city) and not is_admin(uid):
        return await callback.message.answer(
            f"🔒 حالت اتو برای <b>{e(city)}</b> فعال نیست.\n"
            "ادمین → «🤖 شهرهای اتو» را برای تست روشن کند.",
            reply_markup=get_inline_back_row("menu:economy"),
        )
    await state.update_data(upg_city=city)
    builder = InlineKeyboardBuilder()
    for key, (title, _items) in UPGRADE_SECTIONS.items():
        builder.row(_btn(title, f"upg:sec:{key}", "primary"))
    builder.row(_btn("✍️ دستور متنی", "upg:text", "success"))
    builder.row(_btn("🔙 بازگشت", "menu:economy"))
    text = (
        f"⬆️ <b>ارتقا — {e(city)}</b>\n{DIV}\n"
        "بخش را انتخاب کنید، سپس ساختمان و تعداد سطح.\n"
        "هزینه از قوانین محاسبه و پس از تایید اعمال می‌شود."
    )
    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("upg:"))
async def handle_upgrade_nav(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_player(uid) or is_admin(uid) or is_leader(uid)):
        return await callback.answer("❌", show_alert=True)
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    city = (await state.get_data()).get("upg_city") or resolve_player_city(uid) or city_of(uid)
    if not city:
        return await callback.answer("شهر؟", show_alert=True)
    if not is_auto_city(city) and not is_admin(uid):
        return await callback.answer("اتو غیرفعال", show_alert=True)

    if action == "text":
        await callback.answer()
        return await callback.message.answer(
            "بنویسید:\n<code>اعمال ارتقا: بندر 2, خزانه 1</code>",
            reply_markup=get_inline_back_row("menu:upgrade"),
        )

    if action == "sec" and len(parts) >= 3:
        await callback.answer()
        sec = parts[2]
        meta = UPGRADE_SECTIONS.get(sec)
        if not meta:
            return
        title, items = meta
        builder = InlineKeyboardBuilder()
        for i, name in enumerate(items):
            lock = "🔒" if is_building_locked(city, name) else ""
            builder.row(_btn(f"{lock}{name}", f"upg:b:{sec}:{i}", "primary"))
        builder.row(_btn("🔙 بخش‌ها", "menu:upgrade"))
        text = f"{title}\n{DIV}\nساختمان را انتخاب کنید:"
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
        except Exception:
            await callback.message.answer(text, reply_markup=builder.as_markup())
        return

    if action == "b" and len(parts) >= 4:
        await callback.answer()
        sec, idx_s = parts[2], parts[3]
        meta = UPGRADE_SECTIONS.get(sec)
        if not meta:
            return
        _title, items = meta
        try:
            idx = int(idx_s)
            name = items[idx]
        except (ValueError, IndexError):
            return await callback.answer("نامعتبر", show_alert=True)
        if is_building_locked(city, name):
            return await callback.answer("قفل است — اول بازکردن قفل", show_alert=True)
        bag = normalize_stats_keys(get_city_asset_stats(city))
        stock = _bag_stock(bag)
        aff = max_affordable_levels(name, stock)
        cost1 = format_cost_dict(cost_for_levels(name, 1))
        builder = InlineKeyboardBuilder()
        for lv in (1, 2, 3):
            if lv <= max(aff, 1):
                c = format_cost_dict(cost_for_levels(name, lv))
                builder.row(_btn(f"+{lv} سطح · {c[:40]}", f"upg:do:{sec}:{idx}:{lv}", "success"))
        builder.row(_btn("🔙", f"upg:sec:{sec}"))
        sheet = get_city_asset_text(city) or ""
        cur = guess_current_level(name, bag, sheet)
        cur_s = str(cur) if cur is not None else "?"
        text = (
            f"🏢 <b>{e(name)}</b> — {e(city)}\n{DIV}\n"
            f"🔹 لول کنونی: <b>{cur_s}</b>\n"
            f"🧮 هزینه هر سطح: <code>{e(cost1)}</code>\n"
            f"📊 حداکثر قابل‌پرداخت الان: <b>{aff}</b> سطح\n\n"
            "تعداد سطح را انتخاب کنید:"
        )
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
        except Exception:
            await callback.message.answer(text, reply_markup=builder.as_markup())
        return

    if action == "do" and len(parts) >= 5:
        sec, idx_s, lv_s = parts[2], parts[3], parts[4]
        meta = UPGRADE_SECTIONS.get(sec)
        if not meta:
            return await callback.answer()
        _title, items = meta
        try:
            name = items[int(idx_s)]
            levels = int(lv_s)
        except (ValueError, IndexError):
            return await callback.answer("نامعتبر", show_alert=True)
        ok, msg = apply_upgrade_levels(city, name, levels)
        if ok:
            _append_change(city, f"ارتقا {name} ×{levels}")
            await callback.answer("✅ اعمال شد")
        else:
            await callback.answer(msg[:80], show_alert=True)
        await callback.message.answer(
            f"{'✅' if ok else '❌'} <b>{e(name)}</b>\n{msg}",
            reply_markup=get_inline_back_row("menu:upgrade"),
        )
        if ok:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⬆️ ارتقا اتو\n🏙 {e(city)}\n👤 {mention(uid, city)}\n{msg[:800]}",
                )
            except Exception:
                pass
        return
    await callback.answer()


@dp.callback_query(F.data.startswith("eco:"))
async def handle_economy_extra(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]
    city = resolve_player_city(uid) or city_of(uid)
    await callback.answer()

    if action == "help":
        text = (
            f"❓ <b>راهنمای منوی اقتصادی</b>\n{DIV}\n"
            "• <b>مشاهده دارایی</b> — شیت شخصی / کل قلمرو\n"
            "• <b>ارتقا</b> — فقط شهر اتو: بخش → ساختمان → سطح → تایید\n"
            "• <b>مشاور</b> — پلن بهینه با منابع (اعمال جداست)\n"
            "• <b>بازکردن قفل</b> — یونیت‌های 🔒 با هزینه قوانین\n"
            "• <b>باف/نرف آپ</b> — انتخاب اثرهایی که با آپ عددی شوند "
            "(باف نبرد روی دارایی اعمال نمی‌شود)\n"
            "• <b>تغییرات اخیر</b> — لاگ ارتقا/آپ/ویرایش\n"
            "• <b>ویرایش</b> — ادمین: فرمول یا شیت کامل\n\n"
            "دستور متنی:\n<code>اعمال ارتقا: بندر 2, خزانه 1</code>\n"
            "ویرایش ادمین:\n<code>ویرایش دارایی سکه +500</code>\n"
            "<code>ویرایش دارایی چوب -100</code>"
        )
        return await callback.message.answer(text, reply_markup=get_inline_back_row("menu:economy"))

    if action == "changes":
        if not city:
            return await callback.message.answer("شهر؟", reply_markup=get_inline_back_row("menu:economy"))
        logs = _city_change_log(city)
        body = "\n".join(f"• {e(x)}" for x in logs) if logs else "هنوز تغییری ثبت نشده."
        return await callback.message.answer(
            f"📜 <b>تغییرات اخیر — {e(city)}</b>\n{DIV}\n{body}",
            reply_markup=get_inline_back_row("menu:economy"),
        )

    if action == "unlock":
        if not city:
            return await callback.message.answer("شهر؟")
        if not is_auto_city(city) and not is_admin(uid):
            return await callback.message.answer("فقط شهر اتو / ادمین.", reply_markup=get_inline_back_row("menu:economy"))
        builder = InlineKeyboardBuilder()
        locked = [n for n in LOCKED_DEFAULT if is_building_locked(city, n)]
        if not locked:
            return await callback.message.answer(
                "✅ قفل فعالی در لیست پیش‌فرض نیست.",
                reply_markup=get_inline_back_row("menu:economy"),
            )
        for i, name in enumerate(locked):
            c1 = format_cost_dict(cost_for_levels(name, 1))
            builder.row(_btn(f"🔓 {name}", f"unlock:do:{i}", "success"))
        builder.row(_btn("🔙", "menu:economy"))
        return await callback.message.answer(
            f"🔓 <b>بازکردن قفل — {e(city)}</b>\n{DIV}\n"
            "هزینه ≈ یک سطح ساخت (قوانین). پس از آنلاک، ارتقا و آپ مجاز است.",
            reply_markup=builder.as_markup(),
        )

    if action == "buffpick":
        return await callback.message.answer(
            f"🎛 <b>باف / نرف آپ</b>\n{DIV}\n"
            "باف‌های <b>نبرد</b> (روحیه، مقاومت و…) روی عدد دارایی اعمال نمی‌شوند.\n"
            "فقط اثرهایی که ادمین مشخص کند با آپ عددی می‌شوند.\n\n"
            "فعلاً: باف/نرف در شیت فقط <b>نمایش</b> است.\n"
            "برای اعمال عددی ادمین از «ویرایش دارایی» استفاده کند.\n"
            "مثال: <code>ویرایش دارایی اقتدار -3</code>",
            reply_markup=get_inline_back_row("menu:economy"),
        )

    if action == "politics":
        bag = normalize_stats_keys(get_city_asset_stats(city)) if city else {}
        auth = bag.get("اقتدار")
        leg = bag.get("مشروعیت")
        try:
            auth_f = float(auth) if auth is not None else None
        except (TypeError, ValueError):
            auth_f = None
        try:
            leg_f = float(leg) if leg is not None else None
        except (TypeError, ValueError):
            leg_f = None
        auth_s = f"{auth_f:g}" if auth_f is not None else "—"
        leg_s = f"{leg_f:g}" if leg_f is not None else "—"
        auth_tier = _tier_label(auth_f, AUTHORITY_TIERS)
        leg_tier = _tier_label(leg_f, LEGITIMACY_TIERS)
        text = (
            f"🗡🛡 <b>اقتدار و مشروعیت</b>\n{DIV}\n"
            f"🏙 <b>{e(city or '—')}</b>\n"
            f"🗡 اقتدار: <b>{auth_s}</b> — <i>{e(auth_tier)}</i>\n"
            f"🛡 مشروعیت: <b>{leg_s}</b> — <i>{e(leg_tier)}</i>\n\n"
            f"<b>🗡 اقتدار</b>\n"
            "اعتبار میان مردم و جهانیان. با بخشندگی، پیروزی، ارتش قوی و اقتصاد خوب بالا می‌رود؛ "
            "روحیه ارتش را بالا می‌برد. پیش‌فرض قوانین: <b>۴۰</b>.\n"
            "• ۰–۲۰: بی‌اعتبار — شورش ارتش / خواهان برکناری\n"
            "• ۲۰–۴۰: ضعیف — مردم منتظر جرقه\n"
            "• ۴۰–۶۰: متوسط — حاکم قابل‌قبول\n"
            "• ۶۰–۸۰: بالا — جان‌فشانی در جنگ\n"
            "• ۸۰–۱۰۰: اوج — مردم هفتگی <b>۲۵۰ سکه</b> · کاهش اثر جاسوسی/خرابکاری\n\n"
            f"<b>🛡 مشروعیت</b>\n"
            "پذیرش حکومت نزد مردم، اشراف، فرماندهان و نیروها — برحق و سزاوار اطاعت بودن. "
            "از عدالت، ثبات، پیروزی/شکست، وفاداری اشراف و اجرای قانون اثر می‌پذیرد. "
            "برخلاف اقتدار (هیبت و انگیزه ارتش)، مشروعیت <b>پایه ثبات حکومت</b> است.\n"
            "• ۰–۲۰: <b>بحران</b> — خطر شورش، کودتا، نافرمانی، فکر استقلال استان‌ها\n"
            "• ۲۰–۴۰: <b>ضعیف</b> — نارضایتی؛ شکست کوچک می‌تواند آشوب کند\n"
            "• ۴۰–۶۰: <b>متوسط</b> — قابل قبول؛ در بحران ریسک نارضایتی\n"
            "• ۶۰–۸۰: <b>بالا</b> — ثبات داخلی و وفاداری نیروها\n"
            "• ۸۰–۱۰۰: <b>مطلق</b> — حمایت گسترده؛ خطر کودتا/شورش بسیار کم\n\n"
            f"<b>آپ و تغییر اعداد</b>\n"
            "• آپ هفتگی این دو را <b>خودکار عوض نمی‌کند</b>.\n"
            "• تغییر با رول، رویداد، کودتا، مالیات سنگین، یا دستور ادمین:\n"
            "<code>ویرایش دارایی اقتدار -5</code>\n"
            "<code>ویرایش دارایی مشروعیت +3</code>\n"
            "• مالیات جمعیت ۶–۱۰ → معمولاً −۵ اقتدار · ۱۱–۱۵ → −۱۰ اقتدار و مشروعیت (ادمین/رول)\n"
            "• نرف شخصیت/قلعه هر آپ تکرار نمی‌شود.\n\n"
            "<i>شاخص سیاسی‌اند؛ موجودی سکه یا نیرو نیستند.</i>"
        )
        return await callback.message.answer(
            text, reply_markup=get_inline_back_row("menu:economy")
        )


@dp.callback_query(F.data.startswith("unlock:do:"))
async def handle_unlock_do(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    city = resolve_player_city(uid) or city_of(uid)
    if not city:
        return await callback.answer("شهر؟", show_alert=True)
    if not is_auto_city(city) and not is_admin(uid):
        return await callback.answer("اتو؟", show_alert=True)
    locked = [n for n in LOCKED_DEFAULT if is_building_locked(city, n)]
    try:
        idx = int(callback.data.split(":")[2])
        name = locked[idx]
    except (ValueError, IndexError):
        return await callback.answer("نامعتبر", show_alert=True)
    # فناوری نظامی لازم (طبق قوانین) + هزینه ساخت لول ۱
    bag = normalize_stats_keys(get_city_asset_stats(city))
    need_tech = TECH_UNLOCK_COST.get(name)
    if need_tech:
        mil_tech = float(bag.get("فناوری نظامی") or bag.get("نظامی") or 0)
        if mil_tech < need_tech and not is_admin(uid):
            return await callback.answer(
                f"فناوری نظامی ≥ {need_tech} لازم است (الان {mil_tech:g})",
                show_alert=True,
            )
    stock = _bag_stock(bag)
    if max_affordable_levels(name, stock) < 1:
        return await callback.answer("موجودی کافی نیست", show_alert=True)
    cd = cost_for_levels(name, 1)
    deltas = {}
    for key, lab in _RES_MAP:
        need = cd.get(key, 0)
        if need and lab != "جمعیت":
            deltas[lab if lab != "سکه" else "سکه"] = -need
    apply_stat_delta(city, deltas, note=f"آنلاک {name}")
    entry = CITY_ASSETS.setdefault(city, {"text": "", "stats": {}, "unlocked": []})
    un = list(entry.get("unlocked") or [])
    if name not in un:
        un.append(name)
    entry["unlocked"] = un
    # حذف قفل از متن در صورت وجود
    text = entry.get("text") or ""
    if name in text and "🔒" in text:
        new_lines = []
        for ln in text.splitlines():
            if name in ln:
                ln = ln.replace("🔒", "🔓")
            new_lines.append(ln)
        entry["text"] = "\n".join(new_lines)
    CITY_ASSETS[city] = entry
    _append_change(city, f"آنلاک {name}")
    save_data(critical=True)
    await callback.answer("✅ باز شد")
    await callback.message.answer(
        f"🔓 <b>{e(name)}</b> باز شد.\nهزینه: {e(format_cost_dict(cd))}",
        reply_markup=get_inline_back_row("menu:economy"),
    )


@dp.message(F.text.regexp(r"(?i)^\s*ویرایش\s*دارایی"))
async def handle_asset_formula_edit(message: types.Message):
    """ویرایش دارایی سکه +500 | چوب -100 — فقط ادمین"""
    if not is_admin(message.from_user.id):
        return
    body = re.sub(r"(?i)^\s*ویرایش\s*دارایی\s*:?\s*", "", message.text or "").strip()
    if not body:
        return await message.answer(
            "فرمول:\n<code>ویرایش دارایی سکه +500</code>\n"
            "<code>ویرایش دارایی چوب -100, جمعیت +20</code>\n"
            "شهر از گروه فعلی یا ریپلای مشخص می‌شود."
        )
    city = None
    if message.chat.type in ("group", "supergroup"):
        grp = GROUPS.get(message.chat.id)
        if grp:
            city = grp.get("city")
    if not city:
        city = resolve_player_city(message.from_user.id)
    if not city:
        return await message.answer("❌ شهر مشخص نیست (در گروه شهر بزنید).")
    deltas = {}
    for chunk in re.split(r"[,،]\s*", body):
        m = re.match(r"(.+?)\s*([+-]\s*\d+(?:\.\d+)?)\s*$", chunk.strip())
        if not m:
            continue
        key = _clean_item_name(m.group(1).strip())
        try:
            val = float(m.group(2).replace(" ", ""))
        except ValueError:
            continue
        key = {"سکه": "سکه", "غذا": "غذا", "جمعیت": "جمعیت", "رعیت": "جمعیت"}.get(key, key)
        deltas[key] = deltas.get(key, 0) + val
    if not deltas:
        return await message.answer("❌ فرمول نامعتبر.")
    log = apply_stat_delta(city, deltas, note="ویرایش ادمین")
    _append_change(city, f"ویرایش ادمین: {body[:80]}")
    await message.answer(f"✅ ویرایش <b>{e(city)}</b>\n{log}")


async def start_upgrade_advise(callback: types.CallbackQuery, state: FSMContext):
    """قدم ۱: انتخاب نوع مشاور."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return await callback.answer("❌ فقط فرمانده / لیدر / ادمین.", show_alert=True)
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("💰 اقتصادی", "advise_mode:econ", "success"),
        _btn("⚔️ نظامی", "advise_mode:mil", "danger"),
    )
    builder.row(
        _btn("🛡 زمینی", "advise_mode:land", "primary"),
        _btn("⚓️ دریایی", "advise_mode:naval", "primary"),
    )
    builder.row(_btn("⚖️ ترکیبی / بالانس", "advise_mode:balance", "success"))
    builder.row(_btn("💬 چت آزاد (پلن ۱–۲ پیام)", "advise_mode:chat", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    ai_note = "🤖 Grok فعال است." if XAI_API_KEY else "💡 کلید Grok را در کد (`XAI_API_KEY_IN_CODE`) بگذار."
    await callback.message.answer(
        f"🧠 <b>مشاور ارتقا</b>\n{DIV}\n"
        "نوع مشاوره را انتخاب کنید:\n"
        "• اقتصادی / نظامی / زمینی / دریایی\n"
        "• ترکیبی برای حفظ بالانس\n"
        "• چت آزاد: ۱ یا ۲ پیام درباره سلیقه و پلن‌تان\n\n"
        f"{ai_note}",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("advise_mode:"))
async def handle_advise_mode(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    mode = callback.data.split(":", 1)[1]
    if mode not in ADVISE_MODES:
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer()
    await state.update_data(advise_mode=mode, advise_notes="", advise_msg_count=0)

    # پلیر عادی → فقط شهر خودش، بدون لیست
    if is_plain_player(uid):
        my = resolve_player_city(uid)
        if not my:
            return await callback.message.answer(
                "❌ شهر شما ثبت نشده. اول با کد ورود وارد ربات شوید.",
                reply_markup=get_inline_back_row("menu:home"),
            )
        return await _advise_after_city_pick(callback, state, my, mode)

    # لیدر / ادمین → انتخاب از شهرهای مجاز
    side = leader_side(uid) or side_of_user(uid)
    builder = InlineKeyboardBuilder()
    if is_admin(uid) and not leader_side(uid):
        for s in FACTIONS:
            flag, title = FACTION_META[s]
            cities = [c for c in cities_for_side_assets(s) if c in CITY_ASSETS]
            for i, city in enumerate(cities[:8]):
                short = city.rsplit("_", 1)[0] if "_" in city else city
                if short.isascii():
                    short = short.replace("_", " ").title()
                builder.row(_btn(f"{flag} {short}", f"advise_ci:{s}:{i}:{mode}"))
    elif side and side in FACTIONS:
        cities = [c for c in cities_for_side_assets(side) if c in CITY_ASSETS]
        if not cities:
            # اگر دارایی نیست، باز هم شهرهای ساید را نشان بده
            cities = cities_for_side_assets(side)
        if not cities:
            return await callback.message.answer(
                "📭 شهری برای این ساید ثبت نشده.",
                reply_markup=get_inline_back_row("menu:advise"),
            )
        for i, city in enumerate(cities):
            short = city.rsplit("_", 1)[0] if "_" in city else city
            if short.isascii():
                short = short.replace("_", " ").title()
            has = "📦" if city in CITY_ASSETS else "—"
            builder.row(_btn(f"{has} {short}", f"advise_ci:{side}:{i}:{mode}"))
    else:
        my = resolve_player_city(uid)
        if my:
            return await _advise_after_city_pick(callback, state, my, mode)
        return await callback.message.answer(
            "❌ شهر/ساید مشخص نیست.",
            reply_markup=get_inline_back_row("menu:home"),
        )
    builder.row(_btn("🔙 بازگشت", "menu:advise"))
    mode_fa = ADVISE_MODES[mode][1]
    await callback.message.answer(
        f"🧠 مشاور <b>{e(mode_fa)}</b>\n{DIV}\nشهر را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


async def _advise_after_city_pick(callback, state, city: str, mode: str):
    """بعد از انتخاب شهر: چت آزاد یا تحلیل مستقیم."""
    await state.update_data(advise_city=city, advise_mode=mode, advise_notes="", advise_msg_count=0)
    if mode == "chat":
        builder = InlineKeyboardBuilder()
        builder.row(_btn("⏭ بدون توضیح — تحلیل کن", f"advise_run:{mode}", "success"))
        builder.row(_btn("🔙 انصراف", "menu:advise", "danger"))
        await state.set_state(GameStates.advise_pref)
        return await callback.message.answer(
            f"💬 <b>چت آزاد مشاور</b> — شهر <b>{e(city)}</b>\n{DIV}\n"
            "در <b>۱ یا ۲ پیام</b> بگو:\n"
            "• هدف‌ت چیه؟ (اقتصاد / فتح / دفاع / دریا…)\n"
            "• بودجه یا محدودیت داری؟\n"
            "• سلیقه‌ت چیه؟\n\n"
            "بعد از پیام‌ها خودکار تحلیل می‌شود.\n"
            "یا دکمه «بدون توضیح» را بزن.",
            reply_markup=builder.as_markup(),
        )
    # غیر چت: مستقیم یا یک سوال کوتاه اختیاری
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🚀 تحلیل همین الان", f"advise_run:{mode}", "success"))
    builder.row(_btn("✍️ یک توضیح کوتاه می‌دهم", f"advise_want_note:{mode}", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:advise"))
    mode_fa = ADVISE_MODES.get(mode, ("", mode))[1]
    await callback.message.answer(
        f"🎯 مشاور <b>{e(mode_fa)}</b> · شهر <b>{e(city)}</b>\n{DIV}\n"
        "می‌خواهید بدون توضیح تحلیل شود یا یک پیام کوتاه درباره پلن‌تان بفرستید؟",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("advise_ci:"))
async def handle_advise_city(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    # advise_ci:side:idx:mode  یا قدیمی advise_ci:side:idx
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    side, idx_s = parts[1], parts[2]
    mode = parts[3] if len(parts) > 3 else (await state.get_data()).get("advise_mode", "balance")
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر", show_alert=True)
    my_side = leader_side(uid) or side_of_user(uid)
    if is_plain_player(uid):
        return await callback.answer("❌ فقط شهر خودتان از منوی مشاور.", show_alert=True)
    if not is_admin(uid) and leader_side(uid) and leader_side(uid) != side:
        return await callback.answer("❌ فقط ساید خودتان.", show_alert=True)
    try:
        idx = int(idx_s)
    except ValueError:
        return await callback.answer("نامعتبر", show_alert=True)
    cities = [c for c in cities_for_side_assets(side) if c in CITY_ASSETS]
    if not cities:
        cities = cities_for_side_assets(side)
    if idx < 0 or idx >= len(cities):
        return await callback.answer("شهر پیدا نشد.", show_alert=True)
    city = cities[idx]
    await callback.answer()
    await _advise_after_city_pick(callback, state, city, mode)


@dp.callback_query(F.data.startswith("advise_want_note:"))
async def handle_advise_want_note(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    d = await state.get_data()
    city = d.get("advise_city")
    if not city:
        return await callback.answer("شهر مشخص نیست.", show_alert=True)
    await callback.answer()
    await state.update_data(advise_mode=mode, advise_msg_count=0, advise_notes="")
    await state.set_state(GameStates.advise_pref)
    await callback.message.answer(
        f"✍️ یک یا دو پیام درباره پلن‌تان بنویسید (شهر: <b>{e(city)}</b>).\n"
        "مثال: «می‌خوام این هفته روی بندر و کشتی تمرکز کنم، بودجه حدود ۴۰۰۰ سکه»\n"
        "برای انصراف بنویس: <code>بازگشت</code>",
        reply_markup=get_back_keyboard(),
    )


@dp.callback_query(F.data.startswith("advise_run:"))
async def handle_advise_run(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    d = await state.get_data()
    city = d.get("advise_city")
    mode = callback.data.split(":", 1)[1] if ":" in callback.data else d.get("advise_mode", "balance")
    notes = d.get("advise_notes") or ""
    if not city:
        return await callback.answer("شهر مشخص نیست. دوباره از منو.", show_alert=True)
    await callback.answer("در حال تحلیل…")
    try:
        text = await build_upgrade_advice(city, mode=mode, notes=notes, user_id=uid)
    except Exception:
        logging.exception("upgrade advice")
        text = "❌ تحلیل ناموفق بود."
    await state.set_state(GameStates.main_menu)
    if len(text) > 4000:
        await send_chunks(callback.message, [text], reply_markup=get_inline_back_row("menu:advise"))
    else:
        await callback.message.answer(text, reply_markup=get_inline_back_row("menu:advise"))


@dp.message(GameStates.advise_pref)
async def process_advise_pref(message: types.Message, state: FSMContext):
    """حداکثر ۲ پیام سلیقه/پلن سپس تحلیل."""
    uid = message.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return
    txt = (message.text or "").strip()
    if not txt:
        return await message.answer("متن بفرستید یا از منو انصراف دهید.")
    if txt in ("بازگشت", "لغو", "/cancel"):
        await state.clear()
        return await go_menu(message, state, user_id=uid)
    d = await state.get_data()
    notes = (d.get("advise_notes") or "")
    count = int(d.get("advise_msg_count") or 0) + 1
    notes = (notes + "\n" + txt).strip() if notes else txt
    await state.update_data(advise_notes=notes, advise_msg_count=count)
    city = d.get("advise_city")
    mode = d.get("advise_mode") or "chat"
    if count < 2:
        builder = InlineKeyboardBuilder()
        builder.row(_btn("🚀 همین کافی‌ست — تحلیل کن", f"advise_run:{mode}", "success"))
        return await message.answer(
            f"✅ پیام {count}/۲ ثبت شد.\n"
            "می‌توانید یک پیام دیگر بفرستید یا دکمه تحلیل را بزنید.\n"
            "مثال: <code>بندر ۳ لول و خزانه ۲ لول</code>",
            reply_markup=builder.as_markup(),
        )
    await message.answer("⏳ در حال چیدن بهترین پلن با منابع شما…")
    try:
        text = await build_upgrade_advice(city, mode=mode, notes=notes, user_id=uid)
    except Exception:
        logging.exception("upgrade advice")
        text = "❌ تحلیل ناموفق بود."
    await state.set_state(GameStates.main_menu)
    if len(text) > 4000:
        await send_chunks(message, [text], reply_markup=get_inline_back_row("menu:advise"))
    else:
        await message.answer(text, reply_markup=get_inline_back_row("menu:advise"))


async def start_asset_view(callback: types.CallbackQuery, state: FSMContext):
    """منوی شیشه‌ای: دارایی شخصی (شهر) یا دارایی کل قلمرو (جمع)."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ فقط لیدر ساید / ادمین.", show_alert=True)
    await callback.answer()
    side = leader_side(uid)
    # ادمین بدون ساید لیدری → انتخاب ساید
    if is_admin(uid) and not side:
        builder = InlineKeyboardBuilder()
        for s in FACTIONS:
            flag, title = FACTION_META[s]
            builder.row(
                _btn(f"{flag} {title} · شخصی", f"asset_view:cities:{s}", "success"),
                _btn(f"{flag} کل", f"asset_view:realm:{s}", "primary"),
            )
        builder.row(_btn("🔙 بازگشت", "menu:home"))
        return await callback.message.answer(
            f"📦 <b>مشاهده دارایی</b>\n{DIV}\n"
            "• <b>شخصی</b> = شیت کامل هر شهر ثبت‌شده\n"
            "• <b>کل</b> = یک پیام جمع قلمرو (بدون شیت جداگانه)",
            reply_markup=builder.as_markup(),
        )
    if not side:
        # لیدر نیست ولی ادمین هم نیست — یا ساید از شهر کاربر
        side = side_of_user(uid)
    if not side or side not in FACTIONS:
        return await callback.message.answer(
            "❌ ساید شما مشخص نیست. لیدر باید با دستور ست لیدر ثبت شود.",
            reply_markup=get_inline_back_row("menu:home"),
        )
    flag, title = FACTION_META[side]
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🏙 دارایی شخصی (شهرها)", f"asset_view:cities:{side}", "success"))
    builder.row(_btn("🌐 دارایی کل قلمرو (جمع)", f"asset_view:realm:{side}", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    await callback.message.answer(
        f"📦 <b>دارایی {flag}{title}</b>\n{DIV}\n"
        "نوع مشاهده را انتخاب کنید:\n"
        "• <b>شخصی</b> — شیت کامل هر شهر\n"
        "• <b>کل قلمرو</b> — فقط آمار جمع‌خورده در یک پیام",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("asset_view:"))
async def handle_asset_view(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    mode, side = parts[1], parts[2]
    my_side = leader_side(uid) or side_of_user(uid)
    if not is_admin(uid) and my_side != side:
        return await callback.answer("❌ فقط ساید خودتان.", show_alert=True)
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر.", show_alert=True)
    await callback.answer()
    flag, title = FACTION_META.get(side, ("", side))
    if mode == "realm":
        return await callback.message.answer(
            format_realm_view(side)[:4000],
            reply_markup=get_inline_back_row("menu:assets"),
        )
    # دارایی شخصی — فقط شهرهایی که دارایی دارند + بقیه با علامت
    cities = cities_for_side_assets(side)
    builder = InlineKeyboardBuilder()
    if not cities:
        builder.row(_btn("❗️ شهری ثبت نشده", "noop"))
    else:
        for i, city in enumerate(cities):
            has = "✅" if city in CITY_ASSETS and get_city_asset_text(city) else "—"
            short = city.rsplit("_", 1)[0] if "_" in city else city
            if short.isascii():
                short = short.replace("_", " ").title()
            builder.row(_btn(f"{has} {short}", f"asset_ci:{side}:{i}"))
    builder.row(_btn("🔙 بازگشت", "menu:assets"))
    await callback.message.answer(
        f"🏙 <b>دارایی شخصی — {flag}{title}</b>\n{DIV}\n"
        "شهر را انتخاب کنید تا شیت کامل همان شهر نمایش داده شود:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("asset_ci:"))
async def handle_asset_city_idx(callback: types.CallbackQuery):
    """انتخاب شهر با ایندکس — جلوگیری از باگ callback طولانی."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    side, idx_s = parts[1], parts[2]
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر.", show_alert=True)
    my_side = leader_side(uid) or side_of_user(uid)
    if not is_admin(uid) and my_side != side:
        return await callback.answer("❌ فقط ساید خودتان.", show_alert=True)
    try:
        idx = int(idx_s)
    except ValueError:
        return await callback.answer("نامعتبر", show_alert=True)
    cities = cities_for_side_assets(side)
    if idx < 0 or idx >= len(cities):
        return await callback.answer("شهر پیدا نشد.", show_alert=True)
    city = cities[idx]
    await callback.answer()
    body = format_city_asset_view(city)
    if len(body) > 4000:
        await send_chunks(callback.message, [body], reply_markup=get_inline_back_row("menu:assets"))
    else:
        await callback.message.answer(body, reply_markup=get_inline_back_row("menu:assets"))


@dp.callback_query(F.data.startswith("asset_city:"))
async def handle_asset_city(callback: types.CallbackQuery):
    """سازگاری با callbackهای قدیمی."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    city = callback.data.split(":", 1)[1]
    side = country_key(city)
    my_side = leader_side(uid) or side_of_user(uid)
    if not is_admin(uid):
        if not side or my_side != side:
            return await callback.answer("❌ فقط شهرهای ساید خودتان.", show_alert=True)
    await callback.answer()
    body = format_city_asset_view(city)
    if len(body) > 4000:
        await send_chunks(callback.message, [body], reply_markup=get_inline_back_row("menu:assets"))
    else:
        await callback.message.answer(body, reply_markup=get_inline_back_row("menu:assets"))


@dp.message(GameStates.order_target)
async def process_order_target(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "order_target", txt)


@dp.message(GameStates.order_stats)
async def process_order_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    await state.update_data(stats=txt)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {
        "kind": d.get("kind", "siege"),
        "data": dict(d),
        "chat_id": message.chat.id,
    }
    await message.answer(
        f"📩 <b>دستور شما دریافت شد.</b> آیا دستور خود را تایید می‌کنید؟\n{DIV}\n\n"
        f"🧭 نوع {ORDERS[d['kind']]['noun']}: <b>{mtype_tag(d)}</b>\n"
        f"🎯 شهر هدف: <b>{e(d['target'])}</b>\n📊 آمار:\n<blockquote>{e(d['stats'])}</blockquote>",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.order_confirm)


async def _finish_order(callback: types.CallbackQuery, state: FSMContext, d: dict):
    kind = d.get("kind", "siege")
    cfg = ORDERS[kind]
    user_id = callback.from_user.id
    city = city_of(user_id)
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


@dp.callback_query(F.data.startswith("confirm:"))
async def process_universal_confirm(callback: types.CallbackQuery, state: FSMContext):
    """
    تایید واحد — وابسته به pending_confirms است تا اگر FSM از بین رفت
    (ری‌استارت / باگ گروه) دکمه تایید همچنان کار کند.
    """
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]
    pending = pending_confirms.pop(uid, None)

    # اگر pending نبود از state بخوان
    if not pending:
        st = await state.get_state()
        d = await state.get_data()
        if st == GameStates.camp_confirm.state and d.get("origin"):
            pending = {"kind": "campaign", "data": d}
        elif st == GameStates.order_confirm.state and d.get("target"):
            pending = {"kind": d.get("kind", "siege"), "data": d}
        elif st == GameStates.ann_confirm.state and d.get("ann"):
            pending = {"kind": "ann", "data": d}
        elif st == GameStates.ambush_confirm.state and d.get("action_id"):
            pending = {"kind": "ambush", "data": d}
        elif st == GameStates.redirect_confirm.state and d.get("new_dest"):
            pending = {"kind": "redirect", "data": d}
        elif st == GameStates.back_confirm.state and d.get("back_time"):
            pending = {"kind": "back", "data": d}
        elif st == GameStates.trade_confirm.state and d.get("origin") and d.get("dest"):
            pending = {"kind": "trade", "data": d}
        elif st == GameStates.trade_ambush_confirm.state and d.get("action_id"):
            pending = {"kind": "trade_ambush", "data": d}
        elif st == GameStates.mtrade_confirm.state and d.get("mtrade_order"):
            pending = {
                "kind": "mtrade",
                "data": {
                    "order": d.get("mtrade_order"),
                    "buff": d.get("mtrade_buff", 0),
                    "after": d.get("mtrade_after"),
                    "cost": d.get("mtrade_cost", 0),
                    "mode": d.get("mtrade_mode", "buy"),
                },
            }

    if not pending:
        return await callback.answer(
            "این تایید منقضی شده. دوباره از منو شروع کنید.",
            show_alert=True,
        )

    await callback.answer()
    kind = pending["kind"]
    d = pending["data"]

    if action in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        cancel_msgs = {
            "campaign": "❌ سرورم اعزام لشکرکشی شما <b>لغو</b> شد.",
            "siege": ORDERS["siege"]["cancelled"],
            "war": ORDERS["war"]["cancelled"],
            "ann": "❌ سرورم صدور بیانیه شما <b>لغو</b> شد.",
            "ambush": "❌ سرورم دستور کمین شما <b>لغو</b> شد.",
            "redirect": "❌ سرورم تغییر مسیر لشکریان شما <b>لغو</b> شد.",
            "back": "❌ سرورم دستور بازگشت لشکریان شما <b>لغو</b> شد.",
            "trade": "❌ سرورم تجارت شما <b>لغو</b> شد.",
            "trade_ambush": "❌ کمین کاروان <b>لغو</b> شد.",
            "mtrade": "❌ تجارت با تجار <b>لغو</b> شد.",
        }
        return await go_menu(callback.message, state, cancel_msgs.get(kind, "❌ لغو شد."))

    if action != "yes":
        return

    if kind == "campaign":
        return await _finish_campaign(callback, state, d)
    if kind in ("siege", "war"):
        return await _finish_order(callback, state, d)
    if kind == "ann":
        return await _finish_ann(callback, state, d)
    if kind == "ambush":
        return await _finish_ambush(callback, state, d)
    if kind == "redirect":
        return await _finish_redirect(callback, state, d)
    if kind == "back":
        return await _finish_back(callback, state, d)
    if kind == "trade":
        return await _finish_trade(callback, state, d)
    if kind == "trade_ambush":
        return await _finish_trade_ambush(callback, state, d)
    if kind == "mtrade":
        return await _finish_mtrade(callback, state, d)
    await callback.message.answer("⚠️ نوع تایید ناشناخته. از منو دوباره شروع کنید.")


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


@dp.callback_query(F.data.startswith("chan_cancelsiege:"))
async def handle_cancel_siege(callback: types.CallbackQuery):
    await cancel_order(callback, "chan_cancelsiege:", "siege")


@dp.callback_query(F.data.startswith("chan_cancelwar:"))
async def handle_cancel_war(callback: types.CallbackQuery):
    await cancel_order(callback, "chan_cancelwar:", "war")


# ======================================================================
#                              ۴. بیانیه
# ======================================================================
async def start_announcement(message: types.Message, state: FSMContext):
    await message.answer(
        "📜 سرورم بیانیه خود را به یکی از این روش‌ها بفرستید:\n\n"
        "1️⃣ فقط <b>متن</b>\n"
        "2️⃣ <b>عکس یا ویدیو همراه کپشن</b> (متن روی همان فایل)\n"
        "3️⃣ فقط <b>عکس یا ویدیو</b> — بعد متن را جداگانه می‌پرسد\n\n"
        "↩️ برای انصراف «بازگشت» را بزنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.ann_media)


@dp.message(GameStates.ann_media)
async def process_ann_media(message: types.Message, state: FSMContext):
    if message.text and is_back_text(message.text):
        return await go_menu(message, state)
    if message.photo or message.video:
        caption = (message.caption or "").strip()
        if message.photo:
            kind, file_id = "photo", message.photo[-1].file_id
        else:
            kind, file_id = "video", message.video.file_id
        if caption:
            if len(caption) > 850:
                return await message.answer("❌ متن بیانیه برای عکس/ویدیو خیلی طولانی است (حداکثر ۸۵۰ کاراکتر). کوتاه‌تر کنید.")
            media = {"kind": kind, "file_id": file_id, "caption": caption}
        else:
            await state.update_data(ann_pending={"kind": kind, "file_id": file_id})
            await message.answer(
                "📝 حالا <b>متن بیانیه</b> را بفرستید (حداکثر ۸۵۰ کاراکتر).\n↩️ به این پیام <b>ریپلای</b> کنید.",
                reply_markup=get_back_keyboard(),
            )
            return
    elif message.text:
        d = await state.get_data()
        pending = d.get("ann_pending")
        if pending:
            if len(message.text) > 850:
                return await message.answer("❌ متن خیلی طولانی است (حداکثر ۸۵۰ کاراکتر). کوتاه‌تر کنید.")
            media = {"kind": pending["kind"], "file_id": pending["file_id"], "caption": message.text.strip()}
            await state.update_data(ann_pending=None)
        else:
            if len(message.text) > 3500:
                return await message.answer("❌ متن بیانیه خیلی طولانی است. کوتاه‌تر کنید.")
            media = {"kind": "text", "file_id": None, "caption": message.text.strip()}
    else:
        return await message.answer("❌ لطفاً متن، عکس یا ویدیو ارسال کنید (به پیام ربات ریپلای کنید).")

    await state.update_data(ann=media)
    pending_confirms[message.from_user.id] = {
        "kind": "ann",
        "data": {"ann": media},
        "chat_id": message.chat.id,
    }
    preview = e(media["caption"][:200]) + ("…" if len(media["caption"]) > 200 else "")
    extra = "🖼 همراه تصویر/ویدیو" if media["kind"] != "text" else "📝 فقط متن"
    await message.answer(
        f"📜 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>صدور بیانیه</b> خود مطمئن هستید؟\n"
        f"{DIV}\n{extra}\n<blockquote>{preview}</blockquote>",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.ann_confirm)


async def _finish_ann(callback: types.CallbackQuery, state: FSMContext, d: dict):
    user_id = callback.from_user.id
    city = city_of(user_id)
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
    await go_menu(callback.message, state, "✅ سرورم بیانیه شما با موفقیت <b>منتشر</b> شد. 📢")
    await send_report(f"📢 <b>بیانیه جدید منتشر شد</b>\n{DIV}\n👤 فرمانده: {mention(user_id, city)} (ID: <code>{user_id}</code>)\n🏙 شهر: {e(city)}")


# ======================================================================
#                              ۵. تجارت
# ======================================================================
async def start_trade(message: types.Message, state: FSMContext):
    """انتخاب نوع تجارت: با بازیکن یا با تجار."""
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🤝 تجارت با بازیکن", "trade_kind:player", "primary"))
    builder.row(_btn("🛒 تجارت با تجار", "trade_kind:merchant", "success"))
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    await message.answer(
        f"🐪 <b>تجارت</b>\n{DIV}\nنوع تجارت را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


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
    if not MERCHANT_ENABLED:
        return await callback.message.answer(
            "❌ تجارت با تجار فعلاً توسط ادمین <b>غیرفعال</b> است.",
            reply_markup=get_main_menu_keyboard(callback.from_user.id),
        )
    if not is_game_time_open():
        return await callback.message.answer(
            f"🛑 الان خارج از بازه مجاز است.\n"
            f"استارت <code>{SETTINGS.get('time_start')}</code> — "
            f"استاپ <code>{SETTINGS.get('time_stop')}</code>",
            reply_markup=get_main_menu_keyboard(callback.from_user.id),
        )
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
        detail.append(f"• {k}: {q:g} × {unit:g} = <b>{q * unit:g}</b>")
    verb = "هزینه خرید" if mode == "buy" else "درآمد فروش"
    await message.answer(
        f"✅ لیست مجاز ({'خرید' if mode == 'buy' else 'فروش'}):\n{format_goods(applied)}\n\n"
        + "\n".join(detail) + "\n"
        f"💰 {verb}: <b>{cost:g}</b> سکه\n\n"
        f"🎚 باف پیش‌فرض: <b>{MERCHANT_BUFF_DEFAULT:g}%</b>\n"
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
        buff = float(MERCHANT_BUFF_DEFAULT)
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
        f"🎚 باف: <b>{buff:g}%</b>\n"
        f"💰 {money_lbl} (محرمانه): <b>{cost:g}</b> سکه\n\n"
        f"📦 کالا:\n{format_goods(order)}\n\n"
        f"📦 پس از باف:\n{format_goods(after)}\n\n"
        "⚠️ سکه و جزئیات فقط برای شما/ادمین است — در کانال نمی‌آید.\n"
        "تایید می‌کنید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.mtrade_confirm)


async def _finish_mtrade(callback: types.CallbackQuery, state: FSMContext, d: dict):
    user_id = callback.from_user.id
    city = city_of(user_id)
    order = d.get("order") or {}
    buff = d.get("buff", 0)
    after = d.get("after") or order
    cost = d.get("cost", 0)
    mode = d.get("mode") or "buy"
    verb_fa = "خرید کرد" if mode == "buy" else "فروخت"
    # کانال اصلی: فقط متن ساده — بدون زمان و سکه
    public_text = (
        f"🛒 <b>معامله با تجار</b>\n{DIV}\n\n"
        f"👑 {mention(user_id, 'فرمانده شهر')}\n"
        f"🏙 فرمانده قلعه <b>{e(city)}</b> با تجار {verb_fa}."
    )
    try:
        await post_to_channel("trade", public_text, None, "land", city)
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پست تجارت با تجار")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(callback.message, state, "✅ معامله با تجار ثبت شد. 🛒")

    money_lbl = "هزینه خرید" if mode == "buy" else "درآمد فروش"
    tag = "#خرید" if mode == "buy" else "#فروش"
    full = (
        f"🛒 <b>گزارش کامل معامله با تجار</b>\n#تجارت #تجار {tag}\n{DIV}\n"
        f"👤 فرمانده: {mention(user_id, city)}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🏙 شهر: <b>{e(city)}</b>\n"
        f"🔀 نوع: <b>{'خرید' if mode == 'buy' else 'فروش'}</b>\n"
        f"🎚 باف: <b>{buff:g}%</b>\n"
        f"💰 {money_lbl}: <b>{cost:g}</b> سکه\n\n"
        f"📦 درخواست:\n{format_goods(order)}\n\n"
        f"📦 پس از باف:\n{format_goods(after)}\n\n"
        "⚠️ ربات دارایی را تغییر نداد — فقط گزارش."
    )
    await send_trade_reports(public_text, full)


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


async def _finish_trade(callback: types.CallbackQuery, state: FSMContext, d: dict):
    user_id = callback.from_user.id
    city = city_of(user_id)
    mtype = d.get("mtype") if d.get("mtype") in ("land", "sea") else "land"
    mlabel = "زمینی" if mtype == "land" else "دریایی"
    action_id = secrets.token_hex(4)

    # کانال اصلی: فقط حرکت کاروان — بدون محموله
    public_text = (
        f"🐪 <b>کاروان تجاری به راه افتاد</b> 🐪\n{DIV}\n\n"
        f"👑 {mention(user_id, 'فرمانده شهر')}\n"
        f"🏙 شهر فرمانده: <b>{e(city)}</b>\n"
        f"🧭 مسیر: <b>{mlabel}</b>\n\n"
        f"📍 از: <b>{e(d['origin'])}</b>\n"
        f"🎯 به: <b>{e(d['dest'])}</b>\n"
        f"🗺️ مسیر حرکت: <b>{e(d.get('route', '-'))}</b>\n"
        f"⏳ زمان رسیدن: <b>{e(d.get('time', '-'))}</b>\n"
        f"🛡 نیروی حفاظتی: اعلام‌شده\n\n"
        f"🛤️ کاروانیان حرکت کردند…"
    )
    try:
        sent = await post_to_channel(
            "trade", public_text, get_trade_channel_buttons(action_id), mtype, city,
        )
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پست تجارت")

    active_actions[action_id] = {
        "owner_id": user_id,
        "type": "trade",
        "time_created": time.time(),
        "msg_id": sent.message_id,
        "data": {
            "origin": d["origin"],
            "dest": d["dest"],
            "route": d.get("route", "-"),
            "mtype": mtype,
            "guard": d.get("guard", "-"),
            "recv": d.get("recv", "-"),
            "send": d.get("send", "-"),
            "time": d.get("time", "-"),
        },
    }
    save_data()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(callback.message, state, "✅ کاروان تجاری ثبت شد. محموله فقط برای ادمین گزارش شد. 🐪")

    # کانال گزارش + ادمین دارایی: جزئیات کامل + محموله
    full = (
        f"🐪 <b>گزارش کامل تجارت</b>\n"
        f"#تجارت #{mlabel}\n{DIV}\n"
        f"👤 فرمانده: {mention(user_id, city)}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🏙 شهر فرمانده: <b>{e(city)}</b>\n"
        f"🧭 نوع مسیر: <b>{mlabel}</b>\n"
        f"📍 مبدا: <b>{e(d['origin'])}</b>\n"
        f"🎯 مقصد: <b>{e(d['dest'])}</b>\n"
        f"🗺️ مسیر حرکت: <b>{e(d.get('route', '-'))}</b>\n"
        f"⏳ زمان رسیدن: <b>{e(d.get('time', '-'))}</b>\n\n"
        f"🛡 نیروی حفاظتی:\n<blockquote>{e(d.get('guard', '-'))}</blockquote>\n"
        f"📦 <b>کالای دریافتی:</b>\n<blockquote>{e(d.get('recv', '-'))}</blockquote>\n"
        f"📦 <b>کالای ارسالی:</b>\n<blockquote>{e(d.get('send', '-'))}</blockquote>\n\n"
        "⚠️ ربات دارایی را تغییر نداد — فقط گزارش ثبت شد."
    )
    await send_trade_reports(public_text, full)


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


def bot_open_url():
    """لینک مستقیم باز کردن پی‌وی ربات."""
    if BOT_USERNAME:
        return f"https://t.me/{BOT_USERNAME}"
    return None


def get_open_bot_keyboard():
    """دکمهٔ اینلاین برای رفتن به پی‌وی ربات."""
    url = bot_open_url()
    if not url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text="📩 باز کردن پی‌وی ربات", url=url)
    return builder.as_markup()


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


# ---------------- کمین ----------------
@dp.callback_query(F.data.startswith("chan_ambush:"))
async def handle_inline_ambush(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(callback, "chan_ambush:", owner=False)
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.ambush_stats,
        f"🪓 سرورم شما هم اکنون در حال دستور <b>کمین</b> بر لشکریان <b>{e(city_of(action['owner_id']))}</b> هستید.\n\n"
        "📊 لطفا آمار خود را با توجه به <b>قوانین کمین</b> وارد کنید.",
    )


@dp.message(GameStates.ambush_stats)
async def process_ambush_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    d = await state.get_data()
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(message, state, "این عملیات دیگر معتبر نیست.")
    await state.update_data(stats=txt)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {"kind": "ambush", "data": dict(d), "chat_id": message.chat.id}
    await message.answer(
        f"🪓 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از دستور کمین خود بر لشکریان "
        f"<b>{e(city_of(action['owner_id']))}</b> با آمار:\n<blockquote>{e(txt)}</blockquote>\nموافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.ambush_confirm)


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


# ---------------- کمین کاروان تجاری ----------------
@dp.callback_query(F.data.startswith("chan_trade_ambush:"))
async def handle_trade_ambush(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(
        callback, "chan_trade_ambush:", owner=False, types_ok=("trade",),
    )
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.trade_ambush_stats,
        f"🪓 سرورم در حال <b>کمین به کاروان</b> شهر <b>{e(city_of(action['owner_id']))}</b> هستید.\n\n"
        "📊 آمار نیروی کمین‌زننده را وارد کنید (ریپلای):",
    )


@dp.message(GameStates.trade_ambush_stats)
async def process_trade_ambush_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    d = await state.get_data()
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(message, state, "این کاروان دیگر معتبر نیست.")
    await state.update_data(stats=txt)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {
        "kind": "trade_ambush", "data": dict(d), "chat_id": message.chat.id,
    }
    await message.answer(
        f"🪓 کمین به کاروان <b>{e(city_of(action['owner_id']))}</b>\n"
        f"آمار شما:\n<blockquote>{e(txt)}</blockquote>\nتایید می‌کنید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.trade_ambush_confirm)


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


# ---------------- تغییر مسیر ----------------
@dp.callback_query(F.data.startswith("chan_redir:"))
async def handle_inline_redirect(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(callback, "chan_redir:", owner=True)
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.redirect_target,
        "🔄 سرورم قصد دارید لشکریان خود را به کدام <b>مقصد جدید</b> ارسال کنید؟\n\n🎯 (شهر و کشور مقصد را وارد کنید)",
    )


@dp.message(GameStates.redirect_target)
async def process_redir_target(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(new_dest=txt)
    await message.answer("⏳ سرورم لطفا <b>زمان رسیدن جدید</b> لشکریان خود را وارد کنید.", reply_markup=get_back_keyboard())
    await state.set_state(GameStates.redirect_time)


@dp.message(GameStates.redirect_time)
async def process_redir_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    parsed, err = parse_player_time(txt)
    if err:
        return await message.answer(f"❌ {err}\nمثال: <code>12:00</code> یا <code>45</code>")
    await state.update_data(new_time=parsed)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {"kind": "redirect", "data": dict(d), "chat_id": message.chat.id}
    await message.answer(
        f"🔄 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>تغییر مسیر</b> لشکریان خود به مقصد "
        f"<b>{e(d['new_dest'])}</b> 🎯 با زمان رسیدن <b>{e(txt)}</b> ⏳ موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.redirect_confirm)


async def _finish_redirect(callback: types.CallbackQuery, state: FSMContext, d: dict):
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(callback.message, state, "این عملیات دیگر معتبر نیست.")
    user_id = callback.from_user.id
    city = city_of(user_id)
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


# ---------------- بک ----------------
@dp.callback_query(F.data.startswith("chan_back:"))
async def handle_inline_back(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(callback, "chan_back:", owner=True)
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.back_time,
        "🔙 سرورم شما هم اکنون قصد <b>بک زدن</b> ارتش خود را دارید.\n\n⏳ لطفا <b>تایم رسیدن به مبدا</b> را وارد کنید.",
    )


@dp.message(GameStates.back_time)
async def process_back_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    parsed, err = parse_player_time(txt)
    if err:
        return await message.answer(f"❌ {err}\nمثال: <code>12:00</code> یا <code>45</code>")
    await state.update_data(back_time=parsed)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {"kind": "back", "data": dict(d), "chat_id": message.chat.id}
    await message.answer(
        f"🔙 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>بازگشت</b> لشکریان خود به مبدا "
        f"با زمان رسیدن <b>{e(txt)}</b> ⏳ موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.back_confirm)


async def _finish_back(callback: types.CallbackQuery, state: FSMContext, d: dict):
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(callback.message, state, "این عملیات دیگر معتبر نیست.")
    user_id = callback.from_user.id
    city = city_of(user_id)
    try:
        await channel_reply(
            f"🔙 <b>بازگشت لشکر</b> 🏳️\n{DIV}\n\n"
            f"👑 {mention(user_id)} شهر <b>{e(city)}</b> دستور بازگشت ارسال کرد.\n\n"
            f"⏳ زمان رسیدن به مبدا: <b>{e(d['back_time'])}</b>",
            action["msg_id"],
        )
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پیام بازگشت")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(callback.message, state, "✅ سرورم دستور بازگشت لشکریان شما ثبت شد. 🔙")
    await send_report(
        f"🔙 <b>گزارش بازگشت لشکر</b>\n{DIV}\n👤 فرمانده: {mention(user_id, city)} (ID: <code>{user_id}</code>)\n"
        f"⏳ زمان رسیدن به مبدا: {e(d['back_time'])}"
    )


# ======================================================================
#        پیام‌های بدون وضعیت (مثلاً بعد از ری‌استارت ربات)
# ======================================================================
@dp.message(StateFilter(None), F.chat.type == "private")
async def fallback_handler(message: types.Message, state: FSMContext):
    u = authenticated_users.get(message.from_user.id)
    if u and u.get("role") == "player":
        await go_menu(message, state)
    elif u and u.get("role") == "admin":
        await message.answer("⚡️ پنل مدیریت:", reply_markup=get_admin_inline_keyboard())
    else:
        await message.answer("👋 برای شروع /start را بزنید.")


load_art()


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


@dp.callback_query(F.data == "adm_send_update")
async def admin_send_update(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("✅ بله، به گروه‌ها بفرست", "adm_send_update_yes", "success"))
    builder.row(_btn("❌ انصراف", "back_to_admin"))
    await callback.message.answer(
        f"پیش‌نمایش پیام آپدیت:\n{DIV}\n{UPDATE_CHANGELOG}\n{DIV}\n"
        f"گروه‌های هدف: <b>{len(GROUPS)}</b>\nارسال شود؟",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "adm_send_update_yes")
async def admin_send_update_yes(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer("در حال ارسال…")
    await notify_groups_updated()
    await callback.message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())


# آخرین تاریخ ارسال خودکار استارت/استاپ (YYYY-MM-DD) تا دوبار نفرستد
_auto_timing_sent = {"start": "", "stop": ""}


async def timing_scheduler_loop():
    """هر ۳۰ ثانیه چک می‌کند؛ در ساعت استارت/استاپ پیام را به گروه‌ها و کانال می‌فرستد."""
    while True:
        try:
            now = datetime.now(TZ) if TZ else datetime.now()
            today = now.strftime("%Y-%m-%d")
            hm = f"{now.hour:02d}:{now.minute:02d}"
            start = SETTINGS.get("time_start", "08:00")
            stop = SETTINGS.get("time_stop", "23:00")
            if hm == start and _auto_timing_sent.get("start") != today:
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
            if hm == stop and _auto_timing_sent.get("stop") != today:
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


async def main():
    global BOT_USERNAME
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logging.info("ربات @%s آماده است. CHANNEL_ID=%s", BOT_USERNAME, CHANNEL_ID)
    await init_storage()
    # مهاجرت نام شهرهای انگلیس قدیمی → monarchist/parliamentarian (داده حفظ می‌شود)
    migrated = migrate_city_names()
    seeded = seed_default_cities()
    if migrated or seeded:
        save_data(critical=True)
        logging.info("migrate=%s seed=%s", migrated, seeded)
    # بکاپ فوری بعد از بالا آمدن
    try:
        await push_backup()
    except Exception:
        logging.exception("startup backup")
    # حلقه‌های پس‌زمینه
    spawn(timing_scheduler_loop())
    spawn(periodic_backup_loop())
    try:
        builder = InlineKeyboardBuilder()
        builder.row(_btn("📢 ارسال پیام آپدیت به گروه‌ها", "adm_send_update", "primary"))
        builder.row(_btn("ورود به پنل", "back_to_admin"))
        extra = ""
        if seeded:
            extra += f"\n🌱 شهر جدید: <b>{seeded}</b>"
        if migrated:
            extra += f"\n🔄 مهاجرت نام شهر: <b>{migrated}</b> مورد"
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"✅ ربات آنلاین شد.\n"
                f"🏙 شهر: {len(PLAYER_CODES)} · 👤 فرمانده: {len(all_players)} · 👥 گروه: {len(GROUPS)}"
                f"{extra}\n\n"
                "⏰ ارسال خودکار استارت/استاپ فعال است.\n"
                "💾 بکاپ دوره‌ای هر ۶ ساعت."
            ),
            reply_markup=builder.as_markup(),
            disable_notification=True,
        )
    except Exception:
        logging.exception("پیام استارت به ادمین ناموفق بود.")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
