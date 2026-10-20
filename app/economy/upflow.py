"""آپ کلی — یک تابع مشترک برای دکمه‌ی ادمین و آپ زمان‌بندی‌شده.

قفل دارد: تا آپ قبلی تمام نشده، آپ دوم شروع نمی‌شود (قبلاً دابل‌کلیک روی «آپ کلی» =
دو هفته بازدهی برای همه شهرها).
"""
import logging

from app.config import DIV
from app.state import AUTO_CITIES
from app.storage import push_backup, save_data
from app.economy.up import UP_HOLD, run_weekly_up_for_city, snapshot_all_assets
from app.economy.reportcard import send_up_result
from app.utils import e, html_cut

_running = {"on": False}
_running_cities = set()   # آپ تکی در حال اجرا (همان الگوی قفل آپ کلی، برای هر شهر)


def up_all_running() -> bool:
    return _running["on"]


def up_one_running(city: str) -> bool:
    return _running["on"] or city in _running_cities


def is_held(log) -> bool:
    """آپ به‌خاطر عدد مشکوک متوقف شد (چیزی اعمال نشده؛ منتظر تأیید ادمین)."""
    return str(log or "").startswith(UP_HOLD)


async def run_up_one(city: str, allow_suspicious: bool = False) -> str | None:
    """آپ تکی یک شهر (دکمه ادمین / «آپ» در گروه). None = همین شهر یا آپ کلی در حال اجراست.
    قبلاً دابل‌کلیک روی «تأیید آپ این شهر» = دو هفته بازدهی برای آن شهر."""
    if up_one_running(city):
        return None
    _running_cities.add(city)   # قبل از هر await
    try:
        log = run_weekly_up_for_city(city, force=True, allow_suspicious=allow_suspicious)
        if is_held(log):
            return log   # فقط به ادمین؛ رسید/کارنامه برای شهر نمی‌رود
        try:
            await send_up_result(city, log)
        except Exception:
            logging.exception("رسید آپ %s", city)
        save_data(critical=True)
        try:
            await push_backup()
        except Exception:
            logging.exception("بکاپ تلگرام آپ تکی")
        return log
    finally:
        _running_cities.discard(city)


async def run_up_all(reason: str = "up_all") -> str | None:
    """None = آپ دیگری در حال اجراست. در غیر این صورت متن نتیجه برای ادمین."""
    if _running["on"]:
        return None
    _running["on"] = True   # قبل از هر await
    try:
        n_snap = snapshot_all_assets(reason=reason)
        save_data(critical=True)
        done = []
        for city in list(AUTO_CITIES.keys()):
            if not AUTO_CITIES.get(city):
                continue
            done.append((city, run_weekly_up_for_city(city, force=False)))
        if not done:
            return "📭 هیچ شهر اتویی فعال نیست.\nاز «شهرهای اتو» فعال کنید یا آپ تکی بزنید."
        # کارنامه/رسید بعد از آپ همه شهرها — تا رتبه‌ها با وضعیت نهایی مقایسه شوند
        held = [c for c, log in done if is_held(log)]
        for city, log in done:
            if city in held:
                continue
            try:
                await send_up_result(city, log)
            except Exception:
                logging.exception("رسید آپ %s", city)
        save_data(critical=True)
        try:
            await push_backup()
        except Exception:
            logging.exception("بکاپ تلگرام بعد از آپ کلی")
        body = (
            f"♻️ <b>نتیجه آپ کلی</b>\n"
            f"🗄 بکاپ قبل از آپ: <b>{n_snap}</b> شهر (قدیم نگه داشته شد)\n"
            f"✅ بکاپ جدید + تلگرام ذخیره شد\n"
            f"{DIV}\n" + "\n".join(e(log) for _c, log in done[:40])
        )
        if held:
            # بالای پیام تا با کوتاه شدن متن طولانی گم نشود
            body = (
                f"⏸ <b>{len(held)} شهر متوقف شد (بازدهی مشکوک)</b>: "
                + "، ".join(e(c) for c in held)
                + "\nاز «آپ تکی» همان شهر را بررسی و تأیید کنید.\n\n" + body
            )
        return html_cut(body)
    finally:
        _running["on"] = False
