"""تغییر دارایی شهر: ارتقا، تلفات، ویرایش، آنلاک و لاگ تغییرات."""
import logging
import re
from datetime import datetime

from aiogram import types

from app.config import DIV, TZ
from app.state import AUTO_CITIES, CITY_ASSETS, GROUPS, PLAYER_CODES, authenticated_users
from app.utils import _clean_item_name, _norm_country_token, e, fmt_num, normalize_digits, num_plain
from app.factions import all_known_cities, cities_for_side_assets, country_key
from app.storage import save_data
from app.economy.rules import (
    CASTLE_CAPACITY,
    CASTLE_LEVEL_INFO,
    LOCKED_DEFAULT,
    SPECIAL_UNITS,
    UPGRADE_TABLE,
    _RES_MAP,
)
from app.economy.sheet import (
    _apply_stock_to_sheet,
    _format_shop_packs,
    _parse_multi_asset_edit,
    _parse_shop_from_sheet,
    _parse_shop_packs,
    _patch_sheet_level_yield,
    _patch_warehouse_cap,
    _strip_auto_footers,
    _sum_force_soldiers,
    enforce_warehouse_capacity,
    extract_asset_stats,
    get_city_asset_stats,
    normalize_stats_keys,
    parse_roll_buff_form,
    warehouse_capacity_for,
)
from app.economy.costs import (
    _bag_stock,
    cost_for_levels,
    format_cost_dict,
    guess_current_level,
    max_affordable_levels,
)


def is_auto_city(city: str) -> bool:
    """آیا این شهر حالت فول‌اتو دارد؟"""
    if not city:
        return False
    if AUTO_CITIES.get(city):
        return True
    cn = _norm_country_token(city)
    base = cn.split("_")[0] if cn else ""
    for k, v in AUTO_CITIES.items():
        if not v:
            continue
        kn = _norm_country_token(k)
        if kn == cn or (base and kn.split("_")[0] == base):
            return True
        if kn.replace("_", "") == cn.replace("_", ""):
            return True
    return False


def enable_auto_city(city: str) -> None:
    if not city:
        return
    key = city
    cn = _norm_country_token(city)
    for c in list(CITY_ASSETS.keys()) + list(all_known_cities()):
        if _norm_country_token(c) == cn:
            key = c
            break
    for k in list(AUTO_CITIES.keys()):
        if _norm_country_token(k) == _norm_country_token(key):
            AUTO_CITIES.pop(k, None)
    AUTO_CITIES[key] = True


def sum_realm_assets(side: str = None):
    """
    جمع عددی دارایی فقط همان ساید (اگر side داده شود).
    شهرهای ساید دیگر هرگز وارد جمع نمی‌شوند.
    """
    total = {}
    for city in list(CITY_ASSETS.keys()):
        ck = country_key(city)
        if side:
            if ck != side:
                continue
        elif not ck:
            continue
        for name, qty in normalize_stats_keys(get_city_asset_stats(city)).items():
            total[name] = total.get(name, 0) + float(qty)
    return normalize_stats_keys(total)


def realm_breakdown(side: str):
    """
    (total, by_city, city_list) — فقط شهرهای همان ساید.
    by_city: فقط شهرهایی که دارایی ثبت‌شده دارند.
    """
    by_city = {}
    total = {}
    city_list = cities_for_side_assets(side) if side else []
    for city in city_list:
        if country_key(city) != side:
            continue
        if city not in CITY_ASSETS:
            continue
        st = normalize_stats_keys(get_city_asset_stats(city))
        by_city[city] = st
        for name, qty in st.items():
            total[name] = total.get(name, 0) + float(qty)
    return normalize_stats_keys(total), by_city, city_list


