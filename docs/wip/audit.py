"""لاگ ممیزی ادمین + برگشت آخرین تغییر.

هر تغییر ادمینی روی دارایی شهر با «قبل» ذخیره می‌شود تا مالک بتواند برگرداند.
فرد انجام‌دهنده از روی آپدیت جاری (contextvar) خوانده می‌شود؛ لازم نیست هر تابع آن را پاس بدهد.
"""
import contextvars
import functools
import inspect
import json
import logging
import secrets
import time
import zlib
from datetime import datetime

from app.config import ADMIN_ID, DIV, TZ
from app.features import enabled, setting
from app.loader import bot
from app.state import AUDIT_LOG, CITY_ASSETS, authenticated_users, spawn
from app.utils import e

# آیدی کاربرِ آپدیتی که الان در حال پردازش است (۰ = سیستم/زمان‌بند)
CURRENT_ACTOR = contextvars.ContextVar("current_actor", default=0)
_DEPTH = contextvars.ContextVar("audit_depth", default=0)

UNDO_KEEP = 30          # فقط ۳۰ مورد آخر نسخه‌ی «قبل» کامل دارند (حجم بکاپ کم بماند)
AUDIT_MAX = 300


def actor_is_admin(uid: int) -> bool:
    if not uid:
        return False
    if uid == ADMIN_ID:
        return True
    u = authenticated_users.get(uid) or {}
    return u.get("role") == "admin"


