"""خواندن و به‌روزرسانی متن شیت دارایی."""
import re

from app.state import CITY_ASSETS
from app.utils import _clean_item_name, fmt_num, format_goods, normalize_digits, num_plain
from app.economy.rules import FORCE_UNIT_NAMES, SPECIAL_UNITS


# برچسب‌هایی که در جمع قلمرو نباید بیایند (توضیحی / غیرعددی)
_ASSET_SKIP_LABELS = {
    "", "-", "—", "0", "ظرفیت", "محدودیت", "باف", "نرف", "باف ویژه",
    "نام شخصیت", "نام جناج", "نام جناح",
}
_ASSET_SKIP_SUBSTR = ("باف", "نرف", "ظرفیت", "محدودیت")


# تشخیص بخش شیت VIP برای نام‌گذاری درست موجودی/بازدهی
_SECTION_RULES = [
    # (کلمات کلیدی در خط عنوان، نام بخش)
    (("خزانه",), "treasury"),
    (("آشپزخانه", "اشپزخانه"), "kitchen"),
    (("دهکده",), "village"),
    (("بندر",), "port"),
    (("انبار",), "warehouse"),
    (("کارگاه تولیدی", "چوب بری", "معدن"), "workshop"),
    (("پادگان", "پیاده‌نظام", "سواره‌نظام", "توپخانه", "ناوگان"), "army"),
    (("قلعه",), "castle"),
    (("تجارت خانه", "تجارتخانه"), "tradehouse"),
]


def _detect_section(line: str, current: str) -> str:
    low = line.replace(" ", "").replace("\u200c", "")
    for keys, sec in _SECTION_RULES:
        if any(k in low or k in line for k in keys):
            return sec
    return current


def _contextual_label(label: str, section: str) -> str | None:
    """
    موجودی/بازدهی عمومی را بر اساس بخش شیت نام‌گذاری می‌کند:
      خزانه → سکه / بازدهی خزانه
      آشپزخانه → غذا
      دهکده → رعیت
      بندر → بازدهی بندر
    بقیه برچسب‌ها (چوب، سرباز، …) همان‌اند.
    """
    lab = label.strip()
    lab_n = lab.replace(" ", "").replace("\u200c", "")
    if lab_n in ("موجودی", "موجودیخزانه"):
        if section == "treasury":
            return "سکه"
        if section == "kitchen":
            return "غذا"
        if section == "warehouse":
            return "موجودی انبار"
        return f"موجودی ({section or '?'})"
    if lab_n in ("بازدهی",):
        if section == "treasury":
            return "بازدهی خزانه"
        if section == "village":
            return "بازدهی دهکده"  # در آپ → جمعیت؛ نه موجودی جمعیت
        if section == "port":
            return "بازدهی بندر"
        if section == "kitchen":
            return "بازدهی آشپزخانه"
        if section == "tradehouse":
            return "بازدهی تجارت‌خانه"
        return f"بازدهی ({section or '?'})"
    # جمعیت / رعیت / نفر یکی هستند
    if lab_n in ("جمعیت", "رعیت", "نفر"):
        return "جمعیت"
    if lab_n.startswith("تعدادسرباز") or lab_n in ("تعدادسربازان", "سربازان"):
        return "سربازان"
    return lab


def normalize_stats_keys(bag: dict) -> dict:
    """ادغام کلیدهای هم‌معنی (مثل جمعیت+رعیت) قبل از نمایش/جمع."""
    if not bag:
        return {}
    out = {}
    merge = {"رعیت": "جمعیت", "نفر": "جمعیت", "اهن": "آهن", "اسب‌ها": "اسب"}
    for k, v in bag.items():
        key = merge.get(k, k)
        out[key] = out.get(key, 0) + float(v)
    return {k: (int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)) for k, v in out.items()}


