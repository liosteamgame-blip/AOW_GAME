"""سایدها، نام شهرها، نام‌های مستعار و تطبیق شهر."""
import re
import secrets

from app.config import ADMIN_CODE, CODE_PREFIX
from app.state import CITY_ASSETS, GROUPS, PLAYER_CODES, authenticated_users
from app.utils import _norm_country_token, norm_cmd


def gen_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = CODE_PREFIX + "".join(secrets.choice(alphabet) for _ in range(5))
        if code not in PLAYER_CODES and code != ADMIN_CODE:
            return code
COUNTRY_ALIASES = {
    # دو جناح انگلیس
    "monarchist": {
        "مونارشیست", "مونارش", "پادشاهی", "پادشاهیخواه", "رویالیست",
        "monarchist", "monarch", "royal", "royalist", "king",
    },
    "parliamentarian": {
        "پارلمانری", "پارلمان", "پارلمانتاریان", "جمهوریخواه",
        "parliamentarian", "parliament", "parliamentary", "roundhead",
    },
    # سازگاری با نام قدیمی england در شهر/آرت
    "england": {
        "انگلستان", "انگلیس", "بریتانیا", "بریتانیایکبیر", "انگلند",
        "england", "engeland", "englend", "britain", "greatbritain", "uk", "eng",
    },
    "france": {
        "فرانسه", "فرانسوی", "france", "franse", "fransa", "fran",
    },
    "ireland": {
        "ایرلند", "ایرلندی", "ireland", "ire", "eire", "éire",
    },
}
# چهار ساید رسمی (انگلیس = مونارشیست + پارلمانری)
FACTIONS = ("monarchist", "parliamentarian", "france", "ireland")

# آرت فایل‌ها هنوز با england برچسب خورده‌اند
ART_FACTION_MAP = {
    "monarchist": "england",
    "parliamentarian": "england",
    "england": "england",
    "france": "france",
    "ireland": "ireland",
}

# پارلمانری: ۱۰ شهر مشخص — بقیه انگلیس = مونارشیست
DEFAULT_CITIES = [
    # Parliamentarian
    "norwich_parliamentarian",
    "leeds_parliamentarian",
    "dover_parliamentarian",
    "winchester_parliamentarian",
    "bridgwater_parliamentarian",
    "exeter_parliamentarian",
    "york_parliamentarian",
    "gloucester_parliamentarian",
    "newcastle_parliamentarian",
    "manchester_parliamentarian",
    "celtic_parliamentarian",
    # Monarchist (بقیه انگلیس)
    "london_monarchist",
    "cambridge_monarchist",
    "leicester_monarchist",
    "bristol_monarchist",
    "edinburgh_monarchist",
    "glasgow_monarchist",
    "oxford_monarchist",
    "colchester_monarchist",
    "pembroke_monarchist",
    "liverpool_monarchist",
    "nottingham_monarchist",
    # Ireland
    "dublin_ireland",
    "armagh_ireland",
    "limerick_ireland",
    "waterford_ireland",
    "cork_ireland",
    # France
    "amiens_france",
    "nantes_france",
    "brest_france",
    "paris_france",
    "caen_france",
    "montauban_france",
]


def seed_default_cities():
    """شهرهای پیش‌فرضِ گمشده را اضافه می‌کند (نام تکراری را رد می‌کند)."""
    existing = {str(v).lower() for v in PLAYER_CODES.values()}
    n = 0
    for name in DEFAULT_CITIES:
        if name.lower() in existing:
            continue
        code = gen_code()
        while code in PLAYER_CODES:
            code = gen_code()
        PLAYER_CODES[code] = name
        existing.add(name.lower())
        n += 1
    return n


def _canonical_city_name(name: str) -> str:
    """
    نام شهر را به فرم رسمی می‌برد:
    oxford_england / آکسفورد_انگلیس → oxford_monarchist
    norwich_england → norwich_parliamentarian
    اگر از قبل monarchist/parliamentarian/france/ireland باشد همان می‌ماند.
    """
    if not name:
        return name
    raw = str(name).strip()
    # اگر از قبل پسوند درست دارد
    ck = country_key(raw)
    if ck in ("monarchist", "parliamentarian", "france", "ireland"):
        # اگر پسوند england قدیمی بود، country_key درست برمی‌گرداند ولی نام را عوض کن
        low = raw.lower().replace("ي", "ی")
        if low.endswith("_england") or low.endswith("_انگلیس") or low.endswith("_انگلستان"):
            base = raw.rsplit("_", 1)[0]
            base_l = _norm_country_token(base)
            parl = {_norm_country_token(x) for x in PARLIAMENT_CITY_BASES}
            suffix = "parliamentarian" if base_l in parl else "monarchist"
            # نام پایه را انگلیسی نگه دار اگر در DEFAULT هست
            eng_base = None
            for c in DEFAULT_CITIES:
                if c.endswith(f"_{suffix}") and _norm_country_token(c.rsplit("_", 1)[0]) == base_l:
                    eng_base = c.rsplit("_", 1)[0]
                    break
            return f"{eng_base or base}_{suffix}"
        return raw
    # بدون پسوند شناخته‌شده
    base_l = _norm_country_token(raw.split("_")[0] if "_" in raw else raw)
    for c in DEFAULT_CITIES:
        if _norm_country_token(c.rsplit("_", 1)[0]) == base_l:
            return c
    return raw


