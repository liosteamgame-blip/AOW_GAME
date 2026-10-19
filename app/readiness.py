"""✅ چک‌لیست آمادگی شروع بازی — فقط خواندنی؛ هیچ داده‌ای را تغییر نمی‌دهد.

برای هر شهر: گروه وصل؟ چند فرمانده؟ کد ورود؟ شیت دارایی؟ — برای هر جناح: چند لیدر؟
"""
from app.config import DIV, MAX_LEADERS
from app.factions import FACTIONS, FACTION_META, country_key
from app.state import CITY_ASSETS, GROUPS, LEADERS, PLAYER_CODES, authenticated_users
from app.utils import _norm_country_token, e, fmt_num


def _n(name) -> str:
    return _norm_country_token(name or "")


def all_cities() -> list:
    """شهرهای شناخته‌شده (کد + گروه + دارایی)، بدون تکرار نام."""
    seen, out = set(), []
    for c in list(PLAYER_CODES.values()) + [g.get("city") for g in GROUPS.values()] + list(CITY_ASSETS.keys()):
        if c and _n(c) not in seen:
            seen.add(_n(c))
            out.append(str(c))
    return out


def city_status(city: str) -> dict:
    key = _n(city)
    groups = [gid for gid, g in GROUPS.items() if _n(g.get("city")) == key]
    commanders = set()
    for gid in groups:
        g = GROUPS[gid]
        asst = set(g.get("assistants") or [])
        for uid in list(g.get("commanders") or []) + ([g["commander"]] if g.get("commander") else []):
            if uid and uid not in asst:
                commanders.add(uid)
    for uid, u in authenticated_users.items():
        if u.get("role") == "player" and _n(u.get("country")) == key:
            commanders.add(uid)
    has_code = any(_n(v) == key for v in PLAYER_CODES.values())
    entry = next((v for k, v in CITY_ASSETS.items() if _n(k) == key), None) or {}
    has_sheet = bool((entry.get("text") or "").strip() or entry.get("stats"))
    st = {"city": city, "group": bool(groups), "commanders": len(commanders), "code": has_code, "sheet": has_sheet}
    st["ready"] = st["group"] and st["commanders"] > 0 and st["code"] and st["sheet"]
    return st


def _mark(ok: bool) -> str:
    return "✅" if ok else "❌"


def build_report() -> str:
    rows = [city_status(c) for c in all_cities()]
    rows.sort(key=lambda r: (r["ready"], str(r["city"]).lower()))   # ناقص‌ها اول
    ready = sum(1 for r in rows if r["ready"])
    lines = [
        f"🧭 <b>چک‌لیست آمادگی شروع</b>\n{DIV}",
        f"<b>آماده: {fmt_num(ready)} از {fmt_num(len(rows))}</b> شهر",
        "<i>ستون‌ها: گروه · فرمانده · کد ورود · شیت دارایی (فقط خواندنی)</i>\n",
    ]
    if not rows:
        lines.append("📭 هنوز شهری ثبت نشده.")
    for r in rows:
        flag = FACTION_META.get(country_key(r["city"]) or "", ("🏙", ""))[0]
        lines.append(
            f"{'🟢' if r['ready'] else '🔴'} {flag} <b>{e(r['city'])}</b> — "
            f"👥{_mark(r['group'])} · 👑{fmt_num(r['commanders'])}{'' if r['commanders'] else '❌'} · "
            f"🔑{_mark(r['code'])} · 📦{_mark(r['sheet'])}"
        )
    lines.append(f"\n{DIV}\n<b>🏴 لیدرهای جناح</b>")
    for side in FACTIONS:
        flag, title = FACTION_META[side]
        n = len(LEADERS.get(side) or [])
        lines.append(f"{'✅' if n else '❌'} {flag} {title}: <b>{fmt_num(n)}</b> از {fmt_num(MAX_LEADERS)}")
    return "\n".join(lines)
