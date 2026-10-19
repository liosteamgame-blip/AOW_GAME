"""نمایش دارایی و لیدربورد قدرت."""
import re

from app.config import DIV
from app.state import CITY_ASSETS, SETTINGS
from app.utils import e, fmt_num
from app.factions import FACTIONS, FACTION_META, country_key
from app.economy.sheet import get_city_asset_stats, get_city_asset_text, normalize_stats_keys
from app.economy.assets import realm_breakdown
from app.castles import castle_trait_block


# گروه‌بندی نمایش اعداد استخراج‌شده — جلوی هر بخش معنی مشخص است
_STATS_SECTIONS = [
    ("👤 شخصیت / جمعیت", (
        "اقتدار", "مشروعیت", "جمعیت", "رعیت", "سربازان", "پوینت", "پوئن",
    )),
    ("🏦 خزانه (سکه)", (
        "سکه", "بازدهی خزانه",
    )),
    ("🍽 آشپزخانه (غذا)", (
        "غذا", "بازدهی آشپزخانه",
    )),
    ("⚓️ بندر", (
        "بازدهی بندر",
    )),
    ("🏬 تجارت‌خانه", (
        "بازدهی تجارت‌خانه",
    )),
    ("📦 انبار منابع", (
        "چوب", "آهن", "اهن", "سنگ", "پوشاک", "باروت", "موجودی انبار",
    )),
    ("🏗 تولید / کارگاه", (
        "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
    )),
    ("🛡 پیاده‌نظام", (
        "شبه نظامی", "شمشیرزن", "نیزه دار", "نیزه‌دار", "رایفلدار", "افسر",
    )),
    ("🐴 سواره‌نظام", (
        "سواره نظام شمشیرزن", "سواره‌نظام شمشیرزن",
        "سواره‌نظام زره پوش", "سواره نظام زره پوش",
        "سواره‌نظام تفنگدار", "سواره نظام تفنگدار",
    )),
    ("🌟 ویژه", (
        "کشتی خط شکن", "کیوراسیرها", "رایفلداران مدرن",
    )),
    ("🧨 توپخانه", (
        "توپ سبک", "توپ سنگین", "توپ محاصره", "توپ خمپاره ای",
    )),
    ("⚓️ ناوگان", (
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
    )),
]


# کلیدهای امتیازدهی لیدربورد — مطابق شیت VIP
# اقتصادی: موجودی خزانه ×۵ · تولید کارگاه ×۲ · منابع/غذا/جمعیت
# نظامی: پیاده / سواره / ویژه / توپ (با ضریب)
# دریایی: ناوگان
_LB_ECON = (
    "سکه", "بازدهی خزانه", "غذا", "بازدهی آشپزخانه", "جمعیت",
    "بازدهی بندر", "بازدهی تجارت‌خانه",
    "چوب", "آهن", "اهن", "سنگ", "پوشاک", "باروت", "موجودی انبار",
    "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی",
)
_LB_MIL = (
    "سربازان", "شبه نظامی", "شمشیرزن", "نیزه دار", "نیزه‌دار", "رایفلدار", "افسر",
    "سواره نظام شمشیرزن", "سواره‌نظام شمشیرزن",
    "سواره‌نظام زره پوش", "سواره نظام زره پوش",
    "سواره‌نظام تفنگدار", "سواره نظام تفنگدار",
    "کیوراسیرها", "رایفلداران مدرن",
    "توپ سبک", "توپ سنگین", "توپ محاصره", "توپ خمپاره ای",
)
_LB_NAV = (
    "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی", "کشتی خط شکن",
)
# ضرایب: خزانه×۵ · تولید×۲ · پیاده/سواره/توپ/ناوگان
_LB_WEIGHT = {
    # اقتصادی
    "سکه": 5,              # موجودی خزانه
    "بازدهی خزانه": 2,
    "غذا": 1, "بازدهی آشپزخانه": 1, "جمعیت": 1,
    "بازدهی بندر": 1, "بازدهی تجارت‌خانه": 1,
    "چوب": 1, "آهن": 1, "اهن": 1, "سنگ": 1, "پوشاک": 1, "باروت": 1, "موجودی انبار": 1,
    "چوب بری": 2, "معدن سنگ": 2, "معدن آهن": 2, "پوشاک سازی": 2, "باروت سازی": 2,  # لول/خروجی تولید
    # نظامی — پیاده‌نظام
    "شبه نظامی": 1, "شمشیرزن": 1.5, "نیزه دار": 1.5, "نیزه‌دار": 1.5,
    "رایفلدار": 2, "افسر": 5, "سربازان": 0.5,
    # نظامی — سواره‌نظام
    "سواره نظام شمشیرزن": 3, "سواره‌نظام شمشیرزن": 3,
    "سواره‌نظام زره پوش": 4, "سواره نظام زره پوش": 4,
    "سواره‌نظام تفنگدار": 4, "سواره نظام تفنگدار": 4,
    "کیوراسیرها": 5, "رایفلداران مدرن": 3,
    # نظامی — توپخانه
    "توپ سبک": 10, "توپ سنگین": 15, "توپ محاصره": 20, "توپ خمپاره ای": 12,
    # دریایی — ناوگان
    "قایق": 5, "کشتی جنگی": 15, "ناو جنگی": 25, "کشتی سلطنتی": 40, "کشتی خط شکن": 20,
}


