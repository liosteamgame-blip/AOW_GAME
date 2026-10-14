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

# تجارت‌های در انتظار تأیید ادمین اصلی: trade_id -> dict
PENDING_TRADES = {}

# باف/نرف ثبت‌شده برای آپ: city -> [ {id, kind, target, pct, text, apply_on_up} ]
# kind: buff|nerf · target: اقتدار|مشروعیت|نام ساختمان|کمپ|...
CITY_BUFFS = {}

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

# لیدرهای هر ساید — حداکثر ۵ نفر
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
# آخرین بکاپ قبل از آپ هر شهر (برای بازگردانی شخصی)
UP_SNAPSHOTS = {}

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
        "pending_trades": {str(k): dict(v) for k, v in list(PENDING_TRADES.items())[-80:]},
        "up_snapshots": {str(k): dict(v) for k, v in list(UP_SNAPSHOTS.items())[-60:]},
        "city_buffs": {
            str(c): [dict(x) for x in (lst or [])]
            for c, lst in CITY_BUFFS.items()
        },
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
    
    UP_SNAPSHOTS.clear()
    for ck, sv in (raw.get("up_snapshots") or {}).items():
        if isinstance(sv, dict):
            UP_SNAPSHOTS[str(ck)] = {
                "text": sv.get("text") or "",
                "stats": dict(sv.get("stats") or {}),
                "levels": dict(sv.get("levels") or {}),
                "yields": dict(sv.get("yields") or {}),
                "unlocked": list(sv.get("unlocked") or []),
                "shop": dict(sv.get("shop") or {}),
                "shop_packs": list(sv.get("shop_packs") or []),
                "changes": list(sv.get("changes") or []),
                "ts": sv.get("ts") or "",
            }

    PENDING_TRADES.clear()
    pt = raw.get("pending_trades") or {}
    if isinstance(pt, dict):
        for tid, tv in pt.items():
            if isinstance(tv, dict):
                PENDING_TRADES[str(tid)] = tv
    CITY_BUFFS.clear()
    cb = raw.get("city_buffs") or {}
    if isinstance(cb, dict):
        for cname, lst in cb.items():
            if isinstance(lst, list):
                CITY_BUFFS[str(cname)] = [dict(x) for x in lst if isinstance(x, dict)]
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
        LEADERS[key] = cleaned[:5]
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


def player_group_access(user_id: int, chat_id: int | None = None, chat_type: str | None = None) -> tuple[bool, str | None, str]:
    """
    دسترسی پلیر — یک‌بار ثبت کافی است.
    • پی‌وی: شهر اصلی پلیر
    • گپ ست‌شده: همیشه شهر همان گپ (دارایی/لشکرکشی روی همان گپ)
      پلیر می‌تواند در چند گپ ست‌شده کار کند بدون ثبت مجدد
    • گپ ست‌نشده: رد
    """
    if is_admin(user_id):
        if chat_id and GROUPS.get(chat_id):
            return True, GROUPS[chat_id].get("city"), ""
        return True, resolve_player_city(user_id) or city_of(user_id), ""

    if not is_player(user_id) and not is_leader(user_id):
        return False, None, "❌ اول در پی‌وی ربات /start بزنید و کد ورود را وارد کنید (یک‌بار کافی است)."

    my_city = resolve_player_city(user_id) or city_of(user_id)
    cities = list((authenticated_users.get(user_id) or {}).get("cities") or [])
    if my_city and my_city not in cities and my_city != "ناشناس":
        cities = [my_city] + [c for c in cities if c != my_city]

    # پی‌وی
    if chat_type == "private" or (chat_id is not None and chat_type not in ("group", "supergroup")):
        if not my_city or my_city == "ناشناس":
            return False, None, "❌ شهر شما مشخص نیست. ادمین یک‌بار «ست پلیر» در گپ شهر بزند."
        return True, my_city, ""

    # گروه
    if chat_id is None:
        return True, my_city or (cities[0] if cities else None), ""
    grp = GROUPS.get(chat_id)
    if not grp:
        return False, my_city, (
            "❌ این گروه هنوز «ست گپ» نشده.\n"
            "دستورات فقط در گپ‌های رسمی ست‌شده تأیید می‌شوند."
        )
    gcity = grp.get("city") or ""
    # هر پلیر/لیدر ثبت‌شده می‌تواند در هر گپ ست‌شده کار کند؛ شهر = شهر همین گپ
    return True, gcity or my_city, ""



# ---------- آرت / فکشن / شهرهای پیش‌فرض ----------
ART = {}
ART_RE = re.compile(
    r"^(?:.*/)?art_(campaign|siege|war|ambush|trade)_(land|sea|all)_([a-z]+)_\d+\.(?:jpe?g|png)$",
    re.I,
)
ART_FACTION_MAP = {
    "monarchist": "england",
    "parliamentarian": "england",
    "france": "france",
    "ireland": "ireland",
    "england": "england",
}
FACTIONS = ("monarchist", "parliamentarian", "france", "ireland")
COUNTRY_ALIASES = {
    "monarchist": ["monarchist", "مونارشیست", "سلطنت", "سلطنت طلب", "پادشاهی خواه", "king", "royal"],
    "parliamentarian": ["parliamentarian", "پارلمانری", "پارلمان", "جمهوری", "cromwell"],
    "france": ["france", "فرانسه", "french"],
    "ireland": ["ireland", "ایرلند", "irish"],
    "england": ["england", "انگلیس", "انگلستان", "english"],
}
DEFAULT_CITIES = [
    # monarchist
    "london_monarchist", "oxford_monarchist", "bristol_monarchist", "exeter_monarchist",
    "nottingham_monarchist", "leicester_monarchist", "pembroke_monarchist", "gloucester_monarchist",
    "liverpool_monarchist", "colchester_monarchist", "glasgow_monarchist",
    # parliamentarian
    "norwich_parliamentarian", "leeds_parliamentarian", "dover_parliamentarian",
    "winchester_parliamentarian", "bridgwater_parliamentarian", "exeter_parliamentarian",
    "york_parliamentarian", "gloucester_parliamentarian", "newcastle_parliamentarian",
    "manchester_parliamentarian", "celtic_parliamentarian", "cambridge_parliamentarian",
    "edinburgh_parliamentarian",
    # france
    "paris_france", "nantes_france", "brest_france", "amiens_france", "caen_france",
    "montauban_france",
    # ireland
    "dublin_ireland", "cork_ireland", "limerick_ireland", "waterford_ireland", "armagh_ireland",
]
# باف/نرف پیش‌فرض قلعه‌ها (اقتصادی؛ نبردها apply_on_up=False در seed)
CASTLE_META = {}


def seed_castle_buffs():
    """ثبت باف/نرف اقتصادی قلعه در CITY_BUFFS بدون دوباره‌نویسی دستی."""
    n = 0
    for city, meta in CASTLE_META.items():
        existing = list(CITY_BUFFS.get(city) or [])
        have = {str(x.get("id")) for x in existing}
        for i, bf in enumerate(meta.get("buffs") or []):
            bid = f"castle_{city}_{i}"
            if bid in have:
                continue
            existing.append({
                "id": bid,
                "kind": bf.get("kind") or "buff",
                "target": bf.get("target") or "",
                "pct": float(bf.get("pct") or 0),
                "text": bf.get("text") or "",
                "apply_on_up": bool(bf.get("apply_on_up")),
                "source": "castle",
            })
            n += 1
        CITY_BUFFS[city] = existing
    return n


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
    "exeter", "york", "gloucester", "newcastle", "manchester", "celtic",
    "نورویچ", "لیدز", "دوور", "وینچستر", "بریجواتر", "بریجوایتر",
    "اکستر", "یورک", "گلاستر", "نیوکاسل", "نیوکسل", "منچستر", "سلتیک", "سلتیک",
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
    adm_buff_add = State()         # ثبت باف/نرف

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

    # ثبت شاپ (فوروارد پک‌ها)
    adm_shop_collect = State()

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
        builder.row(
            _btn("✏️ ویرایش دارایی", "menu:asset_edit", "danger"),
            _btn("🛒 شاپ", "eco:shop_admin", "primary"),
        )
    builder.row(_btn("❓ راهنما", "eco:help"), _btn("🔙 بازگشت", "menu:home"))
    return builder.as_markup()