def extract_asset_stats(text: str) -> dict:
    """
    استخراج اعداد از شیت VIP با درک بخش‌ها.

    قواعد قطعی:
    - موجودی بخش خزانه = سکه
    - بازدهی خزانه / تجارتخانه / بندر = سکه در آپ (اگر پرانتز ❌ نباشد)
    - فرمت عمومی: (لول) : بازدهی
    - ❌ داخل پرانتز = غیرفعال (نه لول نه بازدهی)
    """
    text = normalize_digits(text or "")
    stats = {}
    levels = {}
    disabled = set()
    section = ""
    # | نام | (لول یا ❌) : عدد
    line_pat = re.compile(
        r"\|\s*([^|%{}]+?)\s*\|\s*"
        r"(?:\(([^)]*)\))?\s*[:=：]?\s*"
        r"([\d]+(?:\.\d+)?)?\s*$"
    )
    plain_pat = re.compile(
        r"^\s*([^\n|:=：%{}]{1,40}?)\s*"
        r"(?:\(([^)]*)\))?\s*[:=：]\s*"
        r"([\d]+(?:\.\d+)?)\s*$"
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ("﴿" in line or "🏦" in line or "🍽" in line
                or "🛖" in line or "⚓️" in line or "🏗" in line
                or "📦" in line or "🏰" in line or "🛡" in line
                or "خزانه" in line or "آشپزخانه" in line
                or "دهکده" in line or "بندر" in line
                or "تجارت" in line or "انبار" in line
                or "قلعه" in line):
            if not re.search(r"[:=：]\s*\d", line):
                section = _detect_section(line, section)
                # لول قلعه از عنوان: 🍽 ﴿ قلعه﴾ (2)
                if "قلعه" in line:
                    m_cast = re.search(r"قلعه[^\d]*\((\d+)\)", line)
                    if m_cast:
                        try:
                            levels["قلعه"] = int(m_cast.group(1))
                        except ValueError:
                            pass
                # انبار 《4》 یا (4)
                if "انبار" in line:
                    m_wh = re.search(r"انبار[^\d]*[《\[(](\d+)", line)
                    if m_wh:
                        try:
                            levels["انبار"] = int(m_wh.group(1))
                        except ValueError:
                            pass
                continue
        section = _detect_section(line, section)

        # تگ باف/نرف مثل +30% را بردار تا عدد بازدهی خوانده شود
        if "%" in line or "٪" in line:
            line = re.sub(r"[+\-−]?\s*\d+(?:\.\d+)?\s*[%٪]", "", line)
        # ظرفیت انبار: پر/سقف — سقف همیشه عدد بزرگ‌تر (یا از لول انبار)
        if "ظرفیت" in line and re.search(r"\d+\s*/\s*\d+", line):
            mcap = re.search(r"(\d+)\s*/\s*(\d+)", line)
            if mcap:
                try:
                    a, b = float(mcap.group(1)), float(mcap.group(2))
                    # سقف = بزرگ‌تر؛ پر = کوچک‌تر (اگر جابه‌جا نوشته شده باشد هم درست می‌شود)
                    stats["انبار_سقف"] = max(a, b)
                    stats["انبار_پر"] = min(a, b)
                except ValueError:
                    pass
            continue
        # فناوری فقط خطوط بخش فناوری: {نظامی}:《 3》 — نه «شبه نظامی»
        if (
            ("{" in line or "《" in line or "》" in line)
            and any(x in line for x in ("نظامی", "اقتصادی", "پزشکی"))
            and "شبه" not in line
            and "کمپ" not in line
            and "|" not in line  # خطوط جدول نیرو/کمپ
        ):
            mt = re.search(r"(نظامی|اقتصادی|پزشکی)[^\d\n]{0,12}(\d+)", line)
            if mt:
                try:
                    stats[f"فناوری {mt.group(1)}"] = float(mt.group(2))
                except ValueError:
                    pass
                continue

        # محدودیت تجارتخانه قبل از پارس عادی (چون بعد از عدد متن دارد)
        if "محدودیت" in line and section in ("tradehouse", "trade", ""):
            nums = re.findall(r"(\d+(?:\.\d+)?)", normalize_digits(line))
            if nums:
                stats["محدودیت_سکه"] = float(nums[0])
                if len(nums) >= 2:
                    stats["محدودیت_منبع"] = float(nums[1])
            continue

        m = line_pat.search(line)
        if not m:
            m = plain_pat.match(line)
        if not m:
            # |🐎| اسب: 50  یا  اسب: 50
            m2 = re.search(r"(?:\|\s*)?([^|:%{}]{1,30}?)\s*[:=：]\s*(\d+(?:\.\d+)?)\s*$", line)
            if m2:
                class _M:
                    def group(self, i):
                        if i == 1: return m2.group(1)
                        if i == 2: return None
                        if i == 3: return m2.group(2)
                        return None
                m = _M()
            else:
                continue
        label = re.sub(r"\s+", " ", m.group(1)).strip(" |-~•·*_/:：")
        label = _clean_item_name(label) if label else ""
        paren = (m.group(2) or "").strip()
        num_s = (m.group(3) or "").strip()

        if not label or len(label) > 40:
            continue
        if label in _ASSET_SKIP_LABELS:
            continue
        # محدودیت تجارتخانه: 3000سکه، 300منبع
        if "محدودیت" in label or (section == "tradehouse" and "محدود" in label):
            nums = re.findall(r"(\d+(?:\.\d+)?)", normalize_digits(line))
            if nums:
                stats["محدودیت_سکه"] = float(nums[0])
                if len(nums) >= 2:
                    stats["محدودیت_منبع"] = float(nums[1])
            continue
        if any(s in label for s in _ASSET_SKIP_SUBSTR):
            continue
        if re.fullmatch(r"[\W\d_]+", label):
            continue

        # ❌ = غیرفعال
        if "❌" in paren or "x" == paren.lower() or "×" in paren:
            final = _contextual_label(label, section)
            if final:
                disabled.add(final)
                # بازدهی صفر
                if "بازدهی" in (final or "") or label in ("بازدهی",):
                    stats[final] = 0
            continue

        # لول از پرانتز
        lv = None
        if paren and re.fullmatch(r"\d+", paren):
            try:
                lv = int(paren)
            except ValueError:
                lv = None

        if not num_s:
            # فقط لول بدون بازدهی عددی
            if lv is not None:
                final = _contextual_label(label, section) or label
                levels[final] = lv
            continue

        try:
            qty = float(num_s)
        except ValueError:
            continue

        final = _contextual_label(label, section)
        if not final:
            continue

        # نیروی نظامی/تولیدی با (لول): بازدهی → yields نه موجودی لیست
        mil_units = {
            "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
            "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
            "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
            "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
            "کلداستریم گارد", "گرنادیر گارد", "رایفلداران اسکاتلندی",
            "گاردپادشاهی فرانسه", "رایفلداران ایرلندی", "سواره‌نظام دراگون",
            "سواران رایتر", "کیوراسیرها", "رایفلداران مدرن",
            "توپ کولورین", "توپ خمپاره‌ای", "توپخانه امپراطوری",
            "کشتی بریگانتین", "کشتی جنگی سنگین خط نبرد", "چریک هلندی",
            "چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی", "اصطبل",
        }
        mil_units |= set(SPECIAL_UNITS.keys())
        if label not in ("موجودی", "بازدهی") and lv is not None:
            levels[final] = lv
            # بازدهی کمپ/تولیدی جدا از موجودی نیرو
            if final in mil_units or section in (
                "barracks", "production", "military", "army", "workshop", "castle"
            ):
                # (لول): بازدهی → yields (نه موجودی لیست نیرو)
                stats[f"yield:{final}"] = qty
                levels[final] = lv
            else:
                # یونیت ویژه داینامیک با پرانتز لول
                stats[f"yield:{final}"] = qty
                levels[final] = lv
        else:
            # بدون لول = موجودی (لیست نیرو / سکه / …)
            # دانشکده‌ها: عدد تنها = لول (بازدهی جدا یا ۰)
            if any(x in final for x in ("دانشکده", "مجمع نخبگان", "دانشگاه پزشکی")):
                levels[final] = int(qty)
                stats[final] = qty  # لول برای نمایش
            elif final in mil_units:
                stats[final] = qty  # موجودی نیرو (جایگزین نه جمع)
            else:
                stats[final] = stats.get(final, 0) + qty
            if lv is not None and "بازدهی" in final:
                bname = {
                    "بازدهی خزانه": "خزانه",
                    "بازدهی بندر": "بندر",
                    "بازدهی تجارت‌خانه": "تجارتخانه",
                    "بازدهی تجارتخانه": "تجارتخانه",
                    "بازدهی آشپزخانه": "آشپزخانه",
                    "بازدهی دهکده": "دهکده",
                }.get(final)
                if not bname and section:
                    # بخش دهکده/آشپزخانه بدون پیشوند
                    sec_map = {
                        "village": "دهکده",
                        "kitchen": "آشپزخانه",
                        "treasury": "خزانه",
                        "port": "بندر",
                        "tradehouse": "تجارتخانه",
                    }
                    bname = sec_map.get(section)
                if bname:
                    levels[bname] = lv
                    stats[bname] = qty
                    stats[f"yield:{bname}"] = qty

    # موجودی خزانه همیشه سکه است
    if "سکه" not in stats and section:
        pass
    # همگام‌سازی کلید خزانه با بازدهی خزانه
    if stats.get("بازدهی خزانه") and not stats.get("خزانه"):
        stats["خزانه"] = stats["بازدهی خزانه"]
    if stats.get("بازدهی بندر") and not stats.get("بندر"):
        stats["بندر"] = stats["بازدهی بندر"]
    if stats.get("بازدهی تجارت‌خانه") and not stats.get("تجارتخانه"):
        stats["تجارتخانه"] = stats["بازدهی تجارت‌خانه"]

    out = {k: (int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)) for k, v in stats.items()}
    # levels را در کلیدهای رزرو نمی‌گذاریم؛ set_city_asset جدا می‌گیرد
    out["__levels__"] = levels
    out["__disabled__"] = list(disabled)
    return out


