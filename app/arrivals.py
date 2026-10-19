"""⏳ هشدار رسیدن لشکر و کاروان.

- زمان(های) رسیدن به لحظه‌ی مطلق تبدیل و روی خود اکشن ذخیره می‌شود (action["arrival"]).
- حلقه‌ی زمان‌بند هر دقیقه tick می‌زند؛ شمارش معکوس پست کانال فقط در چند آستانه ویرایش می‌شود
  (۶۰/۳۰/۱۵/۵/۱ دقیقه) تا به محدودیت تلگرام نخوریم.
- با رسیدن: پیام به گروه مهاجم و گروه(های) مدافع — فقط اطلاعات عمومی، بدون آمار.
- «تغییر مسیر» و «بک» زمان را از نو حساب می‌کنند (reschedule).
"""
import logging
import time
from datetime import datetime, timedelta

from app.config import CHANNEL_ID, DIV, TZ
from app.chronicle import record_event
from app.factions import match_registered_cities
from app.features import enabled
from app.keyboards import get_channel_buttons, get_trade_channel_buttons
from app.loader import bot
from app.players import city_of, groups_of_city
from app.state import active_actions
from app.storage import save_data
from app.utils import _parse_hhmm, e, fmt_num, mtype_tag
from app.channel import send_report

BUCKETS = (60, 30, 15, 5, 1)   # دقیقه — فقط در این آستانه‌ها پست ویرایش می‌شود
MAX_HORIZON = 2 * 24 * 3600     # زمانی که بیش از ۲ روز دور باشد را جدی نمی‌گیریم


def _dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, TZ) if TZ else datetime.fromtimestamp(ts)


def parse_arrivals(time_str: str, base_ts: float) -> list:
    """«12:00» یا «12:00, 14:30» → لیست epoch. اگر ساعت از لحظه‌ی ثبت گذشته باشد = روز بعد.
    چند زمان = چند موج؛ هر موج بعد از موج قبلی است."""
    out = []
    prev = base_ts - 60
    for part in str(time_str or "").replace("،", ",").split(","):
        hm = _parse_hhmm(part.strip())
        if not hm:
            continue
        base = _dt(base_ts)
        cand = base.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        while cand.timestamp() <= prev:
            cand += timedelta(days=1)
        ts = cand.timestamp()
        if ts - base_ts > MAX_HORIZON:
            continue
        out.append(ts)
        prev = ts
    return out


def schedule(action_id: str, time_str: str, post_text: str, is_photo: bool, *,
             via: str = "campaign", origin_chat: int | None = None, city: str = "") -> bool:
    """ثبت زمان رسیدن روی اکشن. via = campaign | caravan."""
    act = active_actions.get(action_id)
    if not act:
        return False
    times = parse_arrivals(time_str, float(act.get("time_created") or time.time()))
    act["arrival"] = {
        "times": times, "next": 0, "mode": "go", "via": via,
        "post_text": post_text or "", "photo": bool(is_photo),
        "bucket": None, "done": not times,
        "origin_chat": origin_chat, "city": city,
    }
    return bool(times)


def reschedule(action_id: str, time_str: str, mode: str = "go", dest: str | None = None) -> bool:
    """تغییر مسیر (mode=go, dest جدید) یا بک (mode=back → مقصد = مبدأ)."""
    act = active_actions.get(action_id)
    if not act:
        return False
    arr = act.get("arrival")
    if not isinstance(arr, dict):
        arr = {"post_text": "", "photo": False, "via": "campaign", "city": city_of(act.get("owner_id"))}
        act["arrival"] = arr
    times = parse_arrivals(time_str, time.time())
    arr.update({"times": times, "next": 0, "mode": mode, "bucket": None, "done": not times})
    if dest:
        arr["dest"] = dest
    return bool(times)


def _bucket(rem_min: float):
    for b in reversed(BUCKETS):          # 1, 5, 15, 30, 60
        if rem_min <= b:
            return b
    return None


def countdown_line(arr: dict, now: float) -> str:
    if arr.get("done"):
        return "🔙 <b>لشکر به مبدأ بازگشت.</b>" if arr.get("mode") == "back" else "🏁 <b>رسید.</b>"
    times = arr.get("times") or []
    i = int(arr.get("next") or 0)
    if i >= len(times):
        return ""
    rem = max(0, int(round((times[i] - now) / 60)))
    wave = f" (موج {fmt_num(i + 1)} از {fmt_num(len(times))})" if len(times) > 1 else ""
    if arr.get("mode") == "back":
        return f"🔙 در راه بازگشت{wave} — حدود <b>{fmt_num(rem)}</b> دقیقه"
    return f"⏳ تا رسیدن{wave}: حدود <b>{fmt_num(rem)}</b> دقیقه"


