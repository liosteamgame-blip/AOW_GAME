"""وقایع‌نامه: ثبت رویدادهای عمومی کانال و ساخت متن هفتگی با قالب محلی.

قانون دید: فقط همان چیزی که در کانال عمومی است (شهر، مبدأ، مقصد، هدف، نوع). هرگز آمار لشکر،
محموله یا آمار کمین این‌جا ذخیره نمی‌شود.
"""
import time
from datetime import datetime

from app.config import DIV, TZ
from app.factions import FACTION_META, country_key
from app.features import enabled, setting
from app.state import CHRONICLE, CHRONICLE_MAX
from app.utils import e, fmt_num

# فیلدهایی که اجازه دارند ذخیره شوند (عمومی)
PUBLIC_FIELDS = ("city", "origin", "dest", "target", "mtype", "defender", "via")

SECTIONS = (
    ("campaign", "⚔️ لشکرکشی‌ها"),
    ("war", "🔥 اعلان‌های جنگ"),
    ("siege", "🏰 محاصره‌ها"),
    ("cancel", "🏳️ فرمان‌های پس‌گرفته"),
    ("redirect", "🔄 تغییر مسیرها"),
    ("back", "🔙 بازگشت لشکرها"),
    ("ambush", "🪓 کمین‌ها"),
    ("caravan", "🐪 کاروان‌های تجاری"),
    ("arrival", "🏁 رسیدن‌ها"),
    ("statement", "📜 بیانیه‌ها"),
    ("event", "🌍 رویدادهای جهانی"),
)
_MTYPE = {"sea": "دریایی", "land": "زمینی"}


def record_event(kind: str, **fields) -> None:
    if not enabled("chronicle"):
        return
    ev = {"ts": time.time(), "kind": kind}
    for k in PUBLIC_FIELDS:
        v = fields.get(k)
        if v:
            ev[k] = str(v)[:80]
    CHRONICLE.append(ev)
    del CHRONICLE[:-CHRONICLE_MAX]


def since_ts() -> float:
    try:
        return float(setting("chronicle_since") or 0)
    except ValueError:
        return 0.0


def events_since(ts: float | None = None) -> list:
    t0 = since_ts() if ts is None else ts
    return [x for x in CHRONICLE if float(x.get("ts") or 0) > t0]


def _flag(city: str) -> str:
    return FACTION_META.get(country_key(city or "") or "", ("🏙", ""))[0]


def _line(ev: dict) -> str:
    k = ev.get("kind")
    c = f"{_flag(ev.get('city'))} <b>{e(ev.get('city') or '—')}</b>"
    mt = f" ({_MTYPE[ev['mtype']]})" if ev.get("mtype") in _MTYPE else ""
    if k == "campaign":
        return f"{c} لشکر{mt} از {e(ev.get('origin') or '—')} به سوی <b>{e(ev.get('dest') or '—')}</b> گسیل کرد."
    if k in ("war", "siege"):
        verb = "طبل جنگ را علیه" if k == "war" else "حلقه محاصره را گرد"
        return f"{c} {verb} <b>{e(ev.get('target') or '—')}</b>{mt} {'نواخت' if k == 'war' else 'کشید'}."
    if k == "cancel":
        return f"{c} فرمان خود علیه <b>{e(ev.get('target') or '—')}</b> را پس گرفت."
    if k == "redirect":
        return f"لشکریان {c} ناگهان راه <b>{e(ev.get('dest') or '—')}</b> را در پیش گرفتند."
    if k == "back":
        return f"لشکریان {c} به خانه بازگشتند."
    if k == "ambush":
        what = "کاروان" if ev.get("via") == "caravan" else "لشکر"
        return f"{c} در کمین {what} <b>{e(ev.get('defender') or '—')}</b> نشست."
    if k == "caravan":
        return f"کاروان {c}{mt} از {e(ev.get('origin') or '—')} راهی <b>{e(ev.get('dest') or '—')}</b> شد."
    if k == "arrival":
        what = "کاروان" if ev.get("via") == "caravan" else "لشکر"
        return f"{what} {c} به <b>{e(ev.get('dest') or '—')}</b> رسید."
    if k == "event":
        return f"{e(ev.get('via') or 'رویدادی')} سرزمین‌ها را فرا گرفت."
    if k == "statement":
        return f"{c} بیانیه‌ای رسمی صادر کرد."
    return f"{c} — {e(k)}"


def _date(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, TZ) if TZ else datetime.fromtimestamp(ts)
    return dt.strftime("%m/%d")


def build_local_text(events: list | None = None) -> str:
    events = events_since() if events is None else events
    if not events:
        return ""
    t0, t1 = float(events[0]["ts"]), float(events[-1]["ts"])
    lines = [
        "📖 <b>وقایع‌نامه خاکستر جنگ</b>",
        f"🗓 {_date(t0)} تا {_date(t1)}",
        DIV,
        "<i>کاتبان دربار آنچه را در میدان‌ها و راه‌ها رخ داد، چنین ثبت کردند:</i>",
    ]
    for kind, title in SECTIONS:
        items = [ev for ev in events if ev.get("kind") == kind]
        if not items:
            continue
        lines.append(f"\n<b>{title}</b> ({fmt_num(len(items))})")
        for ev in items[:12]:
            lines.append(f"▫️ {_line(ev)}")
        if len(items) > 12:
            lines.append(f"▫️ … و {fmt_num(len(items) - 12)} مورد دیگر")
    # پرتحرک‌ترین جناح (فقط از شمار رویدادهای عمومی)
    per_side = {}
    for ev in events:
        side = country_key(ev.get("city") or "")
        if side:
            per_side[side] = per_side.get(side, 0) + 1
    if per_side:
        side = max(per_side, key=per_side.get)
        flag, title = FACTION_META.get(side, ("🏴", side))
        lines.append(f"\n{DIV}\n🏅 پرتحرک‌ترین جناح این هفته: {flag} <b>{title}</b> با {fmt_num(per_side[side])} رویداد.")
    lines.append("\n<i>تاریخ را پیروزان می‌نویسند؛ هفته‌ی بعد نوبت کیست؟</i>\n#وقایع_نامه")
    text = "\n".join(lines)
    return text[:4000]