def _sum_force_soldiers(bag: dict) -> int:
    """جمع نفر سرباز از لیست نیرو (بدون توپ و کشتی).
    یونیت‌های ویژه پیاده/سواره هر شهر از SPECIAL_UNITS + شیت همان گپ حساب می‌شوند.
    """
    bag = bag or {}
    keys = [
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "کیوراسیرها", "رایفلداران مدرن", "کلداستریم گارد", "گرنادیر گارد",
        "رایفلداران اسکاتلندی", "چریک هلندی",
        "گاردپادشاهی فرانسه", "رایفلداران ایرلندی", "سواره‌نظام دراگون",
        "سواران رایتر",
    ]
    # همه ویژهٔ پیاده/سواره ثبت‌شده در بازی
    for _su, _meta in (SPECIAL_UNITS or {}).items():
        if (_meta or {}).get("cat") in ("inf", "cav") and _su not in keys:
            keys.append(_su)
    total = 0.0
    seen = set()
    for k in keys:
        if k in seen:
            continue
        seen.add(k)
        try:
            total += float(bag.get(k) or 0)
        except (TypeError, ValueError):
            pass
    skip = {"توپ", "کشتی", "ناو", "قایق", "اسب", "سکه", "چوب", "سنگ", "آهن", "باروت", "پوشاک"}
    for k, v in bag.items():
        if k in seen or any(s in str(k) for s in skip):
            continue
        # توپخانه امپراطوری و کشتی‌های ویژه = نه نفر سرباز
        if k in (SPECIAL_UNITS or {}) and (SPECIAL_UNITS.get(k) or {}).get("cat") in ("arty", "ship"):
            continue
        if any(x in str(k) for x in ("نظام", "گارد", "سوار", "پیاده", "رایفل", "شمشیر", "نیزه", "افسر", "چریک", "مزدور", "گرناد", "کیورا", "رایتر")):
            try:
                n = float(v)
            except (TypeError, ValueError):
                continue
            if 0 < n < 500000:
                total += n
    return int(round(total))

def get_city_asset_text(city: str) -> str:
    """متن کامل شیت — بدون هیچ ویرایش."""
    entry = CITY_ASSETS.get(city) or {}
    if isinstance(entry, dict) and "text" in entry:
        return entry.get("text") or ""
    if isinstance(entry, dict):
        return format_goods(entry)
    return ""


def get_city_asset_stats(city: str) -> dict:
    entry = CITY_ASSETS.get(city) or {}
    if isinstance(entry, dict) and "stats" in entry:
        return dict(entry.get("stats") or {})
    if isinstance(entry, dict) and "text" not in entry:
        out = {}
        for k, v in entry.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    return {}

def set_city_asset(city: str, text: str):
    """
    متن کامل را عیناً ذخیره می‌کند (هیچ کاراکتری عوض نمی‌شود).
    فقط یک دیکشنری stats جدا برای جمع قلمرو ساخته می‌شود.
    """
    text = text if text is not None else ""
    if text.startswith("\n"):
        text = text.lstrip("\n")
    text = _strip_auto_footers(text.rstrip())
    raw = extract_asset_stats(text)
    levels_ex = dict(raw.pop("__levels__", {}) or {})
    disabled = list(raw.pop("__disabled__", []) or [])
    yields_ex = {}
    stats = {}
    for k, v in raw.items():
        if str(k).startswith("__"):
            continue
        if str(k).startswith("yield:"):
            yields_ex[str(k)[6:]] = v
        else:
            stats[k] = v
    prev = CITY_ASSETS.get(city) or {}
    # حفظ موجودی نیرو اگر شیت جدید فقط بازدهی کمپ را خواند
    prev_st = dict(prev.get("stats") or {})
    try:
        _fn = FORCE_UNIT_NAMES | set((SPECIAL_UNITS or {}).keys())
    except Exception:
        _fn = set(prev_st.keys())
    for fk in _fn:
        try:
            old_v = float(prev_st.get(fk) or 0)
            new_v = float(stats.get(fk) or 0)
        except (TypeError, ValueError):
            continue
        yv = float(yields_ex.get(fk) or 0)
        if new_v <= 0 and old_v > 0:
            stats[fk] = old_v
        elif yv > 0 and abs(new_v - yv) < 0.01 and old_v > new_v:
            stats[fk] = old_v
    shop = _parse_shop_from_sheet(text)
    merged_lv = dict(prev.get("levels") or {})
    merged_lv.update(levels_ex)
    merged_y = dict(prev.get("yields") or {})
    merged_y.update(yields_ex)
    # تعداد سربازان = جمع لیست نیرو (بات خودش جمع می‌کند)
    _force_sum = _sum_force_soldiers(stats)
    if _force_sum > 0:
        stats["سربازان"] = _force_sum
    CITY_ASSETS[city] = {
        "text": text,
        "stats": stats,
        "unlocked": list(prev.get("unlocked") or []),
        "changes": list(prev.get("changes") or []),
        "yields": merged_y,
        "levels": merged_lv,
        "disabled": disabled,
        "shop": shop or dict(prev.get("shop") or {}),
    }
    return stats


