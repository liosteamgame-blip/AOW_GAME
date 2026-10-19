"""🚨 گزارش خطا به مالک (dp.errors): هر نوع خطا حداکثر هر ۱۰ دقیقه، با شمار تکرارها."""
import logging
import os

from aiogram.types import ErrorEvent

from app.config import ADMIN_ID, DIV
from app.errorlog import note
from app.features import enabled
from app.loader import bot, dp
from app.utils import e


def _update_info(event: ErrorEvent) -> str:
    upd = event.update
    if upd is None:
        return "—"
    for kind in ("message", "callback_query", "poll_answer"):
        obj = getattr(upd, kind, None)
        if obj is None:
            continue
        user = getattr(obj, "from_user", None) or getattr(obj, "user", None)
        detail = ""
        if kind == "message":
            detail = (obj.text or obj.caption or "")[:60]
        elif kind == "callback_query":
            detail = obj.data or ""
        return f"{kind} · کاربر <code>{user.id if user else '—'}</code> · <code>{e(detail)}</code>"
    return "other"


@dp.errors()
async def report_error(event: ErrorEvent):
    exc = event.exception
    logging.error("خطای هندلر: %r", exc, exc_info=exc)
    # اگر کاربر دکمه زده بود، چرخش دکمه را تمام کن
    cq = getattr(event.update, "callback_query", None) if event.update else None
    if cq is not None:
        try:
            await bot.answer_callback_query(cq.id, "❌ خطایی رخ داد؛ ادمین مطلع شد.", show_alert=False)
        except Exception:
            pass
    should, suppressed, where = note(exc)
    if should and enabled("error_reports"):
        await _send(event, exc, suppressed, where)
    if os.getenv("AOW_RAISE_ERRORS") == "1":
        raise exc   # در تست‌ها خطا پنهان نشود (tests/fakebot.setup_env)
    return True


async def _send(event: ErrorEvent, exc: BaseException, suppressed: int, where: str):
    extra = f"\n🔁 {suppressed} تکرار دیگر از گزارش قبلی تاکنون" if suppressed else ""
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🚨 <b>خطای ربات</b>\n{DIV}\n"
            f"❗️ <code>{e(type(exc).__name__)}: {e(str(exc)[:300])}</code>\n"
            f"📍 <code>{e(where)}</code>\n"
            f"🧩 {_update_info(event)}{extra}\n\n"
            "<i>همین خطا تا ۱۰ دقیقه دوباره گزارش نمی‌شود.</i>",
            disable_notification=True,
        )
    except Exception:
        logging.exception("ارسال گزارش خطا به مالک ناموفق بود")
