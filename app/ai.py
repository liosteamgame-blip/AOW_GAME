"""تنها راه صدا زدن xAI/Grok: با سقف روزانه و کش.

قانون: هیچ کار خودکار/زمان‌بندی‌شده این‌جا را صدا نمی‌زند — فقط دکمه‌ای که کاربر می‌زند.
"""
import asyncio
import json
import logging
import time
import zlib
from datetime import datetime

from app.config import TZ, XAI_API_KEY, XAI_MODEL
from app.features import setting
from app.state import AI_CACHE, AI_CACHE_MAX, SETTINGS


def ai_available() -> bool:
    return bool(XAI_API_KEY)


def _today() -> str:
    return (datetime.now(TZ) if TZ else datetime.now()).strftime("%Y-%m-%d")


def daily_limit() -> int:
    try:
        return max(0, int(setting("ai_daily_limit") or 0))
    except ValueError:
        return 15


def used_today() -> int:
    if setting("ai_used_date") != _today():
        return 0
    try:
        return int(setting("ai_used_count") or 0)
    except ValueError:
        return 0


def remaining_today() -> int:
    return max(0, daily_limit() - used_today())


def _consume():
    SETTINGS["ai_used_count"] = str(used_today() + 1)
    SETTINGS["ai_used_date"] = _today()


def cache_key(*parts) -> str:
    raw = "␟".join(str(p) for p in parts)
    return f"{zlib.crc32(raw.encode('utf-8')):08x}"


def cached(key: str):
    hit = AI_CACHE.get(key)
    return hit.get("text") if isinstance(hit, dict) else None


def _post_sync(body: dict) -> dict:
    import urllib.request
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {XAI_API_KEY}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=55) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def ask(key: str, system: str, prompt: str, max_tokens: int = 1200, temperature: float = 0.4) -> tuple:
    """برمی‌گرداند (text | None, note). اول کش، بعد سقف روزانه، بعد درخواست واقعی (در ترد جدا)."""
    hit = cached(key)
    if hit:
        return hit, "♻️ از کش (سهمیه مصرف نشد)"
    if not ai_available():
        return None, "کلید xAI تنظیم نشده است."
    if remaining_today() <= 0:
        return None, f"سقف روزانه گروک ({daily_limit()}) پر شده؛ فردا دوباره."
    _consume()   # قبل از await — دو کلیک هم‌زمان از سقف رد نمی‌شوند
    body = {
        "model": XAI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        data = await asyncio.to_thread(_post_sync, body)
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        logging.exception("xAI request failed")
        return None, "پاسخ گروک دریافت نشد؛ کمی بعد دوباره."
    if text:
        AI_CACHE[key] = {"ts": time.time(), "text": text}
        while len(AI_CACHE) > AI_CACHE_MAX:
            AI_CACHE.pop(next(iter(AI_CACHE)))
    return text or None, f"🤖 سهمیه امروز: {remaining_today()} از {daily_limit()}"