def migrate_city_names():
    """
    شهرهای قدیمی *_england را به monarchist/parliamentarian تبدیل می‌کند.
    داده (کد، گروه، دارایی، بازیکن) حفظ می‌شود؛ فقط نام شهر عوض می‌شود.
    """
    changed = 0

    # PLAYER_CODES: code -> city
    for code, city in list(PLAYER_CODES.items()):
        new = _canonical_city_name(city)
        if new != city:
            PLAYER_CODES[code] = new
            changed += 1

    # CITY_ASSETS keys
    for city in list(CITY_ASSETS.keys()):
        new = _canonical_city_name(city)
        if new != city:
            if new in CITY_ASSETS:
                # ادغام: متن جدیدتر ترجیح / نگه داشتن هر دو اگر متفاوت
                old_e = CITY_ASSETS.pop(city)
                if not CITY_ASSETS[new].get("text") and old_e.get("text"):
                    CITY_ASSETS[new] = old_e
            else:
                CITY_ASSETS[new] = CITY_ASSETS.pop(city)
            changed += 1

    # GROUPS
    for gid, g in list(GROUPS.items()):
        city = g.get("city")
        if city:
            new = _canonical_city_name(city)
            if new != city:
                g["city"] = new
                changed += 1

    # authenticated_users
    for uid, u in list(authenticated_users.items()):
        city = u.get("country") or u.get("city") or u.get("name")
        if city:
            new = _canonical_city_name(str(city))
            if new != city:
                if "country" in u:
                    u["country"] = new
                if "city" in u:
                    u["city"] = new
                if "name" in u and u["name"] == city:
                    u["name"] = new
                changed += 1

    # حذف شهرهای تکراری هم‌نام در PLAYER_CODES (همان نام با کدهای مختلف)
    seen = {}
    for code, city in list(PLAYER_CODES.items()):
        key = city.lower()
        if key in seen:
            # کد قدیمی‌تر را نگه دار؛ این را حذف نکن اگر به بازیکن وصل است
            pass
        else:
            seen[key] = code

    return changed


# شهرهای پایهٔ پارلمانری (برای تشخیص پسوند england قدیمی)
PARLIAMENT_CITY_BASES = {
    "norwich", "leeds", "dover", "winchester", "bridgwater", "bridgewater",
    "exeter", "york", "gloucester", "newcastle", "manchester", "celtic",
    "نورویچ", "لیدز", "دوور", "وینچستر", "بریجواتر", "بریجوایتر",
    "اکستر", "یورک", "گلاستر", "نیوکاسل", "نیوکسل", "منچستر", "سلتیک",
}

# نسخه‌ی نرمال‌شده‌ی نام‌ها — یک‌بار ساخته می‌شود نه در هر فراخوانی country_key
_ALIASES_NORM = {k: {_norm_country_token(n) for n in v} for k, v in COUNTRY_ALIASES.items()}
_PARLIAMENT_BASES_NORM = {_norm_country_token(x) for x in PARLIAMENT_CITY_BASES}


def country_key(city):
    """
    از نام شهر (مثل london_monarchist / norwich_parliamentarian / dublin_ireland)
    ساید را برمی‌گرداند: monarchist | parliamentarian | france | ireland
    فقط پسوند/کلید دقیق — نه substring کوتاه مثل ire/fran/king
    """
    if not city:
        return None
    raw = _norm_country_token(city)
    parts = raw.split("_") if "_" in raw else [raw]
    suffix = parts[-1]
    base = parts[0]

    # ۱) پسوند دقیق
    for key in ("monarchist", "parliamentarian", "france", "ireland"):
        if suffix == key or suffix in _ALIASES_NORM[key]:
            return key

    # ۲) نام کامل کلید داخل نام شهر (حداقل طول ۴ تا اشتباه نشود)
    for key in ("parliamentarian", "monarchist", "ireland", "france"):
        if key in raw:
            return key
        for nn in _ALIASES_NORM[key]:
            if len(nn) >= 5 and nn in raw:
                return key

    # ۳) پسوند england قدیمی
    if suffix in _ALIASES_NORM["england"] or suffix == "england":
        if _norm_country_token(base) in _PARLIAMENT_BASES_NORM:
            return "parliamentarian"
        return "monarchist"
    return None


FACTION_META = {
    "monarchist": ("👑", "مونارشیست"),
    "parliamentarian": ("🏛", "پارلمانری"),
    "france": ("🇫🇷", "فرانسه"),
    "ireland": ("🇮🇪", "ایرلند"),
}


def cities_by_faction(faction=None):
    """لیست شهرها؛ اگر faction داده شود فقط همان فکشن."""
    all_c = sorted({str(v) for v in PLAYER_CODES.values()}, key=lambda s: s.lower())
    if not faction:
        return all_c
    return [c for c in all_c if country_key(c) == faction]


