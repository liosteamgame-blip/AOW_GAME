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
    chat = await bot.get_chat(backup_chat())
    pm = getattr(chat, "pinned_message", None)
    if pm and getattr(pm, "document", None) and pm.document.file_name == BACKUP_NAME:
        return pm
    return None


async def push_backup():
    """داده‌ها را به‌صورت فایل داخل تلگرام (پیام پین‌شده) نگه می‌دارد تا با Deploy مجدد از بین نرود."""
    chat = backup_chat()
    payload = json.dumps(snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    caption = "🗄 پشتیبان داده‌های ربات — این پیام را حذف نکنید"
    mid = backup_state["mid"]
    if mid:
        try:
            doc = BufferedInputFile(payload, filename=BACKUP_NAME)
            await bot.edit_message_media(media=InputMediaDocument(media=doc, caption=caption), chat_id=chat, message_id=mid)
            return
        except TelegramBadRequest as ex:
            if "not modified" in str(ex).lower():
                return
            logging.warning("ویرایش پیام پشتیبان ناموفق بود؛ پیام جدید ساخته می‌شود: %s", ex)
    doc = BufferedInputFile(payload, filename=BACKUP_NAME)
    sent = await bot.send_document(chat_id=chat, document=doc, caption=caption, disable_notification=True)
    backup_state["mid"] = sent.message_id
    try:
        await bot.pin_chat_message(chat_id=chat, message_id=sent.message_id, disable_notification=True)
    except Exception:
        logging.exception("پین کردن پیام پشتیبان ناموفق بود.")


async def _backup_worker():
    try:
        # تأخیر بیشتر = پشتیبان تلگرام کمتر و ربات روان‌تر
        await asyncio.sleep(8)
        while _backup_flags["dirty"]:
            _backup_flags["dirty"] = False
            try:
                await push_backup()
            except Exception:
                logging.exception("پشتیبان‌گیری در تلگرام ناموفق بود.")
            if _backup_flags["dirty"]:
                await asyncio.sleep(3)
    finally:
        _backup_flags["running"] = False


def save_data():
    """ذخیره محلی فوری؛ پشتیبان تلگرام در پس‌زمینه و با تأخیر."""
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


async def init_storage():
    try:
        pm = await find_backup_message()
        if pm:
            backup_state["mid"] = pm.message_id
        if not has_data() and pm:
            buf = io.BytesIO()
            await bot.download(pm.document, destination=buf)
            apply_data(json.loads(buf.getvalue().decode("utf-8")))
            write_local()
            logging.info("داده‌ها از پشتیبان تلگرام بازیابی شد: %s شهر، %s فرمانده.", len(PLAYER_CODES), len(all_players))
        elif not pm:
            logging.info("پشتیبان تلگرامی پیدا نشد.")
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
    """منوی اصلی بازی فقط در گروه شهر؛ در پی‌وی فقط راهنما نشان داده می‌شود."""
    await state.clear()
    if message.chat.type == "private":
        await message.answer(text if text != MENU_TEXT else PV_PLAYER_TEXT, reply_markup=ReplyKeyboardRemove())
        return
    await state.set_state(GameStates.main_menu)
    body = text if text != MENU_TEXT else MENU_TEXT
    # یک پیام کافی است (اینلاین + متن) — دو پیام باعث تأخیر می‌شد
    await message.answer(body, reply_markup=get_main_menu_keyboard())


async def channel_failed(message: types.Message, state: FSMContext, ex, what):
    logging.exception("خطا در ارسال به کانال (%s)", what)
    await send_report(f"⚠️ <b>خطا در ارسال به کانال</b>\n{DIV}\n🛠 عملیات: {e(what)}\n❗️ خطا: <code>{e(str(ex)[:300])}</code>")
    await go_menu(message, state, "❌ ارسال به کانال ناموفق بود. ادمین مطلع شد؛ کمی بعد دوباره تلاش کنید.")


class GameStates(StatesGroup):
    waiting_for_code = State()
    main_menu = State()
    admin_broadcast = State()
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

    # دکمه‌های پست لشکرکشی در کانال
    ambush_stats = State()
    ambush_confirm = State()
    redirect_target = State()
    redirect_time = State()
    redirect_confirm = State()
    back_time = State()
    back_confirm = State()


# ======================================================================
#                              کیبوردها
# ======================================================================
def get_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⚔️ لشکرکشی", callback_data="menu:campaign")
    builder.button(text="🛡️ اعلان جنگ", callback_data="menu:war")
    builder.button(text="🏰 محاصره", callback_data="menu:siege")
    builder.button(text="📜 بیانیه", callback_data="menu:statement")
    builder.adjust(2)
    return builder.as_markup()


def get_confirm_keyboard():
    """تایید/لغو با دکمه اینلاین — در گروه هم بدون مشکل کار می‌کند."""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_YES, callback_data="confirm:yes")
    builder.button(text=BTN_NO, callback_data="confirm:no")
    builder.button(text=BTN_BACK, callback_data="confirm:back")
    builder.adjust(2, 1)
    return builder.as_markup()


