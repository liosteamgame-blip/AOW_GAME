"""کاتالوگ شاپ — دقیقاً طبق بخش «قوانین شاپ» و پست‌های کانال شاپ در rules.txt.

هر آیتم: نام فارسی/انگلیسی، دسته، قیمت (T) و محتوا.
- یونیت مزدور / جاسوس / گارد: «تعداد» یک‌بار هنگام خرید + «بازدهی» هر آپ
- فرمانده/هیرو و گروهک مزدور: «ارتش همراه» فقط یک‌بار (بازدهی هفتگی ندارد)
- پک منابع: منابع یک‌بار · استارتر: سکه یک‌بار (لول‌ها و درصدها را ادمین اعمال می‌کند)
- کاراکتر VIP، پک ارتش و تسلیحات: فقط ثبت و یادداشت؛ اعمال با ادمین
"""
import re

# دسته‌ها و برچسب نمایشی
CATEGORIES = {
    "vip": "👑 کاراکتر VIP",
    "starter": "🎁 استارتر",
    "resources": "📦 پک منابع",
    "army": "⚔️ پک ارتش",
    "weapon": "🔫 تسلیحات",
    "hero": "🥷 فرمانده/هیرو",
    "minister": "🤵 وزیر",
    "merc_group": "🛡 گروهک مزدور",
    "merc": "🗡 یونیت مزدور",
    "spy": "🕵️ جاسوس",
    "guard": "💂 گارد",
}

# نام یونیت‌های ارتش همراه → کلید همان یونیت در ربات (اگر در جدول قوانین هست)
_UNIT_ALIASES = {
    "سوارنظام تفنگدار": "سواره‌نظام تفنگدار",
    "رایفلدار مدرن": "رایفلداران مدرن",
    "تفنگدار مدرن": "رایفلداران مدرن",
    "رایفلدار ایرلندی": "رایفلداران ایرلندی",
    "کیوراسیر": "کیوراسیرها",
    "سوار کیوراسیر": "کیوراسیرها",
    "گارد پادشاهی فرانسه": "گاردپادشاهی فرانسه",
    "گارد کلداستریم": "کلداستریم گارد",
    "کلداستریم": "کلداستریم گارد",
    "کلداستریم گارد انگلیسی": "کلداستریم گارد",
    "خمپاره انداز": "توپ خمپاره‌ای",
    "قایق عادی": "قایق",
    "ملوان": "ملوان شمالی",
}