def city_by_index(idx: int, faction: str = None):
    if faction == "other":
        cities = [c for c in cities_by_faction() if country_key(c) not in FACTION_META]
    elif faction:
        cities = cities_by_faction(faction)
    else:
        cities = cities_by_faction()
    if 0 <= idx < len(cities):
        return cities[idx]
    return None


def cities_of_side(side: str):
    return cities_by_faction(side)


def cities_for_side_assets(side: str):
    """
    شهرهای یک ساید برای دارایی/جمع:
    ترکیب شهرهای ثبت‌شده در PLAYER_CODES + کلیدهای CITY_ASSETS همان ساید.
    هرگز شهر ساید دیگر را برنمی‌گرداند.
    """
    if not side:
        return []
    names = set(cities_by_faction(side))
    for c in CITY_ASSETS:
        if country_key(c) == side:
            names.add(c)
    return sorted(names, key=lambda s: str(s).lower())


# ======================================================================
#                    سیستم هشدار تهدید + مشاور ارتقا
# ======================================================================
def all_known_cities():
    names = set(str(v) for v in PLAYER_CODES.values())
    names |= set(CITY_ASSETS.keys())
    for g in GROUPS.values():
        if g.get("city"):
            names.add(str(g["city"]))
    return names


def match_registered_cities(raw: str) -> list:
    """تطبیق متن مقصد/هدف با شهرهای ثبت‌شده (انگلیسی/فارسی)."""
    if not raw:
        return []
    text = str(raw).strip()
    # «آمیان از فرانسه» / «amiens from france»
    text = re.sub(r"\s+از\s+", "_", text)
    text = re.sub(r"\s+from\s+", "_", text, flags=re.I)
    norm = _norm_country_token(text)
    hits = []
    for city in all_known_cities():
        cn = _norm_country_token(city)
        base = cn.split("_")[0] if "_" in cn else cn
        if not base:
            continue
        if cn == norm or base == norm:
            hits.append(city)
            continue
        if base in norm or cn in norm:
            hits.append(city)
            continue
        # تطبیق سست روی بخش اول مقصد
        dest_base = norm.split("_")[0] if "_" in norm else norm
        if dest_base and len(dest_base) >= 3 and (dest_base in base or base in dest_base):
            hits.append(city)
    # یکتا
    seen, out = set(), []
    for c in hits:
        k = c.lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


# ---- ست / حذف لیدر ساید ----
_SIDE_ALIASES = {
    # مونارشیست
    "monarchist": "monarchist", "monarch": "monarchist", "royal": "monarchist",
    "royalist": "monarchist", "king": "monarchist",
    "مونارشیست": "monarchist", "مونارش": "monarchist",
    "پادشاهی": "monarchist", "پادشاهیخواه": "monarchist", "رویالیست": "monarchist",
    # پارلمانری
    "parliamentarian": "parliamentarian", "parliament": "parliamentarian",
    "parliamentary": "parliamentarian", "roundhead": "parliamentarian",
    "پارلمانری": "parliamentarian", "پارلمان": "parliamentarian",
    "پارلمانتاریان": "parliamentarian",
    # فرانسه / ایرلند
    "france": "france", "فرانسه": "france",
    "ireland": "ireland", "ایرلند": "ireland",
}


def _resolve_side_token(tok: str):
    if not tok:
        return None
    t = tok.strip().lower().replace("ي", "ی").replace("ك", "ک")
    # انگلیس مبهم است → باید مونارشیست یا پارلمانری مشخص شود
    if re.search(r"(انگلیس|انگلستان|\bengland\b)", t):
        if not re.search(r"(مونارش|پارلمان|monarch|parliament|royal)", t):
            return None
    if t in _SIDE_ALIASES:
        return _SIDE_ALIASES[t]
    for alias, side in sorted(_SIDE_ALIASES.items(), key=lambda x: -len(x[0])):
        a = alias.lower().replace("ي", "ی")
        if len(a) >= 3 and a in t:
            return side
    return None


def _parse_leader_cmd(text: str):
    """برمی‌گرداند ('set'|'del', side|None) یا (None, None)."""
    raw = (text or "").strip()
    n = norm_cmd(raw)
    if n in ("حذف‌لیدر", "حذفلیدر", "removeleader", "delleader", "unsetleader", "حذف لیدر"):
        return "del", None
    # فقط دستورهای ست لیدر
    if not re.match(
        r"^[/\\]?\s*(ست\s*لیدر|ستلیدر|set\s*leader|setleader)\b",
        raw,
        re.I | re.U,
    ):
        return None, None
    # ساید از کل متن
    side = _resolve_side_token(raw)
    if side:
        return "set", side
    # توکن‌به‌توکن
    parts = re.split(r"[\s/_-]+", re.sub(r"^[/\\]", "", raw))
    for tok in reversed(parts):
        side = _resolve_side_token(tok)
        if side and side in FACTIONS:
            return "set", side
    return "set", None
