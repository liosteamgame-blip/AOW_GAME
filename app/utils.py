"""ابزارهای عمومی: HTML امن، فرمت اعداد، ارقام فارسی، پارس زمان و لیست کالا."""
import html
import math
import re

from aiogram import types

from app.config import BTN_BACK, BTN_NO, BTN_YES, MTYPES, MTYPE_EMOJI


# ======================================================================
#                              ابزارها
# ======================================================================
def e(value):
    """متن کاربر را برای HTML امن می‌کند."""
    return html.escape(str(value), quote=False)


_TAG_RE = re.compile(r"<(/?)([a-zA-Z-]+)[^>]*>")


def _open_tags(text: str) -> list:
    """تگ‌های HTML باز در انتهای متن (به ترتیب باز شدن)."""
    stack = []
    for m in _TAG_RE.finditer(text):
        closing, name = m.group(1), m.group(2).lower()
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == name:
                    del stack[i:]
                    break
        else:
            stack.append((name, m.group(0)))
    return stack


def html_chunks(text: str, limit: int = 3800) -> list:
    """
    تقسیم متن HTML به تکه‌های ≤ limit بدون شکستن تگ‌ها (کرش «Can't find end tag»).
    از مرز خط می‌بُرد؛ تگ باز در انتهای هر تکه بسته و در تکه‌ی بعد دوباره باز می‌شود.
    """
    text = text or ""
    if len(text) <= limit:
        return [text] if text else []
    margin = 64  # جا برای تگ‌های بستن/بازکردن دوباره
    room = max(200, limit - margin * 2)
    lines = []
    for ln in text.split("\n"):
        # خط خیلی بلند (متن شیت بدون تگ) را تکه کن
        while len(ln) > room:
            lines.append(ln[:room])
            ln = ln[room:]
        lines.append(ln)
    chunks, cur = [], ""
    for ln in lines:
        add = ln if not cur else "\n" + ln
        if cur and len(cur) + len(add) > room:
            stack = _open_tags(cur)
            chunks.append(cur + "".join(f"</{n}>" for n, _t in reversed(stack)))
            cur = "".join(t for _n, t in stack) + ln
        else:
            cur += add
    if cur.strip():
        stack = _open_tags(cur)
        chunks.append(cur + "".join(f"</{n}>" for n, _t in reversed(stack)))
    return chunks


def html_cut(text: str, limit: int = 4000) -> str:
    """جایگزین امن text[:limit] برای پیام HTML: از مرز خط می‌بُرد و تگ‌های باز را می‌بندد."""
    parts = html_chunks(text, limit)
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return parts[0] + "\n…"


def num_plain(value, decimals: int = 2) -> str:
    """عدد برای متن شیت (که دوباره پارس می‌شود): بدون جداکننده و بدون نماد علمی."""
    try:
        v = round(float(value), decimals)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return str(value)
    if v == int(v):
        return str(int(v))
    return f"{v:.{decimals}f}".rstrip("0").rstrip(".")


def fmt_num(value, signed: bool = False, decimals: int = 2) -> str:
    """عدد نمایشی: جداکننده هزارگان (12,500)، بدون نماد علمی، حداکثر ۲ رقم اعشار."""
    try:
        v = round(float(value), decimals)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return str(value)
    v = v + 0.0  # -0.0 → 0.0
    if v == int(v):
        s = f"{int(v):,}"
    else:
        s = f"{v:,.{decimals}f}".rstrip("0").rstrip(".")
    return f"+{s}" if signed and v > 0 else s


def norm_cmd(text):
    """چند نوشتار مختلف یک دستور را یکسان می‌کند: «ست پلیر»، «/set player»، «/setplayer» و ... ."""
    return re.sub(r"[\s/_-]+", "", (text or "").strip()).lower()


def _norm_country_token(s):
    return (
        str(s or "")
        .replace("ي", "ی")
        .replace("ك", "ک")
        .replace("\u200c", "")
        .replace(" ", "")
        .replace("-", "")
        .lower()
    )


async def send_chunks(target: types.Message, blocks, reply_markup=None, limit=3800):
    parts, chunk = [], ""
    for b in blocks:
        if chunk and len(chunk) + len(b) + 1 > limit:
            parts.append(chunk)
            chunk = ""
        chunk += b + "\n"
    if chunk:
        parts.append(chunk)
    # بلوک بزرگ‌تر از سقف: تقسیم امن (بدون شکستن تگ HTML)
    parts = [c for p in parts for c in html_chunks(p, limit)]
    for i, p in enumerate(parts):
        await target.answer(p, reply_markup=reply_markup if i == len(parts) - 1 else None)


async def need_text(message: types.Message, max_len=100):
    txt = (message.text or "").strip()
    if not txt:
        await message.answer("❌ لطفاً فقط متن ارسال کنید (به پیام ربات ریپلای کنید).")
        return None
    if is_back_text(txt):
        return "__BACK__"
    if len(txt) > max_len:
        await message.answer(f"❌ متن خیلی طولانی است (حداکثر {max_len} کاراکتر). کوتاه‌تر بنویسید.")
        return None
    return txt


def mtype_label(data):
    return MTYPES.get((data or {}).get("mtype"), "-")


def mtype_tag(data):
    k = (data or {}).get("mtype")
    return f"{MTYPE_EMOJI[k]} {MTYPES[k]}" if k in MTYPES else "-"