def _score_bag(bag: dict, keys: tuple) -> float:
    total = 0.0
    for k in keys:
        if k not in bag:
            continue
        w = _LB_WEIGHT.get(k, 1.0)
        total += float(bag[k]) * w
    return total


def city_power_scores(city: str) -> dict:
    """امتیاز اقتصادی / نظامی / دریایی یک شهر."""
    bag = normalize_stats_keys(get_city_asset_stats(city))
    return {
        "econ": round(_score_bag(bag, _LB_ECON), 1),
        "mil": round(_score_bag(bag, _LB_MIL), 1),
        "nav": round(_score_bag(bag, _LB_NAV), 1),
        "bag": bag,
    }


RANK_CATS = ("all", "econ", "mil", "nav")
RANK_TITLES = {"all": "🏆 کل قدرت", "econ": "💰 اقتصادی", "mil": "⚔️ نظامی", "nav": "⚓️ دریایی"}


def city_ranks(city: str) -> dict:
    """رتبه‌ی همین شهر در هر محور: {cat: (rank, total)}. عدد شهرهای دیگر بیرون نمی‌رود."""
    scores = {}
    for c in list(CITY_ASSETS.keys()):
        sc = city_power_scores(c)
        sc["all"] = sc["econ"] + sc["mil"] + sc["nav"]
        scores[c] = sc
    if city not in scores:
        return {}
    out = {}
    for cat in RANK_CATS:
        order = sorted(scores, key=lambda c: (-scores[c][cat], str(c).lower()))
        out[cat] = (order.index(city) + 1, len(order))
    return out


def rank_arrow(prev, now) -> str:
    """▲ بهتر شدن (عدد رتبه کمتر)، ▼ بدتر شدن."""
    if not prev:
        return "🆕"
    diff = int(prev) - int(now)
    if diff > 0:
        return f"▲{fmt_num(diff)}"
    if diff < 0:
        return f"▼{fmt_num(-diff)}"
    return "＝"


def _lb_rows(scope: str, category: str):
    """لیست رتبه‌بندی‌شده [(label, flag, scores_dict), ...]"""
    if scope == "side":
        rows = []
        for side in FACTIONS:
            total, _, _ = realm_breakdown(side)
            scores = {
                "econ": round(_score_bag(total, _LB_ECON), 1),
                "mil": round(_score_bag(total, _LB_MIL), 1),
                "nav": round(_score_bag(total, _LB_NAV), 1),
            }
            scores["total"] = scores["econ"] + scores["mil"] + scores["nav"]
            flag, title = FACTION_META.get(side, ("", side))
            rows.append((title, flag, scores))
    else:
        rows = []
        for city in list(CITY_ASSETS.keys()):
            sc = city_power_scores(city)
            sc["total"] = sc["econ"] + sc["mil"] + sc["nav"]
            flag = FACTION_META.get(country_key(city) or "", ("", ""))[0]
            rows.append((city, flag, sc))
    key = "total" if category == "all" else category
    rows.sort(key=lambda r: r[2].get(key, 0), reverse=True)
    return rows


