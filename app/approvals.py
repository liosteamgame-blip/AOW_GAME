"""تایید دونفره: کارهای حساس ادمین غیرمالک (حذف شهر، بازیابی کامل، واگذاری) منتظر تایید مالک می‌مانند.

وقتی فیچر dual_approval خاموش است یا خود مالک کار را انجام می‌دهد، کار مستقیم اجرا می‌شود.
"""
import logging
import secrets
import time

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.audit import actor_label, record
from app.config import ADMIN_ID, DIV
from app.features import enabled
from app.keyboards import _btn
from app.loader import bot
from app.state import (
    APPROVAL_BLOBS,
    GROUPS,
    PENDING_APPROVALS,
    PLAYER_CODES,
    all_players,
    authenticated_users,
)
from app.storage import apply_restore, save_data
from app.utils import e
from app.economy.assets import transfer_city

KIND_TITLES = {
    "delete_city": "🗑 حذف شهر",
    "restore": "♻️ بازیابی کامل داده",
    "transfer": "🏙 واگذاری شهر",
}
APPROVAL_TTL = 48 * 3600


def needs_approval(user_id: int) -> bool:
    return enabled("dual_approval") and user_id != ADMIN_ID


def delete_city(code: str) -> tuple:
    """حذف شهر با کدش + فرمانده‌ی متصل + گروه‌های آن. برمی‌گرداند (ok, msg)."""
    city = PLAYER_CODES.pop(code, None)
    if not city:
        return False, "ℹ️ این شهر از قبل حذف شده است."
    uid = None
    for u_id, u in list(authenticated_users.items()):
        if u.get("role") == "player" and u.get("code") == code:
            uid = u_id
            authenticated_users.pop(u_id, None)
            all_players.discard(u_id)
            break
    for gid, g in list(GROUPS.items()):
        if (g.get("code") == code) or (g.get("city") or "").lower() == str(city).lower():
            GROUPS.pop(gid, None)
    save_data(critical=True)
    record("حذف شهر", city, f"کد {code}" + (f" · فرمانده {uid}" if uid else ""))
    msg = f"✅ شهر <b>{e(city)}</b> حذف شد.\n🔑 کد باطل: <code>{e(code)}</code>"
    if uid:
        msg += f"\n👤 فرمانده <code>{uid}</code> هم حذف شد."
    return True, msg


def do_transfer(src: str, dst: str) -> str:
    msg = transfer_city(src, dst)
    record("واگذاری شهر", src, f"{src} → {dst}")
    return msg


async def request_approval(kind: str, payload: dict, requester: int, summary: str, blob=None) -> str:
    """ثبت درخواست و فرستادن آن برای مالک با دکمه تایید/رد."""
    aid = secrets.token_hex(4)
    PENDING_APPROVALS[aid] = {
        "kind": kind,
        "payload": dict(payload or {}),
        "requester": requester,
        "summary": summary,
        "ts": time.time(),
        "status": "pending",
    }
    if blob is not None:
        APPROVAL_BLOBS[aid] = blob
    save_data()
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ تایید و اجرا", f"appr:ok:{aid}", "success"),
        _btn("❌ رد", f"appr:no:{aid}", "danger"),
    )
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔐 <b>درخواست تایید مالک</b>\n{DIV}\n"
            f"📌 کار: <b>{KIND_TITLES.get(kind, kind)}</b>\n"
            f"👤 درخواست‌دهنده: {e(actor_label(requester))} (<code>{requester}</code>)\n"
            f"📝 {summary}\n\n"
            "سرورم، این کار تا تایید شما اجرا نمی‌شود.",
            reply_markup=builder.as_markup(),
        )
    except Exception:
        logging.exception("ارسال درخواست تایید به مالک ناموفق بود")
    return aid


async def execute(aid: str) -> tuple:
    """اجرای درخواست تاییدشده. برمی‌گرداند (ok, msg)."""
    item = PENDING_APPROVALS.get(aid)
    if not item:
        return False, "❌ درخواست پیدا نشد."
    kind, p = item.get("kind"), item.get("payload") or {}
    if kind == "delete_city":
        return delete_city(str(p.get("code") or ""))
    if kind == "transfer":
        return True, do_transfer(str(p.get("src") or ""), str(p.get("dst") or ""))
    if kind == "restore":
        raw = APPROVAL_BLOBS.pop(aid, None)
        if raw is None:
            return False, "❌ فایل بازیابی دیگر در حافظه نیست (ربات ری‌استارت شده). فایل را دوباره بفرستید."
        ok, msg = await apply_restore(raw)
        if ok:
            record("بازیابی کامل داده", "", "با تایید مالک")
        return ok, msg
    return False, "❌ نوع درخواست ناشناخته است."


def pending_list() -> list:
    now = time.time()
    out = []
    for aid, it in list(PENDING_APPROVALS.items()):
        if it.get("status") != "pending":
            continue
        if now - float(it.get("ts") or 0) > APPROVAL_TTL:
            it["status"] = "expired"
            APPROVAL_BLOBS.pop(aid, None)
            continue
        out.append((aid, it))
    return out
