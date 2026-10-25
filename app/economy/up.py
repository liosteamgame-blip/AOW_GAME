"""آپ هفتگی و بکاپ/بازگردانی آن."""
import copy
import logging
from datetime import datetime

from app import state as app_state
from app.config import ADMIN_ID, DIV, TZ
from app.loader import bot
from app.state import CITY_ASSETS, CITY_BUFFS, UP_HISTORY_MAX, UP_SNAPSHOTS, is_junk_key
from app.utils import e, fmt_num, html_cut
from app.players import groups_of_city, player_ids_for_city
from app.storage import save_data
from app.audit import audited
from app.events import consume_event_buffs
from app.features import setting
from app.economy.rules import FORCE_UNIT_NAMES, SPECIAL_UNITS, UPGRADE_TABLE, UP_YIELD_DEST
from app.economy.sheet import (
    VALID_RESOURCES,
    WAREHOUSE_RESOURCES,
    _annotate_yield_pct,
    _apply_stock_to_sheet,
    _parse_shop_from_sheet,
    _sum_force_soldiers,
    extract_asset_stats,
    get_city_asset_stats,
    manual_offsets,
    normalize_stats_keys,
    sane_levels,
    with_manual_offsets,
)
from app.economy.costs import army_food_need
from app.economy.assets import _append_change, apply_stat_delta, is_auto_city, is_building_locked