# ---------------- شهرهای اتو / آپ / واگذاری ----------------
def _strip_auto_footers(text: str) -> str:
    """حذف بلوک‌های ——— / 📝 تغییر اتو از ته شیت — وقایع فقط در تغییرات اخیر."""
    if not text:
        return text
    text = re.sub(
        r"\n*\s*—{3,}\s*\n\s*📝[^\n]*(?:\n(?!\s*—{3,})[^\n]*)*",
        "",
        text,
    )
    return text.rstrip()


def _fmt_num(v) -> str:
    try:
        f = float(v)
        return num_plain(f)
    except (TypeError, ValueError):
        return str(v)


def _patch_sheet_field(text: str, label: str, new_val) -> str:
    """به‌روز کردن فقط عدد بعد از : — پرانتز لول حفظ می‌شود."""
    if not text or not label:
        return text
    val = _fmt_num(new_val)
    pat = re.compile(
        rf"(\|[^\n|]{{0,12}}\|(?:-|~)\|[^\n|]{{0,8}}\|\s*"
        rf"{re.escape(label)}\s*\|[ \t]*(?:\([^)]*\))?[ \t]*:?[ \t]*)"
        rf"[\d۰-۹.]*",
        re.I,
    )
    nt, n = pat.subn(rf"\g<1>{val}", text, count=1)
    if n:
        return nt
    pat2 = re.compile(
        rf"(\|\s*{re.escape(label)}\s*\|[ \t]*(?:\([^)]*\))?[ \t]*:?[ \t]*)"
        rf"[\d۰-۹.]*",
        re.I,
    )
    nt, n = pat2.subn(rf"\g<1>{val}", text, count=1)
    return nt if n else text


def _patch_sheet_level_yield(text: str, name: str, new_lv: int, new_yield: float) -> str:
    """
    ثبت لول و بازدهی روی همان خط لیست شیت.
    تولیدی/کمپ: |…|-| نام | (لول) : بازدهی
    خزانه/بندر/…: خط «بازدهی» زیر همان بخش.
    """
    if not text or not name:
        return text
    y = _fmt_num(new_yield)
    lv = int(new_lv)

    # ۱) خط مستقیم نام ساختمان/کمپ (فقط همان خط — \s خط بعد را نخورد)
    pat = re.compile(
        rf"(\|[^\n|]*\|[^\n|]*\|\s*{re.escape(name)}\s*\|)[ \t]*"
        rf"(?:\([^)]*\))?[ \t]*:?[ \t]*[\d۰-۹.]*",
        re.I,
    )
    nt, n = pat.subn(rf"\1 ({lv}) : {y}", text, count=1)
    if n:
        return nt

    # ۲) ساختمان‌های بخشی: خزانه / بندر / آشپزخانه / دهکده / تجارتخانه
    section_keys = {
        "خزانه": r"خزانه",
        "تجارتخانه": r"تجارت\s*خانه|تجارتخانه",
        "بندر": r"بندر",
        "آشپزخانه": r"آشپزخانه",
        "دهکده": r"دهکده",
        "دانشکده افسری": r"دانشکده\s*افسری",
        "مجمع نخبگان": r"مجمع\s*نخبگان",
        "دانشگاه پزشکی": r"دانشگاه\s*پزشکی",
    }
    sk = section_keys.get(name)
    if sk:
        # پیدا کردن بلوک بخش و جایگزینی خط بازدهی داخل آن
        sec = re.compile(
            rf"({sk}[^\n]*\n)(.*?)(?=\n[🏦🏬🍽🛖⚓️🏗🏰]|$)",
            re.I | re.S,
        )
        m = sec.search(text)
        if m:
            block = m.group(0)
            bpat = re.compile(
                r"(\|\s*📥\s*\|[^\n|]*\|\s*بازدهی\s*\|)[ \t]*(?:\([^)]*\))?[ \t]*:?[ \t]*[\d۰-۹.]*",
                re.I,
            )
            nblock, bn = bpat.subn(rf"\1 ({lv}) : {y}", block, count=1)
            if bn:
                return text[: m.start()] + nblock + text[m.end():]
            # دانشکده‌ها گاهی فقط عدد بعد از نام دارند
            if name.startswith("دانشکده") or "مجمع" in name or "دانشگاه" in name:
                apat = re.compile(
                    rf"(\|[^\n|]*\|\s*{re.escape(name)}[^\n|]*\|)\s*:?\s*[\d۰-۹.]*",
                    re.I,
                )
                nt, n = apat.subn(rf"\1 : {lv}", text, count=1)
                if n:
                    return nt

    # ۳) فقط سلول دقیق | نام |
    pat2 = re.compile(
        rf"(\|\s*{re.escape(name)}\s*\|)[ \t]*(?:\([^)]*\))?[ \t]*:?[ \t]*[\d۰-۹.]*",
        re.I,
    )
    nt, n = pat2.subn(rf"\1 ({lv}) : {y}", text, count=1)
    return nt if n else text


def _patch_force_list_counts(text: str, stats: dict, names: tuple) -> str:
    """
    موجودی نیرو را فقط در بلوک لیست نیرو (پایین شیت) به‌روز می‌کند.
    خطوط کمپ پادگان با (لول) دست نمی‌خورند.
    """
    if not text:
        return text
    idx = -1
    for marker in ("|🛡|", "پیاده‌نظام", "|🐴|~| سوار", "|🌟|~| ویژه", "ناوگان جنگی"):
        j = text.rfind(marker)
        if j >= 0 and (idx < 0 or j < idx or marker.startswith("|🛡")):
            if marker.startswith("|🛡") or "پیاده" in marker or "ناوگان" in marker:
                idx = j
                break
    if idx < 0:
        idx = text.rfind("پیاده‌نظام")
    if idx < 0:
        return text
    head, tail = text[:idx], text[idx:]
    shop = re.search(r"\n\s*💵|\n\s*شاپ\s*:", tail)
    if shop:
        mid, end = tail[:shop.start()], tail[shop.start():]
    else:
        mid, end = tail, ""
    for nm in names:
        if nm not in stats:
            continue
        val = _fmt_num(stats[nm])
        # خط بدون پرانتز لول — فقط موجودی لیست نیرو
        pat = re.compile(
            r"(\|[^\n|]{0,12}\|(?:-|~)\|[^\n|]{0,8}\|\s*)("
            + re.escape(nm)
            + r")(\s*\|)[ \t]*(?![(\uFF08])(?:🔒)?[ \t]*:?[ \t]*[\d۰-۹.]*[ \t]*(?:🔒)?",
            re.I,
        )
        mid, n = pat.subn(r"\1\2\3 : " + val, mid, count=1)
        if not n:
            pat2 = re.compile(
                r"(\|\s*" + re.escape(nm) + r"\s*\|)[ \t]*(?![(\uFF08])(?:🔒)?[ \t]*:?[ \t]*[\d۰-۹.]*",
                re.I,
            )
            mid, _ = pat2.subn(r"\1 : " + val, mid, count=1)
    return head + mid + end


