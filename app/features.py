"""کلیدهای روشن/خاموش فیچرهای جدید و تنظیمات تکمیلی.

همه در SETTINGS ذخیره می‌شوند و از پنل ادمین («🧪 فیچرها») قابل تغییرند — بدون ری‌استارت.
هر فیچر جدید که ساخته می‌شود باید یک کلید اینجا بگیرد.
"""
from app.state import SETTINGS

# key -> (عنوان، پیش‌فرض، توضیح کوتاه)
FEATURES = {
    "audit_log": ("📜 لاگ ممیزی ادمین", True,
                  "ثبت تغییرات ادمینی دارایی شهرها با امکان برگشت توسط مالک"),
    "dual_approval": ("🔐 تایید دونفره", False,
                      "حذف شهر، بازیابی کامل و واگذاری توسط ادمین غیرمالک نیاز به تایید مالک دارد"),
    "leader_panel": ("🏴 پنل لیدر جناح", True,
                     "خلاصه قدرت شهرهای جناح، پیام به گروه‌های جناح و نظرسنجی"),
    "assistant_perms": ("🤝 اختیارات کمکی‌ها", True,
                        "فرمانده تعیین می‌کند کمکی‌ها کدام فرمان‌ها را بدهند"),
}

# تنظیمات تکمیلی (رشته‌ای) و مقدار پیش‌فرض‌شان — در apply_data بازیابی می‌شوند
EXTRA_SETTINGS = {
    # کانال/گروه لاگ ممیزی (اختیاری، آیدی عددی)
    "log_chat": "",
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


def restore_features(raw_settings: dict) -> None:
    """بخش فیچرها از بکاپ؛ بکاپ قدیمی بدون این کلیدها هم سالم لود می‌شود (پیش‌فرض‌ها)."""
    feats = raw_settings.get("features") if isinstance(raw_settings, dict) else None
    SETTINGS["features"] = {}
    if isinstance(feats, dict):
        for k, v in feats.items():
            if k in FEATURES:
                SETTINGS["features"][k] = bool(v)
    for k, default in EXTRA_SETTINGS.items():
        if isinstance(raw_settings, dict) and raw_settings.get(k) is not None:
            SETTINGS[k] = str(raw_settings[k])
        else:
            SETTINGS[k] = default
    ensure_defaults()


ensure_defaults()