def apply_stat_delta(city: str, deltas: dict, note: str = "") -> str:
    """
    اعمال تغییر روی stats + اعداد لیست شیت.
    لاگ فقط در «تغییرات اخیر» می‌رود — ته شیت آلوده نمی‌شود.
    """
    entry = CITY_ASSETS.get(city) or {"text": "", "stats": {}}
    stats = normalize_stats_keys(dict(entry.get("stats") or {}))
    lines_log = []
    for k, delta in deltas.items():
        try:
            dlt = float(delta)
        except (TypeError, ValueError):
            continue
        old = float(stats.get(k) or 0)
        new = old + dlt
        if new < 0:
            new = 0
        stats[k] = new
        lines_log.append(f"{k}: {fmt_num(old)} → {fmt_num(new)} ({fmt_num(dlt, signed=True)})")
    # شمارش سربازان از لیست نیرو — اگر جمع واحدها صفر شد ولی سربازان قبلی بود، حفظ کن
    _prev_sol = float(stats.get("سربازان") or 0)
    _sum_sol = float(_sum_force_soldiers(stats))
    if _sum_sol > 0:
        stats["سربازان"] = _sum_sol
    elif _prev_sol > 0:
        stats["سربازان"] = _prev_sol
    else:
        stats["سربازان"] = 0
    # ظرفیت انبار + سوخت مازاد
    if not stats.get("انبار_سقف"):
        stats["انبار_سقف"] = float(warehouse_capacity_for(city, entry))
    stats, wh_notes = enforce_warehouse_capacity(city, stats)
    for wn in wh_notes:
        lines_log.append(wn)
    text = _strip_auto_footers(entry.get("text") or "")
    text = _apply_stock_to_sheet(text, stats)
    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "unlocked": list(entry.get("unlocked") or []),
        "changes": list(entry.get("changes") or []),
        "yields": dict(entry.get("yields") or {}),
        "levels": dict(entry.get("levels") or {}),
        "shop": dict(entry.get("shop") or {}),
        "shop_packs": list(entry.get("shop_packs") or []),
        "disabled": list(entry.get("disabled") or []),
        "roll_yields": dict(entry.get("roll_yields") or {}),
        "roll_buffs": list(entry.get("roll_buffs") or []),
        "trade_cap_used": entry.get("trade_cap_used") or 0,
    }
    if note or lines_log:
        _append_change(city, (note + " · " if note else "") + "؛ ".join(lines_log[:12]))
    save_data(critical=True)
    return "\n".join(lines_log) or "—"


