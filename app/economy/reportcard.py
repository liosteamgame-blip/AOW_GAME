"""🧾 کارنامه هفتگی بعد از آپ — برای گروه و فرمانده‌ی همان شهر.

- تولید = موجودی بعد از آپ − اسنپ درست قبل از آپ (UP_SNAPSHOTS[city]["latest"])
- ارتقاهای هفته = لول‌ها در اسنپ این آپ − لول‌ها در اسنپ آپ قبلی (history[0])
- رتبه ▲▼ نسبت به کارنامه‌ی قبلی (CITY_RANKS)؛ فقط رتبه‌ی خود شهر
- یک پیشنهاد مشاور محلی (بدون xAI)
"""
import logging

from app.config import ADMIN_ID, DIV
from app.features import enabled
from app.loader import bot
from app.players import groups_of_city, player_ids_for_city
from app.state import CITY_ASSETS, CITY_RANKS, UP_SNAPSHOTS
from app.utils import e, fmt_num
from app.economy.rules import FORCE_UNIT_NAMES
from app.economy.sheet import normalize_stats_keys
from app.economy.views import RANK_CATS, RANK_TITLES, city_ranks, rank_arrow
from app.economy.up import send_up_receipts
from app.economy.advisor import build_optimal_plan

RESOURCES = (
    ("سکه", "💰"), ("غذا", "🍽"), ("جمعیت", "👥"), ("چوب", "🪵"), ("سنگ", "🪨"),
    ("آهن", "🔩"), ("پوشاک", "🧥"), ("باروت", "💥"), ("اسب", "🐴"),
)


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _snapshots(city: str):
    snap = UP_SNAPSHOTS.get(city) or {}
    latest = snap.get("latest") if isinstance(snap.get("latest"), dict) else None
    hist = snap.get("history") or []
    prev = hist[0] if hist and isinstance(hist[0], dict) else None
    return latest, prev


def production_lines(city: str) -> list:
    latest, _ = _snapshots(city)
    if not latest:
        return []
    before = normalize_stats_keys(dict(latest.get("stats") or {}))
    after = normalize_stats_keys(dict((CITY_ASSETS.get(city) or {}).get("stats") or {}))
    out = []
    for key, icon in RESOURCES:
        d = _num(after.get(key)) - _num(before.get(key))
        if abs(d) >= 0.5:
            out.append(f"{icon} {key}: <b>{fmt_num(d, signed=True)}</b>")
    troops = []
    for name in sorted(set(FORCE_UNIT_NAMES)):
        d = _num(after.get(name)) - _num(before.get(name))
        if d >= 0.5:
            troops.append(f"{name} {fmt_num(d, signed=True)}")
    if troops:
        out.append("🪖 نیروی تازه: " + "، ".join(troops[:8]))
    return out


def upgrade_lines(city: str) -> list | None:
    """None = اسنپ آپ قبلی نیست (اولین کارنامه)."""
    latest, prev = _snapshots(city)
    if not latest or not prev:
        return None
    lv_now = dict(latest.get("levels") or {})
    lv_old = dict(prev.get("levels") or {})
    out = []
    for name in sorted(lv_now):
        a, b = int(_num(lv_old.get(name))), int(_num(lv_now.get(name)))
        if b > a:
            out.append(f"🏗 {e(name)}: {fmt_num(a)} → <b>{fmt_num(b)}</b>")
    for u in sorted(set(latest.get("unlocked") or []) - set(prev.get("unlocked") or [])):
        out.append(f"🔓 {e(u)} باز شد")
    return out


def rank_lines(city: str, update: bool = True) -> list:
    now = city_ranks(city)
    if not now:
        return []
    prev = CITY_RANKS.get(city) or {}
    out = []
    for cat in RANK_CATS:
        r, total = now[cat]
        out.append(f"{RANK_TITLES[cat]}: <b>{fmt_num(r)}</b> از {fmt_num(total)}  {rank_arrow(prev.get(cat), r)}")
    if update:
        CITY_RANKS[city] = {cat: now[cat][0] for cat in RANK_CATS}
    return out


def advisor_line(city: str) -> str:
    bag = normalize_stats_keys(dict((CITY_ASSETS.get(city) or {}).get("stats") or {}))
    try:
        plan = build_optimal_plan(bag, mode="balance", sheet=(CITY_ASSETS.get(city) or {}).get("text") or "", city=city)
    except Exception:
        logging.exception("advisor_line %s", city)
        plan = []
    if not plan:
        return "🧠 مشاور: این هفته منابع برای ارتقای تازه کافی نیست؛ ذخیره کنید."
    p = plan[0]
    return (f"🧠 پیشنهاد مشاور: <b>{e(p['name'])}</b> {e(p['from_lv'])} → {e(p['to_lv'])}"
            f"\n   🧮 {e(p['cost'])}")


def build_card(city: str, update_rank: bool = True) -> str:
    lines = [f"🧾 <b>کارنامه هفتگی — {e(city)}</b>", DIV]
    prod = production_lines(city)
    lines.append("<b>📦 تولید و درآمد این آپ</b>")
    lines.extend(prod or ["— تغییری در موجودی ثبت نشد."])
    ups = upgrade_lines(city)
    lines.append("\n<b>⬆️ ارتقاهای این هفته</b>")
    if ups is None:
        lines.append("— اولین کارنامه؛ از هفته‌ی بعد مقایسه می‌شود.")
    else:
        lines.extend(ups or ["— ارتقایی انجام نشد."])
    ranks = rank_lines(city, update=update_rank)
    if ranks:
        lines.append("\n<b>🏆 رتبه شهر</b>")
        lines.extend(ranks)
    lines.append("\n" + advisor_line(city))
    lines.append("\n<i>📜 جزئیات: منوی اقتصادی ← تغییرات اخیر</i>")
    return "\n".join(lines)[:4000]


async def send_up_result(city: str, log: str):
    """کارنامه به گروه/فرمانده‌ی شهر (اگر فیچر روشن است) و رسید خام فقط برای ادمین‌ها."""
    ok_up = str(log).startswith("✅")
    if not (enabled("report_card") and ok_up):
        return await send_up_receipts(city, log)
    card = build_card(city)
    for gid in groups_of_city(city):
        try:
            await bot.send_message(gid, card)
        except Exception:
            logging.exception("کارنامه به گپ %s", gid)
    for uid in player_ids_for_city(city):
        if uid == ADMIN_ID:
            continue
        try:
            await bot.send_message(uid, card)
        except Exception:
            logging.exception("کارنامه به پلیر %s", uid)
    await send_up_receipts(city, log, to_city=False)