def city_fingerprint(city: str) -> int:
    ent = CITY_ASSETS.get(city) or {}
    raw = json.dumps(
        {"t": ent.get("text") or "", "s": ent.get("stats") or {}, "l": ent.get("levels") or {}},
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return zlib.crc32(raw.encode("utf-8"))


def _city_copy(city: str):
    ent = CITY_ASSETS.get(city)
    if ent is None:
        return None
    return json.loads(json.dumps(ent, ensure_ascii=False, default=str))


def _stamp(ts=None):
    dt = datetime.fromtimestamp(ts or time.time(), TZ) if TZ else datetime.fromtimestamp(ts or time.time())
    return dt.strftime("%m-%d %H:%M")


def record(action: str, city: str = "", note: str = "", before=None, admin_only: bool = True) -> str | None:
    """یک مورد به لاگ اضافه می‌کند. before = کپی دارایی شهر قبل از تغییر (برای برگشت)."""
    if not enabled("audit_log"):
        return None
    actor = CURRENT_ACTOR.get()
    if admin_only and actor and not actor_is_admin(actor):
        return None
    eid = secrets.token_hex(3)
    entry = {
        "id": eid,
        "ts": time.time(),
        "actor": actor,
        "action": action,
        "city": city or "",
        "note": (note or "")[:300],
    }
    if before is not None and city:
        entry["before"] = before
        entry["after_fp"] = city_fingerprint(city)
    AUDIT_LOG.append(entry)
    # نسخه‌ی کامل فقط برای موارد اخیر
    with_before = [x for x in AUDIT_LOG if "before" in x]
    for old in with_before[:-UNDO_KEEP]:
        old.pop("before", None)
        old["undo_expired"] = True
    del AUDIT_LOG[:-AUDIT_MAX]
    chat = setting("log_chat").strip()
    if chat:
        try:
            spawn(_post_log(int(chat), entry))
        except (ValueError, RuntimeError):
            pass
    return eid


async def _post_log(chat_id: int, entry: dict):
    try:
        await bot.send_message(chat_id, format_entry(entry), disable_notification=True)
    except Exception:
        logging.exception("ارسال لاگ ممیزی به کانال لاگ ناموفق بود")


def actor_label(uid: int) -> str:
    if not uid:
        return "🤖 سیستم"
    if uid == ADMIN_ID:
        return "👑 مالک"
    u = authenticated_users.get(uid) or {}
    name = u.get("name") or u.get("username") or str(uid)
    return f"⚡️ {name}"


def format_entry(x: dict) -> str:
    undo = ""
    if x.get("undone"):
        undo = " · ↩️ برگشت خورد"
    elif "before" in x:
        undo = " · ↩️ قابل برگشت"
    city = f" · 🏙 {e(x.get('city'))}" if x.get("city") else ""
    note = f"\n   <i>{e(x.get('note'))}</i>" if x.get("note") else ""
    return (
        f"<code>{_stamp(x.get('ts'))}</code> {e(actor_label(x.get('actor') or 0))} — "
        f"<b>{e(x.get('action'))}</b>{city}{undo}{note}"
    )


def find(eid: str):
    for x in AUDIT_LOG:
        if x.get("id") == eid:
            return x
    return None


def undo(eid: str, force: bool = False) -> tuple:
    """برگرداندن دارایی شهر به حالت قبل از این تغییر."""
    x = find(eid)
    if not x:
        return False, "❌ این مورد در لاگ پیدا نشد."
    if x.get("undone"):
        return False, "ℹ️ این تغییر قبلاً برگشت خورده است."
    if "before" not in x:
        return False, "❌ برای این مورد نسخه‌ی «قبل» نگه داشته نشده (فقط ۳۰ مورد آخر قابل برگشت‌اند)."
    city = x.get("city") or ""
    if not force and city_fingerprint(city) != x.get("after_fp"):
        return False, (
            "⚠️ بعد از این تغییر، دارایی همین شهر دوباره عوض شده است.\n"
            "برگشت، تغییرهای بعدی را هم پاک می‌کند. اگر مطمئنید «برگشت اجباری» را بزنید."
        )
    before = x["before"]
    with audit_suppressed():
        if before is None:
            CITY_ASSETS.pop(city, None)
        else:
            CITY_ASSETS[city] = before
    x["undone"] = True
    record("برگشت تغییر", city, f"برگشت مورد {eid} ({x.get('action')})", admin_only=False)
    return True, f"✅ دارایی <b>{e(city)}</b> به قبل از «{e(x.get('action'))}» برگشت."


class audit_suppressed:
    """داخل این بلوک، توابعِ دارای audited دوباره ثبت نمی‌کنند."""

    def __enter__(self):
        self._tok = _DEPTH.set(_DEPTH.get() + 1)

    def __exit__(self, *a):
        _DEPTH.reset(self._tok)


def audited(action: str, city_arg: int = 0, note_fn=None):
    """دکوراتور برای توابعی که دارایی یک شهر را عوض می‌کنند (sync یا async).

    فقط بیرونی‌ترین فراخوانی ثبت می‌شود (فراخوانی‌های تودرتو دوبار ثبت نمی‌شوند).
    کارهای پلیر (مثلاً ارتقای شهر اتو) ثبت نمی‌شوند — آن‌ها در «تغییرات اخیر» شهر هستند.
    """
    def _prepare(args, kwargs):
        if _DEPTH.get() > 0 or not enabled("audit_log"):
            return None
        actor = CURRENT_ACTOR.get()
        if actor and not actor_is_admin(actor):
            return None
        city = kwargs.get("city") if "city" in kwargs else (args[city_arg] if len(args) > city_arg else "")
        return city, (_city_copy(city) if city else None)

    def _finish(prep, args, kwargs):
        city, before = prep
        try:
            note = note_fn(*args, **kwargs) if note_fn else ""
        except Exception:
            note = ""
        record(action, city, note, before=before)

    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                prep = _prepare(args, kwargs)
                if prep is None:
                    return await fn(*args, **kwargs)
                tok = _DEPTH.set(_DEPTH.get() + 1)
                try:
                    result = await fn(*args, **kwargs)
                finally:
                    _DEPTH.reset(tok)
                _finish(prep, args, kwargs)
                return result
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            prep = _prepare(args, kwargs)
            if prep is None:
                return fn(*args, **kwargs)
            tok = _DEPTH.set(_DEPTH.get() + 1)
            try:
                result = fn(*args, **kwargs)
            finally:
                _DEPTH.reset(tok)
            _finish(prep, args, kwargs)
            return result
        return wrapper
    return deco


def audit_text(limit: int = 15, offset: int = 0) -> str:
    rows = list(reversed(AUDIT_LOG))[offset:offset + limit]
    if not rows:
        return f"📜 <b>لاگ ممیزی</b>\n{DIV}\nهنوز موردی ثبت نشده."
    body = "\n".join(format_entry(x) for x in rows)
    return f"📜 <b>لاگ ممیزی</b> ({len(AUDIT_LOG)} مورد)\n{DIV}\n{body}"