def _apply_stock_to_sheet(text: str, stats: dict) -> str:
    """اعداد لیست شیت را با stats هم‌تراز: سکه/انبار/اسب/غذا/نیرو."""
    if not text:
        return text
    if "سکه" in stats:
        text = _patch_sheet_field(text, "موجودی", stats["سکه"])
    for sk, lab in (
        ("چوب", "چوب"), ("آهن", "اهن"), ("سنگ", "سنگ"),
        ("پوشاک", "پوشاک"), ("باروت", "باروت"),
        ("جمعیت", "جمعیت"), ("اسب", "اسب"),
    ):
        if sk in stats:
            text = _patch_sheet_field(text, lab, stats[sk])
            if lab == "اهن":
                text = _patch_sheet_field(text, "آهن", stats[sk])
    if "غذا" in stats:
        text = re.sub(
            r"(\|\s*🥣\s*\|[^\n|]*\|\s*موجودی\s*\|)[ \t]*:?[ \t]*[\d۰-۹.]*",
            rf"\1 : {_fmt_num(stats['غذا'])}",
            text,
            count=1,
            flags=re.I,
        )
    force_names = [
        "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
        "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
        "ویژه", "توپ سبک", "توپ محاصره", "توپ سنگین",
        "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
        "کلداستریم گارد", "گرنادیر گارد", "رایفلداران اسکاتلندی",
        "گاردپادشاهی فرانسه", "رایفلداران ایرلندی", "سواره‌نظام دراگون",
        "سواران رایتر", "کیوراسیرها", "رایفلداران مدرن",
        "توپ کولورین", "توپ خمپاره‌ای", "توپخانه امپراطوری",
        "کشتی بریگانتین", "کشتی جنگی سنگین خط نبرد",
        "اسب",
    ]
    for _su in (SPECIAL_UNITS or {}):
        if _su not in force_names:
            force_names.append(_su)
    # یونیت‌های ویژه/داینامیک که در stats هستند
    skip = {
        "سکه", "چوب", "سنگ", "آهن", "پوشاک", "باروت", "غذا", "جمعیت",
        "اقتدار", "مشروعیت", "پوینت", "پوئن", "خزانه", "بندر", "تجارتخانه",
        "آشپزخانه", "دهکده", "اصطبل", "ظرفیت قلعه", "موجودی",
    }
    for k in stats:
        if k in skip or str(k).startswith("yield:") or str(k).startswith("__"):
            continue
        if k not in force_names:
            force_names.append(k)
    text = _patch_force_list_counts(text, stats, tuple(force_names))
    # اسب گاهی بیرون از بلوک نیروست
    if "اسب" in stats:
        text = _patch_sheet_field(text, "اسب", stats["اسب"])
    return text


def _annotate_yield_pct(text: str, name: str, signed_pct: float) -> str:
    """جلوی بازدهی ساختمان در شیت +۳۰٪ یا −۱۰٪ می‌نویسد (لول عوض نمی‌شود)."""
    if not text or not name:
        return text
    sign = "+" if signed_pct >= 0 else ""
    tag = f"{sign}{fmt_num(signed_pct)}%"
    # پاک کردن تگ قبلی همان نام
    text = re.sub(
        rf"({re.escape(name)}[^\n]*?\(\s*\d+\s*\)\s*)([+\-]\s*\d+(?:\.\d+)?\s*%\s*)?(:)",
        rf"\1{tag} :",
        text,
        count=1,
        flags=re.I,
    )
    # اگر تگ نخورد، بعد از پرانتز لول اضافه کن
    if tag not in text:
        text = re.sub(
            rf"({re.escape(name)}[^\n]*?\(\s*\d+\s*\))(\s*:)",
            rf"\1 {tag}\2",
            text,
            count=1,
            flags=re.I,
        )
    return text


def warehouse_capacity_for(city: str, entry=None) -> int:
    """سقف ظرفیت انبار: max(شیت، لول×۵۰۰) — حداقل ۵۰۰."""
    entry = entry or CITY_ASSETS.get(city) or {}
    st = entry.get("stats") or {}
    sheet_cap = 0
    try:
        if st.get("انبار_سقف"):
            sheet_cap = max(0, int(float(st["انبار_سقف"])))
    except (TypeError, ValueError):
        sheet_cap = 0
    lv = int((entry.get("levels") or {}).get("انبار") or 0)
    if lv <= 0:
        lv = 1
    level_cap = max(500, lv * 500)
    return max(sheet_cap, level_cap)


def _patch_warehouse_cap(text: str, stats: dict) -> str:
    """به‌روزرسانی خط ظرفیت انبار: فعلی/سقف."""
    if not text:
        return text
    filled = 0.0
    for k in ("چوب", "آهن", "سنگ", "پوشاک", "باروت"):
        try:
            filled += float(stats.get(k) or 0)
        except (TypeError, ValueError):
            pass
    try:
        cap = float(stats.get("انبار_سقف") or 0)
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0:
        return text
    stats["انبار_پر"] = filled
    text2, n = re.subn(
        r"(\{?\s*ظرفیت\s*\}?\s*[:：]?\s*)\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?",
        lambda m: f"{m.group(1)}{int(round(filled))}/{int(round(cap))}",
        text,
        count=1,
        flags=re.I,
    )
    if n:
        return text2
    text2, n = re.subn(
        r"(ظرفیت[^\n\d]{0,8})\d+\s*/\s*\d+",
        lambda m: f"{m.group(1)}{int(round(filled))}/{int(round(cap))}",
        text,
        count=1,
        flags=re.I,
    )
    return text2 if n else text


