"""محاسبه هزینه ارتقا با باف/نرف هزینه شهر."""
import re

from app.state import CITY_BUFFS
from app.utils import _norm_country_token
from app.economy.rules import UPGRADE_TABLE, _RES_MAP
from app.economy.sheet import _sum_force_soldiers, normalize_stats_keys


def count_army_soldiers(bag: dict) -> int:
    """تعداد نفر سرباز زمینی (هر نفر = ۱ غذا در آپ). توپ و کشتی حساب نمی‌شوند."""
    bag = bag or {}
    total = float(_sum_force_soldiers(bag) or 0)
    if total <= 0:
        try:
            total = float(bag.get("سربازان") or 0)
        except (TypeError, ValueError):
            total = 0
    return int(round(total))


def _fmt_upgrade_cost(name: str, city: str | None = None) -> str:
    """هزینه ۱ سطح؛ با city ضریب باف/نرف هزینه همان شهر اعمال می‌شود."""
    t = UPGRADE_TABLE.get(name) or {}
    if not t:
        return "—"
    if city:
        out = format_cost_dict(cost_for_levels(name, 1, city=city))
    else:
        parts = [f"{t.get('coin', 0)} سکه"]
        for k, lab in (
            ("wood", "چوب"), ("stone", "سنگ"), ("iron", "آهن"),
            ("pop", "نفر"), ("cloth", "پوشاک"), ("powder", "باروت"), ("horse", "اسب"),
        ):
            if t.get(k):
                parts.append(f"{t[k]} {lab}")
        out = " + ".join(parts)
    y = t.get("yield")
    yu = t.get("yunit", "")
    if y is not None:
        out += f" → بازده +{y} {yu}/سطح"
    if t.get("max"):
        out += f" (مکس {t['max']})"
    return out


def _can_afford(bag: dict, name: str, city: str | None = None) -> bool:
    """همان منطق max_affordable_levels (همه منابع + باف/نرف هزینه شهر)."""
    if not UPGRADE_TABLE.get(name):
        return False
    return max_affordable_levels(name, _bag_stock(bag), city=city) >= 1


def _bag_stock(bag: dict) -> dict:
    bag = normalize_stats_keys(bag or {})
    return {
        "coin": float(bag.get("سکه") or 0),
        "wood": float(bag.get("چوب") or 0),
        "stone": float(bag.get("سنگ") or 0),
        "iron": float(bag.get("آهن") or bag.get("اهن") or 0),
        "pop": float(bag.get("جمعیت") or 0),
        "cloth": float(bag.get("پوشاک") or 0),
        "powder": float(bag.get("باروت") or 0),
        "horse": float(bag.get("اسب") or 0),
    }


def upgrade_cost_modifier(city: str | None, name: str) -> float:
    """
    ضریب هزینه ارتقا برای یک ساختمان/کمپ.
    باف هزینه (وزیر و …) → کاهش · نرف هزینه → افزایش.
    تشخیص: effect=cost|هزینه  یا  target شامل «هزینه»  یا  متن شامل «هزینه».
    هدف: نام ساختمان / «همه» / «ارتقا»
    """
    if not city or not name:
        return 1.0
    mod = 1.0
    for bf in list(CITY_BUFFS.get(city) or []):
        pct = float(bf.get("pct") or 0)
        if pct <= 0:
            continue
        effect = (bf.get("effect") or "").lower().strip()
        target = (bf.get("target") or "").strip()
        text = (bf.get("text") or "")
        is_cost = (
            effect in ("cost", "هزینه", "upgrade_cost")
            or target.startswith("هزینه")
            or "هزینه" in text
        )
        if not is_cost:
            continue
        # هدف ساختمان
        tname = target
        for prefix in ("هزینه ", "هزینه", "cost "):
            if tname.lower().startswith(prefix.lower()):
                tname = tname[len(prefix):].strip()
                break
        tname_n = _norm_country_token(tname) if tname else ""
        name_n = _norm_country_token(name)
        applies = (
            not tname
            or tname in ("همه", "ارتقا", "ساختمان", "all", "any")
            or tname == name
            or tname_n == name_n
            or (tname and tname in name)
            or (name and name in tname)
        )
        if not applies:
            continue
        kind = bf.get("kind") or "buff"
        if kind == "buff":
            mod *= max(0.0, 1.0 - abs(pct) / 100.0)
        else:
            mod *= 1.0 + abs(pct) / 100.0
    return max(0.05, min(mod, 5.0))  # بین ۵٪ تا ۵×


def cost_for_levels(name: str, levels: int, city: str | None = None) -> dict:
    """هزینه N سطح (جدول قوانین × ضریب باف/نرف هزینه شهر)."""
    t = UPGRADE_TABLE.get(name) or {}
    levels = max(1, min(int(levels or 1), int(t.get("max") or 10)))
    mod = upgrade_cost_modifier(city, name)
    out = {}
    for key, _lab in _RES_MAP:
        v = int(t.get(key) or 0) * levels
        if v:
            # گرد به عدد صحیح — حداقل ۱ اگر قبل از باف >0 بود
            nv = int(round(v * mod))
            if v > 0 and nv < 1 and mod < 1:
                nv = 1
            out[key] = nv
    out["_levels"] = levels
    out["_yield_total"] = (t.get("yield") or 0) * levels
    out["_yunit"] = t.get("yunit", "")
    out["_max"] = t.get("max") or 10
    out["_cost_mod"] = round(mod, 4)
    return out


def format_cost_dict(cd: dict) -> str:
    parts = []
    for key, lab in _RES_MAP:
        if cd.get(key):
            parts.append(f"{cd[key]} {lab}")
    base = " + ".join(parts) if parts else "—"
    mod = cd.get("_cost_mod")
    if mod is not None and abs(float(mod) - 1.0) > 0.001:
        pct = (1.0 - float(mod)) * 100
        if pct > 0:
            base += f" (باف هزینه −{pct:.0f}%)"
        else:
            base += f" (نرف هزینه +{abs(pct):.0f}%)"
    return base


def max_affordable_levels(name: str, stock: dict, city: str | None = None) -> int:
    """حداکثر سطحی که با موجودی فعلی قابل پرداخت است (با باف هزینه)."""
    t = UPGRADE_TABLE.get(name) or {}
    if not t:
        return 0
    mx = int(t.get("max") or 10)
    mod = upgrade_cost_modifier(city, name)
    lim = mx
    for key, _lab in _RES_MAP:
        unit = int(t.get(key) or 0)
        if unit <= 0:
            continue
        unit_eff = max(1, int(round(unit * mod))) if mod < 1 else int(round(unit * mod)) or unit
        if unit_eff <= 0:
            continue
        have = float(stock.get(key) or 0)
        lim = min(lim, int(have // unit_eff))
    return max(0, lim)


def guess_current_level(name: str, bag: dict, sheet: str = "") -> int | None:
    """حدس لول فعلی از شیت یا از بازده نسبی."""
    t = UPGRADE_TABLE.get(name) or {}
    y_unit = t.get("yield") or 0
    if sheet:
        # الگو: چوب بری | (3) : 300
        pat = re.compile(
            re.escape(name).replace("\\ ", r"\s*") + r"[^\n]{0,40}?\((\d+)\)",
            re.I,
        )
        m = pat.search(sheet)
        if m:
            return int(m.group(1))
    if y_unit and name in (bag or {}):
        val = float(bag.get(name) or 0)
        if val > 0:
            return max(1, int(round(val / y_unit)))
    return None
