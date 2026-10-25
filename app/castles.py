"""باف/نرف قلعه‌ها طبق کانال اطلاعات بازی."""

from app.state import CITY_BUFFS
from app.utils import _norm_country_token, e
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
    # rules.txt: «توپ محاصره … بازدهی ۴ توپ صحرایی» → توپ صحرایی = توپ محاصره (نه توپ سبک)
    "amiens": {"buff": "۱۵٪ سواره بیشتر", "nerf": "هزینه کارگاه توپ صحرایی (توپ محاصره) ۱۰٪ بیشتر"},
    "armagh": {"buff": "هزینه ساخت چوب‌بری ۳۰٪ کمتر (+ قلعه لول ۲ پیش‌فرض)", "nerf": "۱۰٪ کمتر تولیدی پوشاک"},
    "cork": {"buff": "۲۰٪ قدرت بیشتر ناوگان", "nerf": "هزینه خرید از تجار ۱۰٪ بیشتر"},
    "dublin": {"buff": "بازدهی چوب‌بری ۳۰٪ بیشتر", "nerf": "هزینه کارگاه کشتی جنگی ۱۰٪ بیشتر"},
    "waterford": {"buff": "بازدهی تجارتخانه ۳۰٪ بیشتر", "nerf": "بازدهی تولیدی چوب ۱۰٪ کمتر"},
    "limerick": {"buff": "۳۰٪ بازدهی بیشتر آشپزخانه", "nerf": "هزینه ساخت معدن سنگ ۱۰٪ بیشتر"},
}


