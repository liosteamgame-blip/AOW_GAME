"""انتخاب و ارسال آرت پست‌ها از assets/art.zip."""
import logging
import os
import re
import secrets
import zipfile

from aiogram.types import BufferedInputFile, FSInputFile

from app.config import ART_DIR, ART_ZIP
from app.loader import bot
from app.factions import ART_FACTION_MAP, country_key


# ---------------- آرت پست‌ها ----------------
# نام فایل‌ها:  art_<نوع>_<land|sea|all>_<کشور|all>_<شماره>.jpg
#   نوع = campaign | war | siege | ambush | trade
#   کشور = england | france | ireland | all
#   مثال:
#     art_campaign_land_england_1.jpg
#     art_campaign_sea_france_2.jpg
#     art_war_land_ireland_1.jpg
#     art_trade_land_all_1.jpg
#     art_campaign_land_all_1.jpg   ← عمومی (فقط اگر فکشن پیدا نشد)
ART_RE = re.compile(
    r"^(?:.*/)?art_(campaign|siege|war|ambush|trade)_(land|sea|all)_([a-z]+)_\d+\.(?:jpe?g|png)$",
    re.I,
)

ART = {}            # (نوع، land/sea/all) -> {کشور: [آرت‌ها]}
_file_ids = {}      # آرت -> file_id تلگرام (بعد از اولین ارسال دیگر آپلود نمی‌شود)


def _add_art(name, entry):
    base = os.path.basename(name)
    m = ART_RE.match(name) or ART_RE.match(base)
    if m:
        kind, typ, country = (x.lower() for x in m.groups())
        ART.setdefault((kind, typ), {}).setdefault(country, []).append(entry)


def load_art():
    ART.clear()
    if os.path.isfile(ART_ZIP):
        try:
            with zipfile.ZipFile(ART_ZIP) as z:
                for n in z.namelist():
                    if n.endswith("/") or n.startswith("__"):
                        continue
                    _add_art(n, ("zip", n))
        except Exception:
            logging.exception("خواندن art.zip ناموفق بود.")
    if os.path.isdir(ART_DIR):
        for n in sorted(os.listdir(ART_DIR)):
            _add_art(n, ("file", os.path.join(ART_DIR, n)))
    total = sum(len(v) for g in ART.values() for v in g.values())
    eng = sum(len(group.get("england", [])) for group in ART.values())
    fra = sum(len(group.get("france", [])) for group in ART.values())
    ire = sum(len(group.get("ireland", [])) for group in ART.values())
    logging.info("آرت‌های بارگذاری‌شده: %s | england=%s france=%s ireland=%s",
                 total, eng, fra, ire)


def art_country_key(city):
    """برای انتخاب آرت: هر دو جناح انگلیس → england."""
    side = country_key(city)
    return ART_FACTION_MAP.get(side, side)


def _pool(kind, typ, country=None):
    group = ART.get((kind, typ), {})
    if country is None:
        return [x for arts in group.values() for x in arts]
    return list(group.get(country, []))


def pick_art(kind, mtype=None, city=None):
    """
    آرت فکشن‌محور:
    1) آرت مخصوص همان فکشن + همان نوع (land/sea)
    2) آرت مخصوص فکشن با typ=all
    3) آرت عمومی all
    هرگز آرت فکشن دیگر را جایگزین نمی‌کند.
    دو جناح انگلیس هر دو از آرت england استفاده می‌کنند.
    """
    country = art_country_key(city)
    typ = mtype if mtype in ("land", "sea") else "all"

    if kind == "ambush":
        chains = [("ambush", "all"), ("ambush", typ)]
    elif kind == "trade":
        # تجارت فقط آرت مخصوص خودش — fallback به campaign همان نوع
        chains = [("trade", typ), ("trade", "all"), ("campaign", typ), ("campaign", "all")]
    else:
        chains = [(kind, typ)]
        if typ != "all":
            chains.append((kind, "all"))
        if kind == "siege":
            chains.append(("war", typ))
            chains.append(("war", "all"))
        if typ == "sea" and kind != "campaign":
            chains.append(("campaign", "sea"))

    for k, t in chains:
        if country:
            pool = _pool(k, t, country)
            if pool:
                return secrets.choice(pool)
        pool = _pool(k, t, "all")
        if pool:
            return secrets.choice(pool)
    return None


def _art_media(entry):
    cached = _file_ids.get(entry)
    if cached:
        return cached
    src, path = entry
    if src == "zip":
        with zipfile.ZipFile(ART_ZIP) as z:
            return BufferedInputFile(z.read(path), filename=os.path.basename(path))
    return FSInputFile(path)


async def send_art(chat_id, entry, caption, markup=None, reply_parameters=None):
    try:
        sent = await bot.send_photo(chat_id=chat_id, photo=_art_media(entry), caption=caption,
                                    reply_markup=markup, reply_parameters=reply_parameters)
    except Exception:
        if entry not in _file_ids:
            raise
        _file_ids.pop(entry, None)           # file_id قدیمی بود؛ دوباره آپلود می‌شود
        sent = await bot.send_photo(chat_id=chat_id, photo=_art_media(entry), caption=caption,
                                    reply_markup=markup, reply_parameters=reply_parameters)
    try:
        _file_ids[entry] = sent.photo[-1].file_id
    except Exception:
        pass
    return sent
