"""ثبت خطاها و محدودیت گزارش: هر نوع خطا (نوع + محل) حداکثر هر ۱۰ دقیقه یک گزارش.

فقط در حافظه است (نیازی به بکاپ ندارد). داشبورد زنده از recent_count استفاده می‌کند.
"""
import time
import traceback

RATE_SECONDS = 600
RECENT_MAX = 300

RECENT = []    # [(ts, key)]
_LAST = {}     # key -> {"sent": ts, "suppressed": n}


def error_key(exc: BaseException) -> tuple:
    """(کلید یکتا، محل) — محل = آخرین فریم داخل کد خود ربات (app/)."""
    where = "?"
    for fr in reversed(traceback.extract_tb(exc.__traceback__) or []):
        fn = fr.filename.replace("\\", "/")
        if "/app/" in fn:
            where = f"{fn.rsplit('/app/', 1)[1]}:{fr.lineno} ({fr.name})"
            break
    return f"{type(exc).__name__}@{where}", where


def note(exc: BaseException, now: float | None = None) -> tuple:
    """ثبت یک خطا. برمی‌گرداند (باید_گزارش_شود، تعداد تکرارهای ساکت‌شده‌ی قبلی، محل)."""
    now = time.time() if now is None else now
    key, where = error_key(exc)
    RECENT.append((now, key))
    del RECENT[:-RECENT_MAX]
    st = _LAST.get(key)
    if st and now - st["sent"] < RATE_SECONDS:
        st["suppressed"] += 1
        return False, 0, where
    suppressed = st["suppressed"] if st else 0
    _LAST[key] = {"sent": now, "suppressed": 0}
    return True, suppressed, where


def recent_count(seconds: int = 3600, now: float | None = None) -> int:
    now = time.time() if now is None else now
    return sum(1 for ts, _k in RECENT if now - ts <= seconds)


def reset():
    RECENT.clear()
    _LAST.clear()