def enforce_warehouse_capacity(city: str, stats: dict):
    """فقط هشدار پر بودن انبار — سوخت خودکار انجام نمی‌شود (ادمین تصمیم می‌گیرد)."""
    notes = []
    try:
        cap = int(float(stats.get("انبار_سقف") or 0))
    except (TypeError, ValueError):
        cap = 0
    if cap <= 0:
        entry = CITY_ASSETS.get(city) or {}
        cap = warehouse_capacity_for(city, entry)
        stats["انبار_سقف"] = float(cap)
    else:
        # همگام با لول انبار
        entry = CITY_ASSETS.get(city) or {}
        cap = max(cap, warehouse_capacity_for(city, entry))
        stats["انبار_سقف"] = float(cap)
    order = ["باروت", "پوشاک", "سنگ", "آهن", "چوب"]
    total = 0.0
    for k in order:
        try:
            total += max(0.0, float(stats.get(k) or 0))
        except (TypeError, ValueError):
            pass
    stats["انبار_پر"] = total
    if total > cap + 1e-6:
        overflow = total - cap
        notes.append(
            f"⚠️ انبار پر ({int(total)}/{cap}) — مازاد {int(round(overflow))} "
            f"(سوخت خودکار نیست؛ ادمین تصمیم بگیرد)"
        )
    return stats, notes


