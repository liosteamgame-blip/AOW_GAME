"""مشاور ارتقا (محلی + xAI)."""
import re
import zlib

from app.config import ADVISE_MODES, DIV, UPGRADE_FORM_TEMPLATE, XAI_API_KEY
from app.ai import ask as ai_ask, cache_key as ai_cache_key
from app.utils import e, fmt_num
from app.economy.rules import FOOD_PER, UPGRADE_TABLE, _RES_MAP, _RULES_DIGEST
from app.economy.sheet import get_city_asset_stats, get_city_asset_text, normalize_stats_keys
from app.economy.costs import (
    _bag_stock,
    _can_afford,
    _fmt_upgrade_cost,
    cost_for_levels,
    format_cost_dict,
    guess_current_level,
    max_affordable_levels,
)
from app.economy.views import format_stats_labeled


def local_upgrade_advice(city: str, bag: dict) -> str:
    """تحلیل هزینه/بازده طبق قوانین رسمی خاکستر جنگ."""
    bag = normalize_stats_keys(bag or {})
    coins = float(bag.get("سکه") or 0)
    food = float(bag.get("غذا") or 0)
    pop = float(bag.get("جمعیت") or 0)
    iron = float(bag.get("آهن") or bag.get("اهن") or 0)
    powder = float(bag.get("باروت") or 0)
    authority = float(bag.get("اقتدار") or 40)

    prod = {
        "چوب بری": float(bag.get("چوب بری") or 0),
        "معدن سنگ": float(bag.get("معدن سنگ") or 0),
        "معدن آهن": float(bag.get("معدن آهن") or 0),
        "باروت سازی": float(bag.get("باروت سازی") or 0),
        "پوشاک سازی": float(bag.get("پوشاک سازی") or 0),
    }
    inf_units = {
        "شبه نظامی": float(bag.get("شبه نظامی") or 0),
        "شمشیرزن": float(bag.get("شمشیرزن") or 0),
        "نیزه دار": float(bag.get("نیزه دار") or bag.get("نیزه‌دار") or 0),
        "رایفلدار": float(bag.get("رایفلدار") or 0),
        "افسر": float(bag.get("افسر") or 0),
    }
    cav_units = {
        "سواره نظام شمشیرزن": float(bag.get("سواره نظام شمشیرزن") or bag.get("سواره‌نظام شمشیرزن") or 0),
        "سواره‌نظام زره پوش": float(bag.get("سواره‌نظام زره پوش") or bag.get("سواره نظام زره پوش") or 0),
        "سواره‌نظام تفنگدار": float(bag.get("سواره‌نظام تفنگدار") or bag.get("سواره نظام تفنگدار") or 0),
    }
    infantry = sum(inf_units.values()) + float(bag.get("سربازان") or 0)
    cavalry = sum(cav_units.values()) + float(bag.get("کیوراسیرها") or 0)
    elite = float(bag.get("کیوراسیرها") or 0) + float(bag.get("رایفلداران مدرن") or 0)
    arty = sum(float(bag.get(k) or 0) for k in ("توپ سبک", "توپ سنگین", "توپ محاصره", "توپ خمپاره ای"))
    navy = sum(float(bag.get(k) or 0) for k in ("قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی", "کشتی خط شکن"))

    # مصرف غذا تقریبی هفته‌ای (قوانین)
    food_need = pop + infantry * FOOD_PER["inf"] + cavalry * FOOD_PER["cav"] + elite * FOOD_PER["elite"]

    tips = []

    # اقتدار
    if authority < 20:
        tips.append((
            "👑 اقتدار بحرانی (۰–۲۰)",
            "مردم خواهان برکناری‌اند و در ارتش شورش محتمل است.",
            "اولویت: رول مردمی/پاداش نظامی · پیروزی کوچک · جلوگیری از باخت پی‌درپی",
        ))
    elif authority < 40:
        tips.append((
            "👑 اقتدار شکننده (۲۰–۴۰)",
            "مردم منتظر جرقه شورش‌اند؛ روحیه ارتش پایین.",
            "پاداش مردم‌پسند + رول اجتماعی · هزینه کم · بازده ثبات داخلی",
        ))

    # خزانه
    if coins < UPGRADE_TABLE["خزانه"]["coin"]:
        tips.append((
            "💰 نقدینگی برای ارتقای خزانه کافی نیست",
            f"برای ۱ سطح خزانه نیاز به {_fmt_upgrade_cost('خزانه', city)}.",
            "فروش مازاد به تجار (دوشنبه) یا تمرکز بازدهی بندر/تجارتخانه",
        ))
    elif coins >= 1500 and float(bag.get("بازدهی خزانه") or 0) < 2000:
        ok = "✅" if _can_afford(bag, "خزانه", city) else "⚠️ مواد کم"
        tips.append((
            f"🏦 ارتقای خزانه {ok}",
            f"هزینه: {_fmt_upgrade_cost('خزانه', city)}",
            "بازده پایدار سکه — اولویت اقتصادی بلندمدت",
        ))

    # غذا
    if food_need > 0 and food < food_need * 1.5:
        ok = "✅" if _can_afford(bag, "آشپزخانه", city) else "⚠️"
        tips.append((
            f"🍽 فشار غذایی {ok}",
            f"مصرف تقریبی نیرو+جمعیت ≈ {fmt_num(food_need)} · موجودی غذا: {fmt_num(food)}",
            f"ارتقای آشپزخانه: {_fmt_upgrade_cost('آشپزخانه', city)} · در محاصره مصرف×۲ است",
        ))

    # تولید ضعیف
    for pname, pval in sorted(prod.items(), key=lambda x: x[1]):
        if pval >= 200:
            continue
        t = UPGRADE_TABLE.get(pname, {})
        if not t:
            continue
        afford = _can_afford(bag, pname, city)
        tips.append((
            f"🏗 {pname} ضعیف (≈{fmt_num(pval)})",
            f"هزینه ۱ سطح: {_fmt_upgrade_cost(pname, city)} · {'موجودی کافی' if afford else 'کمبود منابع/سکه'}",
            f"بازده +{t.get('yield', 100)} {t.get('yunit', '')}/سطح · مکس لول {t.get('max', 10)}",
        ))
        break  # فقط ضعیف‌ترین

    if iron < 150 and (infantry > 400 or arty > 0):
        tips.append((
            "🔩 کمبود آهن",
            f"موجودی آهن {fmt_num(iron)} — ارتش/توپ وابسته به آهن است.",
            f"معدن آهن: {_fmt_upgrade_cost('معدن آهن', city)}",
        ))
    if powder < 80 and (arty > 0 or inf_units.get("رایفلدار", 0) > 50):
        tips.append((
            "💥 کمبود باروت",
            f"باروت {fmt_num(powder)} برای رایفل/توپ کافی نیست.",
            f"باروت‌سازی: {_fmt_upgrade_cost('باروت سازی', city)}",
        ))

    # نظامی — نسبت‌ها
    if infantry > 300 and cavalry < max(50, infantry * 0.12):
        tips.append((
            "🐴 کمبود سواره",
            f"پیاده≈{fmt_num(infantry)} · سواره≈{fmt_num(cavalry)}",
            f"کمپ سواره شمشیرزن: {_fmt_upgrade_cost('سواره نظام شمشیرزن', city)}",
        ))
    if arty == 0 and infantry >= 500:
        tips.append((
            "🧨 نبود توپخانه",
            "برای محاصره حداقل ۵۰۰ نیرو + ۵ ادوات لازم است (قوانین).",
            f"توپ سبک: {_fmt_upgrade_cost('توپ سبک', city)} · یا توپ محاصره: {_fmt_upgrade_cost('توپ محاصره', city)}",
        ))
    if navy == 0:
        tips.append((
            "⚓️ ناوگان خالی",
            "بدون کشتی، لشکرکشی/تجارت دریایی محدود است. ظرفیت بندر: ۱۵ کشتی.",
            f"قایق: {_fmt_upgrade_cost('قایق', city)} · کشتی جنگی: {_fmt_upgrade_cost('کشتی جنگی', city)}",
        ))

    # تقویم بازی
    tips.append((
        "📅 یادآوری تقویم",
        "تجارت پلیر: شنبه–یکشنبه · تجار: دوشنبه · ارتقا/ساخت: سه‌شنبه–چهارشنبه · آپ: پنجشنبه–جمعه (ممنوع نظامی).",
        "فرم ارتقا را فقط در روز مجاز بفرستید.",
    ))

    if not any(t[0].startswith(("💰", "🏦", "🍽", "🏗", "🔩", "💥", "🐴", "🧨", "⚓️", "👑")) for t in tips[:-1]):
        tips.insert(0, (
            "✅ وضعیت نسبتاً پایدار",
            "کمبود بحرانی دیده نشد.",
            "تمرکز: فناوری (دانشکده/نخبگان) و ذخیره باروت–آهن",
        ))

    lines = [
        f"🧠 <b>مشاور ارتقا — {e(city)}</b>",
        "<i>طبق قوانین رسمی خاکستر جنگ · هزینه و بازده واقعی</i>",
        DIV,
        f"💰 سکه <b>{fmt_num(coins)}</b> · 🍽 غذا <b>{fmt_num(food)}</b> · 👥 جمعیت <b>{fmt_num(pop)}</b>",
        f"🛡 پیاده≈<b>{fmt_num(infantry)}</b> · 🐴 سواره≈<b>{fmt_num(cavalry)}</b> · 🧨 توپ≈<b>{fmt_num(arty)}</b> · ⚓️ ناو≈<b>{fmt_num(navy)}</b>",
        f"👑 اقتدار: <b>{fmt_num(authority)}</b> · مصرف‌غذای تقریبی: <b>{fmt_num(food_need)}</b>",
        "",
    ]
    for i, (title, why, advise) in enumerate(tips[:7], 1):
        lines.append(f"<b>{i}. {title}</b>\n{why}\n➡️ {advise}\n")
    lines.append(
        f"{DIV}\n"
        "<i>تحلیل محلی بر اساس جدول ارتقای رسمی. با XAI_API_KEY تحلیل Grok هم اضافه می‌شود.</i>"
    )
    return "\n".join(lines)


