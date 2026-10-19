"""باف/نرف قلعه‌ها طبق کانال اطلاعات بازی."""

from app.state import CITY_BUFFS


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