def free_level_up(city: str, name: str, levels: int = 1):
    """افزایش سطح بدون هزینه (ادمین) — لول و بازدهی جدول روی شیت."""
    levels = max(1, int(levels or 1))
    entry = dict(CITY_ASSETS.get(city) or {})
    lv = dict(entry.get("levels") or {})
    ymap = dict(entry.get("yields") or {})
    cur = int(lv.get(name) or 0)
    new_lv = cur + levels
    lv[name] = new_lv
    entry["levels"] = lv
    tdef = UPGRADE_TABLE.get(name) or {}
    base_y = float(tdef.get("yield") or 0)
    try:
        old_y = float(ymap.get(name) or 0)
    except (TypeError, ValueError):
        old_y = 0.0
    if old_y <= 0 and cur > 0 and base_y:
        old_y = base_y * cur
    if base_y or old_y:
        ymap[name] = old_y + base_y * levels
        entry["yields"] = ymap
        st = dict(entry.get("stats") or {})
        st[f"yield:{name}"] = ymap[name]
        if name in (
            "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
            "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        ):
            st[name] = ymap[name]
            _al = {
                "خزانه": "بازدهی خزانه", "بندر": "بازدهی بندر",
                "تجارتخانه": "بازدهی تجارت‌خانه", "آشپزخانه": "بازدهی آشپزخانه",
                "دهکده": "بازدهی دهکده",
            }
            if name in _al:
                st[_al[name]] = ymap[name]
        entry["stats"] = st
    text = entry.get("text") or ""
    if text and name:
        try:
            ny = float(ymap.get(name) or (old_y + base_y * levels) or 0)
            text = _patch_sheet_level_yield(text, name, new_lv, ny)
            entry["text"] = text
        except Exception:
            logging.exception("free_level patch sheet")
    if name == "انبار":
        cap = warehouse_capacity_for(city, entry)
        st = dict(entry.get("stats") or {})
        st["انبار_سقف"] = float(cap)
        entry["stats"] = st
        if entry.get("text"):
            entry["text"] = _patch_warehouse_cap(entry["text"], st)
    CITY_ASSETS[city] = entry
    _append_change(city, f"افزایش رایگان سطح {name} ×{levels} ({cur}→{new_lv})")
    save_data(critical=True)
    extra = f" · بازدهی {fmt_num(ymap.get(name))}" if ymap.get(name) else ""
    return True, f"✅ <b>{e(name)}</b>: {cur} → <b>{new_lv}</b> (بدون هزینه){extra}"


async def _process_gasset_form(message, kind: str, city: str, txt: str) -> str:
    """پردازش فرم‌های تلفات / افزایش لول / باف / ویرایش از منوی دارایی گپ."""
    txt = normalize_digits((txt or "").strip())
    if kind == "gasset_loss" or (kind == "gasset_edit" and re.search(r"تلفات|کسر", txt)):
        body = re.sub(r"(?i)^\s*ثبت\s*تلفات\s*:?\s*", "", txt).strip()
        stock, yld = _parse_multi_asset_edit("تلفات " + body if "تلفات" not in body else body)
        if not stock and not yld:
            # خطوط: 500 شبه نظامی
            stock = {}
            for line in body.splitlines():
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"(\d+(?:\.\d+)?)\s+(.+)$", line)
                if m:
                    stock[_clean_item_name(m.group(2))] = -abs(float(m.group(1)))
                    continue
                m = re.match(r"(.+?)\s+(\d+(?:\.\d+)?)$", line)
                if m:
                    stock[_clean_item_name(m.group(1))] = -abs(float(m.group(2)))
        if not stock:
            return "❌ تلفاتی تشخیص داده نشد. مثال:\n<code>ثبت تلفات\n500 شبه نظامی\n200 شمشیرزن</code>"
        log = apply_stat_delta(city, stock, note="ثبت تلفات")
        return f"📉 <b>تلفات ثبت شد — {e(city)}</b>\n{DIV}\n{log}"

    if kind == "gasset_lv":
        body = re.sub(r"(?i)^\s*افزایش\s*لول\s*ساختمان\s*:?\s*", "", txt).strip()
        body = re.sub(r"(?i)^\s*افزایش\s*سطح\s*:?\s*", "", body).strip()
        results = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"(.+?)\s+(\d+)\s*$", line)
            if not m:
                results.append(f"❌ خط نامعتبر: {e(line)}")
                continue
            name, lv = m.group(1).strip(), int(m.group(2))
            matched = None
            for k in list(UPGRADE_TABLE.keys()) + list(SPECIAL_UNITS.keys()):
                if k == name or name in k or k in name:
                    matched = k
                    break
            if not matched:
                matched = _clean_item_name(name)
            ok, msg = free_level_up(city, matched, lv)
            results.append(msg if ok else f"❌ {msg}")
        if not results:
            return "❌ چیزی ثبت نشد. مثال:\n<code>افزایش لول ساختمان\nخزانه 1\nچوب بری 2</code>"
        return f"⬆️ <b>افزایش سطح — {e(city)}</b>\n{DIV}\n" + "\n".join(results)

    if kind in ("gasset_buff", "roll_form"):
        data = parse_roll_buff_form(txt)
        block = apply_extra_yields_to_city(city, data)
        return f"✅ باف/نرف/رول برای <b>{e(city)}</b>:\n<pre>{e(block)}</pre>"

    if kind == "gasset_edit":
        stock, yld = _parse_multi_asset_edit(txt)
        parts = []
        if stock:
            parts.append(apply_stat_delta(city, stock, note="ویرایش ادمین"))
        if yld:
            entry = CITY_ASSETS.setdefault(city, {})
            ry = dict(entry.get("roll_yields") or {})
            for k, v in yld.items():
                ry[k] = ry.get(k, 0) + float(v)
            entry["roll_yields"] = ry
            CITY_ASSETS[city] = entry
            save_data(critical=True)
            parts.append("بازدهی: " + ", ".join(f"{k}{fmt_num(v, signed=True)}" for k, v in yld.items()))
        if not parts:
            return "❌ تغییری تشخیص داده نشد."
        return f"✏️ <b>ویرایش — {e(city)}</b>\n{DIV}\n" + "\n".join(parts)
    return "❌ نوع فرم ناشناخته."