def parse_upgrade_requests(notes: str) -> list:
    """
    از متن پلیر درخواست‌ها را می‌خواند.
    مثال: «بندر ۳ لول»، «خزانه را ۲ تا ببر»، «چوب بری و معدن آهن»
    """
    if not notes:
        return []
    text = notes
    found = []
    # نام‌ها از طولانی به کوتاه تا تداخل کمتر شود
    names = sorted(UPGRADE_TABLE.keys(), key=len, reverse=True)
    for name in names:
        if name not in text and name.replace("‌", "") not in text.replace("‌", ""):
            # جستجوی ساده‌تر بدون نیم‌فاصله
            if name.replace(" ", "") not in text.replace(" ", "").replace("‌", ""):
                continue
        # سطح خواسته‌شده کنار نام
        levels = 1
        m = re.search(
            rf"{re.escape(name)}[^\d]{{0,12}}(\d+)\s*(?:لول|سطح|تا|level)?",
            text,
            re.I,
        )
        if not m:
            m = re.search(
                rf"(\d+)\s*(?:لول|سطح)?[^\n]{{0,12}}{re.escape(name)}",
                text,
                re.I,
            )
        if m:
            try:
                levels = max(1, min(10, int(m.group(1))))
            except ValueError:
                levels = 1
        found.append({"name": name, "levels": levels})
    # یکتا
    seen, out = set(), []
    for f in found:
        if f["name"] in seen:
            continue
        seen.add(f["name"])
        out.append(f)
    return out