def parse_roll_buff_form(text: str) -> dict:
    """
    پارس فرم:
      بازدهی رول {سکه}: 500
      بازدهی رول سکه: 500
      بازدهی باف 50%+ خزانه
      بازدهی نرف 30%- دهکده
      اعمال بازدهی سکه +800
    خروجی: {"rolls": {name: qty}, "buffs": [{kind, pct, target}], "flat": {name: delta}}
    """
    text = normalize_digits(text or "")
    rolls, buffs, flat = {}, [], {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "اعمال بازدهی رول و باف" in line:
            continue
        # بازدهی رول {سکه}: 500  یا  بازدهی رول سکه: 500
        m = re.search(r"بازدهی\s*رول\s*\{?\s*([^\}:\n]+?)\s*\}?\s*[:：]\s*([+\-]?\d+(?:\.\d+)?)", line, re.I)
        if m:
            name = _clean_item_name(m.group(1))
            rolls[name] = rolls.get(name, 0) + float(m.group(2))
            continue
        # بازدهی باف 50%+ خزانه / بازدهی نرف 30%- دهکده
        m = re.search(r"بازدهی\s*(باف|نرف)\s*([+\-]?\d+(?:\.\d+)?)\s*%\s*([+\-])\s*(.+)$", line, re.I)
        if m:
            kind = "buff" if "باف" in m.group(1) else "nerf"
            pct = float(m.group(2))
            sign = m.group(3)
            target = _clean_item_name(m.group(4))
            if sign == "-":
                kind = "nerf"
            buffs.append({"kind": kind, "pct": abs(pct), "target": target})
            continue
        # اعمال بازدهی سکه +800
        m = re.search(r"(?:اعمال\s*)?بازدهی\s+([^\s:+\-]+)\s*([+\-]\d+(?:\.\d+)?)", line, re.I)
        if m:
            name = _clean_item_name(m.group(1))
            flat[name] = flat.get(name, 0) + float(m.group(2))
            continue
        # سکه: +800
        m = re.search(r"^([^\d:+\-]+?)\s*[:：]\s*([+\-]?\d+(?:\.\d+)?)\s*$", line)
        if m:
            name = _clean_item_name(m.group(1))
            if name:
                rolls[name] = rolls.get(name, 0) + float(m.group(2))
            continue
        # منبع(چوب) به تعداد(100)
        m = re.search(r"منبع\s*\(\s*([^)]+)\s*\)\s*به\s*تعداد\s*\(\s*([+\-]?\d+(?:\.\d+)?)\s*\)", line, re.I)
        if m:
            name = _clean_item_name(m.group(1))
            rolls[name] = rolls.get(name, 0) + float(m.group(2))
            continue
        # اعمال نرف/باف بر روی X به درصد(30)
        m = re.search(
            r"اعمال\s*(نرف|باف|بازدهی)?\s*بر\s*روی\s*(.+?)\s*به\s*درصد\s*\(\s*([+\-]?\d+(?:\.\d+)?)\s*\)",
            line, re.I,
        )
        if m:
            kind_raw = (m.group(1) or "باف").strip()
            kind = "nerf" if "نرف" in kind_raw else "buff"
            target = _clean_item_name(m.group(2))
            pct = abs(float(m.group(3)))
            buffs.append({"kind": kind, "pct": pct, "target": target})
            continue
    return {"rolls": rolls, "buffs": buffs, "flat": flat}


def _parse_shop_from_sheet(text: str) -> dict:
    """بازدهی عددی شاپ برای آپ: نام → عدد صحیح."""
    packs = _parse_shop_packs(text)
    out = {}
    for pk in packs:
        y = int(pk.get("yield") or 0)
        unit = (pk.get("unit") or pk.get("name") or "").strip()
        if y > 0 and unit:
            out[unit] = out.get(unit, 0) + y
        # ارتش همراه هیرو
        for u in pk.get("army") or []:
            uy = int(u.get("yield") or 0)
            un = (u.get("unit") or "").strip()
            if uy > 0 and un:
                out[un] = out.get(un, 0) + uy
            elif un and int(u.get("count") or 0) > 0 and uy == 0:
                # فقط تعداد — در آپ همان تعداد به نیرو اضافه می‌شود
                out[un] = out.get(un, 0) + int(u.get("count") or 0)
        # گروهک: تعداد یونیت
        if pk.get("kind") in ("merc_group", "merc", "spy", "guard") and pk.get("count"):
            un = (pk.get("unit") or pk.get("name") or "").strip()
            c = int(pk.get("count") or 0)
            if un and c > 0 and y <= 0:
                out[un] = out.get(un, 0) + c
    return out


def _parse_shop_packs(text: str) -> list:
    """
    پارس ساختاریافته شاپ:
    - وزیر: فقط نام
    - هیرو: نام + ارتش همراه (خطوط بعدی با عدد)
    - گروهک مزدوری: نوع + تعداد
    - مزدور / جاسوس / گارد: تعداد و/یا بازدهی
    - پک عمومی: نام (بازدهی) یا نام (تعداد) : بازدهی
    """
    if not text:
        return []
    m = re.search(r"شاپ\s*:?\s*(.*)$", text, re.I | re.S)
    block = m.group(1) if m else text
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    packs = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        low = ln.replace("ي", "ی").lower()
        # وزیر
        if re.search(r"وزیر", ln):
            name = re.sub(r"^.*?وزیر\s*", "", ln).strip(" :-|")
            name = _clean_item_name(name) or ln
            packs.append({"kind": "minister", "name": name, "yield": 0})
            i += 1
            continue
        # هیرو / فرمانده
        if re.search(r"هیرو|قهرمان|فرمانده|🥷", ln, re.I):
            name = re.sub(r"^.*?(هیرو|قهرمان|فرمانده)\s*", "", ln, flags=re.I).strip(" :-|")
            name = _clean_item_name(name) or ln
            army = []
            i += 1
            while i < len(lines):
                al = lines[i]
                if re.search(r"وزیر|هیرو|قهرمان|فرمانده|گروهک|مزدور|جاسوس|گارد|🥷|🤵|💵", al, re.I):
                    break
                # "50 ژاندارم" یا "ژاندارم: 50" یا "(100) : 300"
                mm = re.search(
                    r"(?:([\d۰-۹]+)\s+)?(.+?)(?:\s*[\(（]\s*([\d۰-۹]+)\s*[\)）])?\s*:?\s*([\d۰-۹.]*)?\s*$",
                    al.strip(),
                )
                if not mm:
                    i += 1
                    continue
                c1 = normalize_digits(mm.group(1) or "")
                unit = _clean_item_name(mm.group(2) or "")
                paren = normalize_digits(mm.group(3) or "")
                tail = normalize_digits(mm.group(4) or "")
                count = 0
                yld = 0
                try:
                    if c1:
                        count = int(float(c1))
                    if paren and tail:
                        count = int(float(paren)) if not count else count
                        yld = int(round(float(tail)))
                    elif paren:
                        yld = int(round(float(paren)))
                    if tail and not yld and not paren:
                        yld = int(round(float(tail)))
                except ValueError:
                    pass
                if unit and (count or yld):
                    army.append({"unit": unit, "count": count, "yield": yld})
                i += 1
            packs.append({"kind": "hero", "name": name, "army": army, "yield": 0})
            continue
        # گروهک مزدوری
        if re.search(r"گروهک\s*مزدور", ln, re.I):
            rest = re.sub(r"^.*?گروهک\s*مزدور[یي]?\s*", "", ln, flags=re.I).strip(" :-|")
            mm = re.search(r"(.+?)\s*[:=：]?\s*([\d۰-۹]+)\s*$", rest)
            if mm:
                unit = _clean_item_name(mm.group(1))
                cnt = int(float(normalize_digits(mm.group(2))))
                packs.append({"kind": "merc_group", "name": f"گروهک {unit}", "unit": unit, "count": cnt, "yield": 0})
            else:
                packs.append({"kind": "merc_group", "name": rest or ln, "unit": rest, "count": 0, "yield": 0})
            i += 1
            continue
        # مزدور / مزدوری / جاسوس / گارد
        mk = None
        if re.search(r"مزدور", ln):
            mk = "merc"
        elif re.search(r"جاسوس", ln):
            mk = "spy"
        elif re.search(r"گارد", ln) and "کمپ" not in ln:
            mk = "guard"
        if mk:
            # مزدوری شمشیرزن 50 (10)
            mm = re.search(
                r"(?:مزدور[یي]?|جاسوس|گارد)\s*(.+?)\s+([\d۰-۹]+)\s*[\(（]\s*([\d۰-۹]+)\s*[\)）]",
                ln,
                re.I,
            )
            if mm:
                unit = _clean_item_name(mm.group(1))
                cnt = int(float(normalize_digits(mm.group(2))))
                yld = int(round(float(normalize_digits(mm.group(3)))))
                packs.append({"kind": mk, "name": unit, "unit": unit, "count": cnt, "yield": yld})
                i += 1
                continue
            mm = re.search(
                r"(.+?)\s*[\(（]\s*([\d۰-۹]+)\s*[\)）]\s*:?\s*([\d۰-۹.]*)?",
                ln,
            )
            if mm:
                unit = _clean_item_name(mm.group(1))
                a = int(float(normalize_digits(mm.group(2))))
                b = mm.group(3)
                yld = int(round(float(normalize_digits(b)))) if b else 0
                if yld:
                    packs.append({"kind": mk, "name": unit, "unit": unit, "count": a, "yield": yld})
                else:
                    packs.append({"kind": mk, "name": unit, "unit": unit, "count": 0, "yield": a})
            else:
                mm2 = re.search(r"(.+?)\s*[:=：]\s*([\d۰-۹]+)", ln)
                if mm2:
                    unit = _clean_item_name(mm2.group(1))
                    cnt = int(float(normalize_digits(mm2.group(2))))
                    packs.append({"kind": mk, "name": unit, "unit": unit, "count": cnt, "yield": 0})
                else:
                    packs.append({"kind": mk, "name": _clean_item_name(ln), "unit": _clean_item_name(ln), "count": 0, "yield": 0})
            i += 1
            continue
        # پک عمومی: نام (N) یا نام (N) : M
        mm = re.search(
            r"(.+?)\s*[\(（]\s*([\d۰-۹]+(?:\.\d+)?)\s*[\)）]\s*:?\s*([\d۰-۹.]*)?",
            ln,
        )
        if mm:
            name = _clean_item_name(mm.group(1))
            a = float(normalize_digits(mm.group(2)))
            b = mm.group(3)
            if b:
                packs.append({
                    "kind": "pack",
                    "name": name,
                    "unit": name,
                    "count": int(round(a)),
                    "yield": int(round(float(normalize_digits(b)))),
                })
            else:
                packs.append({
                    "kind": "pack",
                    "name": name,
                    "unit": name,
                    "count": 0,
                    "yield": int(round(a)),
                })
            i += 1
            continue
        # خط ساده بدون عدد — پک اسمی
        nm = _clean_item_name(ln)
        if nm and len(nm) > 1 and not re.match(r"^[💵💰]+$", nm):
            packs.append({"kind": "pack", "name": nm, "unit": nm, "count": 0, "yield": 0})
        i += 1
    return packs


def _format_shop_packs(packs: list) -> str:
    """متن خوانا برای ذخیره در شیت و نمایش."""
    lines = []
    for pk in packs:
        k = pk.get("kind")
        if k == "minister":
            lines.append(f"🤵 وزیر {pk.get('name') or ''}")
        elif k == "hero":
            lines.append(f"🥷 فرمانده {pk.get('name') or ''}")
            for u in pk.get("army") or []:
                if u.get("count") and u.get("yield"):
                    lines.append(f"  {u.get('count')} {u.get('unit')} ({u.get('yield')})")
                elif u.get("count"):
                    lines.append(f"  {u.get('count')} {u.get('unit')}")
                elif u.get("yield"):
                    lines.append(f"  {u.get('unit')} ({u.get('yield')})")
        elif k == "merc_group":
            lines.append(f"گروهک مزدوری {pk.get('unit') or pk.get('name')}: {pk.get('count') or 0}")
        elif k in ("merc", "spy", "guard"):
            label = {"merc": "مزدور", "spy": "جاسوس", "guard": "گارد"}.get(k, "")
            if pk.get("count") and pk.get("yield"):
                lines.append(f"{label} {pk.get('unit')} ({pk.get('count')}) : {pk.get('yield')}")
            elif pk.get("yield"):
                lines.append(f"{label} {pk.get('unit')} ({pk.get('yield')})")
            else:
                lines.append(f"{label} {pk.get('unit')}: {pk.get('count') or 0}")
        else:
            if pk.get("count") and pk.get("yield"):
                lines.append(f"{pk.get('name')} ({pk.get('count')}) : {pk.get('yield')}")
            elif pk.get("yield"):
                lines.append(f"{pk.get('name')} ({pk.get('yield')})")
            else:
                lines.append(str(pk.get("name") or ""))
    return "\n".join(lines)


def _parse_multi_asset_edit(body: str) -> tuple[dict, dict]:
    """
    پارس یک‌باره با سگمنت‌های اضافه/کسر/تلفات.
    """
    body = normalize_digits(body or "")
    body = body.replace("،", " ").replace("‌", " ")
    body = re.sub(r"\bو\b", " ", body)
    body = re.sub(r",", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    stock, yld = {}, {}

    alias = {
        "سکه": "سکه", "غذا": "غذا", "جمعیت": "جمعیت", "رعیت": "جمعیت", "نفر": "جمعیت",
        "چوب": "چوب", "آهن": "آهن", "اهن": "آهن", "سنگ": "سنگ", "پوشاک": "پوشاک", "باروت": "باروت",
        "اسب": "اسب", "خزانه": "خزانه", "اقتدار": "اقتدار", "مشروعیت": "مشروعیت",
        "شبه نظامی": "شبه نظامی", "شمشیرزن": "شمشیرزن", "نیزه دار": "نیزه دار", "نیزه‌دار": "نیزه دار",
        "رایفلدار": "رایفلدار", "افسر": "افسر",
    }

    def norm_key(raw: str) -> str:
        k = _clean_item_name(raw)
        k = re.sub(r"(?i)^بازدهی\s*", "", k).strip()
        for kn in sorted(alias.keys(), key=len, reverse=True):
            if k == kn or k.endswith(kn) and (len(k) == len(kn) or k[-len(kn)-1:] == " " + kn):
                return alias[kn]
        return alias.get(k, k)

    # تقسیم به سگمنت با علامت: تلفات/کسر → −1 · اضافه → +1
    parts = re.split(
        r"(?i)(\bتلفات\b|\bکسر\b|\bاضافه(?:\s*کردن)?\b|\bافزایش\b)",
        body,
    )
    # parts: [pre, keyword, seg, keyword, seg, ...]
    segments = []  # (sign, text)
    if parts and parts[0].strip():
        segments.append((1, parts[0].strip()))
    i = 1
    while i < len(parts):
        kw = parts[i].strip().lower().replace("ي", "ی")
        seg = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sign = -1 if kw in ("تلفات", "کسر") else 1
        if seg:
            segments.append((sign, seg))
        i += 2
    if not segments:
        segments = [(1, body)]

    # عدد کامل: بعدش رقم نباشد
    item_pat = re.compile(
        r"(?:"
        r"(بازدهی\s+)?([^\d+\-\s][\w\u0600-\u06FF ]{0,24}?)\s*([+-])\s*(\d+(?:\.\d+)?)(?!\d)"
        r"|"
        r"([+-])\s*(\d+(?:\.\d+)?)(?!\d)\s+(بازدهی\s+)?([^\d+\-\s][\w\u0600-\u06FF ]{0,24}?)"
        r"|"
        r"(\d+(?:\.\d+)?)(?!\d)\s+(بازدهی\s+)?([^\d+\-\s][\w\u0600-\u06FF ]{0,24}?)"
        r"|"
        r"(بازدهی\s+)?([^\d+\-\s][\w\u0600-\u06FF ]{0,24}?)\s+(\d+(?:\.\d+)?)(?!\d)"
        r")"
        r"(?=\s|$|[+\-])",
        re.I,
    )

    for seg_sign, seg in segments:
        pos = 0
        while pos < len(seg):
            m = item_pat.search(seg, pos)
            if not m:
                break
            if m.start() < pos:
                pos += 1
                continue
            g = m.groups()
            is_y = False
            key = ""
            val = 0.0
            if g[1] is not None:
                is_y = bool(g[0])
                key = norm_key(g[1])
                val = float(g[3]) if g[2] == "+" else -float(g[3])
            elif g[4] is not None:
                is_y = bool(g[6])
                key = norm_key(g[7])
                val = float(g[5]) if g[4] == "+" else -float(g[5])
            elif g[8] is not None:
                is_y = bool(g[9])
                key = norm_key(g[10])
                val = seg_sign * float(g[8])
            elif g[12] is not None:
                is_y = bool(g[11])
                key = norm_key(g[12])
                val = seg_sign * float(g[13])
            pos = m.end()
            if not key or key.isdigit():
                continue
            # اگر علامت صریح روی جفت بود، seg_sign را دوباره اعمال نکن مگر جفت بدون علامت باشد
            # (حالت 1 و 2 علامت خودشان را دارند)
            if is_y:
                if key == "سکه":
                    key = "خزانه"
                yld[key] = yld.get(key, 0) + val
            else:
                stock[key] = stock.get(key, 0) + val

    return stock, yld