def apply_extra_yields_to_city(city: str, data: dict) -> str:
    """ذخیره بازدهی رول/باف در دارایی شهر و پچ شیت."""
    entry = dict(CITY_ASSETS.get(city) or {})
    rolls = dict(entry.get("roll_yields") or {})
    for k, v in (data.get("rolls") or {}).items():
        rolls[k] = rolls.get(k, 0) + float(v)
    for k, v in (data.get("flat") or {}).items():
        rolls[k] = rolls.get(k, 0) + float(v)
    entry["roll_yields"] = rolls
    buffs = list(entry.get("roll_buffs") or [])
    for b in (data.get("buffs") or []):
        buffs.append(dict(b))
    entry["roll_buffs"] = buffs
    # پچ متن شیت — بلوک پایین دارایی
    text = entry.get("text") or ""
    block_lines = ["اعمال بازدهی رول و باف ونرف های شهر:"]
    for k, v in rolls.items():
        block_lines.append(f"بازدهی رول {{{k}}}: {int(v) if float(v)==int(v) else v}")
    for b in buffs:
        sign = "+" if b.get("kind") == "buff" else "-"
        block_lines.append(f"بازدهی {('باف' if b.get('kind')=='buff' else 'نرف')} {num_plain(b.get('pct',0))}%{sign} {b.get('target','')}")
    block = "\n".join(block_lines)
    if "اعمال بازدهی رول و باف ونرف" in text:
        text = re.sub(
            r"اعمال بازدهی رول و باف ونرف های شهر:.*?(?=\n\s*ست شاپ|\n💵|\n#|$)",
            block + "\n",
            text,
            count=1,
            flags=re.S,
        )
    else:
        # قبل از شاپ یا ته شیت
        if "ست شاپ" in text or "💵" in text:
            text = re.sub(r"(ست شاپ|💵💵)", block + r"\n\n\1", text, count=1)
        else:
            text = text.rstrip() + "\n\n" + block + "\n"
    entry["text"] = text
    CITY_ASSETS[city] = entry
    _append_change(city, "ثبت بازدهی رول/باف:\n" + block)
    save_data(critical=True)
    return block