def _mode_candidates(mode: str, bag: dict) -> list:
    """لیست نام ساختمان‌های مرتبط با نوع مشاور + اولویت."""
    bag = normalize_stats_keys(bag or {})
    cand = []
    prod = ["چوب بری", "معدن سنگ", "معدن آهن", "باروت سازی", "پوشاک سازی"]
    weak = sorted(prod, key=lambda n: float(bag.get(n) or 0))

    if mode in ("econ", "balance", "chat"):
        cand += ["خزانه", "تجارتخانه", "آشپزخانه", "دهکده", "انبار"] + weak
    if mode in ("mil", "land", "balance", "chat"):
        cand += ["شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
                 "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "توپ سبک", "توپ محاصره"]
    if mode in ("naval", "balance", "chat"):
        cand += ["بندر", "قایق", "کشتی جنگی", "ناو جنگی"]
    if mode == "land":
        cand += ["نیزه دار", "توپ محاصره", "توپ سنگین"]
    # یکتا با حفظ ترتیب
    seen, out = set(), []
    for n in cand:
        if n in UPGRADE_TABLE and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _roi_score(name: str, levels: int, mode: str) -> float:
    """امتیاز بازده تقریبی برای اولویت‌بندی."""
    t = UPGRADE_TABLE.get(name) or {}
    y = float(t.get("yield") or 1) * levels
    coin_cost = max(1, int(t.get("coin") or 1) * levels)
    base = y / coin_cost * 1000
    boost = {
        "econ": {"خزانه": 1.4, "چوب بری": 1.2, "معدن آهن": 1.25, "آشپزخانه": 1.15, "تجارتخانه": 1.1},
        "mil": {"توپ سبک": 1.4, "شمشیرزن": 1.2, "رایفلدار": 1.25, "سواره نظام شمشیرزن": 1.2},
        "land": {"توپ محاصره": 1.5, "نیزه دار": 1.2, "شمشیرزن": 1.15},
        "naval": {"کشتی جنگی": 1.4, "بندر": 1.3, "ناو جنگی": 1.35, "قایق": 1.1},
        "balance": {"خزانه": 1.2, "بندر": 1.15, "توپ سبک": 1.15, "معدن آهن": 1.1},
        "chat": {},
    }.get(mode, {})
    return base * boost.get(name, 1.0)


def build_optimal_plan(
    bag: dict,
    mode: str = "balance",
    notes: str = "",
    sheet: str = "",
    city: str = "",
    seed: int = 0,
) -> list:
    """
    بهترین پلن با منابع محدود.
    - درخواست صریح پلیر را اولویت می‌دهد
    - تا ۳ لول روی یک ساختمان اگر بودجه اجازه دهد
    - برای هر شهر/پلیر کمی متنوع (seed)
    دارایی را تغییر نمی‌دهد — فقط محاسبه.
    """
    stock = _bag_stock(bag)
    requests = parse_upgrade_requests(notes)
    plan = []

    def try_add(name, levels, forced=False):
        t = UPGRADE_TABLE.get(name)
        if not t:
            return False
        mx = int(t.get("max") or 10)
        cur = guess_current_level(name, bag, sheet)
        # سقف تا مکس لول
        if cur is not None:
            levels = min(levels, max(0, mx - cur))
        levels = max(0, min(levels, mx))
        if levels <= 0:
            return False
        # اگر forced نیست، تا حد قابل‌پرداخت کم کن
        aff = max_affordable_levels(name, stock, city=city or None)
        if aff <= 0:
            return False
        if not forced:
            levels = min(levels, aff)
        else:
            # forced: اگر کامل نمی‌شود، حداکثر ممکن
            levels = min(levels, aff) if aff else 0
        if levels <= 0:
            return False
        cd = cost_for_levels(name, levels, city=city or None)
        # کم کردن از موجودی مجازی
        for key, _ in _RES_MAP:
            need = cd.get(key, 0)
            if need:
                stock[key] = float(stock.get(key) or 0) - need
        from_lv = cur if cur is not None else "?"
        to_lv = (cur + levels) if cur is not None else f"?+{levels}"
        y_each = t.get("yield") or 0
        y_final = f"+{y_each * levels} {t.get('yunit', '')} (هر سطح +{y_each})"
        plan.append({
            "name": name,
            "from_lv": from_lv,
            "to_lv": to_lv,
            "levels": levels,
            "cost": format_cost_dict(cd),
            "cost_dict": cd,
            "yield_final": y_final,
            "reason": "درخواست شما" if forced else "بهینه منابع",
            "score": _roi_score(name, levels, mode),
        })
        return True

    # ۱) درخواست‌های صریح پلیر
    for req in requests:
        try_add(req["name"], req.get("levels") or 1, forced=True)

    # ۲) پیشنهاد خودکار تا پر شدن بودجه معنادار
    cands = _mode_candidates(mode, bag)
    # تنوع بر اساس seed (شهر + حالت)
    if seed:
        cands = cands[seed % max(1, len(cands)):] + cands[: seed % max(1, len(cands))]
    already = {p["name"] for p in plan}
    for name in cands:
        if name in already:
            continue
        if len(plan) >= 4:
            break
        aff = max_affordable_levels(name, stock, city=city or None)
        if aff <= 0:
            continue
        # چند سطح؟ ۱ تا ۳ بر اساس ROI و موجودی
        best_l, best_s = 1, -1
        for L in range(1, min(3, aff) + 1):
            sc = _roi_score(name, L, mode)
            # جریمه جزئی برای قفل کردن بودجه زیاد
            sc -= L * 0.02
            if sc > best_s:
                best_s, best_l = sc, L
        # ساختمان‌های حیاتی ضعیف → تا ۳ لول
        if name in ("چوب بری", "معدن آهن", "باروت سازی", "خزانه", "بندر") and aff >= 2:
            if float(bag.get(name) or 0) < 200 or name in ("خزانه", "بندر"):
                best_l = min(3, aff)
        try_add(name, best_l, forced=False)
        already.add(name)

    # اگر هیچی نتوانست: حداقل ۱ سطح ارزان‌ترین
    if not plan:
        cheap = sorted(
            UPGRADE_TABLE.items(),
            key=lambda kv: int(kv[1].get("coin") or 9999),
        )
        for name, _t in cheap:
            if try_add(name, 1):
                break
    return plan


def format_plan_summary(plan: list, bag: dict) -> str:
    stock = _bag_stock(bag)
    lines = [
        "📊 <b>موجودی قابل‌مصرف (قبل از ارتقا)</b>",
        f"💰 {fmt_num(stock['coin'])} · 🪵 {fmt_num(stock['wood'])} · 🪨 {fmt_num(stock['stone'])} · 🔩 {fmt_num(stock['iron'])}",
        f"🧥 {fmt_num(stock['cloth'])} · 💥 {fmt_num(stock['powder'])} · 👥 {fmt_num(stock['pop'])}",
        "",
        "🧩 <b>بهترین پلن با منابع محدود</b> <i>(فقط پیشنهاد — دارایی تغییر نمی‌کند)</i>",
        DIV,
    ]
    total = {k: 0 for k, _ in _RES_MAP}
    for i, p in enumerate(plan, 1):
        lines.append(
            f"<b>{i}. {e(p['name'])}</b> · {p['from_lv']} → <b>{p['to_lv']}</b> "
            f"({p['levels']} سطح)\n"
            f"   🧮 {e(p['cost'])}\n"
            f"   ◻️ {e(p['yield_final'])}\n"
            f"   <i>{e(p.get('reason') or '')}</i>"
        )
        for k, _ in _RES_MAP:
            total[k] += int((p.get("cost_dict") or {}).get(k) or 0)
    cost_txt = format_cost_dict({k: v for k, v in total.items() if v})
    lines.append(f"\n{DIV}\nΣ هزینه کل پلن: <b>{e(cost_txt)}</b>")
    remain = []
    for key, lab in _RES_MAP:
        left = float(stock.get(key) or 0) - total.get(key, 0)
        if stock.get(key) or total.get(key):
            remain.append(f"{lab} {fmt_num(left)}")
    if remain:
        lines.append("پس از اجرا (فرضی): " + " · ".join(remain))
    return "\n".join(lines)


def build_upgrade_forms(suggestions: list) -> str:
    if not suggestions:
        return ""
    blocks = [
        "📋 <b>فرم‌های ارتقا</b> — از لول = <i>لول کنونی</i> · به لول = <i>لول دلخواه</i>",
        DIV,
    ]
    for s in suggestions:
        form = UPGRADE_FORM_TEMPLATE.format(
            name=s.get("name", "—"),
            from_lv=s.get("from_lv", "?"),
            to_lv=s.get("to_lv", "?"),
            cost=s.get("cost", "—"),
            yield_final=s.get("yield_final", "—"),
        )
        blocks.append(f"<pre>{e(form)}</pre>")
    return "\n\n".join(blocks)


def local_upgrade_advice_mode(
    city: str,
    bag: dict,
    mode: str = "balance",
    notes: str = "",
    sheet: str = "",
    user_id: int = 0,
) -> str:
    """تحلیل + پلن بهینه منابع + فرم‌های چندسطحی."""
    mode_meta = ADVISE_MODES.get(mode, ADVISE_MODES["balance"])
    seed = (zlib.crc32(((city or "") + mode).encode("utf-8")) + int(user_id or 0)) % 97
    plan = build_optimal_plan(bag, mode=mode, notes=notes, sheet=sheet, city=city, seed=seed)

    header = (
        f"🧠 <b>مشاور حرفه‌ای ارتقا — {e(city)}</b>\n"
        f"🎯 نوع: {mode_meta[0]} <b>{mode_meta[1]}</b>\n"
    )
    if notes:
        header += f"📝 درخواست/پلن: <i>{e(notes[:450])}</i>\n"
    header += (
        f"{DIV}\n"
        f"<i>از لول = لول کنونی · به لول = لول هدف · هزینه = مجموع سطوح</i>\n\n"
    )

    # نکات کلی (کوتاه)
    tips = local_upgrade_advice(city, bag)
    # فقط ۳ خط اول آمار از tips
    tip_lines = tips.split("\n")[:8]
    summary = format_plan_summary(plan, bag)
    forms = build_upgrade_forms(plan)

    extras = []
    if plan:
        max_one = max(plan, key=lambda p: p.get("levels", 1))
        if max_one.get("levels", 1) >= 2:
            extras.append(
                f"💡 روی <b>{e(max_one['name'])}</b> ارتقای "
                f"<b>{max_one['levels']}</b> سطحی پیشنهاد شد (بودجه اجازه داد)."
            )
    if notes and not parse_upgrade_requests(notes):
        extras.append(
            "ℹ️ در پیام‌تان نام ساختمان مشخص نبود؛ پلن خودکار چیده شد. "
            "مثال: «بندر را ۳ لول ببر و خزانه ۲ لول»"
        )

    return (
        header
        + "\n".join(tip_lines)
        + "\n\n"
        + summary
        + ("\n" + "\n".join(extras) if extras else "")
        + "\n\n"
        + forms
    )


async def xai_upgrade_advice(
    city: str,
    bag: dict,
    sheet_excerpt: str = "",
    mode: str = "balance",
    notes: str = "",
    plan: list | None = None,
) -> str | None:
    if not XAI_API_KEY:
        return None
    stats_txt = format_stats_labeled(bag) if bag else "—"
    mode_fa = ADVISE_MODES.get(mode, ADVISE_MODES["balance"])[1]
    plan_txt = ""
    if plan:
        for p in plan:
            plan_txt += (
                f"- {p['name']}: از {p['from_lv']} به {p['to_lv']} | "
                f"هزینه {p['cost']} | بازده {p['yield_final']}\n"
            )
    prompt = (
        "تو مشاور ارشد ارتقای بازی «خاکستر جنگ» هستی. "
        f"تمرکز: {mode_fa}. "
        "پلن محاسبه‌شده زیر را بررسی کن، اگر بهتر می‌شود اصلاح کن، و برای هر مورد "
        "فرم را با قالب زیر بده. از لول=لول کنونی، به لول=لول هدف. "
        "می‌توانی ۲ یا ۳ سطح یکجا پیشنهاد بدهی اگر بودجه برسد. "
        "دارایی را تغییر نده — فقط پیشنهاد. فارسی رسمی مختصر.\n\n"
        "قالب:\n#فرم_ارتقا\n🏢نام ساختمان:\n🔹از لول:\n🔹به لول:\n🧮هزینه ارتقا:\n◻️بازدهی نهایی:\n\n"
        f"قوانین:\n{_RULES_DIGEST}\n\n"
        f"شهر: {city}\nآمار:\n{stats_txt}\n\n"
        f"پلن موتور محلی:\n{plan_txt or '—'}\n"
    )
    if notes:
        prompt += f"\nدرخواست بازیکن:\n{notes[:600]}\n"
    if sheet_excerpt:
        prompt += f"\nگزیده شیت:\n{sheet_excerpt[:800]}"
    system = (
        "Ashes of War senior upgrade planner. "
        "Output optimized multi-level plans and filled #فرم_ارتقا. "
        "Never invent costs; use provided table. Persian."
    )
    key = ai_cache_key("advise", city, mode, notes, plan_txt, stats_txt)
    content, note = await ai_ask(key, system, prompt)
    if not content:
        return f"🤖 <i>{e(note)}</i>"
    return f"🤖 <b>بازنگری Grok — {e(city)}</b> · {e(mode_fa)}\n{DIV}\n{e(content)}\n\n<i>{e(note)}</i>"


async def build_upgrade_advice(
    city: str,
    mode: str = "balance",
    notes: str = "",
    user_id: int = 0,
    use_ai: bool = False,
) -> str:
    """تحلیل محلی؛ گروک فقط وقتی use_ai=True (کاربر دکمه «بازنگری گروک» را زده)."""
    bag = normalize_stats_keys(get_city_asset_stats(city))
    sheet = get_city_asset_text(city) or ""
    seed = (zlib.crc32(((city or "") + mode).encode("utf-8")) + int(user_id or 0)) % 97
    plan = build_optimal_plan(bag, mode=mode, notes=notes, sheet=sheet, city=city, seed=seed)
    local = local_upgrade_advice_mode(
        city, bag, mode=mode, notes=notes, sheet=sheet, user_id=user_id,
    )
    if not use_ai:
        return local
    ai = await xai_upgrade_advice(city, bag, sheet, mode=mode, notes=notes, plan=plan)
    if ai:
        return f"{local}\n\n{DIV}\n{ai}"
    return local