def choice(text):
    if text == BTN_YES:
        return True
    if text == BTN_NO:
        return False
    return None


def is_back_text(text):
    t = (text or "").strip()
    return t in (BTN_BACK, "بازگشت", "back", "/back")


def plain(text) -> str:
    """حذف تگ‌های HTML برای callback.answer (پاپ‌آپ تلگرام HTML را رندر نمی‌کند)."""
    return html.unescape(re.sub(r"<[^>]+>", "", str(text or "")))


def _tier_label(val, tiers):
    """از بالا به پایین؛ مرز مشترک (مثل ۴۰) به پلهٔ بالاتر می‌رود."""
    if val is None:
        return "—"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "—"
    for lo, hi, name in tiers:
        if lo <= v <= hi:
            return name
    return "—"


def _parse_hhmm(s: str):
    """برگرداندن (h, m) یا None."""
    m = re.fullmatch(r"(\d{1,2})[:\.](\d{1,2})", (s or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h, mi


def _mins_of_day(h, mi):
    return h * 60 + mi


_DAY_ALIASES = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "mon": 0, "monday": 0, "دوشنبه": 0,
    "tue": 1, "tuesday": 1, "سهشنبه": 1, "سه‌شنبه": 1,
    "wed": 2, "wednesday": 2, "چهارشنبه": 2,
    "thu": 3, "thursday": 3, "پنجشنبه": 3, "پنج‌شنبه": 3,
    "fri": 4, "friday": 4, "جمعه": 4,
    "sat": 5, "saturday": 5, "شنبه": 5,
    "sun": 6, "sunday": 6, "یکشنبه": 6, "یک‌شنبه": 6,
}
_DAY_FA = ("دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")


def parse_days_setting(raw: str):
    """رشته روزها → set از weekday (۰=دوشنبه … ۶=یکشنبه). خالی = همه."""
    raw = (raw or "").strip()
    if not raw or raw in ("*", "all", "همه"):
        return None  # همه روزها
    out = set()
    for part in re.split(r"[,،/\s]+", raw):
        p = part.strip().lower().replace("‌", "")
        if not p:
            continue
        if p in _DAY_ALIASES:
            out.add(_DAY_ALIASES[p])
            continue
        # عدد مستقیم
        if p.isdigit() and 0 <= int(p) <= 6:
            out.add(int(p))
    return out or None


def format_days_setting(raw: str) -> str:
    days = parse_days_setting(raw)
    if days is None:
        return "همه روزها"
    return "، ".join(_DAY_FA[d] for d in sorted(days))


# ---------------- ارقام و لیست کالا ----------------
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits(s: str) -> str:
    return (s or "").translate(_PERSIAN_DIGITS)


def _clean_item_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip(" |-~•·*_/:：")
    # نرمال املای رایج
    repl = {"اهن": "آهن", "اهَن": "آهن"}
    return repl.get(name, name)


def parse_goods_list(text: str):
    """
    پارس لیست کالا به dict نام→عدد.
    فرمتهای مجاز:
      سکه: 300
      |🪵|~| چوب | : 300
      چوب 300
    خطوط بدون عدد (تیتر) نادیده گرفته می‌شوند.
    """
    text = normalize_digits(text or "").strip()
    if not text:
        return None, "لیست خالی است."
    bag = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # رد کردن تیترهای بدون عدد خالص در انتها
        qty = None
        name = None
        # |…| نام | : عدد
        m = re.search(
            r"\|[^|\n]*\|\s*[~\-•·]?\s*\|?\s*([^|\n:：]+?)\s*\|\s*[:=：]?\s*([\d]+(?:\.\d+)?)\s*$",
            line,
        )
        if m:
            name, qty = m.group(1), m.group(2)
        if name is None:
            m = re.search(r"([^|\n:：=]{1,40}?)\s*[:=：]\s*([\d]+(?:\.\d+)?)\s*$", line)
            if m:
                name, qty = m.group(1), m.group(2)
        if name is None:
            m = re.match(r"^(.+?)\s+([\d]+(?:\.\d+)?)\s*$", line)
            if m:
                name, qty = m.group(1), m.group(2)
        if name is None or qty is None:
            # تیتر یا خط تزئینی — رد
            continue
        name = _clean_item_name(name)
        if not name or len(name) > 40:
            continue
        if re.fullmatch(r"[\W\d_]+", name):
            continue
        try:
            val = float(qty)
        except ValueError:
            continue
        if val < 0:
            return None, f"مقدار منفی برای «{e(name)}» مجاز نیست."
        bag[name] = bag.get(name, 0) + val
    if not bag:
        return None, (
            "هیچ کالایی پیدا نشد.\n"
            "مثال:\n<code>|🪵|~| چوب | : 50</code>\nیا <code>چوب: 50</code>"
        )
    return bag, None


def format_goods(bag: dict) -> str:
    if not bag:
        return "—"
    lines = []
    for k, v in bag.items():
        num = int(v) if float(v) == int(v) else v
        lines.append(f"• {k}: <b>{num}</b>")
    return "\n".join(lines)


def apply_buff(amount: float, buff_pct: float) -> float:
    """باف مثبت = افزایش مقدار دریافتی؛ منفی = کاهش."""
    return amount * (1.0 + (buff_pct or 0) / 100.0)


def apply_buff_to_order(order: dict, buff_pct: float) -> dict:
    return {k: round(apply_buff(v, buff_pct), 2) for k, v in order.items()}
