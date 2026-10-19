"""باف/نرف قلعه‌ها طبق کانال اطلاعات بازی."""

from app.state import CITY_BUFFS
from app.utils import _norm_country_token
from app.factions import country_key
from app.players import is_admin, leader_side, player_cities


# کاراکتر+قلعه (باف اقتصادی apply_on_up؛ نبرد نمایشی)
CASTLE_META = {
    "london_monarchist": {"char": "King Charles I", "buffs": [
        {"kind": "buff", "target": "سکه", "pct": 25, "text": "قلعه: ۲۵٪ اقتصاد بهتر", "apply_on_up": True},
        {"kind": "nerf", "target": "مشروعیت", "pct": 10, "text": "قلعه: ۱۰٪ ثبات کمتر", "apply_on_up": False},
    ]},
    "pembroke_monarchist": {"char": "Henry Prince of Wales", "buffs": [
        {"kind": "buff", "target": "غذا", "pct": 30, "text": "قلعه: ۳۰٪ بازدهی آشپزخانه", "apply_on_up": True},
    ]},
    "leicester_monarchist": {"char": "George Buckingham", "buffs": [
        {"kind": "nerf", "target": "جمعیت", "pct": 10, "text": "قلعه: دهکده ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "nottingham_monarchist": {"char": "James Stanley", "buffs": [
        {"kind": "buff", "target": "غذا", "pct": 30, "text": "قلعه: ۳۰٪ آشپزخانه", "apply_on_up": True},
    ]},
    "bristol_monarchist": {"char": "Ralph Hopton", "buffs": []},
    "colchester_monarchist": {"char": "Sir Charles Lucas", "buffs": []},
    "oxford_monarchist": {"char": "Sir Jacob Astley", "buffs": [
        {"kind": "nerf", "target": "غذا", "pct": 10, "text": "قلعه: مصرف غله آپ ۱۰٪ بیشتر", "apply_on_up": True},
    ]},
    "liverpool_monarchist": {"char": "Prince Rupert", "buffs": []},
    "cambridge_monarchist": {"char": "Sir Lewis Dyve", "buffs": []},
    "edinburgh_monarchist": {"char": "Archibald Campbell", "buffs": [
        {"kind": "nerf", "target": "سکه", "pct": 10, "text": "قلعه: خزانه ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "norwich_parliamentarian": {"char": "Oliver Cromwell", "buffs": [
        {"kind": "buff", "target": "سکه", "pct": 20, "text": "قلعه: ۲۰٪ بازدهی بندر", "apply_on_up": True},
        {"kind": "nerf", "target": "سنگ", "pct": 10, "text": "قلعه: سنگ ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "york_parliamentarian": {"char": "Thomas Fairfax", "buffs": [
        {"kind": "nerf", "target": "پوشاک", "pct": 10, "text": "قلعه: پوشاک ۱۰٪ کمتر", "apply_on_up": True},
        {"kind": "nerf", "target": "جمعیت", "pct": 10, "text": "کاراکتر: جمعیت هفتگی ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "dover_parliamentarian": {"char": "Sir William Waller", "buffs": [
        {"kind": "nerf", "target": "چوب", "pct": 10, "text": "قلعه: چوب‌بری ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "gloucester_parliamentarian": {"char": "Sir Edward Massey", "buffs": [
        {"kind": "buff", "target": "سکه", "pct": 30, "text": "قلعه: ۳۰٪ تجارتخانه", "apply_on_up": True},
    ]},
    "leeds_parliamentarian": {"char": "Philip Skippon", "buffs": []},
    "newcastle_parliamentarian": {"char": "John Lambert", "buffs": [
        {"kind": "nerf", "target": "سکه", "pct": 10, "text": "قلعه: خزانه ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "bridgwater_parliamentarian": {"char": "Robert Blake", "buffs": [
        {"kind": "nerf", "target": "اسب", "pct": 20, "text": "قلعه: اصطبل ۲۰٪ کمتر", "apply_on_up": True},
    ]},
    "winchester_parliamentarian": {"char": "John Desborough", "buffs": [
        {"kind": "buff", "target": "غذا", "pct": 30, "text": "قلعه: ۳۰٪ آشپزخانه", "apply_on_up": True},
    ]},
    "exeter_parliamentarian": {"char": "Thomas Pride", "buffs": [
        {"kind": "buff", "target": "سکه", "pct": 30, "text": "قلعه: ۳۰٪ تجارتخانه", "apply_on_up": True},
    ]},
    "manchester_parliamentarian": {"char": "William Fleetwood", "buffs": [
        {"kind": "nerf", "target": "سکه", "pct": 10, "text": "قلعه: خزانه ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "paris_france": {"char": "Louis XIII", "buffs": [
        {"kind": "nerf", "target": "سنگ", "pct": 10, "text": "قلعه: معدن سنگ ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "caen_france": {"char": "Henri de Rohan", "buffs": [
        {"kind": "buff", "target": "سکه", "pct": 30, "text": "قلعه: ۳۰٪ بندر", "apply_on_up": True},
    ]},
    "nantes_france": {"char": "Marguerite Rohan", "buffs": []},
    "brest_france": {"char": "Cardinal Richelieu", "buffs": [
        {"kind": "buff", "target": "ناو جنگی", "pct": 100, "text": "قلعه: بازدهی ناو ۲×", "apply_on_up": True},
    ]},
    "amiens_france": {"char": "Henri de Schomberg", "buffs": []},
    "armagh_ireland": {"char": "Owen Roe O'Neill", "buffs": [
        {"kind": "nerf", "target": "پوشاک", "pct": 10, "text": "قلعه: پوشاک ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "cork_ireland": {"char": "Alastair MacColla", "buffs": []},
    "dublin_ireland": {"char": "Theobald Dillon", "buffs": [
        {"kind": "buff", "target": "چوب", "pct": 30, "text": "قلعه: ۳۰٪ چوب‌بری", "apply_on_up": True},
    ]},
    "waterford_ireland": {"char": "Sir Phelim O'Neill", "buffs": [
        {"kind": "buff", "target": "سکه", "pct": 30, "text": "قلعه: ۳۰٪ تجارتخانه", "apply_on_up": True},
        {"kind": "nerf", "target": "چوب", "pct": 10, "text": "قلعه: چوب ۱۰٪ کمتر", "apply_on_up": True},
    ]},
    "limerick_ireland": {"char": "Sir George Hamilton", "buffs": [
        {"kind": "buff", "target": "غذا", "pct": 30, "text": "قلعه: ۳۰٪ آشپزخانه", "apply_on_up": True},
    ]},
}


def seed_castle_buffs():
    """ثبت باف/نرف اقتصادی قلعه در CITY_BUFFS بدون دوباره‌نویسی دستی."""
    n = 0
    for city, meta in CASTLE_META.items():
        existing = list(CITY_BUFFS.get(city) or [])
        have = {str(x.get("id")) for x in existing}
        for i, bf in enumerate(meta.get("buffs") or []):
            bid = f"castle_{city}_{i}"
            if bid in have:
                continue
            existing.append({
                "id": bid,
                "kind": bf.get("kind") or "buff",
                "target": bf.get("target") or "",
                "pct": float(bf.get("pct") or 0),
                "text": bf.get("text") or "",
                "apply_on_up": bool(bf.get("apply_on_up")),
                "source": "castle",
            })
            n += 1
        CITY_BUFFS[city] = existing
    return n


# ---------------- ویژگی قلعه — فقط نمایش (هیچ اعمالی در محاسبات ندارد) ----------------
# متن رسمی کانال asheswar_inf (جدول docs/NOTES_FOR_CLAUDE_CODE.md). کلید = نام پایه‌ی شهر.
# unverified = برداشت از متن مبهم است و باید با صاحب بازی تأیید شود.
CASTLE_TRAITS = {
    "london": {"buff": "۲۵٪ وضعیت اقتصاد بهتر", "nerf": "۱۰٪ ثبات اجتماعی کمتر"},
    "pembroke": {"buff": "بازدهی آشپزخانه سلطنتی ۳۰٪ بیشتر", "nerf": "۱۵٪ مقاومت کمتر در محاصره"},
    "leicester": {"buff": "۲۰٪ قدرت بیشتر در دفاع", "nerf": "دهکده ۱۰٪ بازدهی کمتر"},
    "nottingham": {"buff": "۳۰٪ بازدهی بیشتر آشپزخانه", "nerf": "قحطی در محاصره ۲ روزه"},
    "bristol": {"buff": "شروع با ۱۵٪ منابع بیشتر", "nerf": "هزینه ارتقای تجارتخانه ۲۰٪ بیشتر"},
    "colchester": {"buff": "هر هفته یک ارتقای دلخواه رایگان", "nerf": "شروع با ۱۰٪ سکه کمتر"},
    "oxford": {"buff": "شروع با ۱۵٪ پیاده بیشتر", "nerf": "هر آپ مصرف غلات ۱۰٪ بیشتر"},
    "liverpool": {"buff": "هزینه ساخت انواع کشتی ۲۰٪ کمتر",
                  "nerf": "هر هفته بازدهی یک ساختمان تولیدی ۲۰٪ کم (تاس ادمین)"},
    "cambridge": {"buff": "۱۵٪ پیاده بیشتر", "nerf": "شورش مردم در محاصره ۲ روزه"},
    "edinburgh": {"buff": "۱۵٪ توپخانه بیشتر", "nerf": "بازدهی خزانه ۱۰٪ کمتر"},
    "norwich": {"buff": "شروع با ۱۵٪ کشتی بیشتر · ۲۰٪ سکه بیشتر از بندر", "nerf": "۱۰٪ کمتر تولیدی سنگ"},
    "york": {"buff": "۱۵٪ سواره بیشتر", "nerf": "۱۰٪ کمتر پارچه‌سازی"},
    "dover": {"buff": "۱۵٪ ناوگان اولیه بیشتر", "nerf": "۱۰٪ کاهش چوب‌بری"},
    "gloucester": {"buff": "۳۰٪ بازدهی بیشتر تجارتخانه", "nerf": "هزینه ساخت باروت‌سازی ۲۰٪ بیشتر"},
    "leeds": {"buff": "هزینه سکه‌ی ساخت معادن ۳۰٪ کمتر", "nerf": "موجودی آشپزخانه سلطنتی نصف"},
    "newcastle": {"buff": "هزینه ساخت کمپ نیروی دریایی ۳۰٪ کمتر", "nerf": "۱۰٪ بازدهی کمتر خزانه"},
    "bridgwater": {"buff": "قفل کشتی سلطنتی باز + هزینه ساخت ۱۰٪ کمتر", "nerf": "۲۰٪ بازدهی کمتر اصطبل"},
    "winchester": {"buff": "۳۰٪ بازدهی بیشتر آشپزخانه", "nerf": "هزینه ساخت معادن ۱۰٪ بیشتر"},
    "exeter": {"buff": "بازدهی تجارتخانه ۳۰٪ بیشتر", "nerf": "هزینه ساخت نیروی دریایی ۱۰٪ بیشتر"},
    "manchester": {"buff": "هزینه ساخت باروت‌سازی ۲۰٪ کمتر", "nerf": "بازدهی خزانه ۱۰٪ کمتر"},
    "paris": {"buff": "قفل کیوراسیرها باز + بازدهی آن ۳۰٪ بیشتر · هزینه ارتقای کمپ‌های نظامی ۲۰٪ کمتر",
              "nerf": "بازدهی معادن سنگ ۱۰٪ کمتر"},
    "caen": {"buff": "بازدهی بندر ۳۰٪ بیشتر", "nerf": "آنلاک و ارتقای کشتی سلطنتی ۱۰٪ گران‌تر"},
    "nantes": {"buff": "هفتگی ۲ ارتقای رایگان روی تولیدی‌ها", "nerf": "هزینه ساخت کمپ سواره زره‌پوش ۱۰٪ بیشتر"},
    "brest": {"buff": "بازدهی ۲ برابری کمپ ناو جنگی", "nerf": "هزینه ساخت و ارتقای چوب‌بری ۱۰٪ بیشتر"},
    "amiens": {"buff": "۱۵٪ سواره بیشتر", "nerf": "هزینه کارگاه توپ صحرایی ۱۰٪ بیشتر",
               "unverified": "«توپ صحرایی» = «توپ سبک»؟"},
    "armagh": {"buff": "هزینه ساخت چوب‌بری ۳۰٪ کمتر (+ قلعه لول ۲ پیش‌فرض)", "nerf": "۱۰٪ کمتر تولیدی پوشاک"},
    "cork": {"buff": "۲۰٪ قدرت بیشتر ناوگان", "nerf": "هزینه خرید از تجار ۱۰٪ بیشتر"},
    "dublin": {"buff": "بازدهی چوب‌بری ۳۰٪ بیشتر", "nerf": "هزینه کارگاه کشتی جنگی ۱۰٪ بیشتر"},
    "waterford": {"buff": "بازدهی تجارتخانه ۳۰٪ بیشتر", "nerf": "بازدهی تولیدی چوب ۱۰٪ کمتر"},
    "limerick": {"buff": "۳۰٪ بازدهی بیشتر آشپزخانه", "nerf": "هزینه ساخت معدن سنگ ۱۰٪ بیشتر"},
}


def castle_trait(city: str) -> dict | None:
    base = _norm_country_token(city or "").split("_")[0]
    return CASTLE_TRAITS.get(base)


def castle_trait_line(city: str) -> str:
    """یک خط کوتاه (برای پیش‌نمایش آپ ادمین)."""
    t = castle_trait(city)
    if not t:
        return ""
    flag = " ⚠️ تأیید نشده" if t.get("unverified") else ""
    return f"🏰 یادآوری ویژگی قلعه: ✅ {t['buff']} · ❌ {t['nerf']}{flag}"


def can_see_castle_trait(city: str, viewer: int | None) -> bool:
    """فقط فرمانده‌های همان شهر، لیدرهای همان جناح و ادمین."""
    if not viewer:
        return False
    if is_admin(viewer):
        return True
    side = country_key(city)
    if side and leader_side(viewer) == side:
        return True
    key = _norm_country_token(city)
    return any(_norm_country_token(c) == key for c in player_cities(viewer))


def castle_trait_block(city: str, viewer: int | None) -> str:
    """بلوک زیر شیت شهر — فقط نمایش؛ در هیچ محاسبه‌ای اعمال نمی‌شود."""
    t = castle_trait(city)
    if not t or not can_see_castle_trait(city, viewer):
        return ""
    lines = ["🏰 <b>ویژگی قلعه</b> <i>(فقط اطلاع — به‌صورت خودکار اعمال نمی‌شود)</i>",
             f"✅ باف: {t['buff']}", f"❌ نرف: {t['nerf']}"]
    if t.get("unverified"):
        lines.append(f"⚠️ <b>تأیید نشده:</b> {t['unverified']}")
    return "\n".join(lines)
