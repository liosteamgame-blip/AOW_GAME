import asyncio
import html
import io
import json
import logging
import os
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
from aiogram.filters import CommandStart, StateFilter
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


async def find_backup_message():
    chat_id = backup_chat()
    try:
        chat = await bot.get_chat(chat_id)
        pm = getattr(chat, "pinned_message", None)
        if pm and getattr(pm, "document", None) and pm.document.file_name == BACKUP_NAME:
            return pm
        if pm and getattr(pm, "document", None):
            logging.warning("پیام پین هست ولی نام فایل %s است (انتظار: %s)",
                            pm.document.file_name, BACKUP_NAME)
    except Exception:
        logging.exception("خواندن پین پشتیبان از چت %s ناموفق بود.", chat_id)
    return None


async def push_backup():
    """داده‌ها را به‌صورت فایل داخل تلگرام (پیام پین‌شده) نگه می‌دارد تا با Deploy مجدد از بین نرود."""
    chat = backup_chat()
    payload = json.dumps(snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    caption = (
        f"🗄 پشتیبان داده‌های ربات — این پیام را حذف نکنید\n"
        f"🏙 شهر: {len(PLAYER_CODES)} | 👤 فرمانده: {len(all_players)} | 👥 گروه: {len(GROUPS)}"
    )
    mid = backup_state["mid"]
    if mid:
        try:
            doc = BufferedInputFile(payload, filename=BACKUP_NAME)
            await bot.edit_message_media(
                media=InputMediaDocument(media=doc, caption=caption),
                chat_id=chat, message_id=mid,
            )
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
    try:
        await bot.pin_chat_message(chat_id=chat, message_id=sent.message_id, disable_notification=True)
    except Exception:
        logging.exception("پین کردن پیام پشتیبان ناموفق بود.")


async def _backup_worker():
    try:
        await asyncio.sleep(2)  # کوتاه تا روی Railway رایگان داده زود پین شود
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
    ذخیره محلی فوری + پشتیبان تلگرام در پس‌زمینه (یک‌بار، بدون آپلود تکراری).
    critical=True فقط dirty را زودتر پردازش می‌کند — آپلود دوبل نمی‌زند.
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
    # critical دیگر push جداگانه نمی‌زند تا آپلود تکراری و تأخیر نسازد


async def init_storage():
    """
    روی Railway رایگان دیسک پاک می‌شود → منبع حقیقت = پیام پین‌شده تلگرام.
    همیشه اول از تلگرام بازیابی می‌کنیم (اگر باشد).
    """
    try:
        pm = await find_backup_message()
        if pm:
            backup_state["mid"] = pm.message_id
            buf = io.BytesIO()
            await bot.download(pm.document, destination=buf)
            raw = json.loads(buf.getvalue().decode("utf-8"))
            apply_data(raw)
            write_local()
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
            logging.warning("⚠️ پشتیبان تلگرامی پیدا نشد — اگر اولین اجراست طبیعی است.")
            if has_data():
                logging.info("داده محلی موجود است: %s شهر", len(PLAYER_CODES))
                spawn(push_backup())
    except Exception:
        logging.exception("بازیابی از پشتیبان تلگرام ناموفق بود.")


_raw = read_local()
if _raw:
    apply_data(_raw)


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
#   نوع = campaign | war | siege | ambush
#   کشور = england | france | ireland | all
#   مثال:
#     art_campaign_land_england_1.jpg
#     art_campaign_sea_france_2.jpg
#     art_war_land_ireland_1.jpg
#     art_campaign_land_all_1.jpg   ← عمومی (فقط اگر فکشن پیدا نشد)
ART_RE = re.compile(
    r"^(?:.*/)?art_(campaign|siege|war|ambush)_(land|sea|all)_([a-z]+)_\d+\.(?:jpe?g|png)$",
    re.I,
)
COUNTRY_ALIASES = {
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
# سه فکشن رسمی بازی
FACTIONS = ("england", "france", "ireland")
ART = {}            # (نوع، land/sea/all) -> {کشور: [آرت‌ها]}
_file_ids = {}      # آرت -> file_id تلگرام (بعد از اولین ارسال دیگر آپلود نمی‌شود)


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
    by_faction = {f: 0 for f in FACTIONS}
    for group in ART.values():
        for f in FACTIONS:
            by_faction[f] += len(group.get(f, []))
    logging.info("آرت‌های بارگذاری‌شده: %s | england=%s france=%s ireland=%s",
                 total, by_faction["england"], by_faction["france"], by_faction["ireland"])


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


def country_key(city):
    """
    از نام شهر فرمانده (مثل london_england یا دوبلین_ایرلند)
    فکشن را برمی‌گرداند: england | france | ireland
    """
    if not city:
        return None
    raw = _norm_country_token(city)
    part = raw.split("_")[-1] if "_" in raw else raw
    for key, names in COUNTRY_ALIASES.items():
        norm_names = {_norm_country_token(n) for n in names}
        if part in norm_names or raw in norm_names:
            return key
        if any(n and n in raw for n in norm_names):
            return key
    return None


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
    """
    country = country_key(city)
    typ = mtype if mtype in ("land", "sea") else "all"

    if kind == "ambush":
        chains = [("ambush", "all"), ("ambush", typ)]
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


async def go_menu(message: types.Message, state: FSMContext, text=MENU_TEXT):
    """
    منوی اصلی — ترجیحاً همان پیام قبلی ویرایش می‌شود تا منو تکرار نشود.
    فقط وقتی پیام کاربر است (نه ربات) پیام جدید می‌فرستد.
    """
    uid = message.from_user.id if message.from_user else None
    if uid:
        pending_confirms.pop(uid, None)
    await state.clear()
    if message.chat.type == "private":
        await message.answer(text if text != MENU_TEXT else PV_PLAYER_TEXT, reply_markup=ReplyKeyboardRemove())
        return
    await state.set_state(GameStates.main_menu)
    body = text if text != MENU_TEXT else MENU_TEXT
    markup = get_main_menu_keyboard()

    # اگر پیام از خود ربات است (مثلاً callback.message) → ویرایش همان پیام
    is_bot_msg = bool(message.from_user and getattr(message.from_user, "is_bot", False))
    if is_bot_msg:
        try:
            await message.edit_text(body, reply_markup=markup)
            return
        except Exception:
            try:
                # اگر فقط عکس/مدیا بود، markup را عوض کن
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            try:
                await message.delete()
            except Exception:
                pass

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
    group_set_city = State()

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

    # تجارت
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


def get_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(_btn("⚔️ لشکرکشی", "menu:campaign", "danger"))
    builder.row(_btn("🛡️ اعلان جنگ", "menu:war", "danger"), _btn("🏰 محاصره", "menu:siege", "primary"))
    builder.row(_btn("🐪 تجارت", "menu:trade", "success"), _btn("📜 بیانیه", "menu:statement", "primary"))
    builder.row(_btn("🔙 بستن منو", "menu:close"))
    return builder.as_markup()


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
    flag = {"england": "🇬🇧", "france": "🇫🇷", "ireland": "🇮🇪"}.get(fac, "🏙")
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
    "england": ("🇬🇧", "انگلیس"),
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


def parse_player_time(raw: str):
    """
    ورودی زمان پلیر:
    - ساعت مطلق: 12:00 یا 12:00,14:30
    - عدد دقیقه: 45 → الان + 45 دقیقه
    خروجی: رشته‌ی فرمت‌شده (مثلاً 10:16) یا لیست جدا با ویرگول.
    """
    raw = (raw or "").strip()
    if not raw:
        return None, "زمان خالی است."

    now = datetime.now(TZ) if TZ else datetime.now()
    parts = [p.strip() for p in raw.replace("،", ",").split(",") if p.strip()]
    out = []
    for p in parts:
        # فقط عدد = دقیقه از الان
        if re.fullmatch(r"\d{1,4}", p):
            mins = int(p)
            if mins > 24 * 60:
                return None, f"عدد «{p}» خیلی بزرگ است (حداکثر ۱۴۴۰ دقیقه)."
            t = now + timedelta(minutes=mins)
            out.append(t.strftime("%H:%M"))
            continue
        # HH:MM
        m = re.fullmatch(r"(\d{1,2})[:\.](\d{1,2})", p)
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
            if h > 23 or mi > 59:
                return None, f"ساعت «{p}» نامعتبر است."
            out.append(f"{h:02d}:{mi:02d}")
            continue
        return None, f"فرمت «{p}» درست نیست. مثال: <code>12:00</code> یا <code>45</code>"
    return ", ".join(out), None


def get_admin_inline_keyboard():
    """منوی ادمین فشرده."""
    builder = InlineKeyboardBuilder()
    builder.row(_btn("📨 ارسال پیام", "adm_msg", "primary"))
    builder.row(_btn("📊 آمار شهرها", "adm_stats"), _btn("⚙️ مدیریت", "adm_manage"))
    builder.row(_btn("📢 پیام آپدیت گروه‌ها", "adm_send_update"))
    builder.row(_btn("📋 وضعیت", "adm_report"), _btn("❓ راهنما", "adm_help"))
    builder.row(_btn("🚪 خروج", "adm_logout", "danger"))
    return builder.as_markup()


ADMIN_HELP_TEXT = (
    f"⚡️ <b>راهنمای پنل ادمین</b>\n{DIV}\n\n"
    "<b>در گروه ادمینی:</b>\n"
    "• <code>ADMIN</code> — باز کردن پنل\n"
    "• <code>/set admin</code> یا <code>ست ادمین</code> — دادن ادمین (ریپلای)\n\n"
    "<b>در گروه شهر:</b>\n"
    "• <code>/start</code> — ست گپ / اتصال شهر\n"
    "• <code>/set player</code> یا <code>ست پلیر</code> — تعیین فرمانده (ریپلای)\n"
    "• <code>استعلام گپ</code> — شهر + آیدی پلیر + حذف\n\n"
    "<b>پنل شیشه‌ای:</b>\n"
    "• 📢 همگانی — به همه / فرماندهان / گروه‌ها\n"
    "• ✉️ شخصی — پیام به یک فرمانده\n"
    "• 📊 آمار — لیست شهر و کد\n"
    "• ⚙️ مدیریت — حذف پلیر / افزودن شهر\n"
    "• 📋 وضعیت — کانال‌ها و شمارنده‌ها\n\n"
    f"🆔 کانال اصلی لشکرکشی: <code>{CHANNEL_ID}</code>\n"
    f"🆔 کانال گزارش: <code>{REPORT_CHANNEL_ID or '—'}</code>\n"
    f"🆔 کانال توییت/بیانیه: <code>{TWEET_CHANNEL_ID or '—'}</code>"
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
    await callback.message.answer("🏙 نام شهر و کشور این گروه را مانند فرمت (<code>آمیان_فرانسه</code> یا <code>york_england</code>) ارسال کنید.")
    await state.set_state(GameStates.group_set_city)


@dp.message(GameStates.group_set_city)
async def process_group_setcity(message: types.Message, state: FSMContext):
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

    existing = next((c for c, n in PLAYER_CODES.items() if n.lower() == name.lower()), None)
    if existing:
        code, canon_name = existing, PLAYER_CODES[existing]
    else:
        code, canon_name = gen_code(), name
        PLAYER_CODES[code] = canon_name

    GROUPS[message.chat.id] = {"city": canon_name, "code": code}
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ این گروه به شهر <b>{e(canon_name)}</b> متصل شد.\n\n"
        "👤 برای تعیین فرمانده‌ی این گروه، روی پیام او <b>ریپلای</b> کرده و بنویسید: <code>ست پلیر</code> یا <code>/set player</code>"
    )


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
    flag = {"england": "🇬🇧", "france": "🇫🇷", "ireland": "🇮🇪"}.get(fac, "🏙")
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
        flag = {"england": "🇬🇧", "france": "🇫🇷", "ireland": "🇮🇪"}.get(fac, "🏙")
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
    """ارسال پیام یکپارچه: همگانی یا خصوصی."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("📢 همگانی (همه فرماندهان + گروه‌ها)", "adm_msg_scope:all", "primary"))
    builder.row(_btn("🔒 خصوصی (انتخاب گیرنده)", "adm_msg_scope:private", "success"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"📨 <b>ارسال پیام</b>\n{DIV}\nنوع ارسال را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("adm_msg_scope:"))
async def admin_msg_scope(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    scope = callback.data.split(":")[1]
    await callback.answer()
    if scope == "all":
        await state.update_data(msg_scope="all", msg_targets=None)
        await callback.message.answer(
            "📢 محتوای پیام همگانی را بفرستید (متن / عکس / ویدیو):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.admin_broadcast)
        return
    # خصوصی: انتخاب فرمانده
    players = [(uid, u) for uid, u in authenticated_users.items() if u.get("role") == "player"]
    if not players:
        return await callback.message.answer("فرماندهای نیست.", reply_markup=get_admin_inline_keyboard())
    builder = InlineKeyboardBuilder()
    for uid, u in sorted(players, key=lambda x: str(x[1].get("country", "")).lower())[:50]:
        city = u.get("country") or "?"
        builder.row(_btn(f"👤 {city} · {uid}", f"adm_msg_to:{uid}"))
    builder.row(_btn("🔙 بازگشت", "adm_msg"))
    await callback.message.answer("🔒 گیرنده خصوصی را انتخاب کنید:", reply_markup=builder.as_markup())


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
    if scope == "private" and d.get("msg_targets"):
        targets = list(d["msg_targets"])
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
    text = (
        f"📋 <b>گزارش وضعیت ربات</b>\n{DIV}\n"
        f"🏙 شهرها: <b>{len(PLAYER_CODES)}</b>\n"
        f"👤 فرماندهان: <b>{len(all_players)}</b>\n"
        f"👥 گروه‌ها: <b>{len(GROUPS)}</b>\n"
        f"⚔️ اکشن فعال: <b>{len(active_actions)}</b>\n"
        f"🆔 کانال اصلی (لشکر/جنگ/محاصره/تجارت): <code>{CHANNEL_ID}</code>\n"
        f"🆔 کانال گزارش: <code>{REPORT_CHANNEL_ID or '—'}</code>\n"
        f"🆔 کانال توییت (بیانیه): <code>{TWEET_CHANNEL_ID or '—'}</code>"
    )
    await callback.message.answer(text, reply_markup=get_admin_inline_keyboard())


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
    """اعمال شهر انتخاب‌شده/دستی در فلوی لشکرکشی، هدف، تجارت."""
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
    if not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer()
    field, faction = parts[1], parts[2]
    await callback.answer()
    titles = {
        "camp_origin": "📍 مبدا — شهر را انتخاب کنید",
        "camp_dest": "🎯 مقصد — شهر را انتخاب کنید",
        "order_target": "🎯 هدف — شهر را انتخاب کنید",
        "trade_origin": "📍 مبدا تجارت — شهر را انتخاب کنید",
        "trade_dest": "🎯 مقصد تجارت — شهر را انتخاب کنید",
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
    if not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    # citypick:field:faction:idx
    if len(parts) != 4:
        return await callback.answer()
    field, faction, idx_s = parts[1], parts[2], parts[3]
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
    if kind == "close":
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    if kind == "home":
        await callback.answer()
        return await go_menu(callback.message, state)
    if not is_player(callback.from_user.id):
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
    await state.clear()
    await message.answer(
        "🐪 <b>فرم کاروان تجاری</b>\n" + DIV + "\n\n"
        "📍 <b>مبدا تجارت</b> را از منو انتخاب کنید:",
        reply_markup=get_cities_keyboard("trade_origin"),
    )
    await state.set_state(GameStates.trade_origin)


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
    parsed, err = parse_player_time(txt)
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
            "campaign", public_text, get_trade_channel_buttons(action_id), mtype, city,
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

    # کانال گزارش: جزئیات کامل + محموله محرمانه + هشتگ
    await send_report(
        f"🐪 <b>گزارش تجارت</b>\n"
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
        f"📦 <b>کالای ارسالی:</b>\n<blockquote>{e(d.get('send', '-'))}</blockquote>"
    )


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
    "• منوی شهر: اول کشور، بعد شهر\n"
    "• تجارت: مسیر زمینی/دریایی + زمان رسیدن\n"
    "• زمان هوشمند (مثلاً ۴۵ دقیقه از الان)\n"
    "• استعلام گپ و مدیریت حذف شهر\n"
    "• ارسال پیام یکپارچه (همگانی / خصوصی)\n"
    "• کمین کاروان تجاری\n\n"
    "منوی فرماندهی: /start\n"
    "⚔️ لشکرکشی · 🛡️ جنگ · 🏰 محاصره · 🐪 تجارت · 📜 بیانیه"
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


async def main():
    global BOT_USERNAME
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logging.info("ربات @%s آماده است. CHANNEL_ID=%s", BOT_USERNAME, CHANNEL_ID)
    await init_storage()
    # اعلان آپدیت خودکار نیست — فقط با تایید ادمین از پنل
    try:
        builder = InlineKeyboardBuilder()
        builder.row(_btn("📢 ارسال پیام آپدیت به گروه‌ها", "adm_send_update", "primary"))
        builder.row(_btn("ورود به پنل", "back_to_admin"))
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"✅ ربات آنلاین شد.\n"
                f"🏙 شهر: {len(PLAYER_CODES)} · 👤 فرمانده: {len(all_players)} · 👥 گروه: {len(GROUPS)}\n\n"
                "اگر می‌خواهید پیام آپدیت به گروه‌ها برود، تایید کنید:"
            ),
            reply_markup=builder.as_markup(),
            disable_notification=True,
        )
    except Exception:
        logging.exception("پیام استارت به ادمین ناموفق بود.")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