def get_back_keyboard():
    """
    برای دریافت متن در گروه: ForceReply تا کاربر مجبور به ریپلای شود
    و ربات پیام را ببیند (Privacy Mode).
    """
    return ForceReply(selective=True, input_field_placeholder="اینجا بنویسید… (یا بازگشت)")


def get_admin_inline_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 پیام همگانی", callback_data="adm_broadcast")
    builder.button(text="📊 آمار و وضعیت شهرها", callback_data="adm_stats")
    builder.button(text="⚙️ مدیریت و حذف دسترسی‌ها", callback_data="adm_manage")
    builder.button(text="🚪 خروج از پنل", callback_data="adm_logout")
    builder.adjust(1)
    return builder.as_markup()


def get_manage_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ حذف دسترسی بازیکن", callback_data="adm_revoke_list")
    builder.button(text="➕ افزودن شهر و ساخت کد", callback_data="adm_add_city")
    builder.button(text="🔙 بازگشت", callback_data="back_to_admin")
    builder.adjust(1)
    return builder.as_markup()


def get_channel_buttons(action_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="🪓 کمین", callback_data=f"chan_ambush:{action_id}")
    builder.button(text="🔄 تغییر مسیر", callback_data=f"chan_redir:{action_id}")
    builder.button(text="🔙 بک", callback_data=f"chan_back:{action_id}")
    builder.adjust(3)
    return builder.as_markup()


def get_cancel_button(kind, action_id):
    builder = InlineKeyboardBuilder()
    prefix = "chan_cancelsiege" if kind == "siege" else "chan_cancelwar"
    builder.button(text="❌ لغو دستور (۱۰ دقیقه)", callback_data=f"{prefix}:{action_id}")
    return builder.as_markup()


def get_type_keyboard(kind):
    builder = InlineKeyboardBuilder()
    builder.button(text=MTYPE_BUTTONS["sea"], callback_data=f"mtype:{kind}:sea")
    builder.button(text=MTYPE_BUTTONS["land"], callback_data=f"mtype:{kind}:land")
    builder.button(text="🔙 بازگشت", callback_data="mtype:back")
    builder.adjust(2, 1)
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
    save_data()
    await state.clear()
    await message.answer(
        f"✅ این گروه به شهر <b>{e(canon_name)}</b> متصل شد.\n\n"
        "👤 برای تعیین فرمانده‌ی این گروه، روی پیام او <b>ریپلای</b> کرده و بنویسید: <code>ست پلیر</code> یا <code>/set player</code>"
    )