def apply_upgrade_levels(city: str, name: str, levels: int, force: bool = False) -> tuple[bool, str]:
    """
    ارتقا:
    - کسر هزینه از موجودی (سکه/چوب/…)
    - افزایش لول ذخیره‌شده
    - افزایش بازدهی برای آپ بعدی
    force=True برای ادمین حتی بدون اتو.
    """
    if not force and not is_auto_city(city):
        return False, "اتو برای این شهر فعال نیست. ادمین → 🤖 شهرهای اتو"
    t = UPGRADE_TABLE.get(name)
    if not t:
        return False, f"ساختمان «{name}» در جدول نیست."
    if is_building_locked(city, name) and not force:
        return False, f"«{name}» قفل است — اول بازکردن قفل."

    levels = max(1, min(int(levels or 1), int(t.get("max") or 10)))
    # سقف ارتقا بر اساس لول قلعه (اقتصادی و نظامی جدا):
    #   لول۱ → ۱۵ · لول۲ → ۳۰ (+۱۵) · لول۳ → ۴۵ (+۱۵) · لول۴–۵ → نامحدود
    # باف/نرف ارتقا نیستند و از این سقف حساب نمی‌شوند
    # سقف هر بخش جدا: آموزشی / اقتصادی / تولیدی / نظامی
    # قلعه۱ → ۱۵ هر بخش · قلعه۲ → ۳۰ · قلعه۳ → ۴۵ · قلعه۴+ نامحدود
    SEC_EDU = {"دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی"}
    SEC_ECON = {"خزانه", "تجارتخانه", "بندر", "آشپزخانه", "دهکده", "انبار"}
    SEC_PROD = {"چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی"}
    SEC_MIL = {
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی", "اصطبل",
    }
    SEC_LABEL = {
        "edu": "آموزشی", "econ": "اقتصادی", "prod": "تولیدی", "mil": "نظامی",
    }
    if name != "قلعه":
        entry0 = CITY_ASSETS.get(city) or {}
        c_lv = int((entry0.get("levels") or {}).get("قلعه") or 1)
        if c_lv >= 4:
            cap_max = None
        else:
            cap_max = 15 * max(1, min(c_lv, 3))
        if cap_max is not None:
            lvmap = entry0.get("levels") or {}
            sec_key = None
            sec_set = None
            if name in SEC_EDU:
                sec_key, sec_set = "edu", SEC_EDU
            elif name in SEC_ECON:
                sec_key, sec_set = "econ", SEC_ECON
            elif name in SEC_PROD:
                sec_key, sec_set = "prod", SEC_PROD
            elif name in SEC_MIL:
                sec_key, sec_set = "mil", SEC_MIL
            if sec_set is not None:
                total_lv = sum(int(v or 0) for k, v in lvmap.items() if k in sec_set)
                if total_lv + levels > cap_max:
                    lab = SEC_LABEL.get(sec_key, "بخش")
                    return False, (
                        f"سقف <b>{cap_max} لول {lab}</b> (قلعه لول {c_lv}).\n"
                        f"الان این بخش ≈ {total_lv} · ارتقای قلعه سقف را +۱۵ می‌کند "
                        f"(لول۲=۳۰ · لول۳=۴۵ · لول۴+ نامحدود)."
                    )

    entry = CITY_ASSETS.get(city) or {"text": "", "stats": {}, "levels": {}, "yields": {}}
    bag = normalize_stats_keys(dict(entry.get("stats") or get_city_asset_stats(city) or {}))
    # سکه از موجودی خزانه
    if not bag.get("سکه"):
        bag["سکه"] = float(bag.get("موجودی") or 0)

    stock = _bag_stock(bag)
    # اگر سکه در stock صفر است ولی در text هست، از extract دوباره
    if stock.get("coin", 0) <= 0:
        fresh = normalize_stats_keys(extract_asset_stats(entry.get("text") or ""))
        if fresh.get("سکه"):
            bag["سکه"] = float(fresh["سکه"])
            stock = _bag_stock(bag)

    aff = max_affordable_levels(name, stock, city=city)
    if aff < levels:
        if aff <= 0:
            need = format_cost_dict(cost_for_levels(name, 1, city=city))
            return False, (
                f"موجودی کافی نیست.\n"
                f"هزینه ۱ سطح: {need}\n"
                f"سکه الان: {fmt_num(stock.get('coin', 0))}"
            )
        levels = aff

    cd = cost_for_levels(name, levels, city=city)
    # لول فعلی
    lv_map = dict(entry.get("levels") or {})
    ymap = dict(entry.get("yields") or {})
    sheet = entry.get("text") or ""
    cur_lv = lv_map.get(name)
    if cur_lv is None:
        cur_lv = guess_current_level(name, bag, sheet) or 0
    try:
        cur_lv = int(cur_lv)
    except (TypeError, ValueError):
        cur_lv = 0
    max_lv = int(t.get("max") or 10)
    if cur_lv >= max_lv:
        return False, f"«{name}» در لول مکس ({max_lv}) است."
    levels = min(levels, max_lv - cur_lv)
    if levels <= 0:
        return False, "سطحی برای ارتقا نمانده."

    new_lv = cur_lv + levels
    y_each = float(t.get("yield") or 0)
    # کمپ نظامی: بازدهی ≠ تعداد نیرو
    _ECON_BLD = {
        "خزانه", "بندر", "تجارتخانه", "آشپزخانه", "دهکده", "اصطبل",
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
        "قلعه", "انبار", "دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی",
    }
    _MIL_CAMP_NAMES = {
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
        "کلداستریم گارد", "گرنادیر گارد", "رایفلداران اسکاتلندی",
        "کیوراسیرها", "رایفلداران مدرن", "چریک هلندی",
    }
    # ویژه داینامیک: هر نامی که ساختمان اقتصادی نیست و در لیست نیرو/کمپ است
    _is_mil_camp = name in _MIL_CAMP_NAMES or (
        name not in _ECON_BLD
        and any(x in name for x in (
            "نظام", "گارد", "سوار", "پیاده", "رایفل", "شمشیر", "نیزه",
            "افسر", "توپ", "قایق", "کشتی", "ناو", "چریک", "مزدور",
            "گرناد", "کیورا", "رایتر", "امپراط",
        ))
    )
    # بزرگ‌ترین بازدهی واقعی — برای کمپ نظامی stock نیرو را با بازدهی قاطی نکن
    _cands = []
    for _src in (ymap.get(name), bag.get(f"yield:{name}"), bag.get(f"بازدهی {name}")):
        try:
            if _src is not None and float(_src) > 0:
                _cands.append(float(_src))
        except (TypeError, ValueError):
            pass
    if not _is_mil_camp:
        for _src in (bag.get(name),):
            try:
                if _src is not None and float(_src) > 0:
                    _cands.append(float(_src))
            except (TypeError, ValueError):
                pass
    old_y = max(_cands) if _cands else 0.0
    if old_y <= 0 and cur_lv > 0:
        old_y = y_each * cur_lv
    if old_y <= 0:
        old_y = y_each * max(cur_lv, 0)
    new_y = old_y + y_each * levels

    # کسر هزینه — نفر = همان جمعیت
    deltas = {}
    for key, lab in _RES_MAP:
        need = int(cd.get(key) or 0)
        if need <= 0:
            continue
        deltas[lab] = deltas.get(lab, 0) - need

    # اعمال هزینه روی stats
    stats = dict(bag)
    lines_log = []
    for k, dlt in deltas.items():
        old = float(stats.get(k) or 0)
        new = max(0, old + dlt)
        stats[k] = new
        lines_log.append(f"{k}: {fmt_num(old)} → {fmt_num(new)} ({fmt_num(dlt, signed=True)})")

    # لول + بازدهی
    # کمپ نظامی: فقط لول/بازدهی کمپ — تعداد نیرو دست نخورده تا آپ هفتگی
    lv_map[name] = new_lv
    ymap[name] = new_y
    stats[f"yield:{name}"] = new_y
    if _is_mil_camp:
        # stats[name] = موجودی نیرو — عوض نشود
        pass
    else:
        stats[name] = new_y  # ساختمان اقتصادی: بازدهی در stats
        _alias = {
            "خزانه": "بازدهی خزانه",
            "بندر": "بازدهی بندر",
            "تجارتخانه": "بازدهی تجارت‌خانه",
            "آشپزخانه": "بازدهی آشپزخانه",
            "دهکده": "بازدهی دهکده",
        }
        if name in _alias:
            stats[_alias[name]] = new_y
    if name == "قلعه":
        cap = CASTLE_CAPACITY.get(new_lv) or CASTLE_CAPACITY.get(5, 4500)
        stats["ظرفیت قلعه"] = cap
        ymap["قلعه"] = cap
        lines_log.append(f"ظرفیت قلعه → {cap}")
        info = CASTLE_LEVEL_INFO.get(new_lv) or ""
        if info:
            lines_log.append(info)
    if name == "انبار":
        # سقف ظرفیت: ترجیح بازدهی جدول، وگرنه لول×۵۰۰
        wh_cap = int(new_y) if new_y and new_y >= 500 else max(500, new_lv * 500)
        stats["انبار_سقف"] = float(wh_cap)
        stats, whn = enforce_warehouse_capacity(city, stats)
        lines_log.append(f"ظرفیت انبار → {wh_cap}")
        lines_log.extend(whn)

    lines_log.append(f"لول {name}: {cur_lv} → {new_lv}")
    lines_log.append(f"بازدهی {name}: {fmt_num(old_y)} → {fmt_num(new_y)} (+{fmt_num(y_each * levels)})")

    # فقط لیست شیت به‌روز — بدون چسباندن لاگ به ته شیت
    text = _strip_auto_footers(sheet)
    text = _patch_sheet_level_yield(text, name, new_lv, new_y)
    text = _apply_stock_to_sheet(text, stats)

    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "levels": lv_map,
        "yields": ymap,
        "unlocked": list(entry.get("unlocked") or []),
        "changes": list(entry.get("changes") or []),
        "shop": dict(entry.get("shop") or {}),
        "shop_packs": list(entry.get("shop_packs") or []),
        "disabled": list(entry.get("disabled") or []),
        "roll_yields": dict(entry.get("roll_yields") or {}),
        "roll_buffs": list(entry.get("roll_buffs") or []),
        "trade_cap_used": entry.get("trade_cap_used") or 0,
    }
    cost_txt = format_cost_dict(cd)
    detail = (
        f"ارتقا {name} {cur_lv}→{new_lv} · هزینه {cost_txt} · "
        f"بازدهی {fmt_num(old_y)}→{fmt_num(new_y)} · " + "؛ ".join(lines_log[:8])
    )
    _append_change(city, detail)
    save_data(critical=True)
    return True, (
        f"✅ <b>{e(name)}</b>: لول {cur_lv} → <b>{new_lv}</b>\n"
        f"🧮 هزینه: {e(cost_txt)}\n"
        f"◻️ بازدهی: {fmt_num(old_y)} → <b>{fmt_num(new_y)}</b>\n"
        + "\n".join(lines_log)
        + "\n\n📜 جزئیات در «تغییرات اخیر»"
    )


