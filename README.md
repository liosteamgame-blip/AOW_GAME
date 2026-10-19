# ربات خاکستر جنگ (Ashes of War)

ربات تلگرامی بازی نقش‌آفرینی «خاکستر جنگ» — aiogram 3، اجرا روی Railway.

## ساختار پوشه‌ها

```
main.py                 نقطه شروع (Procfile: worker: python main.py)
app/
  config.py             متغیرهای محیطی و متن‌های ثابت
  loader.py             Bot و Dispatcher مشترک
  state.py              همه داده‌های زنده بازی (فقط همین‌جا تعریف می‌شوند)
  storage.py            ذخیره محلی + بکاپ پین‌شده در تلگرام + بازیابی
  players.py            نقش و شهر کاربران و دسترسی در هر گپ
  factions.py           سایدها و نام شهرها
  gametime.py           تایم استارت/استاپ و زمان رسیدن
  keyboards.py          کیبوردها      menus.py   منوی اصلی
  art.py                آرت پست‌ها    channel.py ارسال به کانال‌ها
  castles.py            باف/نرف قلعه‌ها
  screens.py            صفحه‌های منوی اقتصادی/دارایی/مشاور
  flows.py              مرحله نهایی فرمان‌ها بعد از تایید
  economy/              قوانین، شیت دارایی، هزینه، آپ هفتگی، مشاور، تجار
  handlers/             هندلرهای تلگرام — ترتیب import در __init__.py مهم است
  scheduler.py          ارسال خودکار استارت/استاپ و بکاپ دوره‌ای
  bootstrap.py          راه‌اندازی
assets/art.zip          ۵۰ آرت پست‌ها (فایل‌ها: art_<نوع>_<land|sea|all>_<کشور>_<شماره>.jpg)
tests/                  تست‌ها + شبیه‌ساز تلگرام (بدون اینترنت)
docs/                   یادداشت‌ها برای توسعه
```

## راه‌اندازی روی Railway

1. کل پوشه را در یک ریپوی گیت‌هاب بگذارید و به Railway وصل کنید.
2. متغیرهای `.env.example` را در **Variables** ریلوی وارد کنید (حداقل `BOT_TOKEN` و `ADMIN_ID`).
3. Railway خودش `requirements.txt` را نصب و `Procfile` را اجرا می‌کند.

داده‌ها با هر تغییر به‌صورت فایل `aof_data.json` در پی‌وی مالک (یا `BACKUP_CHAT_ID`) پین می‌شوند
و بعد از هر Deploy خودکار بازیابی می‌شوند. آن پیام را حذف یا آن‌پین نکنید.

## اجرای محلی

```bash
pip install -r requirements-dev.txt
cp .env.example .env   # و مقادیر را پر کنید؛ سپس متغیرها را export کنید
python main.py
```

## تست‌ها

```bash
python -m pytest            # یا: python -m unittest discover tests
```

- `tests/test_structure.py` بررسی می‌کند همه ۱۶۷ هندلر نسخه‌ی تک‌فایلی با همان ترتیب ثبت شده باشند.
- `tests/test_smoke.py` چند مسیر کامل را با آپدیت جعلی اجرا می‌کند (ورود ادمین، ست گپ/پلیر، لشکرکشی تا پست کانال، و اینکه پلیر عادی به فرم ادمین دسترسی ندارد).
- `tests/fakebot.py` شبیه‌ساز تلگرام است؛ برای تست فیچرهای جدید از آن استفاده کنید.

## افزودن آرت

فایل جدید را با الگوی نام بالا داخل `assets/art.zip` بگذارید (یا در پوشه `assets/images/`).