def _make_asset_snap(entry: dict) -> dict:
    """کپی سبک از دارایی یک شهر."""
    entry = entry or {}
    return {
        "text": entry.get("text") or "",
        "stats": dict(entry.get("stats") or {}),
        "levels": dict(entry.get("levels") or {}),
        "yields": dict(entry.get("yields") or {}),
        "unlocked": list(entry.get("unlocked") or []),
        "shop": dict(entry.get("shop") or {}),
        "shop_packs": list(entry.get("shop_packs") or []),
        "disabled": list(entry.get("disabled") or []),
        "roll_yields": dict(entry.get("roll_yields") or {}),
        "roll_buffs": list(entry.get("roll_buffs") or []),
        "manual_yield_offsets": dict(entry.get("manual_yield_offsets") or {}),
        "changes": list(entry.get("changes") or [])[-30:],
        "ts": datetime.now(TZ).strftime("%Y-%m-%d %H:%M") if TZ else datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _snapshot_city_assets(city: str) -> None:
    """
    بکاپ قبل از آپ:
    - latest = حالت درست قبل از این آپ
    - history = حداکثر UP_HISTORY_MAX نسخه قدیمی‌تر (حجم بکاپ تلگرام کم بماند)
    """
    entry = CITY_ASSETS.get(city) or {}
    snap = _make_asset_snap(entry)
    prev = UP_SNAPSHOTS.get(city)
    history = []
    if isinstance(prev, dict):
        if "latest" in prev:
            if prev.get("latest"):
                history.append(dict(prev["latest"]))
            history.extend(list(prev.get("history") or []))
        elif prev.get("text") is not None or prev.get("stats") is not None:
            history.append({k: prev[k] for k in prev if k not in ("history", "latest")})
    history = history[:UP_HISTORY_MAX]
    UP_SNAPSHOTS[city] = {"latest": snap, "history": history, "ts": snap["ts"]}


def _snap_entry(city: str):
    prev = UP_SNAPSHOTS.get(city)
    if not isinstance(prev, dict):
        return None
    if "latest" in prev:
        return prev.get("latest")
    if prev.get("text") is not None or prev.get("stats") is not None:
        return prev
    return None


@audited("بازگردانی آپ")
def restore_city_up(city: str, use_history: int = 0) -> tuple:
    """بازگردانی به قبل از آپ. use_history=0 آخرین؛ 1..UP_HISTORY_MAX قدیمی‌تر."""
    prev = UP_SNAPSHOTS.get(city)
    if not prev:
        return False, f"❌ برای «{city}» بکاپ آپ وجود ندارد."
    snap = None
    if isinstance(prev, dict) and "latest" in prev:
        if use_history and use_history > 0:
            hist = list(prev.get("history") or [])
            if 0 <= use_history - 1 < len(hist):
                snap = hist[use_history - 1]
        if snap is None:
            snap = prev.get("latest")
    else:
        snap = prev if isinstance(prev, dict) else None
    if not snap:
        return False, f"❌ بکاپ خالی برای «{city}»."
    CITY_ASSETS[city] = {
        "text": snap.get("text") or "",
        "stats": dict(snap.get("stats") or {}),
        "levels": dict(snap.get("levels") or {}),
        "yields": dict(snap.get("yields") or {}),
        "unlocked": list(snap.get("unlocked") or []),
        "shop": dict(snap.get("shop") or {}),
        "shop_packs": list(snap.get("shop_packs") or []),
        "disabled": list(snap.get("disabled") or []),
        "roll_yields": dict(snap.get("roll_yields") or {}),
        "roll_buffs": list(snap.get("roll_buffs") or []),
        "manual_yield_offsets": dict(snap.get("manual_yield_offsets") or {}),
        "changes": list(snap.get("changes") or []),
    }
    _append_change(city, f"بازگردانی آپ ({snap.get('ts') or '—'})")
    save_data(critical=True)
    return True, f"✅ دارایی «{city}» به بکاپ ({snap.get('ts') or '—'}) برگردید."


def snapshot_all_assets(reason: str = "manual") -> int:
    """بکاپ همه دارایی‌ها (قبل از آپ کلی)."""
    n = 0
    for city in list(CITY_ASSETS.keys()):
        _snapshot_city_assets(city)
        n += 1
    UP_SNAPSHOTS["__meta__"] = {
        "reason": reason,
        "ts": datetime.now(TZ).strftime("%Y-%m-%d %H:%M") if TZ else datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cities": n,
    }
    return n


# اصلاح یک‌باره‌ی وینچستر: موجودی نیروها قبل از آپ خراب v2.1 (لول خراب × بازدهی جدول)
WINCHESTER_CITY = "winchester_parliamentarian"
WINCHESTER_GOOD_STOCK = {
    "شبه نظامی": 300,
    "شمشیرزن": 250,
    "سواره‌نظام زره پوش": 75,
    "توپ سبک": 5,
}


@audited("اصلاح موجودی وینچستر (v2.1.1)")
def repair_winchester_v211(city: str = WINCHESTER_CITY) -> list:
    """
    فقط یک‌بار (پرچم fix_winchester_v211): نیرویی که بیش از ۱۰ برابر مقدار درست است
    به مقدار قبل از باگ برمی‌گردد؛ لول‌های غیرممکن هم پاک می‌شوند. خروجی: خطوط تغییر.
    اگر شهر هنوز لود نشده باشد، پرچم نمی‌خورد تا در استارت بعدی دوباره امتحان شود.
    """
    if setting("fix_winchester_v211") == "done":
        return []
    entry = CITY_ASSETS.get(city)
    if not entry:
        return []
    st = dict(entry.get("stats") or {})
    changed = []
    for unit, good in WINCHESTER_GOOD_STOCK.items():
        try:
            cur = float(st.get(unit) or 0)
        except (TypeError, ValueError):
            continue
        if cur > good * 10:
            st[unit] = float(good)
            changed.append(f"{unit}: {fmt_num(cur)} → {fmt_num(good)}")
    if changed:
        st["سربازان"] = float(_sum_force_soldiers(st))
        entry["stats"] = st
        entry["text"] = _apply_stock_to_sheet(entry.get("text") or "", st)
    entry["levels"] = sane_levels(entry.get("levels") or {})
    CITY_ASSETS[city] = entry
    if changed:
        _append_change(city, "اصلاح باگ آپ v2.1: " + "، ".join(changed))
    app_state.SETTINGS["fix_winchester_v211"] = "done"
    save_data(critical=True)
    return changed


# پیشوند نتیجه‌ی آپ متوقف‌شده (عدد مشکوک) — منتظر تأیید ادمین؛ هیچ تغییری اعمال نشده
UP_HOLD = "⏸"


def _setting_float(key: str, default: float) -> float:
    try:
        return float(setting(key) or default)
    except (TypeError, ValueError):
        return float(default)


def suspicious_deltas(deltas: dict, bag: dict) -> list:
    """
    بازدهی‌های غیرعادی آپ (مثل +۳۷٬۵۰۰ شبه‌نظامی از لول خراب ۲۵۰):
    • نیرو: بازدهی > up_guard_troop_max (۵۰۰۰) یا (موجودی > ۵۰ و بازدهی > ratio× موجودی)
    • منبع انبار: بازدهی > up_guard_res_max (۳۰۰۰) یا (موجودی > ۱۰۰ و بازدهی > ratio× موجودی)
    موجودی کم اولیه (مثلاً سنگ ۱۰ و معدن ۱۰۰) آپ را قفل نمی‌کند.
    سکه/غذا/جمعیت/اسب گردش بزرگ عادی دارند و چک نمی‌شوند.
    """
    troop_max = _setting_float("up_guard_troop_max", 5000)
    res_max = _setting_float("up_guard_res_max", 3000)
    ratio = _setting_float("up_guard_ratio", 10)
    out = []
    for k, dv in deltas.items():
        try:
            dv = float(dv)
            old = float(bag.get(k) or 0)
        except (TypeError, ValueError):
            continue
        if dv <= 0:
            continue
        if k in WAREHOUSE_RESOURCES:
            cap, min_stock, label = res_max, 100, "منبع"
        elif k not in VALID_RESOURCES:
            cap, min_stock, label = troop_max, 50, "نیرو"
        else:
            continue
        if cap > 0 and dv > cap:
            out.append(f"{k}: {fmt_num(old)} → +{fmt_num(dv)} (بیش از سقف {fmt_num(cap)} {label})")
        elif ratio > 0 and old > min_stock and dv > ratio * old:
            out.append(f"{k}: {fmt_num(old)} → +{fmt_num(dv)} (بیش از {fmt_num(ratio)}× موجودی)")
    return out


@audited("آپ هفتگی")
def run_weekly_up_for_city(city: str, force: bool = False, allow_suspicious: bool = False) -> str:
    """آپ یک شهر + کم کردن شمارنده‌ی رویدادهای جهانی همان شهر (فقط وقتی آپ واقعاً انجام شد).
    allow_suspicious=True: ادمین عددهای مشکوک را دیده و تأیید کرده است."""
    log = _run_weekly_up_impl(city, force=force, allow_suspicious=allow_suspicious)
    if not str(log).startswith(("⏭", UP_HOLD)):
        ended = consume_event_buffs(city)
        if ended:
            save_data(critical=True)
            log += "\n🌍 پایان رویداد: " + "، ".join(ended)
    return log


def _run_weekly_up_impl(city: str, force: bool = False, allow_suspicious: bool = False) -> str:
    """
    آپ هفتگی — بازدهی‌ها به مقصد مشخص:
    • خزانه+بندر+تجارتخانه → جمع می‌شود و به موجودی سکه خزانه
    • تولیدی‌ها → انبار (چوب/سنگ/آهن/پوشاک/باروت)
    • اصطبل → تعداد اسب
    • کمپ‌ها → لیست نیرو (همان یونیت)
    • آشپزخانه → غذا · دهکده → جمعیت
    force=True: ادمین حتی بدون اتو می‌تواند یک شهر را آپ کند
    """
    if not force and not is_auto_city(city):
        return f"⏭ {city}: اتو نیست"
    # برای توقف آپ مشکوک: وضعیت قبل از هر تغییر (شامل بکاپ آپ قبلی) دست‌نخورده برگردد
    before_entry = copy.deepcopy(CITY_ASSETS.get(city))
    before_snap = copy.deepcopy(UP_SNAPSHOTS.get(city))
    _snapshot_city_assets(city)
    entry = CITY_ASSETS.get(city) or {}
    # شیت = منبع حقیقت برای بازدهی (مثلاً خزانه ۷۰۰۰ نه پیش‌فرض ۱۰۰۰ جدول)
    sheet_text = entry.get("text") or ""
    if sheet_text.strip():
        try:
            raw_ex = extract_asset_stats(sheet_text)
            levels_ex = dict(raw_ex.pop("__levels__", {}) or {})
            disabled_ex = list(raw_ex.pop("__disabled__", []) or [])
            sheet_y = {}   # بازدهی‌های خوانده‌شده از شیت (بدون آفست دستی)
            for k, v in list(raw_ex.items()):
                if str(k).startswith("__"):
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if str(k).startswith("yield:"):
                    sheet_y[str(k)[6:]] = fv
                    continue
                st = entry.setdefault("stats", {})
                if k in FORCE_UNIT_NAMES or k in (SPECIAL_UNITS or {}):
                    # موجودی نیرو: stats منبع حقیقت است (set_city_asset با شیت همگامش کرده).
                    # قبلاً max(قبلی، شیت) بود → کم شدن نیرو در شیت هیچ‌وقت اعمال نمی‌شد.
                    continue
                st[k] = fv
                entry["stats"] = st
                bname = k
                if str(k).startswith("بازدهی"):
                    bname = {
                        "بازدهی خزانه": "خزانه",
                        "بازدهی بندر": "بندر",
                        "بازدهی تجارت‌خانه": "تجارتخانه",
                        "بازدهی تجارتخانه": "تجارتخانه",
                        "بازدهی آشپزخانه": "آشپزخانه",
                        "بازدهی دهکده": "دهکده",
                    }.get(k, k.replace("بازدهی", "").strip())
                    sheet_y[bname] = fv
                _econ = {
                    "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
                    "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
                }
                if (
                    bname in _econ
                    and k != "سکه"
                    and bname != "سکه"
                    and not str(k).startswith("بازدهی")
                ):
                    sheet_y[bname] = fv
            lv = sane_levels(entry.get("levels") or {})
            lv.update(levels_ex)
            entry["levels"] = lv
            # کلیدهای شیت = عدد شیت + آفست دستی؛ کلیدهای بیرون از شیت همان مقدار قبلی (آفست را دارند)
            offsets = manual_offsets(entry)
            ymap_new = {k: v for k, v in (entry.get("yields") or {}).items() if not is_junk_key(k)}
            ymap_new.update(with_manual_offsets(
                {k: v for k, v in sheet_y.items() if not is_junk_key(k)},
                {k: off for k, off in offsets.items() if k in sheet_y},
            ))
            entry["yields"] = ymap_new
            if disabled_ex:
                entry["disabled"] = disabled_ex
            CITY_ASSETS[city] = entry
        except Exception:
            logging.exception("بازخوانی بازدهی از شیت %s", city)

    bag = normalize_stats_keys(dict(entry.get("stats") or get_city_asset_stats(city) or {}))
    disabled = set(entry.get("disabled") or [])
    lv_map = sane_levels(entry.get("levels") or {})
    ymap = {k: v for k, v in (entry.get("yields") or {}).items() if not is_junk_key(k)}
    deltas = {}

    def _yield_of(name: str, default_y: float = 0) -> float:
        """بازدهی واقعی شیت؛ پیش‌فرض جدول فقط وقتی هیچ عددی روی شیت نباشد."""
        if name in disabled or f"بازدهی {name}" in disabled:
            return 0
        if is_building_locked(city, name):
            return 0
        candidates = []
        if ymap.get(name) is not None:
            try:
                # yields از شیت فعلی بازسازی شده → مقدم بر کلیدهای قدیمی yield: در stats
                if float(ymap[name]) > 0:
                    return float(ymap[name])
            except (TypeError, ValueError):
                pass
        for key in (f"yield:{name}", f"بازدهی {name}"):
            if bag.get(key) is not None:
                try:
                    candidates.append(float(bag[key]))
                except (TypeError, ValueError):
                    pass
        # موجودی لیست نیرو (شبه نظامی و …) هرگز بازدهی کمپ نیست
        _econ_only = {
            "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
            "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
            "انبار", "قلعه",
        }
        if name in _econ_only and bag.get(name) is not None:
            try:
                candidates.append(float(bag[name]))
            except (TypeError, ValueError):
                pass
        positive = [c for c in candidates if c and c > 0]
        if positive:
            return max(positive)
        lv = float(lv_map.get(name) or 0)
        if lv > 0 and default_y > 0:
            return float(default_y) * lv
        return 0

    coin_parts = []
    applied_names = set()
    for name, dest in UP_YIELD_DEST.items():
        if is_building_locked(city, name):
            continue
        default_y = float((UPGRADE_TABLE.get(name) or {}).get("yield") or 0)
        add = _yield_of(name, default_y)
        if add <= 0:
            continue
        applied_names.add(name)
        if dest == "سکه":
            deltas["سکه"] = deltas.get("سکه", 0) + add
            coin_parts.append(f"{name}+{fmt_num(add)}")
        else:
            deltas[dest] = deltas.get(dest, 0) + add

    # کمپ ویژه و یونیت‌های داینامیک: هر نامی در yields که در UP_YIELD_DEST نیست
    # بازدهی همان عبارت → لیست نیرو با همان نام
    skip_dest = {
        "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        "قلعه", "انبار", "دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی",
    }
    for name, yv in list(ymap.items()):
        if name in applied_names or name in skip_dest:
            continue
        if name in UP_YIELD_DEST:
            continue
        try:
            add = float(yv or 0)
        except (TypeError, ValueError):
            continue
        if add <= 0:
            continue
        if is_building_locked(city, name):
            continue
        # یونیت ویژه/داینامیک → همان نام در لیست نیرو
        deltas[name] = deltas.get(name, 0) + add
        applied_names.add(name)
        coin_parts.append(f"{name}+{fmt_num(add)}")

    #兜底: اگر دهکده/اصطبل در ymap بود ولی UP نخورد
    for name, dest in (("دهکده", "جمعیت"), ("اصطبل", "اسب")):
        if name in applied_names:
            continue
        add = _yield_of(name, 0)
        if add > 0:
            deltas[dest] = deltas.get(dest, 0) + add
            applied_names.add(name)
            coin_parts.append(f"{name}→{dest}+{fmt_num(add)}")

    buff_notes = list(coin_parts)

    def _buff_base(target: str, dest: str) -> float:
        """پایه‌ی درصد باف/نرف. اگر هدف یک ساختمان باشد، فقط بازدهی همان ساختمان حساب می‌شود.
        (قبلاً باف «خزانه» از جمع سکه‌ی خزانه+بندر+تجارتخانه حساب می‌شد.)"""
        if target in UP_YIELD_DEST:
            default_y = float((UPGRADE_TABLE.get(target) or {}).get("yield") or 0)
            return float(_yield_of(target, default_y) or 0)
        base = float(deltas.get(dest) or 0)
        if base <= 0:
            base = float(bag.get(dest) or bag.get(target) or 0)
        return base

    # باف/نرف با تیک apply_on_up — فقط روی بازدهی/آپ اثر می‌کند (ارتقا نیست)
    # هدف ساختمان → تغییر بازدهی همان بخش؛ روی شیت هم +N% ثبت می‌شود
    sheet_buff_ann = []  # (building_name, signed_pct)
    for bf in list(CITY_BUFFS.get(city) or []):
        if not bf.get("apply_on_up"):
            continue  # اطلاعی — فقط نمایش
        target = (bf.get("target") or "").strip()
        pct = float(bf.get("pct") or 0)
        kind = bf.get("kind") or "buff"
        if not target or not pct:
            continue
        sign = -1 if kind == "nerf" else 1
        signed_pct = sign * abs(pct)
        # نگاشت هدف به مقصد بازدهی
        dest = UP_YIELD_DEST.get(target)
        if dest is None:
            # هدف مستقیم منبع یا یونیت
            dest = target
        base = _buff_base(target, dest)
        if base <= 0 and target not in ("اقتدار", "مشروعیت"):
            buff_notes.append(f"{kind} {target} {fmt_num(pct)}% (پایه۰)")
            continue
        delta = base * (abs(pct) / 100.0) * sign
        if target in ("اقتدار", "مشروعیت"):
            # درصد از مقدار فعلی نوار
            cur = float(bag.get(target) or 0)
            delta = cur * (abs(pct) / 100.0) * sign
            deltas[target] = deltas.get(target, 0) + delta
        else:
            deltas[dest] = float(deltas.get(dest) or 0) + delta
        buff_notes.append(f"{kind} {target}→{dest} {fmt_num(signed_pct, signed=True)}%")
        if target in UP_YIELD_DEST or target in (
            "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
            "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        ):
            sheet_buff_ann.append((target, signed_pct))

    # اقتدار ۸۰–۱۰۰: +۲۵۰ سکه از مردم (قوانین)
    auth = float(bag.get("اقتدار") or 0)
    if auth >= 80:
        deltas["سکه"] = deltas.get("سکه", 0) + 250
        buff_notes.append("اقتدار اوج: +۲۵۰ سکه مردمی")

    # مصرف غذای ارتش طبق قوانین: پیاده ×۱، سواره ×۲، ویژه ×۳ (توپ/کشتی ندارند)
    need = army_food_need(bag)
    if need["food"] > 0:
        deltas["غذا"] = deltas.get("غذا", 0) - need["food"]
        buff_notes.append(
            f"مصرف غذا: پیاده {need['inf']}×۱ + سواره {need['cav']}×۲ + ویژه {need['elite']}×۳"
            f" = −{fmt_num(need['food'])}"
        )

    # بازدهی رول ذخیره‌شده + باف/نرف رول شیت
    entry = CITY_ASSETS.get(city) or {}
    for rk, rv in dict(entry.get("roll_yields") or {}).items():
        try:
            add = float(rv)
        except (TypeError, ValueError):
            continue
        if not add:
            continue
        dest = {
            "سکه": "سکه", "خزانه": "سکه", "غذا": "غذا", "جمعیت": "جمعیت",
            "چوب": "چوب", "سنگ": "سنگ", "آهن": "آهن", "اهن": "آهن",
            "پوشاک": "پوشاک", "باروت": "باروت", "اسب": "اسب",
        }.get(rk, rk)
        deltas[dest] = deltas.get(dest, 0) + add
        buff_notes.append(f"رول {dest}{fmt_num(add, signed=True)}")
    for bf in list(entry.get("roll_buffs") or []):
        target = (bf.get("target") or "").strip()
        try:
            pct = float(bf.get("pct") or 0)
        except (TypeError, ValueError):
            continue
        kind = bf.get("kind") or "buff"
        if not target or not pct:
            continue
        sign = -1 if kind == "nerf" else 1
        dest = UP_YIELD_DEST.get(target, target)
        base = _buff_base(target, dest)
        if base <= 0:
            continue
        delta = base * (abs(pct) / 100.0) * sign
        deltas[dest] = deltas.get(dest, 0) + delta
        buff_notes.append(f"رول‌باف {kind} {target} {fmt_num(pct)}%→{dest}{delta:+.1f}")

    # شاپ: بازدهی پک‌ها (عدد داخل پرانتز)
    shop = dict(entry.get("shop") or {})
    if not shop:
        shop = _parse_shop_from_sheet(entry.get("text") or "")
    for item, yv in shop.items():
        try:
            yv = int(round(float(yv)))
        except (TypeError, ValueError):
            continue
        if yv <= 0:
            continue
        deltas[item] = deltas.get(item, 0) + yv
        buff_notes.append(f"شاپ {item}+{yv}")

    # ریست ظرفیت هفتگی تجارتخانه
    entry["trade_cap_used"] = 0
    CITY_ASSETS[city] = entry

    if not deltas:
        save_data(critical=True)
        return f"ℹ️ {city}: بازده قابل‌اعمال نبود · ظرفیت تجارتخانه ریست شد"
    note = "آپ هفتگی"
    if buff_notes:
        note += " · " + "، ".join(buff_notes[:8])
    # بلاک‌لیست فقط ساختمان‌های اقتصادی (کلید بازدهی‌شان ≠ موجودی)
    # کمپ/نیرو/ویژه داینامیک (سواران اسکاتلندی و …) همگی عبور می‌کنند
    _econ_holders = {
        "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        "قلعه", "انبار", "دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی",
        "بازدهی خزانه", "بازدهی بندر", "بازدهی تجارت‌خانه", "بازدهی تجارتخانه",
        "بازدهی آشپزخانه", "بازدهی دهکده",
    }
    filtered = {}
    for dk, dv in deltas.items():
        if dk in _econ_holders or str(dk).startswith("بازدهی") or str(dk).startswith("yield:"):
            continue
        if is_junk_key(dk):
            logging.warning("آپ %s: کلید زباله رد شد: %s", city, dk)
            continue
        try:
            filtered[dk] = filtered.get(dk, 0) + float(dv)
        except (TypeError, ValueError):
            continue
    deltas = filtered

    # اسنپ موجودی همه نیروها (جدول + ویژه شیت + هر چیزی در deltas)
    _res_keys = {
        "سکه", "غذا", "جمعیت", "چوب", "سنگ", "آهن", "پوشاک", "باروت", "اسب", "سربازان",
    }
    _force_names = (
        set(FORCE_UNIT_NAMES)
        | set((SPECIAL_UNITS or {}).keys())
        | {k for k in ymap.keys() if k not in _econ_holders and k not in _res_keys}
        | {k for k in deltas.keys() if k not in _res_keys}
    )
    force_snap = {}
    for fk in _force_names:
        try:
            force_snap[fk] = float(bag.get(fk) or 0)
        except (TypeError, ValueError):
            force_snap[fk] = 0.0
    flags = [] if allow_suspicious else suspicious_deltas(deltas, bag)
    if flags:
        if before_entry is None:
            CITY_ASSETS.pop(city, None)
        else:
            CITY_ASSETS[city] = before_entry
        if before_snap is None:
            UP_SNAPSHOTS.pop(city, None)
        else:
            UP_SNAPSHOTS[city] = before_snap
        return (
            f"{UP_HOLD} {city}: آپ متوقف شد — بازدهی مشکوک (هیچ تغییری اعمال نشد)\n"
            + "\n".join(f"⚠️ {f}" for f in flags)
            + "\nشیت را بررسی کنید؛ اگر درست است، ادمین آپ را تأیید کند."
        )
    log = apply_stat_delta(city, deltas, note=note)
    # اگر به‌اشتباه موجودی کمتر از (قبلی + بازدهی) شد، اصلاح کن
    e_fix = CITY_ASSETS.get(city) or {}
    st_fix = dict(e_fix.get("stats") or {})
    fixed = False
    for fk, snap in force_snap.items():
        try:
            add = float(deltas.get(fk) or 0)
        except (TypeError, ValueError):
            add = 0.0
        if add <= 0 and snap <= 0:
            continue
        expected = snap + max(0.0, add)
        try:
            cur = float(st_fix.get(fk) or 0)
        except (TypeError, ValueError):
            cur = 0.0
        if cur < expected - 0.01:
            st_fix[fk] = expected
            fixed = True
    if fixed:
        st_fix["سربازان"] = float(_sum_force_soldiers(st_fix))
        text_fix = _apply_stock_to_sheet(e_fix.get("text") or "", st_fix)
        e_fix["stats"] = st_fix
        e_fix["text"] = text_fix
        CITY_ASSETS[city] = e_fix
        save_data(critical=True)
    # ثبت درصد باف/نرف جلوی بازدهی ساختمان در شیت (بدون تغییر لول)
    e2 = CITY_ASSETS.get(city) or {}
    if sheet_buff_ann:
        text2 = e2.get("text") or ""
        for bname, spct in sheet_buff_ann:
            text2 = _annotate_yield_pct(text2, bname, spct)
        e2["text"] = text2
    e2["trade_cap_used"] = 0
    CITY_ASSETS[city] = e2
    save_data(critical=True)
    return f"✅ آپ {city}\n{log}\n♻️ ظرفیت تجارتخانه ریست شد"


async def send_up_receipts(city: str, log: str, to_city: bool = True):
    """رسید آپ: گپ شهر + پیوی فرمانده + ادمین. to_city=False → فقط ادمین‌ها (کارنامه جدا رفته)."""
    body = (
        f"🧾 <b>رسید آپ هفتگی</b>\n{DIV}\n"
        f"🏙 <b>{e(city)}</b>\n\n{e(log)}\n\n"
        f"📜 جزئیات در منوی اقتصادی → تغییرات اخیر"
    )
    # گپ‌های ست‌شدهٔ همین شهر
    for gid in (groups_of_city(city) if to_city else []):
        try:
            await bot.send_message(gid, html_cut(body))
        except Exception:
            logging.exception("رسید آپ به گپ %s", gid)
    for uid in (player_ids_for_city(city) if to_city else []):
        try:
            await bot.send_message(uid, html_cut(body))
        except Exception:
            logging.exception("رسید آپ به پلیر %s", uid)
    try:
        await bot.send_message(ADMIN_ID, html_cut(body))
    except Exception:
        logging.exception("رسید آپ به ادمین")
    if app_state.ASSET_ADMIN_ID and app_state.ASSET_ADMIN_ID != ADMIN_ID:
        try:
            await bot.send_message(app_state.ASSET_ADMIN_ID, html_cut(body))
        except Exception:
            pass
