"""تجارت با تجار و گزارش تجارت."""
import logging
import random
import re

from app import state as app_state
from app.config import ADMIN_ID, CHANNEL_ID, DIV
from app.loader import bot
from app.state import MERCHANT_LIMITS, MERCHANT_PRICES
from app.utils import _clean_item_name, e, fmt_num, normalize_digits
from app.channel import send_report
from app.economy.assets import _append_change, apply_stat_delta


def item_buy_price(name: str) -> float:
    pr = MERCHANT_PRICES.get(name) or MERCHANT_PRICES.get(_clean_item_name(name)) or {}
    try:
        return float(pr.get("buy", app_state.MERCHANT_BUY_PRICE))
    except (TypeError, ValueError):
        return float(app_state.MERCHANT_BUY_PRICE)


def item_sell_price(name: str) -> float:
    pr = MERCHANT_PRICES.get(name) or MERCHANT_PRICES.get(_clean_item_name(name)) or {}
    try:
        return float(pr.get("sell", app_state.MERCHANT_SELL_PRICE))
    except (TypeError, ValueError):
        return float(app_state.MERCHANT_SELL_PRICE)


def format_merchant_catalog() -> str:
    """نمایش لیست تجار با سقف و قیمت هر کالا."""
    if not MERCHANT_LIMITS:
        return "— لیست خالی —"
    lines = ["⚜️ <b>لیست تجار</b>", DIV]
    for name, lim in MERCHANT_LIMITS.items():
        buy = item_buy_price(name)
        sell = item_sell_price(name)
        lim_s = int(lim) if float(lim) == int(lim) else lim
        lines.append(
            f"• <b>{e(name)}</b> — سقف <b>{lim_s}</b> | "
            f"خرید <b>{fmt_num(buy)}</b>🪙 | فروش <b>{fmt_num(sell)}</b>🪙"
        )
    return "\n".join(lines)


def validate_merchant_order(order: dict, mode: str = "buy"):
    """
    چک سقف + محاسبه هزینه/درآمد با قیمت هر کالا.
    mode: buy | sell
    برمی‌گرداند (ok, errors, applied, cost)
    """
    if not app_state.MERCHANT_ENABLED:
        return False, ["تجارت با تجار فعلاً غیرفعال است."], {}, 0
    if not MERCHANT_LIMITS:
        return False, ["لیست تجار هنوز توسط ادمین تنظیم نشده است."], {}, 0
    errors = []
    applied = {}
    limit_map = {_clean_item_name(str(k)): float(v) for k, v in MERCHANT_LIMITS.items()}
    limit_lower = {k.lower(): k for k in limit_map}
    if "آهن" in limit_map and "اهن" not in limit_lower:
        limit_lower["اهن"] = "آهن"
    for name, qty in order.items():
        clean = _clean_item_name(name)
        key = limit_lower.get(clean.lower())
        if key is None:
            errors.append(f"❌ «{e(name)}» در لیست تجار نیست.")
            continue
        lim = limit_map[key]
        if qty > lim:
            errors.append(
                f"❌ «{e(key)}»: درخواست <b>{fmt_num(qty)}</b> بیش از سقف <b>{fmt_num(lim)}</b> "
                f"(اضافه: {fmt_num((qty - lim))})."
            )
            continue
        applied[key] = applied.get(key, 0) + qty
    if errors:
        return False, errors, applied, 0
    if not applied:
        return False, ["هیچ کالای مجازی انتخاب نشد."], {}, 0
    cost = 0.0
    for k, q in applied.items():
        unit = item_buy_price(k) if mode == "buy" else item_sell_price(k)
        cost += float(q) * unit
    cost = int(cost) if abs(cost - int(cost)) < 1e-9 else round(cost, 2)
    return True, [], applied, cost


async def send_trade_reports(public_report: str, full_report: str):
    """
    گزارش تجارت:
    - کانال گزارش + ادمین اصلی ← public_report یا full
    - ادمین دارایی ← full_report کامل
    """
    await send_report(full_report)
    if app_state.ASSET_ADMIN_ID and app_state.ASSET_ADMIN_ID != ADMIN_ID:
        try:
            await bot.send_message(chat_id=app_state.ASSET_ADMIN_ID, text=full_report)
        except Exception:
            logging.exception("ارسال گزارش تجارت به ادمین دارایی ناموفق بود.")


MERCHANT_ARRIVE_LINES = [
    "🛒 کاروان تجار از راه‌های دوردست رسید.\nبازار گشوده شد؛ معامله آزاد است.",
    "⚜️ تجار با بارِ کالا به شهر درآمدند.\nساعتِ خرید و فروش فرا رسیده است.",
    "🌊 کشتی‌های بازرگانی لنگر انداختند.\nتجار حاضرند؛ بازار آمادهٔ معامله است.",
    "🔔 ناقوس بازار نواخته شد.\nکاروان تجار در شهر ایستاده است.",
]
MERCHANT_LEAVE_LINES = [
    "🌙 کاروان تجار بار بست و راه گرفت.\nبازار تا بازگشت بعدی بسته است.",
    "🕊 تجار آخرین معامله را بستند و رفتند.\nتجارت با تجار تا اطلاع بعدی متوقف است.",
    "🌊 بادبان‌ها بالا رفت؛ تجار بندر را ترک کردند.\nبازار بازرگانی خاموش شد.",
    "🔕 چادرهای بازار جمع شد.\nتجار رفتند؛ معامله تا دیدار بعد بسته است.",
]


def merchant_guide_text() -> str:
    cat = format_merchant_catalog()
    return (
        f"{cat}\n\n"
        f"📖 <b>راهنما</b>\n"
        "منو → 🐪 تجارت → تجارت با تجار → خرید یا فروش\n"
        "لیست کالا: <code>چوب: 50</code> سپس باف و تایید."
    )


async def announce_merchants_to_channel(enabled: bool):
    """اعلان رسمی و کوتاه در کانال اصلی هنگام فعال/غیرفعال شدن تجار."""
    if not CHANNEL_ID:
        return
    if enabled:
        line = random.choice(MERCHANT_ARRIVE_LINES)
        text = f"{line}\n\n{merchant_guide_text()}"
    else:
        line = random.choice(MERCHANT_LEAVE_LINES)
        text = line
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text[:4000])
    except Exception:
        logging.exception("اعلان تجار در کانال ناموفق")


def apply_merchant_trade_to_city(city: str, mode: str, after: dict, cost: float) -> str:
    """اعمال خرید/فروش تجار روی stats شهر."""
    deltas = {}
    if mode == "buy":
        deltas["سکه"] = -abs(float(cost or 0))
        for k, v in (after or {}).items():
            key = _clean_item_name(str(k))
            try:
                deltas[key] = deltas.get(key, 0) + float(v)
            except (TypeError, ValueError):
                continue
    else:
        deltas["سکه"] = abs(float(cost or 0))
        for k, v in (after or {}).items():
            key = _clean_item_name(str(k))
            try:
                deltas[key] = deltas.get(key, 0) - abs(float(v))
            except (TypeError, ValueError):
                continue
    log = apply_stat_delta(city, deltas, note=f"تجارت تجار ({mode})")
    _append_change(city, f"تجارت تجار {mode}")
    return log


def _parse_goods_units(text: str) -> float:
    """جمع تقریبی واحد کالا از متن آزاد برای ظرفیت تجارتخانه."""
    if not text:
        return 0.0
    total = 0.0
    for m in re.finditer(r"(\d+(?:\.\d+)?)", normalize_digits(str(text))):
        try:
            total += float(m.group(1))
        except ValueError:
            continue
    return total