# ---------------- لرد هر قلعه — فقط نمایش ----------------
# منبع: بخش «LIST OF CHARACTER» در rules.txt (کانال CHARACTER). جدا از ویژگی قلعه‌ی بالا
# (که از کانال اطلاعات قلعه‌هاست). کلید = نام پایه‌ی شهر. هیچ‌کدام در محاسبات اعمال نمی‌شوند.
CHARACTER_TRAITS = {
    # ---- سلطنت‌طلبان ----
    "london": {"lord": "King Charles I", "role": "پادشاه انگلستان", "tier": "VIP درجه یک",
               "buff": "۱۰٪ افزایش روحیه ارتش هنگام حضور در نبرد",
               "special": "تا ۱۵٪ افزایش عملکرد رول",
               "nerf": "۸٪ کاهش نرخ ثبات داخلی"},
    "pembroke": {"lord": "Henry Prince of Wales", "role": "وارث تاج‌وتخت و شاهزاده ولز", "tier": "VIP درجه دو",
                 "buff": "۱۰٪ افزایش موفقیت در رول خرابکاری",
                 "special": "۱۵٪ افزایش جنگاوری نیروها",
                 "nerf": "۸٪ کاهش عملکرد در زمینه‌های اجتماعی"},
    "leicester": {"lord": "George Duke of Buckingham", "role": "مشاور پادشاه، فرمانده ارتش", "tier": "عادی",
                  "buff": "توانایی استخدام مهندس برای ساخت یک توپ مخصوص",
                  "nerf": "نرخ خرید از تجار ۱۰٪ بیشتر"},
    "nottingham": {"lord": "James Stanley, 7th Earl of Derby", "role": "فرمانده نظامی", "tier": "عادی",
                   "buff": "ارتش در نبردهای دفاعی ۱۵٪ قوی‌تر",
                   "nerf": "بازدهی دهکده ۱۰٪ کمتر"},
    "bristol": {"lord": "Ralph Hopton", "role": "فرمانده نظامی", "tier": "عادی",
                "buff": "۱۵٪ قدرت انفجار بیشتر در نیروهای دفاعی تحت امر هاپتون",
                "nerf": "هر جنگ −۳ اقتدار (با پیروزی جبران می‌شود)"},
    "colchester": {"lord": "Sir Charles Lucas", "role": "فرمانده سواره‌نظام", "tier": "عادی",
                   "buff": "۱۵٪ قدرت تهاجم سواره‌نظام",
                   "nerf": "۱۰٪ افزایش هزینه رول اقتصادی"},
    "oxford": {"lord": "Sir Jacob Astley", "role": "فرمانده پیاده‌نظام", "tier": "عادی",
               "buff": "۱۵٪ شانس موفقیت بیشتر برای ترور و رول خرابکاری",
               "nerf": "۱۰٪ کاهش قدرت نیرو در نبردهای کوهستانی"},
    "liverpool": {"lord": "Prince Rupert of the Rhine", "role": "فرمانده نظامی و نابغه علمی", "tier": "عادی",
                  "buff": "۱۵٪ قدرت بیشتر نیروی دریایی",
                  "nerf": "۱۰٪ افزایش هزینه ساخت کمپ سواره‌نظام"},
    "cambridge": {"lord": "Sir Lewis Dyve", "role": "فرمانده پیاده‌نظام", "tier": "عادی",
                  "buff": "۱۵٪ افزایش بازدهی یک رول در هفته",
                  "nerf": "۱۰٪ کاهش قدرت توپخانه در نبرد تهاجمی"},
    "edinburgh": {"lord": "Archibald Campbell", "role": "شاهزاده اسکاتلند", "tier": "عادی",
                  "buff": "با فرمان او ضدحمله‌ای مرگبار در نبردهای دفاعی",
                  "nerf": "۱۰٪ افزایش هزینه رول‌ها"},
    # ---- پارلمان‌گرایان ----
    "norwich": {"lord": "Oliver Cromwell", "role": "رهبر سیاسی و نظامی پارلمان‌گراها", "tier": "VIP",
                "buff": "۱۵٪ افزایش روحیه نیرو",
                "special": "در نبردهای تهاجمی با آرایش کامل نیروها خطوط دشمن را ضعیف می‌کند",
                "nerf": "۱۰٪ افزایش هزینه رول اقتصادی"},
    "york": {"lord": "Thomas Fairfax", "role": "فرمانده ارتش نوین", "tier": "VIP",
             "buff": "۱۵٪ شانس موفقیت بهتر ترور یا خرابکاری",
             "special": "در نبردهای دفاعی با آرایش منسجم ۱۵٪ از قدرت دشمن می‌کاهد",
             "nerf": "۱۰٪ کاهش جمعیت هفتگی"},
    "dover": {"lord": "Sir William Waller", "role": "سیاستمدار و فرمانده", "tier": "عادی",
              "buff": "هفتگی گروهی از دانشمندان در یک دانشکده: بازدهی آن دانشکده ۱۵٪ بهتر",
              "nerf": "۱۰٪ افزایش هزینه رول"},
    "gloucester": {"lord": "Sir Edward Massey", "role": "فرمانده نظامی", "tier": "عادی",
                   "buff": "۱۵٪ افزایش جنگاوری نیروها در نبردهای دفاعی",
                   "nerf": "۱۰٪ کاهش قدرت امنیت داخلی"},
    "leeds": {"lord": "Philip Skippon", "role": "فرمانده توپخانه", "tier": "عادی",
              "buff": "با فرمان او شلیک توپخانه ۱۵٪ مؤثرتر (صف‌شکنی)",
              "nerf": "با انعقاد هر قرارداد ۳۰۰ سکه کسر می‌شود"},
    "newcastle": {"lord": "John Lambert", "role": "فرمانده ارتش", "tier": "عادی",
                  "buff": "توانایی اصلاح رول: کاهش هزینه و افزایش بازدهی رول",
                  "nerf": "۱۰٪ کاهش جنگاوری نیروها در آب‌وهوای آفتابی"},
    "bridgwater": {"lord": "Robert Blake", "role": "فرمانده ناوگان دریایی", "tier": "عادی",
                   "buff": "در نبردهای دریایی کشتی‌ها با ۱۵٪ قدرت بیشتر حمله می‌کنند",
                   "nerf": "۱۰٪ افزایش قیمت خرید از تجار"},
    "winchester": {"lord": "John Desborough", "role": "مشاور نظامی و فرمانده سواره‌نظام", "tier": "عادی",
                   "buff": "۱۵٪ افزایش روحیه ارتش در نبرد",
                   "nerf": "۱۰٪ کاهش قیمت فروش به تجار"},
    "exeter": {"lord": "Thomas Pride", "role": "تاجر و افسر نظامی", "tier": "عادی",
               "buff": "۱۵٪ احتمال موفقیت بیشتر در رول خرابکاری یا ترور",
               "nerf": "هر هفته −۳ اقتدار"},
    "manchester": {"lord": "William Fleetwood", "role": "فرمانده قلعه و نخبه علمی", "tier": "عادی",
                   "buff": "با فرمان او سواره‌نظام صفوفی مرگبار شکل می‌دهد",
                   "nerf": "۱۰٪ احتمال موفقیت بیشتر رول خرابکاری یا ترور دشمن"},
    # ---- پادشاهی فرانسه ----
    "paris": {"lord": "Louis XIII", "role": "پادشاه فرانسه", "tier": "VIP",
              "buff": "فراخوانی تعدادی شبه‌نظامی در نبردهای دفاعی",
              "special": "هر هفته یک تولیدی ۲ برابر یا بازدهی یک کمپ ارتش ۵۰٪ بیشتر",
              "nerf": "نیروها در نبرد ۱۰٪ روحیه کمتر"},
    "caen": {"lord": "Henri de Rohan", "role": "فرماندار", "tier": "عادی",
             "buff": "در نبردهای تهاجمی ترکیب توپخانه و سواره‌نظام برای شکستن خطوط یا نفوذ به قلعه",
             "nerf": "۱۰٪ افزایش هزینه خرید از تجار"},
    "nantes": {"lord": "Marguerite, Duchess of Rohan", "role": "فرماندار", "tier": "عادی",
               "buff": "۱۵٪ افزایش سود فروش به تجار",
               "nerf": "۱۰٪ کاهش جنگاوری نیروها در نبرد دفاعی"},
    "brest": {"lord": "Cardinal Richelieu", "role": "کاردینال", "tier": "عادی",
              "buff": "دانشمندان در دانشکده‌ی اقتصادی: بازدهی هفتگی آن ۲ برابر",
              "nerf": "۱۰٪ افزایش هزینه رول‌ها"},
    "amiens": {"lord": "Henri de Schomberg", "role": "مارشال سلطنتی", "tier": "عادی",
               "buff": "۱۵٪ سرعت بیشتر پیاده‌نظام در نبرد",
               "nerf": "۱۰٪ کاهش نرخ فروش به تجار"},
    # ---- کنفدراسیون ایرلند ----
    "armagh": {"lord": "Owen Roe O'Neill", "role": "رهبر کنفدراسیون ایرلند", "tier": "VIP",
               "buff": "۱۵٪ افزایش جنگاوری نیروها در شرایط سخت",
               "special": "صفوف ترکیبی سواره و پیاده با پشتیبانی توپخانه — افزایش تلفات دشمن",
               "nerf": "۱۰٪ امنیت کمتر قلعه"},
    "cork": {"lord": "Alastair MacColla", "role": "فرمانده نظامی", "tier": "عادی",
             "buff": "بسیج ۱۰۰ نیروی دلخواه برای جنگ چریکی",
             "nerf": "۱۰٪ افزایش هزینه رول"},
    "dublin": {"lord": "Theobald Dillon", "role": "نظامی و فرماندار", "tier": "عادی",
               "buff": "۱۵٪ کاهش قیمت خرید و افزایش قیمت فروش به تجار",
               "nerf": "هر آپ −۳ اقتدار"},
    "waterford": {"lord": "Sir Phelim O'Neill", "role": "فرمانده", "tier": "عادی",
                  "buff": "در نبردهای دفاعی فراخوانی ۳۰۰ تا ۵۰۰ نیرو",
                  "nerf": "ارتش در نبردهای متحد ۱۰٪ ناهماهنگی"},
    "limerick": {"lord": "Sir George Hamilton", "role": "فرماندار", "tier": "عادی",
                 "buff": "هر هفته سرباز دلخواه از نیروهای بازی به مدت ۵ استارت",
                 "nerf": "در نبردها ۵٪ افت روحیه"},
}

