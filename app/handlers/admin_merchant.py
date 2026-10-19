"""هندلرهای admin_merchant"""
import re

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import state as app_state
from app.config import DIV
from app.loader import dp
from app.state import MERCHANT_LIMITS, MERCHANT_PRICES
from app.utils import e, fmt_num, format_goods, is_back_text, normalize_digits, parse_goods_list
from app.states import GameStates
from app.players import is_admin
from app.keyboards import _btn, get_admin_inline_keyboard, get_back_keyboard
from app.storage import save_data
from app.economy.merchants import (
    announce_merchants_to_channel,
    format_merchant_catalog,
    item_buy_price,
    item_sell_price,
)


# ---------------- لیست تجار ----------------
@dp.callback_query(F.data == "adm_merchant")
async def admin_merchant_menu(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    body = format_merchant_catalog()
    en_lbl = "✅ فعال" if app_state.MERCHANT_ENABLED else "❌ غیرفعال"
    builder = InlineKeyboardBuilder()
    builder.row(_btn(f"🔌 تجارت با تجار: {en_lbl}", "adm_merchant_toggle"))
    builder.row(_btn("📝 تنظیم لیست سقف", "adm_merchant_set", "primary"))
    builder.row(_btn("🏷 قیمت هر کالا جداگانه", "adm_merchant_item_prices", "success"))
    builder.row(
        _btn(f"💰 خرید پیش‌فرض {fmt_num(app_state.MERCHANT_BUY_PRICE)}", "adm_merchant_price:buy"),
        _btn(f"💰 فروش پیش‌فرض {fmt_num(app_state.MERCHANT_SELL_PRICE)}", "adm_merchant_price:sell"),
    )
    builder.row(_btn(f"🎚 باف پیش‌فرض ({fmt_num(app_state.MERCHANT_BUFF_DEFAULT)}%)", "adm_merchant_buff"))
    builder.row(_btn("🗑 پاک کردن لیست", "adm_merchant_clear", "danger"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"🛒 <b>لیست تجار</b>\n{DIV}\n{body}\n\n"
        f"وضعیت: <b>{en_lbl}</b>\n"
        f"پیش‌فرض خرید/فروش: <b>{fmt_num(app_state.MERCHANT_BUY_PRICE)}</b> / <b>{fmt_num(app_state.MERCHANT_SELL_PRICE)}</b>\n"
        f"🎚 باف: <b>{fmt_num(app_state.MERCHANT_BUFF_DEFAULT)}%</b>",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "adm_merchant_toggle")
async def admin_merchant_toggle(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    app_state.MERCHANT_ENABLED = not app_state.MERCHANT_ENABLED
    save_data(critical=True)
    await callback.answer("✅ فعال شد" if app_state.MERCHANT_ENABLED else "❌ غیرفعال شد")
    # اعلان کانال اصلی
    try:
        await announce_merchants_to_channel(app_state.MERCHANT_ENABLED)
    except Exception:
        pass
    return await admin_merchant_menu(callback, None)


@dp.callback_query(F.data == "adm_merchant_item_prices")
async def admin_merchant_item_prices(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    if not MERCHANT_LIMITS:
        return await callback.message.answer("❌ اول لیست سقف را تنظیم کنید.")
    builder = InlineKeyboardBuilder()
    for name in MERCHANT_LIMITS:
        buy = item_buy_price(name)
        sell = item_sell_price(name)
        builder.row(_btn(f"{name} 🛒{fmt_num(buy)}/💰{fmt_num(sell)}", f"adm_item_price:{name}"))
    builder.row(_btn("🔙 بازگشت", "adm_merchant"))
    await callback.message.answer(
        "🏷 کالا را انتخاب کنید تا قیمت خرید/فروش جداگانه ست شود:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("adm_item_price:"))
async def admin_item_price_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    name = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.update_data(price_item=name)
    buy = item_buy_price(name)
    sell = item_sell_price(name)
    await callback.message.answer(
        f"🏷 قیمت <b>{e(name)}</b>\n"
        f"فعلی — خرید: <b>{fmt_num(buy)}</b> · فروش: <b>{fmt_num(sell)}</b>\n\n"
        "بفرستید به صورت:\n<code>خرید فروش</code>\n"
        "مثال: <code>5 2</code> یا <code>خرید:5 فروش:2</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_price)
    await state.update_data(price_which="item")


@dp.callback_query(F.data == "adm_merchant_set")
async def admin_merchant_set(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "📝 کل لیست تجار را بفرستید (همان فرمت بازی):\n"
        "<code>⚜️ لیست …\n|🪵|~| چوب | : 300\n|🔩|~| آهن | : 300</code>\n\n"
        "اعداد = سقف مجاز خرید.\nمتن کامل برای نمایش به پلیر ذخیره می‌شود.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_merchant)


@dp.message(GameStates.adm_set_merchant)
async def admin_merchant_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    raw = (message.text or "").strip()
    bag, err = parse_goods_list(raw)
    if err:
        return await message.answer(f"❌ {err}")
    MERCHANT_LIMITS.clear()
    MERCHANT_LIMITS.update(bag)
    app_state.MERCHANT_LIST_TEXT = raw
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ لیست تجار ذخیره شد ({len(MERCHANT_LIMITS)} کالا):\n{format_goods(MERCHANT_LIMITS)}\n\n"
        f"💰 خرید: {fmt_num(app_state.MERCHANT_BUY_PRICE)} · فروش: {fmt_num(app_state.MERCHANT_SELL_PRICE)}",
        reply_markup=get_admin_inline_keyboard(),
    )


@dp.callback_query(F.data.startswith("adm_merchant_price:"))
async def admin_merchant_price_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    which = callback.data.split(":")[1]  # buy | sell
    await callback.answer()
    await state.update_data(price_which=which)
    label = "خرید" if which == "buy" else "فروش"
    cur = app_state.MERCHANT_BUY_PRICE if which == "buy" else app_state.MERCHANT_SELL_PRICE
    await callback.message.answer(
        f"💰 قیمت <b>{label}</b> هر عدد کالا (سکه) — فعلی: <b>{fmt_num(cur)}</b>\n"
        "عدد جدید را بفرستید:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_price)


@dp.message(GameStates.adm_set_price)
async def admin_merchant_price_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    raw = normalize_digits(message.text or "").strip()
    d = await state.get_data()
    which = d.get("price_which", "buy")

    # قیمت جداگانه یک کالا: "5 2" یا "خرید:5 فروش:2"
    if which == "item":
        name = d.get("price_item") or ""
        nums = re.findall(r"[\d.]+", raw)
        if len(nums) < 2:
            return await message.answer("❌ دو عدد بفرستید: <code>خرید فروش</code> مثال <code>5 2</code>")
        try:
            buy_v, sell_v = float(nums[0]), float(nums[1])
        except ValueError:
            return await message.answer("❌ عدد نامعتبر.")
        if buy_v < 0 or sell_v < 0:
            return await message.answer("❌ قیمت منفی مجاز نیست.")
        MERCHANT_PRICES[name] = {"buy": buy_v, "sell": sell_v}
        save_data(critical=True)
        await state.clear()
        return await message.answer(
            f"✅ {e(name)} — خرید <b>{fmt_num(buy_v)}</b> · فروش <b>{fmt_num(sell_v)}</b>",
            reply_markup=get_admin_inline_keyboard(),
        )

    try:
        val = float(raw)
    except ValueError:
        return await message.answer("❌ عدد نامعتبر.")
    if val < 0:
        return await message.answer("❌ قیمت منفی مجاز نیست.")
    if which == "sell":
        app_state.MERCHANT_SELL_PRICE = val
        label = "فروش پیش‌فرض"
    else:
        app_state.MERCHANT_BUY_PRICE = val
        label = "خرید پیش‌فرض"
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ قیمت {label}: <b>{fmt_num(val)}</b> سکه",
        reply_markup=get_admin_inline_keyboard(),
    )


@dp.callback_query(F.data == "adm_merchant_buff")
async def admin_merchant_buff(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        f"🎚 باف پیش‌فرض فعلی: <b>{fmt_num(app_state.MERCHANT_BUFF_DEFAULT)}%</b>\n"
        "عدد جدید را بفرستید (مثلاً <code>15</code> یا <code>-10</code>):",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_buff)


@dp.message(GameStates.adm_set_buff)
async def admin_merchant_buff_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    raw = normalize_digits(message.text or "").strip().replace("%", "")
    try:
        app_state.MERCHANT_BUFF_DEFAULT = float(raw)
    except ValueError:
        return await message.answer("❌ عدد نامعتبر.")
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ باف پیش‌فرض: <b>{fmt_num(app_state.MERCHANT_BUFF_DEFAULT)}%</b>",
        reply_markup=get_admin_inline_keyboard(),
    )


@dp.callback_query(F.data == "adm_merchant_clear")
async def admin_merchant_clear(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    MERCHANT_LIMITS.clear()
    save_data(critical=True)
    await callback.answer("پاک شد")
    await callback.message.answer("🗑 لیست تجار خالی شد.", reply_markup=get_admin_inline_keyboard())