def _parse_lb_ranks():
    """رتبه‌های مجاز؛ None = همه."""
    raw = (SETTINGS.get("lb_ranks") or "").strip()
    if not raw or raw in ("*", "all", "همه"):
        return None
    out = set()
    for part in re.split(r'[,،\s]+', raw):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r'(\d+)\s*[-–—]\s*(\d+)', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.update(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.add(int(part))
    return out or None


def format_leaderboard(scope: str = "city", category: str = "all", announce: bool = False) -> str:
    """
    scope: city | side
    category: all | econ | mil | nav
    announce: متن رسمی برای کانال
    """
    medals = ("🥇", "🥈", "🥉")
    cat_fa = {"all": "کل قدرت", "econ": "اقتصادی", "mil": "نظامی", "nav": "دریایی"}[category]
    scope_fa = "سایدها" if scope == "side" else "شهرها"
    rows = _lb_rows(scope, category)
    if not rows:
        return "📭 هنوز دارایی ثبت نشده."
    try:
        max_n = max(1, min(50, int(SETTINGS.get("lb_max") or 10)))
    except (TypeError, ValueError):
        max_n = 10
    allowed = _parse_lb_ranks()
    if allowed is not None:
        rows = [r for i, r in enumerate(rows) if (i + 1) in allowed]
    rows = rows[:max_n]
    if not rows:
        return "📭 با تنظیم رتبهٔ فعلی موردی برای نمایش نیست. <code>lb_ranks=1-10</code>"

    if announce:
        # متن‌های قابل تنظیم از SETTINGS (ادمین می‌نویسد)
        default_intros = {
            "all": (
                "⚔️ در سایهٔ جنگ داخلی، ترازوی قدرت دوباره سنجیده شد.\n"
                "نه با فریاد میدان، که با سنگینی خزانه، صف نیرو و بادبان‌ها."
            ),
            "econ": "💰 در عصر آشوب، ثروت همان تیغی‌ست که بی‌صدا می‌برد.",
            "mil": "🛡 آهن سخن می‌گوید؛ پیاده، سواره و توپخانه رتبه می‌سازند.",
            "nav": "⚓️ دریا پادشاهی بی‌تاج است؛ هر بادبان پیامی از قدرت.",
        }
        intro_key = {"all": "lb_intro_all", "econ": "lb_intro_econ", "mil": "lb_intro_mil", "nav": "lb_intro_nav"}
        intro = (SETTINGS.get(intro_key.get(category, "lb_intro_all")) or "").strip() or default_intros.get(category, default_intros["all"])
        place_words = (
            SETTINGS.get("lb_place_1") or "در صدر ایستاده است",
            SETTINGS.get("lb_place_2") or "پس از او می‌درخشد",
            SETTINGS.get("lb_place_3") or "رتبهٔ سوم را از آن خود کرده",
            SETTINGS.get("lb_place_mid") or "در ردیف‌های میانی قدرت جای گرفته",
            SETTINGS.get("lb_place_low") or "هنوز در سایهٔ بزرگان می‌جنگد",
        )
        footer = (SETTINGS.get("lb_footer") or "").strip() or (
            "جنگ داخلی انگلیس آینهٔ قدرت است؛ رتبه امروز، سرنوشت فرداست."
        )
        lines = [
            f"🏆 <b>اعلامیهٔ لیدربورد — {scope_fa}</b>",
            f"📜 محور: <b>{cat_fa}</b>",
            DIV,
            f"<blockquote>{intro}</blockquote>",
            "",
        ]
        limit = 8 if scope == "city" else len(rows)
        for i, (name, flag, sc) in enumerate(rows[:limit]):
            m = medals[i] if i < 3 else f"▫️ {i + 1}."
            if i < 3:
                verb = place_words[i]
            elif i < 5:
                verb = place_words[3]
            else:
                verb = place_words[4]
            # پشتیبانی {rank} {name} در متن جایگاه
            verb = verb.replace("{rank}", str(i + 1)).replace("{name}", name)
            lines.append(f"{m} {flag} <b>{e(name)}</b>\n   <i>«{e(verb)}»</i>")
        if scope == "city" and len(rows) > limit:
            lines.append("\n… و دیگر شهرها در پردهٔ تاریخ انتظار می‌کشند.")
        lines.append(f"\n{DIV}\n<i>{e(footer)}</i>\n#لیدربورد")
        return "\n".join(lines)

    lines = [f"🏆 <b>لیدربورد {scope_fa}</b> — {cat_fa}", DIV]
    limit = 15 if scope == "city" else len(rows)
    for i, (name, flag, sc) in enumerate(rows[:limit]):
        m = medals[i] if i < 3 else f"{i+1}."
        lines.append(
            f"{m} {flag}<b>{e(name)}</b>\n"
            f"   💰 {fmt_num(sc['econ'])} · ⚔️ {fmt_num(sc['mil'])} · ⚓️ {fmt_num(sc['nav'])}"
            + (f" · Σ {fmt_num(sc['total'])}" if category == "all" else "")
        )
    if scope == "city" and len(rows) > limit:
        lines.append(f"\n… و {len(rows) - limit} شهر دیگر")
    return "\n".join(lines)


def format_stats_labeled(bag: dict) -> str:
    """
    اعداد استخراج‌شده را بخش‌بندی می‌کند و جلوی هر بخش معنی می‌نویسد.
    اقلام ناشناس در انتها زیر «سایر» می‌آیند.
    """
    bag = normalize_stats_keys(bag or {})
    if not bag:
        return "— عددی نیست —"
    used = set()
    lines = []
    for title, keys in _STATS_SECTIONS:
        rows = []
        for k in keys:
            if k in bag:
                v = bag[k]
                num = int(v) if float(v) == int(float(v)) else v
                rows.append(f"  • {k}: <b>{num}</b>")
                used.add(k)
        # تطبیق بدون حساسیت به فاصله/ی
        for k, v in bag.items():
            if k in used:
                continue
            kn = k.replace("\u200c", "").replace(" ", "")
            for key in keys:
                if kn == key.replace("\u200c", "").replace(" ", ""):
                    num = int(v) if float(v) == int(float(v)) else v
                    rows.append(f"  • {k}: <b>{num}</b>")
                    used.add(k)
                    break
        if rows:
            lines.append(f"<b>{title}</b>")
            lines.extend(rows)
    other = []
    for k, v in bag.items():
        if k in used:
            continue
        num = int(v) if float(v) == int(float(v)) else v
        other.append(f"  • {k}: <b>{num}</b>")
    if other:
        lines.append("<b>📋 سایر</b>")
        lines.extend(other)
    return "\n".join(lines) if lines else "— عددی نیست —"


def format_assets_block(title: str, bag: dict) -> str:
    body = format_stats_labeled(bag) if bag else "— خالی —"
    return f"📦 <b>{e(title)}</b>\n{DIV}\n{body}"


def format_realm_view(side: str) -> str:
    """
    دارایی کل قلمرو — فقط یک پیام جمع‌زده (بدون شیت تک‌تک شهرها).
    """
    flag, title = FACTION_META.get(side, ("", side or "?"))
    total, by_city, city_list = realm_breakdown(side)
    n_reg = len(by_city)
    n_all = len(city_list)
    lines = [
        f"🌐 <b>دارایی کل قلمرو {flag}{title}</b>",
        f"<i>جمع تخمینی از {n_reg} شهر ثبت‌شده (از {n_all} شهر ساید)</i>",
        DIV,
        format_stats_labeled(total) if total else "— هنوز دارایی‌ای برای جمع ثبت نشده —",
    ]
    return "\n".join(lines)


def format_city_asset_view(city: str, viewer: int | None = None) -> str:
    """دارایی شخصی یک شهر: متن کامل شیت ثبت‌شده.
    viewer: اگر فرمانده‌ی همین شهر / لیدر همین جناح / ادمین باشد، ویژگی قلعه زیر شیت می‌آید (فقط نمایش)."""
    side = country_key(city)
    flag, title = FACTION_META.get(side, ("", side or "؟")) if side else ("", "؟")
    text = get_city_asset_text(city)
    header = f"📦 <b>دارایی شخصی — {e(city)}</b>\n🏴 ساید: {flag}{title}\n{DIV}\n"
    body = header + (text or "— برای این شهر هنوز دارایی ثبت نشده —")
    trait = castle_trait_block(city, viewer)
    return f"{body}\n\n{trait}" if trait else body