async def _edit_post(action_id: str, act: dict, now: float):
    arr = act["arrival"]
    if not arr.get("post_text") or not act.get("msg_id") or not CHANNEL_ID:
        return
    text = f"{arr['post_text']}\n\n{countdown_line(arr, now)}"
    markup = get_trade_channel_buttons(action_id) if arr.get("via") == "caravan" else get_channel_buttons(action_id)
    try:
        if arr.get("photo"):
            await bot.edit_message_caption(chat_id=CHANNEL_ID, message_id=act["msg_id"], caption=text[:1024],
                                           reply_markup=markup)
        else:
            await bot.edit_message_text(chat_id=CHANNEL_ID, message_id=act["msg_id"], text=text[:4096],
                                        reply_markup=markup)
    except Exception as ex:
        if "not modified" not in str(ex).lower():
            logging.warning("ویرایش شمارش معکوس %s ناموفق: %s", action_id, ex)


def _attacker_groups(act: dict, city: str) -> list:
    arr = act.get("arrival") or {}
    if arr.get("origin_chat"):
        return [arr["origin_chat"]]
    return groups_of_city(city) if city else []


async def _announce(act: dict):
    """پیام رسیدن به گروه مهاجم و مدافع — فقط اطلاعات عمومی."""
    arr = act["arrival"]
    data = act.get("data") or {}
    city = arr.get("city") or city_of(act.get("owner_id"))
    dest = arr.get("dest") or data.get("dest") or "—"
    origin = data.get("origin") or "—"
    via = arr.get("via")
    mine = _attacker_groups(act, city)
    if arr.get("mode") == "back":
        msg_self = f"🔙 <b>سرورم، لشکر شما به مبدأ بازگشت.</b>\n{DIV}\n📍 مبدأ: <b>{e(origin)}</b>"
        targets_other, msg_other = [], ""
    elif via == "caravan":
        msg_self = (f"🐪 <b>سرورم، کاروان شما به مقصد رسید.</b>\n{DIV}\n"
                    f"📍 از: <b>{e(origin)}</b>\n🎯 به: <b>{e(dest)}</b>")
        msg_other = (f"🐪 <b>کاروان تجاری {e(city)} به شهر شما رسید.</b>\n{DIV}\n"
                     f"📍 از: <b>{e(origin)}</b>")
        targets_other = [g for c in match_registered_cities(dest) for g in groups_of_city(c)]
    else:
        msg_self = (f"🏁 <b>سرورم، لشکریان شما به مقصد رسیدند.</b>\n{DIV}\n"
                    f"📍 از: <b>{e(origin)}</b>\n🎯 به: <b>{e(dest)}</b>\n🧭 {mtype_tag(data)}\n\n"
                    "سناریوی نبرد را با ادمین هماهنگ کنید.")
        msg_other = (f"🚨 <b>لشکر {e(city)} به {e(dest)} رسید!</b>\n{DIV}\n"
                     f"🧭 {mtype_tag(data)}\n\nسرورم، مدافعان را آماده کنید و سناریوی دفاع را به ادمین بفرستید.")
        targets_other = [g for c in match_registered_cities(dest) for g in groups_of_city(c)]
    sent = set()
    for gid in mine:
        if gid in sent:
            continue
        sent.add(gid)
        try:
            await bot.send_message(gid, msg_self)
        except Exception:
            logging.exception("پیام رسیدن به گروه مهاجم %s", gid)
    for gid in targets_other:
        if gid in sent:
            continue
        sent.add(gid)
        try:
            await bot.send_message(gid, msg_other)
        except Exception:
            logging.exception("پیام رسیدن به گروه مدافع %s", gid)
    what = "بازگشت" if arr.get("mode") == "back" else ("کاروان" if via == "caravan" else "لشکر")
    if arr.get("mode") != "back":   # «بازگشت» همان لحظه‌ی دستور در وقایع‌نامه ثبت شده
        record_event("arrival", city=city, dest=dest, via=via)
    await send_report(f"🏁 <b>رسیدن {what}</b>\n{DIV}\n🏙 {e(city)} → 🎯 {e(dest if arr.get('mode') != 'back' else origin)}")


async def tick(now: float | None = None) -> int:
    """یک دور بررسی. برمی‌گرداند تعداد رسیدن‌های اعلام‌شده (برای تست)."""
    if not enabled("arrival_alerts"):
        return 0
    now = time.time() if now is None else now
    arrived = 0
    changed = False
    for action_id, act in list(active_actions.items()):
        arr = act.get("arrival")
        if not isinstance(arr, dict) or arr.get("done") or act.get("cancelled"):
            continue
        times = arr.get("times") or []
        i = int(arr.get("next") or 0)
        if i >= len(times):
            arr["done"] = True
            changed = True
            continue
        rem_min = (times[i] - now) / 60
        if rem_min <= 0:
            arr["next"] = i + 1
            arr["bucket"] = None
            if arr["next"] >= len(times):
                arr["done"] = True
            changed = True
            arrived += 1
            await _announce(act)
            await _edit_post(action_id, act, now)
            continue
        b = _bucket(rem_min)
        if b is not None and b != arr.get("bucket"):
            arr["bucket"] = b
            changed = True
            await _edit_post(action_id, act, now)
    if changed:
        save_data()
    return arrived