# نام کاراکتر در CASTLE_META همیشه از همین جدول (یک منبع)
for _city, _meta in CASTLE_META.items():
    _ct = CHARACTER_TRAITS.get(_city.split("_")[0])
    if _ct:
        _meta["char"] = _ct["lord"]


def character_trait(city: str) -> dict | None:
    base = _norm_country_token(city or "").split("_")[0]
    return CHARACTER_TRAITS.get(base)


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
    """بلوک زیر شیت شهر (ویژگی قلعه + لرد) — فقط نمایش؛ در هیچ محاسبه‌ای اعمال نمی‌شود."""
    t = castle_trait(city)
    ch = character_trait(city)
    if not (t or ch) or not can_see_castle_trait(city, viewer):
        return ""
    lines = []
    if t:
        lines += ["🏰 <b>ویژگی قلعه</b> <i>(فقط اطلاع — به‌صورت خودکار اعمال نمی‌شود)</i>",
                  f"✅ باف: {t['buff']}", f"❌ نرف: {t['nerf']}"]
        if t.get("unverified"):
            lines.append(f"⚠️ <b>تأیید نشده:</b> {t['unverified']}")
    if ch:
        if lines:
            lines.append("")
        lines += [f"👤 <b>لرد: {e(ch['lord'])}</b> — {ch['role']} <i>({ch['tier']})</i>",
                  f"✅ باف: {ch['buff']}"]
        if ch.get("special"):
            lines.append(f"🌟 باف ویژه: {ch['special']}")
        lines.append(f"❌ نرف: {ch['nerf']}")
    return "\n".join(lines)