def unit_key(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").replace("‌", " ")).strip()
    return _UNIT_ALIASES.get(name, name)


def _h(fa, en, price, army, cat="hero"):
    return {"cat": cat, "fa": fa, "en": en, "price": price,
            "army": [(n, unit_key(u)) for n, u in army]}


def _u(cat, fa, en, count, yld, stock, price):
    return {"cat": cat, "fa": fa, "en": en, "price": price, "count": count, "yield": yld, "stock": stock}


def _vip(fa, en, city, econ, mil, price):
    return {"cat": "vip", "fa": fa, "en": en, "price": price, "city": city, "econ_pct": econ, "mil_pct": mil}


CATALOG = [
    # ---- کاراکتر VIP ----
    _vip("چارلز اول", "Charles I", "لندن", 80, 60, "250T"),
    _vip("پرنس هنری", "Prince Henry", "پمبورک", 50, 40, "150T"),
    _vip("الیور کرامول", "Oliver Cromwell", "نورویچ", 80, 60, "250T"),
    _vip("توماس فرفکس", "Thomas Fairfax", "یورک", 50, 40, "150T"),
    _vip("لویی سیزدهم", "Louis XIII", "پاریس", 80, 60, "250T"),
    _vip("اوون رو اونیل", "Owen Roe O'Neill", "آرماگ", 50, 40, "150T"),
    # ---- استارتر ----
    {"cat": "starter", "fa": "استارتر طلایی", "en": "Gold Starter", "price": "350T",
     "econ_pct": 60, "mil_pct": 40, "grant": {"سکه": 4000}, "econ_levels": 4, "mil_levels": 3, "ability": 1},
    {"cat": "starter", "fa": "استارتر نقره‌ای", "en": "Silver Starter", "price": "250T",
     "econ_pct": 50, "mil_pct": 30, "grant": {"سکه": 2500}, "econ_levels": 3, "mil_levels": 2},
    {"cat": "starter", "fa": "استارتر برنزی", "en": "Bronze Starter", "price": "150T",
     "econ_pct": 40, "mil_pct": 20, "grant": {"سکه": 1500}, "econ_levels": 2, "mil_levels": 1},
    # ---- پک منابع ----
    {"cat": "resources", "fa": "پک منابع طلایی", "en": "Gold Resource Pack", "price": "300T",
     "grant": {"سکه": 4000, "چوب": 400, "آهن": 300, "سنگ": 300, "پوشاک": 300, "باروت": 500}},
    {"cat": "resources", "fa": "پک منابع نقره‌ای", "en": "Silver Resource Pack", "price": "200T",
     "grant": {"سکه": 3000, "چوب": 300, "آهن": 200, "سنگ": 200, "پوشاک": 200, "باروت": 300}},
    {"cat": "resources", "fa": "پک منابع برنزی", "en": "Bronze Resource Pack", "price": "150T",
     "grant": {"سکه": 2000, "چوب": 150, "آهن": 150, "سنگ": 200, "پوشاک": 100, "باروت": 200}},
    # ---- پک ارتش (ترکیب را ادمین اصلی تعیین می‌کند) ----
    {"cat": "army", "fa": "پک ارتش طلایی", "en": "Gold Army Pack", "price": "250T",
     "budget": {"پیاده": 1000, "سواره": 500, "ویژه": 300, "توپخانه": 40, "کشتی": 30}},
    {"cat": "army", "fa": "پک ارتش نقره‌ای", "en": "Silver Army Pack", "price": "200T",
     "budget": {"پیاده": 750, "سواره": 300, "ویژه": 200, "توپخانه": 20, "کشتی": 20}},
    {"cat": "army", "fa": "پک ارتش برنزی", "en": "Bronze Army Pack", "price": "150T",
     "budget": {"پیاده": 500, "سواره": 150, "ویژه": 100, "توپخانه": 15, "کشتی": 15}},
    # ---- تسلیحات (تجهیز ۲۰۰ نیروی دلخواه) ----
    _u("weapon", "تفنگ سرپر", "Blunderbuss", 200, 0, 4, "100T"),
    _u("weapon", "تپانچه چرخ‌دار", "Wheellock Pistol", 200, 0, 4, "100T"),
    # ---- فرمانده / هیرو ----
    _h("ویلیام کاوندیش", "William Cavendish", "350T",
       [(5, "افسر"), (50, "پیاده نظام سلطنتی انگلیس"), (50, "سوارنظام تفنگدار"), (2, "توپخانه سلطنتی")]),
    _h("رابرت دیورو", "Robert Devereux", "350T",
       [(5, "افسر"), (2, "توپ کولورین"), (50, "گرنادیر گارد"), (50, "سوارنظام ایرلندی")]),
    _h("الکساندر لزلی", "Alexander Leslie", "300T",
       [(5, "افسر"), (50, "شمشیرزن هایلند"), (50, "پیاده نظام اسکاتلندی")]),
    _h("دیوید لزلی", "David Leslie", "300T", [(5, "افسر"), (100, "سوارنظام اسکاتلندی")]),
    _h("جیمز گراهام", "James Graham", "250T", [(3, "توپ کولورین"), (100, "سوارنظام ایرلندی")]),
    _h("هانری دولا", "Henri de La", "350T",
       [(2, "توپ فرانسوی"), (50, "موسکتیر فرانسوی"), (50, "سوار نارنجک انداز"), (50, "پیاده نظام نخبه فرانسوی")]),
    _h("لویی دوم دو بوربون", "Louis II de Bourbon", "250T",
       [(50, "ژاندارم فرانسوی"), (2, "توپ فرانسوی"), (50, "پیاده نظام نخبه فرانسوی")]),
    _h("توماس پرستون", "Thomas Preston", "300T",
       [(2, "توپ کولورین"), (50, "چریک هلندی"), (50, "تفنگدار ایرلندی")]),
    _h("جیمز باتلر", "James Butler", "250T", [(5, "افسر"), (50, "گرنادیر گارد"), (50, "نگهبانان هلندی")]),
    _h("سر آرتور آستون", "Sir Arthur Aston", "300T",
       [(50, "پیاده نظام سلطنتی"), (50, "تک تیرانداز اسپانیایی"), (2, "توپخانه سلطنتی")]),
    _h("سر آرتور هسلریگ", "Sir Arthur Hesilrige", "300T", [(50, "آیرون سایدها"), (50, "پیاده نظام سلطنتی")]),
    _h("سر جان هیدون", "Sir John Heydon", "300T",
       [(2, "توپ ریگا"), (2, "توپخانه سلطنتی انگلیس"), (2, "خمپاره انداز")]),
    _h("جیمز ویمیس", "James Wemyss", "300T", [(2, "توپ هلندی"), (2, "توپ سوئدی"), (2, "توپ کولورین")]),
    _h("فیلبرت امانوئل", "Philbert Emmanuel", "300T", [(5, "توپ فرانسوی")]),
    _h("ویلیام بتن", "William Batten", "250T", [(1, "کشتی فلگشیپ دانمارکی"), (1, "کشتی بریگانتین سوئدی")]),
    _h("ادوارد پوفام", "Edward Popham", "300T", [(1, "کاراک پرتغالی"), (1, "کشتی سلطنتی")]),
    _h("سر جان لاوسون", "Sir John Lawson", "250T", [(1, "کشتی سلطنتی اسپانیا"), (1, "کشتی گرگ یخی")]),
    _h("چارلز وست‌وود", "Charles Westwood", "اختصاصی VIP کرامول",
       [(5, "افسر"), (100, "کلداستریم گارد"), (50, "رایفلدار مدرن")]),
    _h("جیمز هانتینگتون", "James Huntington", "اختصاصی VIP چارلز اول",
       [(5, "افسر"), (100, "کلداستریم گارد انگلیسی"), (50, "گرنادیر گارد")]),
    _h("دکلن اورورک", "Declan O'Rourke", "350T",
       [(5, "افسر"), (100, "پیاده نظام ایرلندی"), (50, "رایفلدار ایرلندی")]),
    _h("شان اوکانل", "Sean O'Connell", "350T", [(5, "افسر"), (100, "سوارنظام ایرلندی")]),
    _h("گاسپار کولینی", "Gaspard de Coligny", "350T",
       [(100, "گارد پادشاهی فرانسه"), (50, "سوار کیوراسیر"), (3, "مورتار سلطنتی فرانسه")]),
    _h("آبراهام دوکن", "Abraham Duquesne", "350T", [(1, "کاراک پرتغالی"), (1, "ناو سلطنتی فرانسه")]),
    _h("آمادور دو لاپورت", "Amador de La Porte", "350T", [(1, "کشتی سلطنتی فرانسه"), (1, "کشتی گرگ یخی")]),
    _h("ایوان کمپبل", "Ewan Campbell", "350T", [(150, "نیروی کمپبل")]),
    _h("ریچارد اشفورد", "Richard Ashford", "350T",
       [(5, "افسر"), (100, "سواره نظام انگلیسی"), (50, "سواره نظام سبک"), (30, "تفنگدار سواره")]),
    _h("رابرت اشکروفت", "Robert Ashcroft", "350T",
       [(5, "افسر"), (100, "گارد کلداستریم"), (50, "تفنگدار مدرن")]),
    _h("سر ناتانیل ویت‌مور", "Sir Nathaniel Whitmore", "350T",
       [(5, "افسر"), (100, "کلداستریم"), (5, "توپ سنگین")]),
    _h("آدرین دو مونتکلر", "Adrien de Montclair", "350T",
       [(100, "کلداستریم"), (50, "نگهبانان هلندی"), (50, "سواران کمپل")]),
    _h("لوسین دو والرو", "Lucien de Valero", "350T",
       [(2, "توپ فرانسوی"), (2, "توپ تندر"), (2, "خمپاره انداز")]),
    _h("ریچارد بلک‌ثورن", "Richard Blackthorn", "350T", [(1, "کشتی گرگ یخی"), (1, "کشتی سلطنتی اسپانیا")]),
    _h("ادوارد وینچستر", "Edward Winchester", "350T", [(6, "توپ ویرانگر")]),
    # ---- وزیر ----
    {"cat": "minister", "fa": "ادوارد هاید", "en": "Edward Hyde", "price": "250T"},
    {"cat": "minister", "fa": "شارل دو لرم", "en": "Charles de Lorraine", "price": "200T"},
    {"cat": "minister", "fa": "ویلیام جکسون", "en": "William Juxon", "price": "250T"},
    {"cat": "minister", "fa": "کلود بوتیه", "en": "Claude Bouthillier", "price": "250T"},
    {"cat": "minister", "fa": "ادوارد نیکلاس", "en": "Edward Nicholas", "price": "250T"},
    {"cat": "minister", "fa": "فرانسوا دو وال", "en": "François du Val", "price": "200T"},
    {"cat": "minister", "fa": "ویلیام لاود", "en": "William Laud", "price": "250T"},
    {"cat": "minister", "fa": "جان برام‌هال", "en": "John Bramhall", "price": "250T"},
    {"cat": "minister", "fa": "رابرت سدنی", "en": "Robert Sidney", "price": "300T"},
    {"cat": "minister", "fa": "توماس ونت‌ورث", "en": "Thomas Wentworth", "price": "350T"},
    {"cat": "minister", "fa": "سر جان کولپپر", "en": "Sir John Culpeper", "price": "350T"},
    # ---- گروهک مزدور (ارتش یک‌بار) ----
    _h("سپاه هایلند اسکاتلند", "Scottish Highland Host", "300T",
       [(100, "پیاده نظام اسکاتلندی"), (100, "جنگجویان هایلند"), (75, "سوارنظام اسکاتلندی"),
        (5, "توپخانه اسکاتلندی")], cat="merc_group"),
    _h("لژیون طلایی اسپانیا", "Spanish Golden Legion", "300T",
       [(100, "ترسیو"), (100, "آرکبوزدار"), (100, "پیکمن اسپانیایی"), (50, "سواره نظام اسپانیایی"),
        (5, "توپخانه سلطنتی محاصره")], cat="merc_group"),
    _h("شیرهای جمهوری هلند", "Lions of the Dutch Republic", "300T",
       [(100, "تفنگدار هلندی"), (100, "پیکمن ایالتی"), (100, "کارابین‌داران"), (50, "گارد آبی"),
        (50, "سوارنظام هلندی")], cat="merc_group"),
    _h("گرگ‌های دریای شمال", "Wolves of the Northern Seas", "300T",
       [(100, "ملوان هلندی"), (100, "تفنگدار دریایی"), (50, "قلابداران دریایی"), (2, "کشتی گرگ یخی"),
        (8, "قایق عادی")], cat="merc_group"),
    _h("ناوگان سلطنتی دانمارک", "Royal Danish Fleet", "300T",
       [(100, "ملوان دانمارکی"), (100, "لژیون دانمارکی"), (2, "کشتی فلگشیپ دانمارکی"), (50, "محافظان عرشه"),
        (5, "قایق عادی")], cat="merc_group"),
    _h("شکارچیان دریای شمال", "Hunters of the Northern Seas", "300T",
       [(100, "ملوان"), (100, "یورشگر"), (50, "تفنگدار دریایی"), (100, "کمانداران ساحلی"),
        (2, "کشتی بریگانتین سوئدی"), (8, "قایق عادی")], cat="merc_group"),
    _h("لژیون توپخانه اروپا", "European Artillery Legion", "300T",
       [(8, "توپ چرمی سوئدی"), (6, "توپ نیمه‌سنگین آلمانی"), (6, "توپ دریایی هلندی")], cat="merc_group"),
    _h("طایفه والاس اسکاتلند", "Wallace Scottish Clan", "300T",
       [(100, "چریک فریزر"), (50, "سوار مرزی"), (100, "تبرکش والاس"), (100, "تیرانداز گلن"),
        (100, "سپردار طوایف")], cat="merc_group"),
    # ---- یونیت مزدور (تعداد یک‌بار + بازدهی هر آپ) ----
    _u("merc", "چریک هلندی", "Dutch Guerrillas", 200, 100, 3, "200T"),
    _u("merc", "تک‌تیرانداز اسپانیایی", "Spanish Sharpshooter", 200, 100, 1, "200T"),
    _u("merc", "سوار نارنجک‌انداز فرانسوی", "French Grenadier Cavalry", 200, 100, 0, "200T"),
    _u("merc", "سواره‌نظام ایرلندی", "Irish Cavalry", 200, 100, 3, "200T"),
    _u("merc", "نگهبانان هلندی", "Dutch Guards", 200, 100, 3, "200T"),
    _u("merc", "سواران کمپل", "Campbell Riders", 200, 100, 3, "200T"),
    _u("merc", "توپ ریگای سوئدی", "Swedish Regimental Cannon", 8, 3, 0, "200T"),
    _u("merc", "کاراک پرتغالی", "Portuguese Carrack", 3, 2, 2, "200T"),
    _u("merc", "ناوگان سلطنتی اسپانیا", "Spanish Royal Fleet", 3, 2, 1, "200T"),
    _u("merc", "مورتار سلطنتی فرانسه", "Mortier Royal", 5, 2, 0, "اختصاصی فرانسه"),
    _u("merc", "توپ ویرانگر", "Devastator Cannon", 5, 2, 1, "200T"),
    _u("merc", "توپ تندر", "Thunder Cannon", 5, 2, 3, "200T"),
    # ---- جاسوس ----
    _u("spy", "محرمان ونیزی", "Venetian Confidants", 100, 50, 2, "200T"),
    _u("spy", "مأموران مخفی فرانسه", "French Secret Agents", 100, 50, 2, "200T"),
    _u("spy", "قاتلان مخفی", "Royal English Intelligencers", 100, 50, 2, "200T"),
    _u("spy", "سایه‌های مرگ", "Imperial Informers", 100, 50, 2, "200T"),
    # ---- گارد ----
    _u("guard", "نگهبانان تاج", "Guardians of the Crown", 100, 50, 1, "150T"),
    _u("guard", "محافظان قلمرو", "Wardens of the Realm", 100, 50, 2, "150T"),
    _u("guard", "گارد سایه", "Shadow Guard", 100, 50, 2, "150T"),
    _u("guard", "نگهبانان دریا", "Guardians of the Sea", 100, 50, 1, "150T"),
    _u("guard", "گارد اسکاتلندی", "Scottish Guard", 100, 50, 1, "150T"),
]


# ---- محدودیت خرید (قوانین شاپ بند ۴ + اعلام ۹/۲۹: کاراکتر ۳) ----
LIMITS = {
    "starter": 1,
    "resources": 1,
    "army_weapon": 1,   # «۱ پک تسلیحات و ارتش»
    "characters": 3,    # هیرو + وزیر (قبلاً ۲؛ به ۳ افزایش یافت)
    "mercs": 3,         # گروهک + یونیت مزدور
    "merc_groups": 2,
}
DOWN_PAYMENT_PCT = 30
SETTLE_DAYS = 14
CANCEL_HOURS = 24


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("أ", "ا").replace("آ", "ا")
    s = re.sub(r"[ً-ْٰ]", "", s)  # اعراب (ِ ُ ْ …)
    s = s.replace("سواره", "سوار").replace("é", "e").replace("ç", "c")
    return re.sub(r"[\s‌\-_|:'’.،,()]+", "", s)


_INDEX = sorted(
    ((_norm(key), item) for item in CATALOG for key in (item["fa"], item["en"]) if key),
    key=lambda kv: -len(kv[0]),
)


def find_item(text: str):
    """آیتم کاتالوگ که نامش (فارسی یا انگلیسی) در متن آمده — طولانی‌ترین تطابق."""
    t = _norm(text)
    if not t:
        return None
    for key, item in _INDEX:
        if key and key in t:
            return item
    return None


_POST_PREFIX = {
    "hero": "فرمانده", "minister": "وزیر", "merc_group": "گروهک مزدوری",
    "merc": "مزدور", "spy": "جاسوس", "guard": "گارد",
}


def collapse_shop_posts(body: str):
    """
    پست‌های فورواردشده‌ی کانال شاپ («《 #فرمانده 》 …» با معرفی و قابلیت‌ها) را به یک خط
    استاندارد تبدیل می‌کند تا خطوط توضیح، پک جعلی نشوند. نام فقط از خط تگ و خط بعدش خوانده می‌شود
    (متن معرفی گاهی نام آیتم دیگری را دارد). خروجی: (متن، لیست پست‌های ناشناخته)
    """
    out, unknown = [], []
    lines = (body or "").splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if "《" not in ln:
            out.append(ln)
            i += 1
            continue
        # پست تا خط «قیمت» (یا پست بعدی) ادامه دارد؛ خطوط بعد از قیمت پک‌های جدا هستند
        j = i + 1
        while j < len(lines) and "《" not in lines[j]:
            j += 1
            if "قیمت" in lines[j - 1]:
                break
        seg = lines[i:j]
        head = ln.split("》", 1)[-1]
        nxt = next((s for s in seg[1:] if s.strip()), "")
        item = find_item(head) or find_item(nxt)
        if item:
            pre = _POST_PREFIX.get(item["cat"])
            out.append(f"{pre} {item['fa']}" if pre else item["fa"])
        else:
            unknown.append((head.strip() or nxt.strip())[:60])
        i = j
    return "\n".join(out), unknown


def one_time_grant(item: dict) -> dict:
    """آنچه یک‌بار هنگام خرید به دارایی اضافه می‌شود."""
    cat = item.get("cat")
    if cat in ("merc", "spy", "guard"):
        return {item["fa"]: item["count"]}
    if cat in ("hero", "merc_group"):
        out = {}
        for n, u in item.get("army") or []:
            out[u] = out.get(u, 0) + n
        return out
    if cat in ("resources", "starter"):
        return dict(item.get("grant") or {})
    return {}


def admin_note(item: dict) -> str:
    """کارهایی که ربات خودکار انجام نمی‌دهد و ادمین باید اعمال کند."""
    cat = item.get("cat")
    if cat == "vip":
        return f"+{item['econ_pct']}٪ دارایی اقتصادی و +{item['mil_pct']}٪ دارایی نظامی، ۲ باف ویژه (دستی)"
    if cat == "starter":
        s = (f"+{item['econ_pct']}٪ اقتصادی، +{item['mil_pct']}٪ نظامی، "
             f"{item['econ_levels']} لول اقتصادی و {item['mil_levels']} لول نظامی (دستی)")
        if item.get("ability"):
            s += "، ۱ توانایی اختصاصی"
        return s
    if cat == "army":
        b = item.get("budget") or {}
        return "ترکیب با ادمین اصلی: " + "، ".join(f"{k} {v}" for k, v in b.items())
    if cat == "weapon":
        return f"تجهیز {item['count']} نیروی دلخواه (دستی)"
    return ""


def limit_bucket(kind: str):
    return {
        "starter": "starter", "resources": "resources",
        "army": "army_weapon", "weapon": "army_weapon",
        "hero": "characters", "minister": "characters",
        "merc_group": "mercs", "merc": "mercs",
    }.get(kind)


def limit_warnings(kinds: list) -> list:
    """هشدار عبور از سقف خرید یک بازیکن (لیست دسته‌ی پک‌های ثبت‌شده)."""
    cnt = {}
    for k in kinds:
        b = limit_bucket(k)
        if b:
            cnt[b] = cnt.get(b, 0) + 1
    groups = sum(1 for k in kinds if k == "merc_group")
    units = sum(1 for k in kinds if k == "merc")
    warns = []
    labels = {"starter": "پک استارتر", "resources": "پک منابع", "army_weapon": "پک تسلیحات/ارتش",
              "characters": "کاراکتر (هیرو + وزیر)"}
    for b, lbl in labels.items():
        if cnt.get(b, 0) > LIMITS[b]:
            warns.append(f"{lbl}: {cnt[b]} از سقف {LIMITS[b]}")
    if groups + units > LIMITS["mercs"] or groups > LIMITS["merc_groups"] or 2 * groups + units > 4:
        warns.append(
            f"مزدور: {groups} گروهک + {units} یونیت — مجاز: ۱ گروهک+۲ یونیت، ۲ گروهک، یا ۳ یونیت"
        )
    return warns
