"""🌍 رویدادهای جهانی روی سیستم CITY_BUFFS.

هر رویداد برای هر شهرِ دامنه‌اش یک باف/نرف با source="event" و ups_left می‌سازد. همان مکانیزم
موجود آپ (apply_on_up) آن را اعمال می‌کند؛ بعد از هر آپ شهر، consume_event_buffs یکی کم می‌کند و
در صفر حذف می‌شود. اعداد پیش‌فرض قالب‌ها فقط پیشنهاد است و ادمین قبل از تایید عوض می‌کند.
"""
import secrets
import time

from app.factions import FACTIONS, FACTION_META, cities_for_side_assets
from app.state import CITY_ASSETS, CITY_BUFFS, PLAYER_CODES, WORLD_EVENTS
from app.utils import fmt_num

# key -> (عنوان، kind، هدف (ساختمان)، درصد پیش‌فرض، تعداد آپ پیش‌فرض، متن اعلام عمومی)
EVENT_TEMPLATES = {
    "plague": ("🦠 طاعون", "nerf", "دهکده", 30, 2,
               "طاعون در {scope} شیوع یافت؛ رشد جمعیت تا مدتی کند خواهد بود."),
    "famine": ("🌾 قحطی", "nerf", "آشپزخانه", 40, 1,
               "قحطی دامن {scope} را گرفت؛ آشپزخانه‌ها نیمه‌خالی‌اند."),
    "festival": ("🎉 جشنواره", "buff", "تجارتخانه", 25, 1,
                 "جشنواره‌ای بزرگ در {scope} برپا شد؛ بازارها پررونق‌اند."),
    "storm": ("⛈ طوفان دریایی", "nerf", "بندر", 30, 1,
              "طوفانی سهمگین سواحل {scope} را درنوردید؛ بندرها آسیب دیدند."),
    "harvest": ("🌱 فصل پربرکت", "buff", "آشپزخانه", 25, 1,
                "برداشتی پربرکت نصیب {scope} شد؛ انبارهای غله پر است."),
    "mine": ("⛏ رگه‌ی تازه معدن", "buff", "معدن آهن", 30, 1,
             "معدنچیان {scope} به رگه‌ای تازه از آهن رسیدند."),
}
MAX_UPS = 5


def scope_cities(scope: str) -> list:
    """all = همه شهرهای ثبت‌شده؛ نام فکشن = شهرهای همان جناح."""
    if scope in FACTIONS:
        return cities_for_side_assets(scope)
    names = {str(v) for v in PLAYER_CODES.values()} | set(CITY_ASSETS.keys())
    return sorted(names, key=lambda s: s.lower())


def scope_title(scope: str) -> str:
    if scope in FACTIONS:
        flag, title = FACTION_META[scope]
        return f"{flag} {title}"
    return "🌍 همه سرزمین‌ها"


def public_text(ev: dict) -> str:
    tpl = EVENT_TEMPLATES.get(ev.get("template")) or ("", "", "", 0, 0, "{scope}")
    return f"{ev.get('title')}\n\n{tpl[5].format(scope=scope_title(ev.get('scope') or 'all'))}"


def start_event(template: str, scope: str, pct: float, ups: int, by: int = 0) -> dict:
    title, kind, target, _p, _u, _t = EVENT_TEMPLATES[template]
    ups = max(1, min(int(ups), MAX_UPS))
    pct = max(1.0, min(float(pct), 100.0))
    eid = secrets.token_hex(3)
    cities = scope_cities(scope)
    for city in cities:
        lst = CITY_BUFFS.setdefault(city, [])
        lst.append({
            "id": f"ev_{eid}", "kind": kind, "target": target, "pct": pct,
            "text": f"رویداد: {title} ({'+' if kind == 'buff' else '−'}{fmt_num(pct)}٪ {target})",
            "apply_on_up": True, "source": "event", "event_id": eid, "ups_left": ups,
        })
    ev = {"template": template, "title": title, "kind": kind, "target": target, "pct": pct,
          "ups": ups, "scope": scope, "cities": cities, "ts": time.time(), "by": by, "active": True}
    WORLD_EVENTS[eid] = ev
    return {"eid": eid, **ev}


def consume_event_buffs(city: str) -> list:
    """بعد از هر آپ شهر: ups_left یکی کم؛ در صفر حذف. برمی‌گرداند عنوان رویدادهای تمام‌شده."""
    lst = CITY_BUFFS.get(city) or []
    keep, ended = [], []
    for bf in lst:
        if bf.get("source") != "event":
            keep.append(bf)
            continue
        left = int(bf.get("ups_left") or 0) - 1
        if left > 0:
            bf["ups_left"] = left
            keep.append(bf)
        else:
            ended.append(bf.get("event_id"))
    if len(keep) != len(lst):
        CITY_BUFFS[city] = keep
    for eid in ended:
        _refresh_active(eid)
    return [WORLD_EVENTS[e]["title"] for e in ended if e in WORLD_EVENTS]


def _refresh_active(eid: str):
    ev = WORLD_EVENTS.get(eid)
    if not ev:
        return
    still = any(bf.get("event_id") == eid for lst in CITY_BUFFS.values() for bf in (lst or []))
    ev["active"] = still


def end_event(eid: str) -> bool:
    """حذف دستی رویداد از همه شهرها."""
    ev = WORLD_EVENTS.get(eid)
    if not ev:
        return False
    for city, lst in list(CITY_BUFFS.items()):
        CITY_BUFFS[city] = [bf for bf in (lst or []) if bf.get("event_id") != eid]
    ev["active"] = False
    return True


def active_events() -> list:
    return [(eid, ev) for eid, ev in WORLD_EVENTS.items() if ev.get("active")]


def ups_left(eid: str) -> int:
    vals = [int(bf.get("ups_left") or 0) for lst in CITY_BUFFS.values() for bf in (lst or [])
            if bf.get("event_id") == eid]
    return max(vals) if vals else 0
