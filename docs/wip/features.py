"""کلیدهای روشن/خاموش فیچرهای جدید و تنظیمات تکمیلی.

همه در SETTINGS ذخیره می‌شوند و از پنل ادمین («🧪 فیچرها») قابل تغییرند — بدون ری‌استارت.
"""
from app.state import SETTINGS

# key -> (عنوان، پیش‌فرض، توضیح کوتاه)
FEATURES = {
    "arrival_alerts": ("⏳ هشدار رسیدن لشکر", True,
                       "شمارش معکوس روی پست کانال + پیام رسیدن به گروه مهاجم و مدافع"),
    "report_card": ("🧾 کارنامه هفتگی", True,
                    "بعد از آپ، به‌جای رسید خام یک کارنامه خوانا برای گروه شهر"),
    "my_rank": ("🏆 رتبه من", True,
                "دکمه رتبه شهر در منوی اقتصادی (فقط رتبه خود شهر؛ اعداد بقیه نمایش داده نمی‌شود)"),
    "chronicle": ("📖 وقایع‌نامه", True,
                  "ثبت رویدادهای عمومی و ساخت وقایع‌نامه هفتگی برای کانال"),
    "quick_order": ("🔁 فرمان سریع", True,
                    "دکمه شهرهای خودم در انتخاب مبدأ + «مثل دفعه قبل»"),
    "audit_log": ("📜 لاگ ممیزی ادمین", True,
                  "ثبت همه تغییرات ادمینی با امکان برگشت"),
    "dual_approval": ("🔐 تایید دونفره", False,
                      "حذف شهر، بازیابی کامل و واگذاری توسط ادمین‌ها نیاز به تایید مالک دارد"),
    "error_reports": ("🚨 گزارش خطا به مالک", True,
                      "خطاهای ربات خلاصه‌شده برای مالک ارسال می‌شود (هر خطا حداکثر هر ۱۰ دقیقه)"),
    "inplace_menus": ("🪟 منوی درجا", True,
                      "دکمه‌های منو همان پیام را ویرایش می‌کنند تا گروه شلوغ نشود"),
    "city_card": ("🖼 کارت تصویری شهر", True,
                  "ساخت تصویر خلاصه شهر برای فرمانده"),
    "castle_buffs": ("🏰 باف/نرف قلعه‌ها", False,
                     "اعمال خودکار باف و نرف ۳۰ قلعه طبق کانال اطلاعات (روی اقتصاد اثر دارد)"),
    "rules_calendar": ("📅 تقویم قوانین", False,
                       "ارتقا، تجارت با بازیکن و تجار فقط در روزهای قانونی (طبق قوانین بازی)"),
}

# تنظیمات تکمیلی و مقدار پیش‌فرض‌شان (رشته‌ای)
EXTRA_SETTINGS = {
    # روزهای قانونی (۰=دوشنبه … ۶=یکشنبه) — طبق قوانین: ارتقا سه‌شنبه/چهارشنبه، تجارت پلیر شنبه/یکشنبه، تجار دوشنبه
    "days_upgrade": "1,2",
    "days_trade": "5,6",
    "days_merchant": "0",
    # آپ زمان‌بندی‌شده (طبق قوانین: بعد از استاپ چهارشنبه)
    "up_auto": "0",            # 1 = روشن
    "up_day": "2",             # ۲ = چهارشنبه
    "up_time": "23:30",
    "up_confirmed_for": "",    # تاریخ YYYY-MM-DD که ادمین آپ آن را تایید کرده
    "up_last_run": "",         # تاریخ آخرین آپ خودکار
    "up_postpone_min": "0",    # تعویق این هفته (دقیقه)
    # داشبورد زنده
    "dash_chat": "",
    "dash_mid": "",
    # کانال لاگ ممیزی (اختیاری)
    "log_chat": "",
    # سقف روزانه درخواست‌های xAI (کلید رایگان زود تمام می‌شود)
    "ai_daily_limit": "15",
    # شروع بازه وقایع‌نامه بعدی (epoch)
    "chronicle_since": "0",
}


def ensure_defaults():
    feats = SETTINGS.get("features")
    if not isinstance(feats, dict):
        feats = {}
    for k, (_t, default, _d) in FEATURES.items():
        feats.setdefault(k, bool(default))
    SETTINGS["features"] = feats
    for k, v in EXTRA_SETTINGS.items():
        SETTINGS.setdefault(k, v)


def enabled(key: str) -> bool:
    feats = SETTINGS.get("features")
    if not isinstance(feats, dict) or key not in feats:
        meta = FEATURES.get(key)
        return bool(meta[1]) if meta else False
    return bool(feats.get(key))


def set_enabled(key: str, value: bool) -> None:
    ensure_defaults()
    SETTINGS["features"][key] = bool(value)


def setting(key: str) -> str:
    v = SETTINGS.get(key)
    if v is None:
        v = EXTRA_SETTINGS.get(key, "")
    return str(v)


ensure_defaults()