# بخش‌های ارتقا برای منوی سلسله‌مراتبی
UPGRADE_SECTIONS = {
    "econ": ("💰 اقتصادی", ["قلعه", "خزانه", "تجارتخانه", "بندر", "آشپزخانه", "دهکده", "انبار"]),
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
    """آیا این شهر حالت فول‌اتو دارد؟ تطبیق با نام کامل، نرمال، پایه شهر."""
    if not city:
        return False
    if AUTO_CITIES.get(city):
        return True
    cn = _norm_country_token(city)
    base = cn.split("_")[0] if cn else ""
    for k, v in AUTO_CITIES.items():
        if not v:
            continue
        kn = _norm_country_token(k)
        if kn == cn:
            return True
        # پایه بدون پسوند ساید (london == london_monarchist)
        if base and kn.split("_")[0] == base:
            return True
        # بدون زیرخط
        if kn.replace("_", "") == cn.replace("_", ""):
            return True
    return False


def enable_auto_city(city: str) -> None:
    """روشن کردن اتو با کلید استاندارد شهر."""
    if not city:
        return
    # کلید ترجیحی: نام موجود در CITY_ASSETS یا همان ورودی
    key = city
    cn = _norm_country_token(city)
    for c in list(CITY_ASSETS.keys()) + list(all_known_cities()):
        if _norm_country_token(c) == cn:
            key = c
            break
    # پاک کردن کلیدهای هم‌نام قبلی
    for k in list(AUTO_CITIES.keys()):
        if _norm_country_token(k) == _norm_country_token(key):
            AUTO_CITIES.pop(k, None)
    AUTO_CITIES[key] = True


def parse_player_time(raw: str, respect_window: bool = True):
    """
    ورودی زمان پلیر:
    - ساعت مطلق: 12:00 یا 12:00,14:30
    - عدد دقیقه: 45 → الان + 45 دقیقه
    اگر respect_window و بازه استارت/استاپ فعال باشد:
      • دقیقه اگر از استاپ رد شود → باقی‌مانده از استارت بعدی به‌صورت ساعت واقعی
        مثال: بازه ۲۰–۲۳، الان ۲۲:۵۹، ورودی ۵ → ۲۰:۰۴
      • ساعت مطلق خارج از بازه رد می‌شود
    خروجی: رشته مثل 10:16 یا چندتایی با ویرگول.
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
        """دقیقه تا استاپ؛ اگر الان خارج/روی استاپ → 0."""
        if stop_m >= start_m:
            # بازه عادی: 08:00–23:00
            if now_m < start_m:
                return -1  # هنوز استارت نشده
            if now_m >= stop_m:
                return 0
            return stop_m - now_m
        # بازه شبانه: مثلاً 20:00–03:00
        if now_m >= start_m:
            return (24 * 60 - now_m) + stop_m
        if now_m <= stop_m:
            return stop_m - now_m
        return 0  # بین استاپ و استارت = بسته

    def _in_window(m: int, start_m: int, stop_m: int) -> bool:
        if stop_m >= start_m:
            return start_m <= m <= stop_m
        return m >= start_m or m <= stop_m

    for p in parts:
        # فقط عدد = دقیقه از الان
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
                    # قبل از استارت امروز → رسیدن = استارت + دقیقه
                    out.append(_at_start_plus(mins, sh, sm))
                elif mins <= remain:
                    t = now + timedelta(minutes=mins)
                    out.append(t.strftime("%H:%M"))
                else:
                    overflow = mins - remain
                    out.append(_at_start_plus(overflow, sh, sm))
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
# لول‌بندی قلعه (۱ تا ۵)
CASTLE_LEVEL_INFO = {
    1: "قلعه پیش‌فرض — دیوار سنگی معمولی، برجک کوچک، دروازه چوبی/آهنی",
    2: "قلعه توسعه‌یافته — دیوار ضخیم‌تر، برجک دیده‌بانی، دروازه مقاوم‌تر",
    3: "قلعه مستحکم — دیوار سنگی ضخیم، برجک بیشتر، مواضع تیرانداز",
    4: "دژ نظامی — دیوار چندلایه، برجک بزرگ، مقاومت محاصره",
    5: "دژ سلطنتی — حداکثر استحکامات، دروازه چندمرحله‌ای، سخت‌ترین هدف",
}
# ظرفیت پایه گنجایش به ازای هر لول قلعه (پیش‌فرض یکسان؛ VIP جدا تنظیم می‌شود)
CASTLE_CAPACITY = {1: 1000, 2: 1500, 3: 2200, 4: 3200, 5: 4500}

UPGRADE_TABLE = {
    # قلعه: ۳۰۰۰ سکه + ۴۰۰ سنگ + ۴۰۰ آهن + ۳۰۰ نفر · مکس ۵ · بازدهی = ظرفیت
    "قلعه": {
        "coin": 3000, "stone": 400, "iron": 400, "pop": 300,
        "yield": 500, "yunit": "ظرفیت", "max": 5,
        "note": "لول۱:۱۵/۱۵ · لول۲:۳۰/۳۰ · لول۳:۴۵/۴۵ · لول۴–۵ نامحدود · ارتقا=ظرفیت",
    },
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
    "قایق": {"coin": 500, "pop": 60, "cloth": 25, "iron": 40, "yield": 2, "yunit": "فروند", "max": 10},
    "کشتی جنگی": {"coin": 600, "pop": 60, "cloth": 25, "iron": 40, "powder": 50, "yield": 2, "yunit": "فروند", "max": 10},
    "ناو جنگی": {"coin": 700, "pop": 70, "cloth": 50, "iron": 40, "powder": 60, "yield": 2, "yunit": "فروند", "max": 10},
    "کشتی سلطنتی": {"coin": 800, "pop": 80, "cloth": 50, "iron": 60, "powder": 80, "yield": 2, "yunit": "فروند", "max": 10},
}


# نیروهای ویژه ثبت‌شده در بازی (نام → دسته · ضریب · بازدهی پیش‌فرض آپ)
# دسته: inf=پیاده yield100 · cav=سواره yield50 · arty=توپ yield5 · ship=کشتی
SPECIAL_UNITS = {
    "کلداستریم گارد": {"cat": "inf", "coef": 8, "yield": 100, "lock": True},
    "رایفلداران مدرن": {"cat": "inf", "coef": 7, "yield": 100, "lock": True},
    "گاردپادشاهی فرانسه": {"cat": "inf", "coef": 9, "yield": 100, "lock": True},
    "رایفلداران ایرلندی": {"cat": "inf", "coef": 6, "yield": 100, "lock": True},
    "گرنادیر گارد": {"cat": "inf", "coef": 7, "yield": 100, "lock": True},
    "سواره‌نظام دراگون": {"cat": "cav", "coef": 6, "yield": 50, "lock": True},
    "کیوراسیرها": {"cat": "cav", "coef": 9, "yield": 50, "lock": True},
    "سواران رایتر": {"cat": "cav", "coef": 7, "yield": 50, "lock": False},
    "توپ کولورین": {"cat": "arty", "coef": 5, "yield": 5, "lock": True},
    "توپ خمپاره‌ای": {"cat": "arty", "coef": 8, "yield": 5, "lock": True},
    "توپخانه امپراطوری": {"cat": "arty", "coef": 8, "yield": 5, "lock": False},
    "کشتی بریگانتین": {"cat": "ship", "coef": 5, "yield": 2, "lock": True},
    "کشتی جنگی سنگین خط نبرد": {"cat": "ship", "coef": 7, "yield": 2, "lock": True},
}

# هزینه پایه ارتقای ویژه بر اساس دسته
_SPECIAL_COST = {
    "inf": {"coin": 900, "wood": 100, "pop": 100, "cloth": 50, "powder": 100},
    "cav": {"coin": 900, "wood": 80, "pop": 80, "cloth": 50, "horse": 80},
    "arty": {"coin": 900, "powder": 80, "iron": 60, "pop": 60},
    "ship": {"coin": 900, "pop": 80, "cloth": 50, "iron": 60, "powder": 60},
}

def _register_special_units_into_tables():
    """یونیت‌های ویژه را در UPGRADE_TABLE و LOCKED_DEFAULT ثبت می‌کند."""
    for name, meta in SPECIAL_UNITS.items():
        cat = meta.get("cat") or "inf"
        y = int(meta.get("yield") or 50)
        cost = dict(_SPECIAL_COST.get(cat) or _SPECIAL_COST["inf"])
        cost.update({"yield": y, "yunit": "نفر" if cat in ("inf", "cav") else ("عراده" if cat == "arty" else "فروند"), "max": 10})
        if name not in UPGRADE_TABLE:
            UPGRADE_TABLE[name] = cost
        if meta.get("lock"):
            LOCKED_DEFAULT.add(name)

_register_special_units_into_tables()



# مصرف غذا (قوانین)
# جمعیت/کارگر/مهندس: مبنا · پیاده ۱ · سواره ۲ · ویژه ۳
FOOD_PER = {"inf": 1, "cav": 2, "elite": 3}

def count_army_soldiers(bag: dict) -> int:
    """تعداد نفر سرباز زمینی (هر نفر = ۱ غذا در آپ). توپ و کشتی حساب نمی‌شوند."""
    bag = bag or {}
    total = float(_sum_force_soldiers(bag) or 0)
    if total <= 0:
        try:
            total = float(bag.get("سربازان") or 0)
        except (TypeError, ValueError):
            total = 0
    return int(round(total))





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



# نام هدف باف/نرف: فارسی و انگلیسی (نرمال‌شده)
BUFF_TARGET_ALIASES = {
    "treasury": "خزانه", "coin": "سکه", "gold": "سکه", "money": "سکه",
    "village": "دهکده", "population": "جمعیت", "pop": "جمعیت", "peasant": "جمعیت",
    "kitchen": "آشپزخانه", "food": "غذا", "port": "بندر", "harbor": "بندر",
    "tradehouse": "تجارتخانه", "trade": "تجارتخانه", "market": "تجارتخانه",
    "wood": "چوب", "lumber": "چوب بری", "sawmill": "چوب بری",
    "stone": "سنگ", "quarry": "معدن سنگ",
    "iron": "آهن", "mine": "معدن آهن",
    "cloth": "پوشاک", "powder": "باروت", "gunpowder": "باروت",
    "stable": "اصطبل", "horse": "اسب", "horses": "اسب",
    "castle": "قلعه", "warehouse": "انبار",
    "militia": "شبه نظامی", "swordsman": "شمشیرزن", "spearman": "نیزه دار",
    "rifleman": "رایفلدار", "officer": "افسر",
    "cavalry": "سواره نظام شمشیرزن", "authority": "اقتدار", "legitimacy": "مشروعیت",
    "all": "همه", "upgrade": "ارتقا", "cost": "هزینه",
    "ship": "کشتی جنگی", "boat": "قایق", "cannon": "توپ سبک",
}


def normalize_buff_target(raw: str) -> str:
    """هدف باف را به نام فارسی جدول نزدیک می‌کند (انگلیسی/فارسی)."""
    s = (raw or "").strip()
    if not s:
        return s
    # هزینه + نام
    cost_prefix = False
    low = s.lower().replace("ي", "ی").replace("ك", "ک")
    for pref in ("هزینه ", "هزینه", "cost of ", "cost ", "upgrade cost "):
        if low.startswith(pref):
            s = s[len(pref):].strip()
            cost_prefix = True
            low = s.lower()
            break
    key = re.sub(r"[\s_\-]+", "", low)
    mapped = BUFF_TARGET_ALIASES.get(key) or BUFF_TARGET_ALIASES.get(low)
    if not mapped:
        # تطبیق جزئی
        for eng, fa in BUFF_TARGET_ALIASES.items():
            if eng in key or key in eng:
                mapped = fa
                break
    out = mapped or s
    if cost_prefix:
        out = f"هزینه {out}"
    return out


def upgrade_cost_modifier(city: str | None, name: str) -> float:
    """
    ضریب هزینه ارتقا برای یک ساختمان/کمپ.
    باف هزینه (وزیر و …) → کاهش · نرف هزینه → افزایش.
    تشخیص: effect=cost|هزینه  یا  target شامل «هزینه»  یا  متن شامل «هزینه».
    هدف: نام ساختمان / «همه» / «ارتقا»
    """
    if not city or not name:
        return 1.0
    mod = 1.0
    for bf in list(CITY_BUFFS.get(city) or []):
        pct = float(bf.get("pct") or 0)
        if pct <= 0:
            continue
        effect = (bf.get("effect") or "").lower().strip()
        target = normalize_buff_target(bf.get("target") or "")
        text = (bf.get("text") or "")
        is_cost = (
            effect in ("cost", "هزینه", "upgrade_cost")
            or target.startswith("هزینه")
            or "هزینه" in text
            or "cost" in text.lower()
        )
        if not is_cost:
            continue
        # هدف ساختمان
        tname = target
        for prefix in ("هزینه ", "هزینه", "cost "):
            if tname.lower().startswith(prefix.lower()):
                tname = tname[len(prefix):].strip()
                break
        tname = normalize_buff_target(tname)
        tname_n = _norm_country_token(tname) if tname else ""
        name_n = _norm_country_token(name)
        applies = (
            not tname
            or tname in ("همه", "ارتقا", "ساختمان", "all", "any")
            or tname == name
            or tname_n == name_n
            or (tname and tname in name)
            or (name and name in tname)
        )
        if not applies:
            continue
        kind = bf.get("kind") or "buff"
        if kind == "buff":
            mod *= max(0.0, 1.0 - abs(pct) / 100.0)
        else:
            mod *= 1.0 + abs(pct) / 100.0
    return max(0.05, min(mod, 5.0))  # بین ۵٪ تا ۵×


def cost_for_levels(name: str, levels: int, city: str | None = None) -> dict:
    """هزینه N سطح (جدول قوانین × ضریب باف/نرف هزینه شهر)."""
    t = UPGRADE_TABLE.get(name) or {}
    levels = max(1, min(int(levels or 1), int(t.get("max") or 10)))
    mod = upgrade_cost_modifier(city, name)
    out = {}
    for key, _lab in _RES_MAP:
        v = int(t.get(key) or 0) * levels
        if v:
            # گرد به عدد صحیح — حداقل ۱ اگر قبل از باف >0 بود
            nv = int(round(v * mod))
            if v > 0 and nv < 1 and mod < 1:
                nv = 1
            out[key] = nv
    out["_levels"] = levels
    out["_yield_total"] = (t.get("yield") or 0) * levels
    out["_yunit"] = t.get("yunit", "")
    out["_max"] = t.get("max") or 10
    out["_cost_mod"] = round(mod, 4)
    return out


def format_cost_dict(cd: dict) -> str:
    parts = []
    for key, lab in _RES_MAP:
        if cd.get(key):
            parts.append(f"{cd[key]} {lab}")
    base = " + ".join(parts) if parts else "—"
    mod = cd.get("_cost_mod")
    if mod is not None and abs(float(mod) - 1.0) > 0.001:
        pct = (1.0 - float(mod)) * 100
        if pct > 0:
            base += f" (باف هزینه −{pct:.0f}%)"
        else:
            base += f" (نرف هزینه +{abs(pct):.0f}%)"
    return base


def max_affordable_levels(name: str, stock: dict, city: str | None = None) -> int:
    """حداکثر سطحی که با موجودی فعلی قابل پرداخت است (با باف هزینه)."""
    t = UPGRADE_TABLE.get(name) or {}
    if not t:
        return 0
    mx = int(t.get("max") or 10)
    mod = upgrade_cost_modifier(city, name)
    lim = mx
    for key, _lab in _RES_MAP:
        unit = int(t.get(key) or 0)
        if unit <= 0:
            continue
        unit_eff = max(1, int(round(unit * mod))) if mod < 1 else int(round(unit * mod)) or unit
        if unit_eff <= 0:
            continue
        have = float(stock.get(key) or 0)
        lim = min(lim, int(have // unit_eff))
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
            return "بازدهی دهکده"  # در آپ → جمعیت؛ نه موجودی جمعیت
        if section == "port":
            return "بازدهی بندر"
        if section == "kitchen":
            return "بازدهی آشپزخانه"
        if section == "tradehouse":
            return "بازدهی تجارت‌خانه"
        return f"بازدهی ({section or '?'})"
    # جمعیت / رعیت / نفر یکی هستند
    if lab_n in ("جمعیت", "رعیت", "نفر"):
        return "جمعیت"
    if lab_n.startswith("تعدادسرباز") or lab_n in ("تعدادسربازان", "سربازان"):
        return "سربازان"
    return lab


def normalize_stats_keys(bag: dict) -> dict:
    """ادغام کلیدهای هم‌معنی (مثل جمعیت+رعیت) قبل از نمایش/جمع."""
    if not bag:
        return {}
    out = {}
    merge = {"رعیت": "جمعیت", "نفر": "جمعیت", "اهن": "آهن", "اسب‌ها": "اسب"}
    for k, v in bag.items():
        key = merge.get(k, k)
        out[key] = out.get(key, 0) + float(v)
    return {k: (int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)) for k, v in out.items()}


def extract_asset_stats(text: str) -> dict:
    """
    استخراج اعداد از شیت VIP با درک بخش‌ها.

    قواعد قطعی:
    - موجودی بخش خزانه = سکه
    - بازدهی خزانه / تجارتخانه / بندر = سکه در آپ (اگر پرانتز ❌ نباشد)
    - فرمت عمومی: (لول) : بازدهی
    - ❌ داخل پرانتز = غیرفعال (نه لول نه بازدهی)
    """
    text = normalize_digits(text or "")
    stats = {}
    levels = {}
    disabled = set()
    section = ""
    # | نام | (لول یا ❌) : عدد
    line_pat = re.compile(
        r"\|\s*([^|%{}]+?)\s*\|\s*"
        r"(?:\(([^)]*)\))?\s*[:=：]?\s*"
        r"([\d]+(?:\.\d+)?)?\s*$"
    )
    plain_pat = re.compile(
        r"^\s*([^\n|:=：%{}]{1,40}?)\s*"
        r"(?:\(([^)]*)\))?\s*[:=：]\s*"
        r"([\d]+(?:\.\d+)?)\s*$"
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ("﴿" in line or "🏦" in line or "🍽" in line
                or "🛖" in line or "⚓️" in line or "🏗" in line
                or "📦" in line or "🏰" in line or "🛡" in line
                or "خزانه" in line or "آشپزخانه" in line
                or "دهکده" in line or "بندر" in line
                or "تجارت" in line or "انبار" in line
                or "قلعه" in line):
            if not re.search(r"[:=：]\s*\d", line):
                section = _detect_section(line, section)
                # لول قلعه از عنوان: 🍽 ﴿ قلعه﴾ (2)
                if "قلعه" in line:
                    m_cast = re.search(r"قلعه[^\d]*\((\d+)\)", line)
                    if m_cast:
                        try:
                            levels["قلعه"] = int(m_cast.group(1))
                        except ValueError:
                            pass
                # انبار 《4》 یا (4)
                if "انبار" in line:
                    m_wh = re.search(r"انبار[^\d]*[《\[(](\d+)", line)
                    if m_wh:
                        try:
                            levels["انبار"] = int(m_wh.group(1))
                        except ValueError:
                            pass
                continue
        section = _detect_section(line, section)

        if "%" in line:
            continue
        # ظرفیت انبار: 2000/1000 → فعلی/سقف
        if "ظرفیت" in line and re.search(r"\d+\s*/\s*\d+", line):
            mcap = re.search(r"(\d+)\s*/\s*(\d+)", line)
            if mcap:
                try:
                    stats["انبار_پر"] = float(mcap.group(1))
                    stats["انبار_سقف"] = float(mcap.group(2))
                except ValueError:
                    pass
            continue
        # فناوری فقط خطوط بخش فناوری: {نظامی}:《 3》 — نه «شبه نظامی»
        if (
            ("{" in line or "《" in line or "》" in line)
            and any(x in line for x in ("نظامی", "اقتصادی", "پزشکی"))
            and "شبه" not in line
            and "کمپ" not in line
            and "|" not in line  # خطوط جدول نیرو/کمپ
        ):
            mt = re.search(r"(نظامی|اقتصادی|پزشکی)[^\d\n]{0,12}(\d+)", line)
            if mt:
                try:
                    stats[f"فناوری {mt.group(1)}"] = float(mt.group(2))
                except ValueError:
                    pass
                continue

        # محدودیت تجارتخانه قبل از پارس عادی (چون بعد از عدد متن دارد)
        if "محدودیت" in line and section in ("tradehouse", "trade", ""):
            nums = re.findall(r"(\d+(?:\.\d+)?)", normalize_digits(line))
            if nums:
                stats["محدودیت_سکه"] = float(nums[0])
                if len(nums) >= 2:
                    stats["محدودیت_منبع"] = float(nums[1])
            continue

        m = line_pat.search(line)
        if not m:
            m = plain_pat.match(line)
        if not m:
            # |🐎| اسب: 50  یا  اسب: 50
            m2 = re.search(r"(?:\|\s*)?([^|:%{}]{1,30}?)\s*[:=：]\s*(\d+(?:\.\d+)?)\s*$", line)
            if m2:
                class _M:
                    def group(self, i):
                        if i == 1: return m2.group(1)
                        if i == 2: return None
                        if i == 3: return m2.group(2)
                        return None
                m = _M()
            else:
                continue
        label = re.sub(r"\s+", " ", m.group(1)).strip(" |-~•·*_/:：")
        label = _clean_item_name(label) if label else ""
        paren = (m.group(2) or "").strip()
        num_s = (m.group(3) or "").strip()

        if not label or len(label) > 40:
            continue
        if label in _ASSET_SKIP_LABELS:
            continue
        # محدودیت تجارتخانه: 3000سکه، 300منبع
        if "محدودیت" in label or (section == "tradehouse" and "محدود" in label):
            nums = re.findall(r"(\d+(?:\.\d+)?)", normalize_digits(line))
            if nums:
                stats["محدودیت_سکه"] = float(nums[0])
                if len(nums) >= 2:
                    stats["محدودیت_منبع"] = float(nums[1])
            continue
        if any(s in label for s in _ASSET_SKIP_SUBSTR):
            continue
        if re.fullmatch(r"[\W\d_]+", label):
            continue

        # ❌ = غیرفعال
        if "❌" in paren or "x" == paren.lower() or "×" in paren:
            final = _contextual_label(label, section)
            if final:
                disabled.add(final)
                # بازدهی صفر
                if "بازدهی" in (final or "") or label in ("بازدهی",):
                    stats[final] = 0
            continue

        # لول از پرانتز
        lv = None
        if paren and re.fullmatch(r"\d+", paren):
            try:
                lv = int(paren)
            except ValueError:
                lv = None

        if not num_s:
            # فقط لول بدون بازدهی عددی
            if lv is not None:
                final = _contextual_label(label, section) or label
                levels[final] = lv
            continue

        try:
            qty = float(num_s)
        except ValueError:
            continue

        final = _contextual_label(label, section)
        if not final:
            continue

        # نیروی نظامی/تولیدی با (لول): بازدهی → yields نه موجودی لیست
        mil_units = {
            "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
            "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
            "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
            "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
            "کلداستریم گارد", "گرنادیر گارد", "رایفلداران اسکاتلندی",
            "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی", "اصطبل",
        }
        if label not in ("موجودی", "بازدهی") and lv is not None:
            levels[final] = lv
            # بازدهی کمپ/تولیدی جدا از موجودی نیرو
            if final in mil_units or section in (
                "barracks", "production", "military", "army", "workshop", "castle"
            ):
                # (لول): بازدهی → yields (نه موجودی لیست نیرو)
                stats[f"yield:{final}"] = qty
                levels[final] = lv
            else:
                # یونیت ویژه داینامیک با پرانتز لول
                stats[f"yield:{final}"] = qty
                levels[final] = lv
        else:
            # بدون لول = موجودی (لیست نیرو / سکه / …)
            # دانشکده‌ها: عدد تنها = لول (بازدهی جدا یا ۰)
            if any(x in final for x in ("دانشکده", "مجمع نخبگان", "دانشگاه پزشکی")):
                levels[final] = int(qty)
                stats[final] = qty  # لول برای نمایش
            elif final in mil_units:
                stats[final] = qty  # موجودی نیرو (جایگزین نه جمع)
            else:
                stats[final] = stats.get(final, 0) + qty
            if lv is not None and "بازدهی" in final:
                bname = {
                    "بازدهی خزانه": "خزانه",
                    "بازدهی بندر": "بندر",
                    "بازدهی تجارت‌خانه": "تجارتخانه",
                    "بازدهی تجارتخانه": "تجارتخانه",
                    "بازدهی آشپزخانه": "آشپزخانه",
                    "بازدهی دهکده": "دهکده",
                }.get(final)
                if not bname and section:
                    # بخش دهکده/آشپزخانه بدون پیشوند
                    sec_map = {
                        "village": "دهکده",
                        "kitchen": "آشپزخانه",
                        "treasury": "خزانه",
                        "port": "بندر",
                        "tradehouse": "تجارتخانه",
                    }
                    bname = sec_map.get(section)
                if bname:
                    levels[bname] = lv
                    stats[bname] = qty
                    stats[f"yield:{bname}"] = qty

    # موجودی خزانه همیشه سکه است
    if "سکه" not in stats and section:
        pass
    # همگام‌سازی کلید خزانه با بازدهی خزانه
    if stats.get("بازدهی خزانه") and not stats.get("خزانه"):
        stats["خزانه"] = stats["بازدهی خزانه"]
    if stats.get("بازدهی بندر") and not stats.get("بندر"):
        stats["بندر"] = stats["بازدهی بندر"]
    if stats.get("بازدهی تجارت‌خانه") and not stats.get("تجارتخانه"):
        stats["تجارتخانه"] = stats["بازدهی تجارت‌خانه"]

    out = {k: (int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)) for k, v in stats.items()}
    # levels را در کلیدهای رزرو نمی‌گذاریم؛ set_city_asset جدا می‌گیرد
    out["__levels__"] = levels
    out["__disabled__"] = list(disabled)
    return out



def _sum_force_soldiers(bag: dict) -> int:
    """جمع نفر سرباز از لیست نیرو (بدون توپ و کشتی)."""
    bag = bag or {}
    keys = (
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "کیوراسیرها", "رایفلداران مدرن", "کلداستریم گارد", "گرنادیر گارد",
        "رایفلداران اسکاتلندی", "چریک هلندی",
    )
    total = 0.0
    for k in keys:
        try:
            total += float(bag.get(k) or 0)
        except (TypeError, ValueError):
            pass
    skip = {"توپ", "کشتی", "ناو", "قایق", "اسب", "سکه", "چوب", "سنگ", "آهن"}
    for k, v in bag.items():
        if k in keys or any(s in str(k) for s in skip):
            continue
        if any(x in str(k) for x in ("نظام", "گارد", "سوار", "پیاده", "رایفل", "شمشیر", "نیزه", "افسر", "چریک", "مزدور", "گرناد", "کیورا")):
            try:
                n = float(v)
            except (TypeError, ValueError):
                continue
            if 0 < n < 500000:
                total += n
    return int(round(total))

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
    if text.startswith("\n"):
        text = text.lstrip("\n")
    text = _strip_auto_footers(text.rstrip())
    raw = extract_asset_stats(text)
    levels_ex = dict(raw.pop("__levels__", {}) or {})
    disabled = list(raw.pop("__disabled__", []) or [])
    yields_ex = {}
    stats = {}
    for k, v in raw.items():
        if str(k).startswith("__"):
            continue
        if str(k).startswith("yield:"):
            yields_ex[str(k)[6:]] = v
        else:
            stats[k] = v
    prev = CITY_ASSETS.get(city) or {}
    shop = _parse_shop_from_sheet(text)
    merged_lv = dict(prev.get("levels") or {})
    merged_lv.update(levels_ex)
    merged_y = dict(prev.get("yields") or {})
    merged_y.update(yields_ex)
    # تعداد سربازان = جمع لیست نیرو (بات خودش جمع می‌کند)
    _force_sum = _sum_force_soldiers(stats)
    if _force_sum > 0:
        stats["سربازان"] = _force_sum
    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "unlocked": list(prev.get("unlocked") or []),
        "changes": list(prev.get("changes") or []),
        "yields": merged_y,
        "levels": merged_lv,
        "disabled": disabled,
        "shop": shop or dict(prev.get("shop") or {}),
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
        _btn("🎛 باف/نرف", "adm_buffs", "primary"),
        _btn("🛒 تجارت‌های معلق", "adm_pending_trades", "success"),
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
    "• 👑 لیدر ساید (حداکثر ۵ نفر)\n"
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
    already = authenticated_users.get(target.id) or {}
    gcity = grp["city"]
    # لیست شهرهای چندگپی — یک‌بار ثبت کافی است
    cities = list(already.get("cities") or [])
    if already.get("country") and already["country"] not in cities:
        cities.append(already["country"])
    if gcity not in cities:
        cities.append(gcity)
    if already.get("role") in ("player", "admin") or is_leader(target.id):
        authenticated_users[target.id] = {
            **already,
            "role": already.get("role") or "player",
            "country": gcity,  # آخرین گپ فعال
            "cities": cities,
            "code": grp.get("code") or already.get("code") or "",
            "username": target.username or already.get("username") or "",
            "name": target.full_name or already.get("name") or "",
        }
        note = " (قبلاً ثبت بود — بدون کد مجدد · چندگپی)"
    else:
        authenticated_users[target.id] = {
            "role": "player",
            "country": gcity,
            "cities": cities or [gcity],
            "code": grp["code"],
            "username": target.username or "",
            "name": target.full_name,
        }
        note = ""
    all_players.add(target.id)
    save_data(critical=True)

    tfsm = chat_fsm(message.chat.id, target.id)
    await tfsm.clear()
    await tfsm.set_state(GameStates.main_menu)

    await message.answer(
        f"✅ {mention(target.id, target.full_name)} فرمانده‌ی شهر <b>{e(grp['city'])}</b> در این گروه شد.{note}\n\n{MENU_TEXT}",
        reply_markup=get_main_menu_keyboard(),
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text=(
                f"👑 شما فرمانده‌ی شهر <b>{e(grp['city'])}</b> در گروه «{e(message.chat.title or '')}» شدید.\n"
                "می‌توانید در چند گپ ست‌شده کار کنید؛ هر گپ شهر و دارایی خودش را دارد. نیازی به ثبت‌نام مجدد نیست."
            ),
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
    if len(ids) >= 5:
        return await message.answer(f"❌ ظرفیت لیدر {FACTION_META[side][1]} پر است (حداکثر ۵ نفر).")
    ids.append(target.id)
    save_data(critical=True)
    flag, title = FACTION_META[side]
    await message.answer(
        f"✅ {mention(target.id, target.full_name)} لیدر {flag}<b>{title}</b> شد "
        f"({len(ids)}/5).\nمشاهده دارایی از منوی اصلی در دسترس است."
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
    if len(ids) >= 5:
        return await callback.answer("ظرفیت پر است (۵/۵).", show_alert=True)
    ids.append(uid)
    save_data(critical=True)
    flag, title = FACTION_META[side]
    await callback.answer("ثبت شد")
    await callback.message.answer(
        f"✅ کاربر <code>{uid}</code> لیدر {flag}<b>{title}</b> شد ({len(ids)}/5)."
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
        ok, msg = apply_upgrade_levels(city, matched, lv, force=is_admin(uid))
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
def _strip_auto_footers(text: str) -> str:
    """حذف بلوک‌های ——— / 📝 تغییر اتو از ته شیت — وقایع فقط در تغییرات اخیر."""
    if not text:
        return text
    text = re.sub(
        r"\n*\s*—{3,}\s*\n\s*📝[^\n]*(?:\n(?!\s*—{3,})[^\n]*)*",
        "",
        text,
    )
    return text.rstrip()


def apply_stat_delta(city: str, deltas: dict, note: str = "") -> str:
    """
    اعمال تغییر روی stats + اعداد لیست شیت.
    لاگ فقط در «تغییرات اخیر» می‌رود — ته شیت آلوده نمی‌شود.
    """
    entry = CITY_ASSETS.get(city) or {"text": "", "stats": {}}
    stats = normalize_stats_keys(dict(entry.get("stats") or {}))
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
    text = _strip_auto_footers(entry.get("text") or "")
    text = _apply_stock_to_sheet(text, stats)
    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "unlocked": list(entry.get("unlocked") or []),
        "changes": list(entry.get("changes") or []),
        "yields": dict(entry.get("yields") or {}),
        "levels": dict(entry.get("levels") or {}),
        "shop": dict(entry.get("shop") or {}),
    }
    if note or lines_log:
        _append_change(city, (note + " · " if note else "") + "؛ ".join(lines_log[:12]))
    save_data(critical=True)
    return "\n".join(lines_log) or "—"


def _fmt_num(v) -> str:
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:g}"
    except (TypeError, ValueError):
        return str(v)


def _patch_sheet_field(text: str, label: str, new_val) -> str:
    """به‌روز کردن سلول دقیق label در شیت (نه زیررشتهٔ نام دیگر)."""
    if not text or not label:
        return text
    val = _fmt_num(new_val)
    # سلول نام دقیقاً label باشد: |…| label | : عدد
    pat = re.compile(
        rf"(\|[^\n|]{{0,12}}\|(?:-|~)\|[^\n|]{{0,8}}\|\s*)"
        rf"({re.escape(label)})"
        rf"(\s*\|)[ \t]*"
        rf"(?:\([^)]*\))?[ \t]*:?[ \t]*[\d۰-۹.]*",
        re.I,
    )
    nt, n = pat.subn(rf"\1\2\3 : {val}", text, count=1)
    if n:
        return nt
    pat2 = re.compile(
        rf"(\|\s*{re.escape(label)}\s*\|)[ \t]*"
        rf"(?:\([^)]*\))?[ \t]*:?[ \t]*[\d۰-۹.]*",
        re.I,
    )
    nt, n = pat2.subn(rf"\1 : {val}", text, count=1)
    return nt if n else text


def _patch_sheet_level_yield(text: str, name: str, new_lv: int, new_yield: float) -> str:
    """
    ثبت لول و بازدهی روی همان خط لیست شیت.
    تولیدی/کمپ: |…|-| نام | (لول) : بازدهی
    خزانه/بندر/…: خط «بازدهی» زیر همان بخش.
    """
    if not text or not name:
        return text
    y = _fmt_num(new_yield)
    lv = int(new_lv)

    # ۱) خط مستقیم نام ساختمان/کمپ (فقط همان خط — \s خط بعد را نخورد)
    pat = re.compile(
        rf"(\|[^\n|]*\|[^\n|]*\|\s*{re.escape(name)}\s*\|)[ \t]*"
        rf"(?:\([^)]*\))?[ \t]*:?[ \t]*[\d۰-۹.]*",
        re.I,
    )
    nt, n = pat.subn(rf"\1 ({lv}) : {y}", text, count=1)
    if n:
        return nt

    # ۲) ساختمان‌های بخشی: خزانه / بندر / آشپزخانه / دهکده / تجارتخانه
    section_keys = {
        "خزانه": r"خزانه",
        "تجارتخانه": r"تجارت\s*خانه|تجارتخانه",
        "بندر": r"بندر",
        "آشپزخانه": r"آشپزخانه",
        "دهکده": r"دهکده",
        "دانشکده افسری": r"دانشکده\s*افسری",
        "مجمع نخبگان": r"مجمع\s*نخبگان",
        "دانشگاه پزشکی": r"دانشگاه\s*پزشکی",
    }
    sk = section_keys.get(name)
    if sk:
        # پیدا کردن بلوک بخش و جایگزینی خط بازدهی داخل آن
        sec = re.compile(
            rf"({sk}[^\n]*\n)(.*?)(?=\n[🏦🏬🍽🛖⚓️🏗🏰]|$)",
            re.I | re.S,
        )
        m = sec.search(text)
        if m:
            block = m.group(0)
            bpat = re.compile(
                r"(\|\s*📥\s*\|[^\n|]*\|\s*بازدهی\s*\|)[ \t]*(?:\([^)]*\))?[ \t]*:?[ \t]*[\d۰-۹.]*",
                re.I,
            )
            nblock, bn = bpat.subn(rf"\1 ({lv}) : {y}", block, count=1)
            if bn:
                return text[: m.start()] + nblock + text[m.end():]
            # دانشکده‌ها گاهی فقط عدد بعد از نام دارند
            if name.startswith("دانشکده") or "مجمع" in name or "دانشگاه" in name:
                apat = re.compile(
                    rf"(\|[^\n|]*\|\s*{re.escape(name)}[^\n|]*\|)\s*:?\s*[\d۰-۹.]*",
                    re.I,
                )
                nt, n = apat.subn(rf"\1 : {lv}", text, count=1)
                if n:
                    return nt

    # ۳) الگوی آزاد
    pat2 = re.compile(
        rf"({re.escape(name)}[^\n]{{0,40}}?)(?:\((\d+)\)\s*)?:?\s*(\d+)",
        re.I,
    )
    nt, n = pat2.subn(lambda m: f"{m.group(1)}({lv}) : {y}", text, count=1)
    return nt if n else text



def _patch_force_list_counts(text: str, stats: dict, names: tuple) -> str:
    """
    موجودی نیرو را فقط در بلوک لیست نیرو (🛡 پیاده‌نظام / 🐴 سواره / …)
    به‌روز می‌کند — خطوط کمپ پادگان دست نمی‌خورند.
    """
    if not text:
        return text
    # برش از اولین هدر لیست نیرو تا انتها (یا شاپ)
    m = re.search(
        r"(\|\s*🛡\s*\|.*?پیاد|پیاده‌نظام|سواره‌نظام\s*\|\s*$|\|\s*🐴\s*\|.*?سواره|\|\s*🧨\s*\|.*?توپخانه|\|\s*⚓️\s*\|.*?ناوگان)",
        text, re.I | re.M,
    )
    # ساده‌تر: از خطی که «پیاده‌نظام» به‌عنوان هدر لیست است
    idx = -1
    for marker in ("|🛡|", "پیاده‌نظام", "|🐴|~| سوار", "|🌟|~| ویژه", "ناوگان جنگی"):
        j = text.find(marker)
        # ترجیح رخداد آخر قبل از شاپ — لیست نیرو معمولاً پایین شیت است
        j = text.rfind(marker)
        if j >= 0 and (idx < 0 or j < idx or marker.startswith("|🛡")):
            if marker.startswith("|🛡") or "پیاده" in marker or "ناوگان" in marker:
                idx = j
                break
    if idx < 0:
        # fallback: rfind پیاده‌نظام
        idx = text.rfind("پیاده‌نظام")
    if idx < 0:
        return text
    head, tail = text[:idx], text[idx:]
    # قطع قبل از شاپ
    shop = re.search(r"\n\s*💵|\n\s*شاپ\s*:", tail)
    if shop:
        mid, end = tail[:shop.start()], tail[shop.start():]
    else:
        mid, end = tail, ""
    for nm in names:
        if nm not in stats:
            continue
        val = _fmt_num(stats[nm])
        # فقط خطوط بدون پرانتز لول کمپ — موجودی ساده : عدد
        pat = re.compile(
            rf"(\|[^\n|]{{0,12}}\|(?:-|~)\|[^\n|]{{0,8}}\|\s*)({re.escape(nm)})(\s*\|)[ \t]*"
            rf"(?:🔒)?[ \t]*:?[ \t]*[\d۰-۹.]*[ \t]*(?:🔒)?",
            re.I,
        )
        mid, n = pat.subn(rf"\1\2\3 : {val}", mid, count=1)
        if not n:
            pat2 = re.compile(
                rf"(\|\s*{re.escape(nm)}\s*\|)[ \t]*(?:🔒)?[ \t]*:?[ \t]*[\d۰-۹.]*",
                re.I,
            )
            mid, _ = pat2.subn(rf"\1 : {val}", mid, count=1)
    return head + mid + end


def _apply_stock_to_sheet(text: str, stats: dict) -> str:
    """اعداد لیست شیت را با stats هم‌تراز: سکه/انبار/اسب/غذا/نیرو."""
    if not text:
        return text
    if "سکه" in stats:
        text = _patch_sheet_field(text, "موجودی", stats["سکه"])
    for sk, lab in (
        ("چوب", "چوب"), ("آهن", "اهن"), ("سنگ", "سنگ"),
        ("پوشاک", "پوشاک"), ("باروت", "باروت"),
        ("جمعیت", "جمعیت"), ("اسب", "اسب"),
    ):
        if sk in stats:
            text = _patch_sheet_field(text, lab, stats[sk])
            if lab == "اهن":
                text = _patch_sheet_field(text, "آهن", stats[sk])
    if "غذا" in stats:
        text = re.sub(
            r"(\|\s*🥣\s*\|[^\n|]*\|\s*موجودی\s*\|)[ \t]*:?[ \t]*[\d۰-۹.]*",
            rf"\1 : {_fmt_num(stats['غذا'])}",
            text,
            count=1,
            flags=re.I,
        )
    force_names = [
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
        "کلداستریم گارد", "گرنادیر گارد", "رایفلداران اسکاتلندی",
        "اسب",
    ]
    # یونیت‌های ویژه/داینامیک که در stats هستند
    skip = {
        "سکه", "چوب", "سنگ", "آهن", "پوشاک", "باروت", "غذا", "جمعیت",
        "اقتدار", "مشروعیت", "پوینت", "پوئن", "خزانه", "بندر", "تجارتخانه",
        "آشپزخانه", "دهکده", "اصطبل", "ظرفیت قلعه", "موجودی",
    }
    for k in stats:
        if k in skip or str(k).startswith("yield:") or str(k).startswith("__"):
            continue
        if k not in force_names:
            force_names.append(k)
    text = _patch_force_list_counts(text, stats, tuple(force_names))
    # اسب گاهی بیرون از بلوک نیروست
    if "اسب" in stats:
        text = _patch_sheet_field(text, "اسب", stats["اسب"])
    return text



def _annotate_yield_pct(text: str, name: str, signed_pct: float) -> str:
    """جلوی بازدهی ساختمان در شیت +۳۰٪ یا −۱۰٪ می‌نویسد (لول عوض نمی‌شود)."""
    if not text or not name:
        return text
    sign = "+" if signed_pct >= 0 else ""
    tag = f"{sign}{signed_pct:g}%"
    # پاک کردن تگ قبلی همان نام
    text = re.sub(
        rf"({re.escape(name)}[^\n]*?\(\s*\d+\s*\)\s*)([+\-]\s*\d+(?:\.\d+)?\s*%\s*)?(:)",
        rf"\1{tag} :",
        text,
        count=1,
        flags=re.I,
    )
    # اگر تگ نخورد، بعد از پرانتز لول اضافه کن
    if tag not in text:
        text = re.sub(
            rf"({re.escape(name)}[^\n]*?\(\s*\d+\s*\))(\s*:)",
            rf"\1 {tag}\2",
            text,
            count=1,
            flags=re.I,
        )
    return text


def apply_upgrade_levels(city: str, name: str, levels: int, force: bool = False) -> tuple[bool, str]:
    """
    ارتقا:
    - کسر هزینه از موجودی (سکه/چوب/…)
    - افزایش لول ذخیره‌شده
    - افزایش بازدهی برای آپ بعدی
    force=True برای ادمین حتی بدون اتو.
    """
    if not force and not is_auto_city(city):
        return False, "اتو برای این شهر فعال نیست. ادمین → 🤖 شهرهای اتو"
    t = UPGRADE_TABLE.get(name)
    if not t:
        return False, f"ساختمان «{name}» در جدول نیست."
    if is_building_locked(city, name) and not force:
        return False, f"«{name}» قفل است — اول بازکردن قفل."

    levels = max(1, min(int(levels or 1), int(t.get("max") or 10)))
    # سقف ارتقا بر اساس لول قلعه (اقتصادی و نظامی جدا):
    #   لول۱ → ۱۵ · لول۲ → ۳۰ (+۱۵) · لول۳ → ۴۵ (+۱۵) · لول۴–۵ → نامحدود
    # باف/نرف ارتقا نیستند و از این سقف حساب نمی‌شوند
    ECON_CAP_NAMES = {
        "خزانه", "تجارتخانه", "بندر", "آشپزخانه", "دهکده", "انبار",
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        "دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی",
    }
    MIL_CAP_NAMES = {
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی", "اصطبل",
    }
    if name != "قلعه":
        entry0 = CITY_ASSETS.get(city) or {}
        c_lv = int((entry0.get("levels") or {}).get("قلعه") or 1)
        # سقف پلکانی
        if c_lv >= 4:
            cap_max = None  # نامحدود
        else:
            cap_max = 15 * max(1, min(c_lv, 3))  # 1→15, 2→30, 3→45
        if cap_max is not None:
            lvmap = entry0.get("levels") or {}
            if name in ECON_CAP_NAMES:
                total_lv = sum(int(v or 0) for k, v in lvmap.items() if k in ECON_CAP_NAMES)
                if total_lv + levels > cap_max:
                    return False, (
                        f"سقف <b>{cap_max} لول اقتصادی</b> (قلعه لول {c_lv}).\n"
                        f"الان اقتصادی ≈ {total_lv} · با ارتقای قلعه سقف +۱۵ می‌شود "
                        f"(لول۲=۳۰ · لول۳=۴۵ · لول۴+ نامحدود)."
                    )
            elif name in MIL_CAP_NAMES:
                total_lv = sum(int(v or 0) for k, v in lvmap.items() if k in MIL_CAP_NAMES)
                if total_lv + levels > cap_max:
                    return False, (
                        f"سقف <b>{cap_max} لول نظامی</b> (قلعه لول {c_lv}).\n"
                        f"الان نظامی ≈ {total_lv} · با ارتقای قلعه سقف +۱۵ می‌شود "
                        f"(لول۲=۳۰ · لول۳=۴۵ · لول۴+ نامحدود)."
                    )
    entry = CITY_ASSETS.get(city) or {"text": "", "stats": {}, "levels": {}, "yields": {}}
    bag = normalize_stats_keys(dict(entry.get("stats") or get_city_asset_stats(city) or {}))
    # سکه از موجودی خزانه
    if not bag.get("سکه"):
        bag["سکه"] = float(bag.get("موجودی") or 0)

    stock = _bag_stock(bag)
    # اگر سکه در stock صفر است ولی در text هست، از extract دوباره
    if stock.get("coin", 0) <= 0:
        fresh = normalize_stats_keys(extract_asset_stats(entry.get("text") or ""))
        if fresh.get("سکه"):
            bag["سکه"] = float(fresh["سکه"])
            stock = _bag_stock(bag)

    aff = max_affordable_levels(name, stock, city=city)
    if aff < levels:
        if aff <= 0:
            need = format_cost_dict(cost_for_levels(name, 1, city=city))
            return False, (
                f"موجودی کافی نیست.\n"
                f"هزینه ۱ سطح: {need}\n"
                f"سکه الان: {stock.get('coin', 0):g}"
            )
        levels = aff

    cd = cost_for_levels(name, levels, city=city)
    # لول فعلی
    lv_map = dict(entry.get("levels") or {})
    ymap = dict(entry.get("yields") or {})
    sheet = entry.get("text") or ""
    cur_lv = lv_map.get(name)
    if cur_lv is None:
        cur_lv = guess_current_level(name, bag, sheet) or 0
    try:
        cur_lv = int(cur_lv)
    except (TypeError, ValueError):
        cur_lv = 0
    max_lv = int(t.get("max") or 10)
    if cur_lv >= max_lv:
        return False, f"«{name}» در لول مکس ({max_lv}) است."
    levels = min(levels, max_lv - cur_lv)
    if levels <= 0:
        return False, "سطحی برای ارتقا نمانده."

    new_lv = cur_lv + levels
    y_each = float(t.get("yield") or 0)
    # کمپ نظامی: بازدهی ≠ تعداد نیرو
    _ECON_BLD = {
        "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        "قلعه", "انبار", "دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی",
    }
    _MIL_CAMP_NAMES = {
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
        "کلداستریم گارد", "گرنادیر گارد", "رایفلداران اسکاتلندی",
        "کیوراسیرها", "رایفلداران مدرن", "چریک هلندی",
    }
    # ویژه داینامیک: هر نامی که ساختمان اقتصادی نیست و در لیست نیرو/کمپ است
    _is_mil_camp = name in _MIL_CAMP_NAMES or (
        name not in _ECON_BLD
        and any(x in name for x in (
            "نظام", "گارد", "سوار", "پیاده", "رایفل", "شمشیر", "نیزه",
            "افسر", "توپ", "قایق", "کشتی", "ناو", "چریک", "مزدور",
            "گرناد", "کیورا", "رایتر", "امپراط",
        ))
    )
    # بزرگ‌ترین بازدهی واقعی — برای کمپ نظامی stock نیرو را با بازدهی قاطی نکن
    _cands = []
    for _src in (ymap.get(name), bag.get(f"yield:{name}"), bag.get(f"بازدهی {name}")):
        try:
            if _src is not None and float(_src) > 0:
                _cands.append(float(_src))
        except (TypeError, ValueError):
            pass
    if not _is_mil_camp:
        for _src in (bag.get(name),):
            try:
                if _src is not None and float(_src) > 0:
                    _cands.append(float(_src))
            except (TypeError, ValueError):
                pass
    old_y = max(_cands) if _cands else 0.0
    if old_y <= 0 and cur_lv > 0:
        old_y = y_each * cur_lv
    if old_y <= 0:
        old_y = y_each * max(cur_lv, 0)
    new_y = old_y + y_each * levels

    # کسر هزینه — نفر = همان جمعیت
    deltas = {}
    for key, lab in _RES_MAP:
        need = int(cd.get(key) or 0)
        if need <= 0:
            continue
        deltas[lab] = deltas.get(lab, 0) - need

    # اعمال هزینه روی stats
    stats = dict(bag)
    lines_log = []
    for k, dlt in deltas.items():
        old = float(stats.get(k) or 0)
        new = max(0, old + dlt)
        stats[k] = new
        lines_log.append(f"{k}: {old:g} → {new:g} ({dlt:+g})")

    # لول + بازدهی
    # کمپ نظامی: فقط لول/بازدهی کمپ — تعداد نیرو دست نخورده تا آپ هفتگی
    lv_map[name] = new_lv
    ymap[name] = new_y
    stats[f"yield:{name}"] = new_y
    if _is_mil_camp:
        # stats[name] = موجودی نیرو — عوض نشود
        pass
    else:
        stats[name] = new_y  # ساختمان اقتصادی: بازدهی در stats
    if name == "قلعه":
        cap = CASTLE_CAPACITY.get(new_lv) or CASTLE_CAPACITY.get(5, 4500)
        stats["ظرفیت قلعه"] = cap
        ymap["قلعه"] = cap
        lines_log.append(f"ظرفیت قلعه → {cap}")
        info = CASTLE_LEVEL_INFO.get(new_lv) or ""
        if info:
            lines_log.append(info)

    lines_log.append(f"لول {name}: {cur_lv} → {new_lv}")
    lines_log.append(f"بازدهی {name}: {old_y:g} → {new_y:g} (+{y_each * levels:g})")

    # فقط لیست شیت به‌روز — بدون چسباندن لاگ به ته شیت
    text = _strip_auto_footers(sheet)
    text = _patch_sheet_level_yield(text, name, new_lv, new_y)
    text = _apply_stock_to_sheet(text, stats)

    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "levels": lv_map,
        "yields": ymap,
        "unlocked": list(entry.get("unlocked") or []),
        "changes": list(entry.get("changes") or []),
        "shop": dict(entry.get("shop") or {}),
    }
    cost_txt = format_cost_dict(cd)
    detail = (
        f"ارتقا {name} {cur_lv}→{new_lv} · هزینه {cost_txt} · "
        f"بازدهی {old_y:g}→{new_y:g} · " + "؛ ".join(lines_log[:8])
    )
    _append_change(city, detail)
    save_data(critical=True)
    return True, (
        f"✅ <b>{e(name)}</b>: لول {cur_lv} → <b>{new_lv}</b>\n"
        f"🧮 هزینه: {e(cost_txt)}\n"
        f"◻️ بازدهی: {old_y:g} → <b>{new_y:g}</b>\n"
        + "\n".join(lines_log)
        + "\n\n📜 جزئیات در «تغییرات اخیر»"
    )


# مقصد بازدهی هر ساختمان در آپ
# سکه ← خزانه/بندر/تجارتخانه | انبار ← تولیدی‌ها | اسب ← اصطبل | لیست نیرو ← کمپ‌ها
UP_YIELD_DEST = {
    "خزانه": "سکه",
    "بندر": "سکه",
    "تجارتخانه": "سکه",
    "آشپزخانه": "غذا",
    "دهکده": "جمعیت",
    "چوب بری": "چوب",
    "معدن سنگ": "سنگ",
    "معدن آهن": "آهن",
    "پوشاک سازی": "پوشاک",
    "باروت سازی": "باروت",
    "اصطبل": "اسب",
    # کمپ‌ها → همان نام یونیت در لیست نیرو
    "شبه نظامی": "شبه نظامی",
    "شمشیرزن": "شمشیرزن",
    "نیزه دار": "نیزه دار",
    "رایفلدار": "رایفلدار",
    "افسر": "افسر",
    "سواره نظام شمشیرزن": "سواره نظام شمشیرزن",
    "سواره‌نظام زره پوش": "سواره‌نظام زره پوش",
    "سواره‌نظام تفنگدار": "سواره‌نظام تفنگدار",
    "ویژه": "ویژه",
    "توپ سبک": "توپ سبک",
    "توپ محاصره": "توپ محاصره",
    "توپ سنگین": "توپ سنگین",
    "قایق": "قایق",
    "کشتی جنگی": "کشتی جنگی",
    "ناو جنگی": "ناو جنگی",
    "کشتی سلطنتی": "کشتی سلطنتی",
}



def trade_house_capacity(city: str) -> int:
    """سقف هفتگی تجارتخانه — از شیت (محدودیت سکه) یا پیش‌فرض بر اساس لول."""
    entry = CITY_ASSETS.get(city) or {}
    bag = entry.get("stats") or {}
    # عدد نوشته‌شده در شیت اولویت دارد
    try:
        cap = float(bag.get("محدودیت_سکه") or 0)
        if cap > 0:
            return int(cap)
    except (TypeError, ValueError):
        pass
    lv = int((entry.get("levels") or {}).get("تجارتخانه") or 0)
    if lv <= 0:
        y = float(bag.get("تجارتخانه") or bag.get("بازدهی تجارت‌خانه") or 0)
        lv = max(1, int(y // 150) if y else 1)
    return 3000 + max(0, lv - 1) * 500


def trade_house_remaining(city: str) -> int:
    entry = CITY_ASSETS.get(city) or {}
    used = int(entry.get("trade_cap_used") or 0)
    return max(0, trade_house_capacity(city) - used)


def consume_trade_house_cap(city: str, amount: float) -> tuple[bool, str]:
    """کسر از ظرفیت هفتگی تجارتخانه."""
    amount = abs(float(amount or 0))
    if amount <= 0:
        return True, ""
    rem = trade_house_remaining(city)
    if amount > rem + 1e-6:
        return False, f"ظرفیت هفتگی تجارتخانه کافی نیست (باقی‌مانده: {rem:g})."
    entry = CITY_ASSETS.setdefault(city, {})
    entry["trade_cap_used"] = int(entry.get("trade_cap_used") or 0) + int(round(amount))
    CITY_ASSETS[city] = entry
    return True, f"ظرفیت تجارتخانه −{int(round(amount))} (باقی: {trade_house_remaining(city)})"



def _snapshot_city_assets(city: str) -> None:
    """بکاپ دارایی شهر قبل از آپ — برای بازگردانی شخصی."""
    entry = CITY_ASSETS.get(city) or {}
    import copy
    UP_SNAPSHOTS[city] = {
        "text": entry.get("text") or "",
        "stats": dict(entry.get("stats") or {}),
        "levels": dict(entry.get("levels") or {}),
        "yields": dict(entry.get("yields") or {}),
        "unlocked": list(entry.get("unlocked") or []),
        "shop": dict(entry.get("shop") or {}),
        "shop_packs": list(entry.get("shop_packs") or []),
        "changes": list(entry.get("changes") or []),
        "ts": datetime.now(TZ).strftime("%Y-%m-%d %H:%M") if TZ else datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def restore_city_up(city: str) -> tuple[bool, str]:
    """بازگردانی دارایی شهر به قبل از آخرین آپ."""
    snap = UP_SNAPSHOTS.get(city)
    if not snap:
        return False, f"❌ برای «{city}» بکاپ آپ وجود ندارد."
    CITY_ASSETS[city] = {
        "text": snap.get("text") or "",
        "stats": dict(snap.get("stats") or {}),
        "levels": dict(snap.get("levels") or {}),
        "yields": dict(snap.get("yields") or {}),
        "unlocked": list(snap.get("unlocked") or []),
        "shop": dict(snap.get("shop") or {}),
        "shop_packs": list(snap.get("shop_packs") or []),
        "changes": list(snap.get("changes") or []),
    }
    _append_change(city, f"بازگردانی آپ ({snap.get('ts') or '—'})")
    save_data(critical=True)
    return True, f"✅ دارایی «{city}» به قبل از آپ ({snap.get('ts') or '—'}) برگردید."


def run_weekly_up_for_city(city: str, force: bool = False) -> str:
    """
    آپ هفتگی — بازدهی‌ها به مقصد مشخص:
    • خزانه+بندر+تجارتخانه → جمع می‌شود و به موجودی سکه خزانه
    • تولیدی‌ها → انبار (چوب/سنگ/آهن/پوشاک/باروت)
    • اصطبل → تعداد اسب
    • کمپ‌ها → لیست نیرو (همان یونیت)
    • آشپزخانه → غذا · دهکده → جمعیت
    force=True: ادمین حتی بدون اتو می‌تواند یک شهر را آپ کند
    """
    if not force and not is_auto_city(city):
        return f"⏭ {city}: اتو نیست"
    _snapshot_city_assets(city)
    entry = CITY_ASSETS.get(city) or {}
    # شیت = منبع حقیقت برای بازدهی (مثلاً خزانه ۷۰۰۰ نه پیش‌فرض ۱۰۰۰ جدول)
    sheet_text = entry.get("text") or ""
    if sheet_text.strip():
        try:
            raw_ex = extract_asset_stats(sheet_text)
            levels_ex = dict(raw_ex.pop("__levels__", {}) or {})
            disabled_ex = list(raw_ex.pop("__disabled__", []) or [])
            for k, v in list(raw_ex.items()):
                if str(k).startswith("yield:"):
                    ymap_sheet = entry.setdefault("yields", {})
                    ymap_sheet[str(k)[6:]] = float(v)
                    entry["yields"] = ymap_sheet
                elif not str(k).startswith("__"):
                    try:
                        st = entry.setdefault("stats", {})
                        # بازدهی ساختمان‌ها را در stats هم همگام کن
                        if k in (
                            "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
                            "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
                        ) or str(k).startswith("بازدهی"):
                            st[k] = float(v)
                            entry["stats"] = st
                    except (TypeError, ValueError):
                        pass
            if levels_ex:
                lv = dict(entry.get("levels") or {})
                lv.update(levels_ex)
                entry["levels"] = lv
            if disabled_ex:
                entry["disabled"] = disabled_ex
            CITY_ASSETS[city] = entry
        except Exception:
            logging.exception("بازخوانی بازدهی از شیت %s", city)

    bag = normalize_stats_keys(dict(entry.get("stats") or get_city_asset_stats(city) or {}))
    disabled = set(entry.get("disabled") or [])
    lv_map = dict(entry.get("levels") or {})
    ymap = dict(entry.get("yields") or {})
    deltas = {}

    def _yield_of(name: str, default_y: float = 0) -> float:
        """بازدهی واقعی شیت؛ پیش‌فرض جدول فقط وقتی هیچ عددی روی شیت نباشد."""
        if name in disabled or f"بازدهی {name}" in disabled:
            return 0
        if is_building_locked(city, name):
            return 0
        candidates = []
        # 1) yields از شیت/ارتقا
        if ymap.get(name) is not None:
            try:
                candidates.append(float(ymap[name]))
            except (TypeError, ValueError):
                pass
        # 2) بازدهی X در bag
        for key in (f"بازدهی {name}", name):
            if bag.get(key) is not None:
                try:
                    candidates.append(float(bag[key]))
                except (TypeError, ValueError):
                    pass
        # اگر چند مقدار بود (شیت ۷۰۰۰ و کش قدیمی ۱۰۰۰) بزرگ‌ترِ مثبت = بازدهی واقعی شیت
        positive = [c for c in candidates if c and c > 0]
        if positive:
            return max(positive)
        # فقط اگر هیچ عددی روی شیت نبود و لول > 0 → پیش‌فرض جدول × لول
        lv = float(lv_map.get(name) or 0)
        if lv > 0 and default_y > 0:
            return float(default_y) * lv
        return 0

    coin_parts = []
    applied_names = set()
    for name, dest in UP_YIELD_DEST.items():
        if is_building_locked(city, name):
            continue
        default_y = float((UPGRADE_TABLE.get(name) or {}).get("yield") or 0)
        add = _yield_of(name, default_y)
        if add <= 0:
            continue
        applied_names.add(name)
        if dest == "سکه":
            deltas["سکه"] = deltas.get("سکه", 0) + add
            coin_parts.append(f"{name}+{add:g}")
        else:
            deltas[dest] = deltas.get(dest, 0) + add

    # کمپ ویژه و یونیت‌های داینامیک: هر نامی در yields که در UP_YIELD_DEST نیست
    # بازدهی همان عبارت → لیست نیرو با همان نام
    skip_dest = {
        "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        "قلعه", "انبار", "دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی",
    }
    for name, yv in list(ymap.items()):
        if name in applied_names or name in skip_dest:
            continue
        if name in UP_YIELD_DEST:
            continue
        try:
            add = float(yv or 0)
        except (TypeError, ValueError):
            continue
        if add <= 0:
            continue
        if is_building_locked(city, name):
            continue
        # یونیت ویژه/داینامیک → همان نام در لیست نیرو
        deltas[name] = deltas.get(name, 0) + add
        applied_names.add(name)
        coin_parts.append(f"{name}+{add:g}")

    #兜底: اگر دهکده/اصطبل در ymap بود ولی UP نخورد
    for name, dest in (("دهکده", "جمعیت"), ("اصطبل", "اسب")):
        if name in applied_names:
            continue
        add = _yield_of(name, 0)
        if add > 0:
            deltas[dest] = deltas.get(dest, 0) + add
            applied_names.add(name)
            coin_parts.append(f"{name}→{dest}+{add:g}")

    buff_notes = list(coin_parts)

    # باف/نرف با تیک apply_on_up — فقط روی بازدهی/آپ اثر می‌کند (ارتقا نیست)
    # هدف ساختمان → تغییر بازدهی همان بخش؛ روی شیت هم +N% ثبت می‌شود
    sheet_buff_ann = []  # (building_name, signed_pct)
    for bf in list(CITY_BUFFS.get(city) or []):
        if not bf.get("apply_on_up"):
            continue  # اطلاعی — فقط نمایش
        target = normalize_buff_target(bf.get("target") or "")
        pct = float(bf.get("pct") or 0)
        kind = bf.get("kind") or "buff"
        if not target or not pct:
            continue
        # باف هزینه فقط روی ارتقا است نه آپ
        if (bf.get("effect") or "") == "cost" or target.startswith("هزینه"):
            continue
        sign = -1 if kind == "nerf" else 1
        signed_pct = sign * abs(pct)
        # نگاشت هدف به مقصد بازدهی
        dest = UP_YIELD_DEST.get(target)
        if dest is None:
            # هدف مستقیم منبع یا یونیت
            dest = target
        # پایه: بازدهی این آپ از deltas یا از _yield_of
        base = float(deltas.get(dest) or 0)
        if base <= 0 and target in UP_YIELD_DEST:
            base = _yield_of(target, 0)
            if base > 0:
                deltas[dest] = deltas.get(dest, 0) + base
        if base <= 0:
            base = float(bag.get(dest) or bag.get(target) or 0)
        if base <= 0 and target not in ("اقتدار", "مشروعیت"):
            buff_notes.append(f"{kind} {target} {pct:g}% (پایه۰)")
            continue
        delta = base * (abs(pct) / 100.0) * sign
        if target in ("اقتدار", "مشروعیت"):
            # درصد از مقدار فعلی نوار
            cur = float(bag.get(target) or 0)
            delta = cur * (abs(pct) / 100.0) * sign
            deltas[target] = deltas.get(target, 0) + delta
        else:
            deltas[dest] = float(deltas.get(dest) or 0) + delta
        buff_notes.append(f"{kind} {target}→{dest} {signed_pct:+g}%")
        if target in UP_YIELD_DEST or target in (
            "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
            "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        ):
            sheet_buff_ann.append((target, signed_pct))

    # اقتدار ۸۰–۱۰۰: +۲۵۰ سکه از مردم (قوانین)
    auth = float(bag.get("اقتدار") or 0)
    if auth >= 80:
        deltas["سکه"] = deltas.get("سکه", 0) + 250
        buff_notes.append("اقتدار اوج: +۲۵۰ سکه مردمی")

    # مصرف غذا: هر نفر سرباز در ارتش = ۱ غذا از آشپزخانه
    # (بازدهی آشپزخانه قبلاً به deltas["غذا"] اضافه شده؛ اینجا کسر می‌شود)
    soldiers = count_army_soldiers(bag)
    if soldiers > 0:
        deltas["غذا"] = deltas.get("غذا", 0) - soldiers
        buff_notes.append(f"مصرف غذا {soldiers} سرباز (−{soldiers})")

    # شاپ: بازدهی پک‌ها (عدد داخل پرانتز)
    entry = CITY_ASSETS.get(city) or {}
    shop = dict(entry.get("shop") or {})
    if not shop:
        shop = _parse_shop_from_sheet(entry.get("text") or "")
    for item, yv in shop.items():
        try:
            yv = int(round(float(yv)))
        except (TypeError, ValueError):
            continue
        if yv <= 0:
            continue
        deltas[item] = deltas.get(item, 0) + yv
        buff_notes.append(f"شاپ {item}+{yv}")

    # ریست ظرفیت هفتگی تجارتخانه
    entry["trade_cap_used"] = 0
    CITY_ASSETS[city] = entry

    if not deltas:
        save_data(critical=True)
        return f"ℹ️ {city}: بازده قابل‌اعمال نبود · ظرفیت تجارتخانه ریست شد"
    note = "آپ هفتگی"
    if buff_notes:
        note += " · " + "، ".join(buff_notes[:8])
    log = apply_stat_delta(city, deltas, note=note)
    # ثبت درصد باف/نرف جلوی بازدهی ساختمان در شیت (بدون تغییر لول)
    e2 = CITY_ASSETS.get(city) or {}
    if sheet_buff_ann:
        text2 = e2.get("text") or ""
        for bname, spct in sheet_buff_ann:
            text2 = _annotate_yield_pct(text2, bname, spct)
        e2["text"] = text2
    e2["trade_cap_used"] = 0
    CITY_ASSETS[city] = e2
    save_data(critical=True)
    return f"✅ آپ {city}\n{log}\n♻️ ظرفیت تجارتخانه ریست شد"



def _parse_shop_from_sheet(text: str) -> dict:
    """بازدهی عددی شاپ برای آپ: نام → عدد صحیح."""
    packs = _parse_shop_packs(text)
    out = {}
    for pk in packs:
        y = int(pk.get("yield") or 0)
        unit = (pk.get("unit") or pk.get("name") or "").strip()
        if y > 0 and unit:
            out[unit] = out.get(unit, 0) + y
        # ارتش همراه هیرو
        for u in pk.get("army") or []:
            uy = int(u.get("yield") or 0)
            un = (u.get("unit") or "").strip()
            if uy > 0 and un:
                out[un] = out.get(un, 0) + uy
            elif un and int(u.get("count") or 0) > 0 and uy == 0:
                # فقط تعداد — در آپ همان تعداد به نیرو اضافه می‌شود
                out[un] = out.get(un, 0) + int(u.get("count") or 0)
        # گروهک: تعداد یونیت
        if pk.get("kind") in ("merc_group", "merc", "spy", "guard") and pk.get("count"):
            un = (pk.get("unit") or pk.get("name") or "").strip()
            c = int(pk.get("count") or 0)
            if un and c > 0 and y <= 0:
                out[un] = out.get(un, 0) + c
    return out


def _parse_shop_packs(text: str) -> list:
    """
    پارس ساختاریافته شاپ:
    - وزیر: فقط نام
    - هیرو: نام + ارتش همراه (خطوط بعدی با عدد)
    - گروهک مزدوری: نوع + تعداد
    - مزدور / جاسوس / گارد: تعداد و/یا بازدهی
    - پک عمومی: نام (بازدهی) یا نام (تعداد) : بازدهی
    """
    if not text:
        return []
    m = re.search(r"شاپ\s*:?\s*(.*)$", text, re.I | re.S)
    block = m.group(1) if m else text
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    packs = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        low = ln.replace("ي", "ی").lower()
        # وزیر
        if re.search(r"وزیر", ln):
            name = re.sub(r"^.*?وزیر\s*", "", ln).strip(" :-|")
            name = _clean_item_name(name) or ln
            packs.append({"kind": "minister", "name": name, "yield": 0})
            i += 1
            continue
        # هیرو / فرمانده
        if re.search(r"هیرو|قهرمان|فرمانده|🥷", ln, re.I):
            name = re.sub(r"^.*?(هیرو|قهرمان|فرمانده)\s*", "", ln, flags=re.I).strip(" :-|")
            name = _clean_item_name(name) or ln
            army = []
            i += 1
            while i < len(lines):
                al = lines[i]
                if re.search(r"وزیر|هیرو|قهرمان|فرمانده|گروهک|مزدور|جاسوس|گارد|🥷|🤵|💵", al, re.I):
                    break
                # "50 ژاندارم" یا "ژاندارم: 50" یا "(100) : 300"
                mm = re.search(
                    r"(?:([\d۰-۹]+)\s+)?(.+?)(?:\s*[\(（]\s*([\d۰-۹]+)\s*[\)）])?\s*:?\s*([\d۰-۹.]*)?\s*$",
                    al.strip(),
                )
                if not mm:
                    i += 1
                    continue
                c1 = normalize_digits(mm.group(1) or "")
                unit = _clean_item_name(mm.group(2) or "")
                paren = normalize_digits(mm.group(3) or "")
                tail = normalize_digits(mm.group(4) or "")
                count = 0
                yld = 0
                try:
                    if c1:
                        count = int(float(c1))
                    if paren and tail:
                        count = int(float(paren)) if not count else count
                        yld = int(round(float(tail)))
                    elif paren:
                        yld = int(round(float(paren)))
                    if tail and not yld and not paren:
                        yld = int(round(float(tail)))
                except ValueError:
                    pass
                if unit and (count or yld):
                    army.append({"unit": unit, "count": count, "yield": yld})
                i += 1
            packs.append({"kind": "hero", "name": name, "army": army, "yield": 0})
            continue
        # گروهک مزدوری
        if re.search(r"گروهک\s*مزدور", ln, re.I):
            rest = re.sub(r"^.*?گروهک\s*مزدور[یي]?\s*", "", ln, flags=re.I).strip(" :-|")
            mm = re.search(r"(.+?)\s*[:=：]?\s*([\d۰-۹]+)\s*$", rest)
            if mm:
                unit = _clean_item_name(mm.group(1))
                cnt = int(float(normalize_digits(mm.group(2))))
                packs.append({"kind": "merc_group", "name": f"گروهک {unit}", "unit": unit, "count": cnt, "yield": 0})
            else:
                packs.append({"kind": "merc_group", "name": rest or ln, "unit": rest, "count": 0, "yield": 0})
            i += 1
            continue
        # مزدور / جاسوس / گارد
        mk = None
        if re.search(r"\bمزدور", ln):
            mk = "merc"
        elif re.search(r"جاسوس", ln):
            mk = "spy"
        elif re.search(r"گارد", ln) and "کمپ" not in ln:
            mk = "guard"
        if mk:
            mm = re.search(
                r"(.+?)\s*[\(（]\s*([\d۰-۹]+)\s*[\)）]\s*:?\s*([\d۰-۹.]*)?",
                ln,
            )
            if mm:
                unit = _clean_item_name(mm.group(1))
                a = int(float(normalize_digits(mm.group(2))))
                b = mm.group(3)
                yld = int(round(float(normalize_digits(b)))) if b else 0
                # (تعداد): بازدهی یا فقط (بازدهی)
                if yld:
                    packs.append({"kind": mk, "name": unit, "unit": unit, "count": a, "yield": yld})
                else:
                    packs.append({"kind": mk, "name": unit, "unit": unit, "count": 0, "yield": a})
            else:
                mm2 = re.search(r"(.+?)\s*[:=：]\s*([\d۰-۹]+)", ln)
                if mm2:
                    unit = _clean_item_name(mm2.group(1))
                    cnt = int(float(normalize_digits(mm2.group(2))))
                    packs.append({"kind": mk, "name": unit, "unit": unit, "count": cnt, "yield": 0})
                else:
                    packs.append({"kind": mk, "name": _clean_item_name(ln), "unit": _clean_item_name(ln), "count": 0, "yield": 0})
            i += 1
            continue
        # پک عمومی: نام (N) یا نام (N) : M
        mm = re.search(
            r"(.+?)\s*[\(（]\s*([\d۰-۹]+(?:\.\d+)?)\s*[\)）]\s*:?\s*([\d۰-۹.]*)?",
            ln,
        )
        if mm:
            name = _clean_item_name(mm.group(1))
            a = float(normalize_digits(mm.group(2)))
            b = mm.group(3)
            if b:
                packs.append({
                    "kind": "pack",
                    "name": name,
                    "unit": name,
                    "count": int(round(a)),
                    "yield": int(round(float(normalize_digits(b)))),
                })
            else:
                packs.append({
                    "kind": "pack",
                    "name": name,
                    "unit": name,
                    "count": 0,
                    "yield": int(round(a)),
                })
            i += 1
            continue
        # خط ساده بدون عدد — پک اسمی
        nm = _clean_item_name(ln)
        if nm and len(nm) > 1 and not re.match(r"^[💵💰]+$", nm):
            packs.append({"kind": "pack", "name": nm, "unit": nm, "count": 0, "yield": 0})
        i += 1
    return packs


def _format_shop_packs(packs: list) -> str:
    """متن خوانا برای ذخیره در شیت و نمایش."""
    lines = []
    for pk in packs:
        k = pk.get("kind")
        if k == "minister":
            lines.append(f"🤵 وزیر {pk.get('name') or ''}")
        elif k == "hero":
            lines.append(f"🥷 فرمانده {pk.get('name') or ''}")
            for u in pk.get("army") or []:
                if u.get("count") and u.get("yield"):
                    lines.append(f"  {u.get('count')} {u.get('unit')} ({u.get('yield')})")
                elif u.get("count"):
                    lines.append(f"  {u.get('count')} {u.get('unit')}")
                elif u.get("yield"):
                    lines.append(f"  {u.get('unit')} ({u.get('yield')})")
        elif k == "merc_group":
            lines.append(f"گروهک مزدوری {pk.get('unit') or pk.get('name')}: {pk.get('count') or 0}")
        elif k in ("merc", "spy", "guard"):
            label = {"merc": "مزدور", "spy": "جاسوس", "guard": "گارد"}.get(k, "")
            if pk.get("count") and pk.get("yield"):
                lines.append(f"{label} {pk.get('unit')} ({pk.get('count')}) : {pk.get('yield')}")
            elif pk.get("yield"):
                lines.append(f"{label} {pk.get('unit')} ({pk.get('yield')})")
            else:
                lines.append(f"{label} {pk.get('unit')}: {pk.get('count') or 0}")
        else:
            if pk.get("count") and pk.get("yield"):
                lines.append(f"{pk.get('name')} ({pk.get('count')}) : {pk.get('yield')}")
            elif pk.get("yield"):
                lines.append(f"{pk.get('name')} ({pk.get('yield')})")
            else:
                lines.append(str(pk.get("name") or ""))
    return "\n".join(lines)


def player_ids_for_city(city: str) -> list:
    """آیدی فرمانده(های) یک شهر."""
    ids = []
    for uid, u in authenticated_users.items():
        if u.get("role") != "player":
            continue
        if (u.get("country") or "") == city:
            try:
                ids.append(int(uid))
            except (TypeError, ValueError):
                continue
    return ids


async def send_up_receipts(city: str, log: str):
    """رسید آپ: گپ شهر + پیوی فرمانده + ادمین."""
    body = (
        f"🧾 <b>رسید آپ هفتگی</b>\n{DIV}\n"
        f"🏙 <b>{e(city)}</b>\n\n{log}\n\n"
        f"📜 جزئیات در منوی اقتصادی → تغییرات اخیر"
    )
    # گپ‌های ست‌شدهٔ همین شهر
    for gid in groups_of_city(city):
        try:
            await bot.send_message(gid, body[:4000])
        except Exception:
            logging.exception("رسید آپ به گپ %s", gid)
    for uid in player_ids_for_city(city):
        try:
            await bot.send_message(uid, body[:4000])
        except Exception:
            logging.exception("رسید آپ به پلیر %s", uid)
    try:
        await bot.send_message(ADMIN_ID, body[:4000])
    except Exception:
        logging.exception("رسید آپ به ادمین")
    if ASSET_ADMIN_ID and ASSET_ADMIN_ID != ADMIN_ID:
        try:
            await bot.send_message(ASSET_ADMIN_ID, body[:4000])
        except Exception:
            pass


@dp.callback_query(F.data == "adm_auto")
async def admin_auto_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    cities = sorted(all_known_cities(), key=lambda s: s.lower())
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ فعال همه", "auto_all_on", "success"),
        _btn("❌ خاموش همه", "auto_all_off", "danger"),
    )
    for i, city in enumerate(cities[:40]):
        on = is_auto_city(city)
        mark = "✅" if on else "❌"
        short = city.rsplit("_", 1)[0] if "_" in city else city
        builder.row(_btn(f"{mark} {short}", f"auto_tog:{i}"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    n_on = sum(1 for c in cities if is_auto_city(c))
    await callback.message.answer(
        f"🤖 <b>شهرهای فول‌اتو</b>\n{DIV}\n"
        f"فعال: <b>{n_on}</b> / {len(cities)}\n"
        "فقط شهرهای ✅ ارتقا/آپ/تلفات اتو دارند.\n"
        "• تیک تک‌تک یا <b>فعال همه</b>\n"
        "• اگر پیام «اتو فعال نیست» دیدید، همین‌جا تیک بزنید.",
        reply_markup=builder.as_markup(),
    )