def trade_house_capacity(city: str) -> int:
    """سقف هفتگی تجارتخانه — از شیت (محدودیت سکه) یا پیش‌فرض بر اساس لول."""
    entry = CITY_ASSETS.get(city) or {}
    bag = entry.get("stats") or {}
    # عدد نوشته‌شده در شیت اولویت دارد
    try:
        cap = float(bag.get("محدودیت_سکه") or 0)
        if cap > 0:
            return int(cap)
    except (TypeError, ValueError):
        pass
    lv = int((entry.get("levels") or {}).get("تجارتخانه") or 0)
    if lv <= 0:
        y = float(bag.get("تجارتخانه") or bag.get("بازدهی تجارت‌خانه") or 0)
        lv = max(1, int(y // 150) if y else 1)
    return 3000 + max(0, lv - 1) * 500


def trade_house_remaining(city: str) -> int:
    entry = CITY_ASSETS.get(city) or {}
    used = int(entry.get("trade_cap_used") or 0)
    return max(0, trade_house_capacity(city) - used)


def consume_trade_house_cap(city: str, amount: float) -> tuple[bool, str]:
    """کسر از ظرفیت هفتگی تجارتخانه."""
    amount = abs(float(amount or 0))
    if amount <= 0:
        return True, ""
    rem = trade_house_remaining(city)
    if amount > rem + 1e-6:
        return False, f"ظرفیت هفتگی تجارتخانه کافی نیست (باقی‌مانده: {fmt_num(rem)})."
    entry = CITY_ASSETS.setdefault(city, {})
    entry["trade_cap_used"] = int(entry.get("trade_cap_used") or 0) + int(round(amount))
    CITY_ASSETS[city] = entry
    return True, f"ظرفیت تجارتخانه −{int(round(amount))} (باقی: {trade_house_remaining(city)})"


def release_trade_house_cap(city: str, amount: float) -> None:
    """برگرداندن ظرفیت کسرشده (مثلاً وقتی پست کانال شکست خورد)."""
    amount = int(round(abs(float(amount or 0))))
    entry = CITY_ASSETS.get(city)
    if not amount or entry is None:
        return
    entry["trade_cap_used"] = max(0, int(entry.get("trade_cap_used") or 0) - amount)


def _city_change_log(city: str) -> list:
    entry = CITY_ASSETS.get(city) or {}
    return list(entry.get("changes") or [])[-15:]


def _append_change(city: str, line: str):
    entry = CITY_ASSETS.setdefault(city, {"text": "", "stats": {}, "changes": []})
    ch = list(entry.get("changes") or [])
    stamp = datetime.now(TZ).strftime("%m-%d %H:%M") if TZ else datetime.now().strftime("%m-%d %H:%M")
    ch.append(f"[{stamp}] {line}")
    entry["changes"] = ch[-40:]
    CITY_ASSETS[city] = entry


async def _commit_shop_text(message: types.Message, city: str, body: str):
    packs = _parse_shop_packs("شاپ:\n" + body)
    shop = _parse_shop_from_sheet("شاپ:\n" + body)
    entry = CITY_ASSETS.setdefault(city, {"text": "", "stats": {}, "shop": {}, "shop_packs": []})
    entry["shop"] = shop
    entry["shop_packs"] = packs
    text = _strip_auto_footers(entry.get("text") or "")
    text = re.sub(r"\n*💵+.*$", "", text, flags=re.S)
    text = re.sub(r"\n*شاپ\s*:.*$", "", text, flags=re.I | re.S)
    pretty = _format_shop_packs(packs) if packs else body
    text = text.rstrip() + "\n\n💵💵💵💵\nشاپ :\n" + pretty
    entry["text"] = text
    CITY_ASSETS[city] = entry
    _append_change(city, f"ست شاپ ({len(packs)} پک)")
    save_data(critical=True)
    lines = [f"🛒 <b>شاپ {e(city)}</b> — {len(packs)} پک ثبت شد\n{DIV}"]
    for pk in packs:
        k = pk.get("kind")
        if k == "minister":
            lines.append(f"🤵 وزیر: <b>{e(pk.get('name'))}</b>")
        elif k == "hero":
            lines.append(f"🥷 هیرو: <b>{e(pk.get('name'))}</b> · ارتش {len(pk.get('army') or [])} خط")
        elif k == "merc_group":
            lines.append(f"🛡 گروهک: {e(pk.get('unit'))} × {pk.get('count') or 0}")
        elif k in ("merc", "spy", "guard"):
            lines.append(
                f"• {e(pk.get('unit'))}: تعداد {pk.get('count') or 0} · بازدهی {pk.get('yield') or 0}"
            )
        else:
            y = pk.get("yield") or 0
            lines.append(f"• {e(pk.get('name'))}" + (f" → آپ +{y}" if y else ""))
    if shop:
        lines.append(f"\n📊 بازدهی آپ: {len(shop)} مورد")
    await message.answer("\n".join(lines))


def _locked_units(city: str) -> list:
    """لیست مرتب‌شده (ترتیب ثابت) — ایندکس دکمه‌های unlock:do به همین لیست اشاره می‌کند."""
    return sorted(n for n in LOCKED_DEFAULT if is_building_locked(city, n))


def transfer_city(src: str, dst: str) -> str:
    """انتقال دارایی و بازیکنان از src به dst (نام شهر مقصد)."""
    src_n = None
    for c in all_known_cities():
        if _norm_country_token(c) == _norm_country_token(src) or c.lower() == src.lower():
            src_n = c
            break
    if not src_n:
        src_n = src
    # دارایی
    if src_n in CITY_ASSETS:
        CITY_ASSETS[dst] = CITY_ASSETS.pop(src_n)
    # کدها
    for code, name in list(PLAYER_CODES.items()):
        if _norm_country_token(name) == _norm_country_token(src_n):
            PLAYER_CODES[code] = dst
    # کاربران
    for uid, u in authenticated_users.items():
        if _norm_country_token(u.get("country") or "") == _norm_country_token(src_n):
            u["country"] = dst
    # گروه‌ها
    for gid, g in GROUPS.items():
        if _norm_country_token(g.get("city") or "") == _norm_country_token(src_n):
            g["city"] = dst
    # اتو
    if is_auto_city(src_n):
        AUTO_CITIES.pop(src_n, None)
        AUTO_CITIES[dst] = True
    save_data(critical=True)
    return f"✅ واگذاری: <b>{e(src_n)}</b> → <b>{e(dst)}</b>"

def is_building_locked(city: str, name: str) -> bool:
    """
    قفل یونیت/کمپ برای همین شهر:
    1) unlocked → باز
    2) 🔒 فقط روی همان نام کامل (نه زیررشته شمشیرزن داخل سواره نظام شمشیرزن)
    3) لول/بازدهی/موجودی بدون 🔒 → باز
    4) LOCKED_DEFAULT → قفل
    """
    if not name:
        return False
    entry = CITY_ASSETS.get(city) or {}
    unlocked = set(entry.get("unlocked") or [])
    if name in unlocked:
        return False
    text = entry.get("text") or ""
    has_lock_mark = False
    has_line = False
    cell_pat = re.compile(rf"\|\s*{re.escape(name)}\s*\|", re.I)
    if text and name:
        for ln in text.splitlines():
            if not cell_pat.search(ln):
                continue
            has_line = True
            if "🔒" in ln:
                has_lock_mark = True
                break
            if "🔓" in ln:
                return False
    if has_lock_mark:
        return True
    lv = (entry.get("levels") or {}).get(name)
    yv = (entry.get("yields") or {}).get(name)
    st = (entry.get("stats") or {}).get(name) or (entry.get("stats") or {}).get(f"yield:{name}")
    try:
        if lv is not None and int(lv) > 0:
            return False
        if yv is not None and float(yv) > 0:
            return False
        if st is not None and float(st) > 0 and has_line:
            return False
    except (TypeError, ValueError):
        pass
    return name in LOCKED_DEFAULT