SET_PLAYER_CMDS = {"ستپلیر", "setplayer"}
SET_ADMIN_CMDS = {"ستادمین", "setadmin"}
ADMIN_WORD = "admin"


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
    save_data()

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
    save_data()
    await message.answer(f"✅ {mention(target.id, target.full_name)} اکنون دسترسی ادمین دارد.")
    try:
        await bot.send_message(chat_id=target.id, text="⚡️ شما توسط ادمین کل، دسترسی ادمین دریافت کردید. برای ورود به پنل، عبارت ADMIN را بفرستید.")
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
        save_data()
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
        return await callback.message.answer("📊 هنوز هیچ شهری ثبت نشده است.\nاز «⚙️ مدیریت» گزینه‌ی «➕ افزودن شهر» را بزنید.", reply_markup=get_admin_inline_keyboard())

    blocks = [f"📊 <b>آمار و وضعیت شهرها</b>\n{DIV}\n"]
    for code, city in PLAYER_CODES.items():
        uid = code_owner(code)
        if uid:
            u = authenticated_users[uid]
            uname = f" (@{e(u['username'])})" if u.get("username") else ""
            status = f"✅ وارد شده — آیدی: <code>{uid}</code>{uname}"
        else:
            status = "❌ هنوز وارد نشده"
        blocks.append(f"🏙 <b>{e(city)}</b>\n🔑 کد: <code>{e(code)}</code>\n👤 {status}\n")
    blocks.append(f"👥 فرماندهان فعال: {len(all_players)} از {len(PLAYER_CODES)} شهر")
    await send_chunks(callback.message, blocks, reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer("📬 محتوای پیام همگانی خود را (متن، عکس یا ویدیو) ارسال کنید:", reply_markup=get_back_keyboard())
    await state.set_state(GameStates.admin_broadcast)


@dp.message(GameStates.admin_broadcast)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not (message.text or message.photo or message.video):
        return await message.answer("❌ فقط متن، عکس یا ویدیو قابل ارسال است:")
    count, failed = 0, 0
    for p_id in list(all_players):
        try:
            if message.photo:
                await bot.send_photo(chat_id=p_id, photo=message.photo[-1].file_id, caption=message.caption, parse_mode=None)
            elif message.video:
                await bot.send_video(chat_id=p_id, video=message.video.file_id, caption=message.caption, parse_mode=None)
            else:
                await bot.send_message(chat_id=p_id, text=message.text, parse_mode=None)
            count += 1
        except Exception:
            failed += 1
    text = f"✅ پیام همگانی برای <code>{count}</code> فرمانده ارسال شد."
    if failed:
        text += f"\n⚠️ ارسال برای {failed} نفر ناموفق بود."
    await message.answer(text, reply_markup=get_admin_inline_keyboard())
    await state.clear()


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
        await callback.message.answer(CAMP_ORIGIN_PROMPT, reply_markup=get_back_keyboard())
        await state.set_state(GameStates.camp_origin)
    else:
        await callback.message.answer(ORDERS[kind]["ask_target"], reply_markup=get_back_keyboard())
        await state.set_state(GameStates.order_target)


@dp.message(GameStates.camp_origin)
async def process_camp_origin(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(origin=txt)
    await message.answer(
        "🎯 سرورم لطفا <b>شهر و کشور مقصد</b> را وارد کنید "
        "(مثال: <code>آمیان_فرانسه</code> یا <code>york_england</code>).\n"
        "↩️ به این پیام <b>ریپلای</b> کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.camp_dest)


@dp.message(GameStates.camp_dest)
async def process_camp_dest(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(dest=txt)
    await message.answer(
        "📊 سرورم لطفا <b>آمار لشکریان</b> خود را به صورت <b>تفکیک شده</b> ارائه دهید.\n\n"
        "⚠️ اگر لشکرکشی متحد است آمار هر شهر را جدا بنویسید.\n"
        "↩️ به این پیام <b>ریپلای</b> کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.camp_stats)


@dp.message(GameStates.camp_stats)
async def process_camp_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(stats=txt)
    await message.answer(
        "⏳ سرورم لطفا <b>زمان رسیدن</b> لشکریان را ارسال کنید.\n↩️ به این پیام <b>ریپلای</b> کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.camp_time)


@dp.message(GameStates.camp_time)
async def process_camp_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(time=txt)
    d = await state.get_data()
    await message.answer(
        f"🧭 نوع لشکرکشی: <b>{mtype_tag(d)}</b>\n{DIV}\n\n"
        f"👑 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از اعزام لشکریان خود از مبدا <b>{e(d['origin'])}</b> 📍 "
        f"به مقصد <b>{e(d['dest'])}</b> 🎯 با آمار:\n<blockquote>{e(d['stats'])}</blockquote>\n"
        f"⏳ و زمان رسیدن <b>{e(d['time'])}</b> موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.camp_confirm)


@dp.callback_query(F.data.startswith("confirm:"), GameStates.camp_confirm)
async def process_camp_final(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await go_menu(callback.message, state, "❌ سرورم اعزام لشکرکشی شما <b>لغو</b> شد.")
    if action != "yes":
        return

    user_id = callback.from_user.id
    city = city_of(user_id)
    d = await state.get_data()
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
    if not is_player(callback.from_user.id):
        return await callback.answer("❌ این دستور برای شما نیست.", show_alert=True)
    # دستورات اصلی فقط داخل گروه شهر
    if callback.message and callback.message.chat.type == "private":
        return await callback.answer("❌ این دستور فقط در گروه شهر شما قابل اجراست.", show_alert=True)
    await callback.answer()
    kind = callback.data.split(":", 1)[1]
    handlers = {"campaign": start_campaign, "siege": start_siege, "war": start_war, "statement": start_announcement}
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
    d = await state.get_data()
    await state.update_data(target=txt)
    await message.answer(
        ORDERS[d["kind"]]["ask_stats"] + "\n\n↩️ به این پیام <b>ریپلای</b> کنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.order_stats)


@dp.message(GameStates.order_stats)
async def process_order_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(stats=txt)
    d = await state.get_data()
    await message.answer(
        f"📩 <b>دستور شما دریافت شد.</b> آیا دستور خود را تایید می‌کنید؟\n{DIV}\n\n"
        f"🧭 نوع {ORDERS[d['kind']]['noun']}: <b>{mtype_tag(d)}</b>\n"
        f"🎯 شهر هدف: <b>{e(d['target'])}</b>\n📊 آمار:\n<blockquote>{e(d['stats'])}</blockquote>",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.order_confirm)


@dp.callback_query(F.data.startswith("confirm:"), GameStates.order_confirm)
async def process_order_final(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    d = await state.get_data()
    kind = d.get("kind", "siege")
    cfg = ORDERS[kind]
    if action in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await go_menu(callback.message, state, cfg["cancelled"])
    if action != "yes":
        return

    user_id = callback.from_user.id
    city = city_of(user_id)
    action_id = secrets.token_hex(4)
    text = cfg["channel"].format(who=mention(user_id), city=e(city), target=e(d["target"]))
    text += f"\n\n🧭 نوع {cfg['noun']}: <b>{mtype_tag(d)}</b>"
    try:
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
    preview = e(media["caption"][:200]) + ("…" if len(media["caption"]) > 200 else "")
    extra = "🖼 همراه تصویر/ویدیو" if media["kind"] != "text" else "📝 فقط متن"
    await message.answer(
        f"📜 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>صدور بیانیه</b> خود مطمئن هستید؟\n"
        f"{DIV}\n{extra}\n<blockquote>{preview}</blockquote>",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.ann_confirm)


@dp.callback_query(F.data.startswith("confirm:"), GameStates.ann_confirm)
async def process_ann_final(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await go_menu(callback.message, state, "❌ سرورم صدور بیانیه شما <b>لغو</b> شد.")
    if action != "yes":
        return

    user_id = callback.from_user.id
    city = city_of(user_id)
    media = (await state.get_data())["ann"]
    target = TWEET_CHANNEL_ID or CHANNEL_ID
    header = f"📜 <b>بیانیه رسمی</b> 📜\n{DIV}\n\n👑 {mention(user_id, 'فرمانده شهر')}\n\n"
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
#              دکمه‌های پست لشکرکشی در کانال (کمین، تغییر مسیر، بک)
# ======================================================================
def resolve_action(callback: types.CallbackQuery, prefix, owner):
    """(action_id, action, خطا) — owner=True فقط صاحب لشکر، owner=False هر بازیکن جز صاحب لشکر."""
    uid = callback.from_user.id
    if not is_player(uid):
        return None, None, "❌ دسترسی شما لغو شده است یا وارد ربات نشده‌اید (/start)."
    action_id = callback.data[len(prefix):]
    action = active_actions.get(action_id)
    if not action or action.get("type") != "campaign":
        return None, None, "این عملیات قدیمی شده یا یافت نشد."
    if owner and uid != action["owner_id"]:
        return None, None, "❌ این ارتش متعلق به شما نیست!"
    if not owner and uid == action["owner_id"]:
        return None, None, "❌ شما نمی‌توانید به ارتش خودتان کمین بزنید!"
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
        return await go_menu(message, state)
    d = await state.get_data()
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(message, state, "این عملیات دیگر معتبر نیست.")
    await state.update_data(stats=txt)
    await message.answer(
        f"🪓 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از دستور کمین خود بر لشکریان "
        f"<b>{e(city_of(action['owner_id']))}</b> با آمار:\n<blockquote>{e(txt)}</blockquote>\nموافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.ambush_confirm)


@dp.callback_query(F.data.startswith("confirm:"), GameStates.ambush_confirm)
async def process_ambush_final(callback: types.CallbackQuery, state: FSMContext):
    action_btn = callback.data.split(":", 1)[1]
    await callback.answer()
    if action_btn in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await go_menu(callback.message, state, "❌ سرورم دستور کمین شما <b>لغو</b> شد.")
    if action_btn != "yes":
        return

    d = await state.get_data()
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(callback.message, state, "این عملیات دیگر معتبر نیست.")
    attacker_id, defender_id = callback.from_user.id, action["owner_id"]
    attacker, defender = city_of(attacker_id), city_of(defender_id)
    try:
        await channel_reply_art(
            "ambush",
            f"🪓 <b>کمین!</b> 💥\n{DIV}\n\n"
            f"لشکر شهر <b>{e(defender)}</b> توسط {mention(attacker_id)} شهر <b>{e(attacker)}</b> مورد <b>کمین</b> قرار گرفت.",
            action["msg_id"],
        )
    except Exception as ex:
        return await channel_failed(callback.message, state, ex, "پیام کمین")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await go_menu(callback.message, state, "✅ کمین شما با موفقیت ثبت شد. منتظر دستورات ادمین باشید. ⏳")
    notice = (
        "🚨 <b>اعلام وضعیت اضطراری نبرد کمین</b> 🚨\n" + DIV + "\n\n"
        "⚔️ نیروهای شما درگیر یک نبرد سنگین شده‌اند! شما <b>۳۰ دقیقه</b> ⏳ فرصت دارید تا «سناریوی دفاع یا تهاجم» خود را "
        "به پی‌وی ادمین ارسال کنید. در غیر این صورت عواقب سختی در انتظار پادشاهی شماست. ☠️"
    )
    for uid in (defender_id, attacker_id):
        try:
            await bot.send_message(chat_id=uid, text=notice)
        except Exception:
            pass
    await send_report(
        f"🪓 <b>گزارش وقوع کمین نظامی</b>\n{DIV}\n"
        f"🛡 مدافع غافلگیر شده: {mention(defender_id, defender)} (ID: <code>{defender_id}</code>)\n"
        f"⚔️ مهاجم کمین‌زننده: {mention(attacker_id, attacker)} (ID: <code>{attacker_id}</code>)\n"
        f"📊 آمار قوا و تجهیزات مهاجم:\n<blockquote>{e(d['stats'])}</blockquote>"
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
        return await go_menu(message, state)
    await state.update_data(new_time=txt)
    d = await state.get_data()
    await message.answer(
        f"🔄 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>تغییر مسیر</b> لشکریان خود به مقصد "
        f"<b>{e(d['new_dest'])}</b> 🎯 با زمان رسیدن <b>{e(txt)}</b> ⏳ موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.redirect_confirm)


@dp.callback_query(F.data.startswith("confirm:"), GameStates.redirect_confirm)
async def process_redir_final(callback: types.CallbackQuery, state: FSMContext):
    action_btn = callback.data.split(":", 1)[1]
    await callback.answer()
    if action_btn in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await go_menu(callback.message, state, "❌ سرورم تغییر مسیر لشکریان شما <b>لغو</b> شد.")
    if action_btn != "yes":
        return

    d = await state.get_data()
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
        return await go_menu(message, state)
    await state.update_data(back_time=txt)
    await message.answer(
        f"🔙 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>بازگشت</b> لشکریان خود به مبدا "
        f"با زمان رسیدن <b>{e(txt)}</b> ⏳ موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.back_confirm)


@dp.callback_query(F.data.startswith("confirm:"), GameStates.back_confirm)
async def process_back_final(callback: types.CallbackQuery, state: FSMContext):
    action_btn = callback.data.split(":", 1)[1]
    await callback.answer()
    if action_btn in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await go_menu(callback.message, state, "❌ سرورم دستور بازگشت لشکریان شما <b>لغو</b> شد.")
    if action_btn != "yes":
        return

    d = await state.get_data()
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


async def main():
    global BOT_USERNAME
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logging.info("ربات @%s آماده است.", BOT_USERNAME)
    await init_storage()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
