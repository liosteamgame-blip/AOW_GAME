"""راه‌اندازی: بارگذاری داده، آرت، مهاجرت نام‌ها و شروع polling."""
import logging

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import handlers  # ثبت همه هندلرها (ترتیب داخل app/handlers/__init__.py)
from app import state as app_state
from app.art import load_art
from app.config import ADMIN_ID, CHANNEL_ID
from app.factions import migrate_city_names, seed_default_cities
from app.keyboards import _btn
from app.loader import bot, dp

HANDLER_MODULES = tuple(handlers.__all__)  # فقط برای لاگ/تست؛ import بالا هندلرها را ثبت می‌کند
from app.scheduler import arrivals_loop, periodic_backup_loop, timing_scheduler_loop
from app.state import GROUPS, PLAYER_CODES, all_players, backup_state, spawn
from app.storage import _load_mid, apply_data, init_storage, push_backup, read_local, save_data


def load_local_data():
    """داده‌ی دیسک محلی (اگر هست) و message_id پشتیبان را بارگذاری می‌کند.

    در نسخه‌ی تک‌فایلی این کار هنگام import انجام می‌شد؛ آن موقع هنوز
    rebuild_player_links تعریف نشده بود و اتصال پلیر‌ها بی‌صدا ترمیم نمی‌شد.
    """
    raw = read_local()
    if raw:
        apply_data(raw)
    mid0 = _load_mid()
    if mid0:
        backup_state["mid"] = mid0


async def main():
    load_local_data()
    load_art()
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    app_state.BOT_USERNAME = me.username
    logging.info("ربات @%s آماده است. CHANNEL_ID=%s", app_state.BOT_USERNAME, CHANNEL_ID)
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
    spawn(arrivals_loop())
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
