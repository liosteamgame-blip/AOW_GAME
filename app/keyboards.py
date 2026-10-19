"""همه کیبوردهای شیشه‌ای ربات."""

from aiogram import types
from aiogram.types import ForceReply
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import state as app_state
from app.config import (
    BTN_BACK,
    BTN_NO,
    BTN_YES,
    CHANNEL_ID,
    DIV,
    MTYPE_BUTTONS,
    REPORT_CHANNEL_ID,
    TWEET_CHANNEL_ID,
)
from app.state import SETTINGS, authenticated_users
from app.factions import FACTION_META, cities_by_faction, country_key
from app.players import is_admin, is_leader, is_player, leader_side
from app.features import enabled
from app.permissions import roles_of


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


def get_main_menu_keyboard(user_id=None, chat_id=None):
    """منوی اصلی — ۴ بخش: نظامی · اقتصادی · تجارت · بیانیه (+ دکمه‌های نقش‌محور)"""
    builder = InlineKeyboardBuilder()
    builder.row(_btn("⚔️ منوی نظامی", "menu:military", "danger"))
    builder.row(_btn("💰 منوی اقتصادی", "menu:economy", "success"))
    builder.row(
        _btn("🐪 تجارت", "menu:trade", "primary"),
        _btn("📜 بیانیه", "menu:statement", "primary"),
    )
    extra = []
    if user_id and enabled("leader_panel") and leader_side(user_id):
        extra.append(_btn("🏴 پنل جناح", "ldr:menu", "primary"))
    if user_id and chat_id and enabled("assistant_perms") and "commander" in roles_of(user_id, chat_id):
        extra.append(_btn("🤝 اختیارات کمکی‌ها", "asst:menu"))
    if extra:
        builder.row(*extra)
    builder.row(_btn("🔙 بستن منو", "menu:close"))
    return builder.as_markup()


def get_pv_menu_keyboard(user_id=None):
    """منوی پی‌وی: فقط نقش‌هایی که کار خصوصی دارند (فعلاً لیدر جناح). None = بدون دکمه."""
    if user_id and enabled("leader_panel") and leader_side(user_id):
        builder = InlineKeyboardBuilder()
        builder.row(_btn("🏴 پنل جناح", "ldr:menu", "primary"))
        return builder.as_markup()
    return None


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
        _btn("⬆️ افزایش سطح رایگان", "adm_free_lv", "success"),
    )
    builder.row(
        _btn("🏙 واگذاری شهر", "adm_transfer", "danger"),
        _btn("🖼 عکس منو", "adm_photo:menu", "primary"),
    )
    builder.row(
        _btn("🧪 فیچرها", "adm_features", "primary"),
        _btn("📜 لاگ ممیزی", "adm_audit"),
    )
    builder.row(
        _btn("🎭 نقش‌ها", "adm_roles"),
        _btn("🔐 تاییدهای معلق", "adm_approvals"),
    )
    builder.row(_btn("🏴 پنل جناح‌ها", "ldr:menu", "primary"))
    builder.row(_btn("⚙️ مدیریت", "adm_manage"), _btn("📢 پیام آپدیت گروه‌ها", "adm_send_update"))
    builder.row(_btn("📋 وضعیت", "adm_report"), _btn("❓ راهنما", "adm_help"))
    builder.row(_btn("🚪 خروج", "adm_logout", "danger"))
    return builder.as_markup()


def admin_help_text():
    """هر بار ساخته می‌شود تا مقادیر (مثل ادمین دارایی) به‌روز باشند."""
    return (
        f"⚡️ <b>راهنمای پنل ادمین</b>\n{DIV}\n\n"
        "<b>در گروه ادمینی / پی‌وی:</b>\n"
        "• <code>ADMIN</code> — باز کردن پنل\n"
        "• <code>/set admin</code> یا <code>ست ادمین</code> — دادن ادمین (ریپلای)\n"
        "• <code>ست ادمین دارایی</code> — ریپلای روی کاربر برای گزارش تجارت\n"
        "• <code>ست لیدر انگلیس</code> / <code>/set leader france</code> — ریپلای\n\n"
        "<b>در گروه شهر:</b>\n"
        "• <code>/start</code> — ست گپ / اتصال شهر\n"
        "• <code>/set player</code> یا <code>ست پلیر</code> — تعیین فرمانده (ریپلای)\n• <code>ست کمکی</code> — پلیر کمکی همین گپ (ریپلای)\n"
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
        f"👤 ادمین دارایی: <code>{app_state.ASSET_ADMIN_ID or '—'}</code>"
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


def get_group_inquiry_keyboard(chat_id: int, city: str, player_ids: list):
    builder = InlineKeyboardBuilder()
    for uid in player_ids:
        builder.row(_btn(f"❌ حذف فرمانده {uid}", f"inq_delplayer:{uid}", "danger"))
    builder.row(_btn("🗑 قطع اتصال گروه از شهر", f"inq_unlink:{chat_id}", "danger"))
    builder.row(_btn("🔙 بستن", "inq_close"))
    return builder.as_markup()


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
        _btn("🎛 رتبه‌ها", "lb_ranks_cfg", "primary"),
    )
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    return builder.as_markup()


def bot_open_url():
    """لینک مستقیم باز کردن پی‌وی ربات."""
    if app_state.BOT_USERNAME:
        return f"https://t.me/{app_state.BOT_USERNAME}"
    return None


def get_open_bot_keyboard():
    """دکمهٔ اینلاین برای رفتن به پی‌وی ربات."""
    url = bot_open_url()
    if not url:
        return None
    builder = InlineKeyboardBuilder()
    builder.button(text="📩 باز کردن پی‌وی ربات", url=url)
    return builder.as_markup()
