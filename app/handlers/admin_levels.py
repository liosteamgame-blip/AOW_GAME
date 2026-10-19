"""هندلرهای admin_levels"""
import re

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.loader import dp
from app.state import GROUPS, pending_confirms
from app.utils import _clean_item_name, _norm_country_token, e, normalize_digits
from app.factions import FACTIONS, FACTION_META, all_known_cities, cities_by_faction, country_key
from app.states import GameStates
from app.players import _admin_cmd_city, is_admin
from app.keyboards import _btn, get_admin_inline_keyboard, get_back_keyboard
from app.economy.rules import SPECIAL_UNITS
from app.economy.sheet import parse_roll_buff_form
from app.economy.assets import _process_gasset_form, apply_extra_yields_to_city, free_level_up


@dp.callback_query(F.data == "adm_free_lv")
async def admin_free_lv_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await state.clear()
    builder = InlineKeyboardBuilder()
    for s in FACTIONS:
        flag, title = FACTION_META[s]
        builder.row(_btn(f"{flag} {title}", f"flv_side:{s}"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"⬆️ <b>افزایش سطح رایگان</b>\n{DIV}\n"
        "ساید شهر را انتخاب کنید (بدون کسر هزینه):",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("flv_side:"))
async def admin_free_lv_side(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    side = callback.data.split(":")[1]
    await callback.answer()
    cities = cities_by_faction(side) if side in FACTIONS else []
    if not cities:
        cities = [c for c in all_known_cities() if country_key(c) == side]
    builder = InlineKeyboardBuilder()
    for i, c in enumerate(cities[:35]):
        short = c.rsplit("_", 1)[0] if "_" in c else c
        builder.row(_btn(short, f"flv_city:{i}:{side}"))
    builder.row(_btn("🔙 بازگشت", "adm_free_lv"))
    await state.update_data(flv_side=side, flv_cities=cities)
    await callback.message.answer("شهر را انتخاب کنید:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("flv_city:"))
async def admin_free_lv_city(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    idx, side = int(parts[1]), parts[2]
    d = await state.get_data()
    cities = d.get("flv_cities") or []
    if idx < 0 or idx >= len(cities):
        return await callback.answer("نامعتبر", show_alert=True)
    city = cities[idx]
    await state.update_data(flv_city=city)
    await callback.answer()
    cats = [
        ("econ", "💰 اقتصادی"),
        ("prod", "🏗 تولیدی"),
        ("edu", "📚 آموزشی"),
        ("mil", "⚔️ نظامی / کمپ"),
        ("castle", "🏰 قلعه"),
        ("spec", "⭐ ویژه"),
    ]
    builder = InlineKeyboardBuilder()
    for ck, lab in cats:
        builder.row(_btn(lab, f"flv_cat:{ck}"))
    builder.row(_btn("🔙 بازگشت", f"flv_side:{side}"))
    await callback.message.answer(
        f"شهر: <b>{e(city)}</b>\nدسته را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("flv_cat:"))
async def admin_free_lv_cat(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    cat = callback.data.split(":")[1]
    await callback.answer()
    names = {
        "econ": ["خزانه", "تجارتخانه", "بندر", "آشپزخانه", "دهکده", "انبار"],
        "prod": ["چوب بری", "معدن سنگ", "معدن آهن", "پوشاک سازی", "باروت سازی"],
        "edu": ["دانشکده افسری", "مجمع نخبگان", "دانشگاه پزشکی"],
        "mil": [
            "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
            "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
            "توپ سبک", "توپ محاصره", "توپ سنگین",
            "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی", "اصطبل",
        ],
        "castle": ["قلعه"],
        "spec": sorted(SPECIAL_UNITS.keys()),
    }.get(cat, [])
    builder = InlineKeyboardBuilder()
    for i, n in enumerate(names[:40]):
        builder.row(_btn(n, f"flv_bldg:{i}"))
    builder.row(_btn("🔙 بازگشت", "adm_free_lv"))
    await state.update_data(flv_names=names)
    await callback.message.answer("ساختمان / کمپ:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("flv_bldg:"))
async def admin_free_lv_bldg(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    idx = int(callback.data.split(":")[1])
    d = await state.get_data()
    names = d.get("flv_names") or []
    if idx < 0 or idx >= len(names):
        return await callback.answer("نامعتبر", show_alert=True)
    name = names[idx]
    await state.update_data(flv_name=name)
    await callback.answer()
    builder = InlineKeyboardBuilder()
    for n in (1, 2, 3, 5):
        builder.row(_btn(f"+{n} سطح", f"flv_do:{n}"))
    builder.row(_btn("🔙 بازگشت", "adm_free_lv"))
    city = d.get("flv_city") or "?"
    await callback.message.answer(
        f"🏙 {e(city)} · 🏗 <b>{e(name)}</b>\nچند سطح؟",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("flv_do:"))
async def admin_free_lv_do(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    levels = int(callback.data.split(":")[1])
    d = await state.get_data()
    city, name = d.get("flv_city"), d.get("flv_name")
    if not city or not name:
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer()
    ok, msg = free_level_up(city, name, levels)
    await state.clear()
    await callback.message.answer(msg, reply_markup=get_admin_inline_keyboard())


@dp.message(F.text.regexp(r"(?i)^\s*افزایش\s*لول\s*ساختمان"))
async def admin_free_level_multi(message: types.Message):
    """افزایش لول ساختمان\nخزانه 1\nچوب بری 2"""
    if not is_admin(message.from_user.id):
        return
    city, err = _admin_cmd_city(message)
    if not city:
        return await message.answer(err)
    body = re.sub(r"(?i)^\s*افزایش\s*لول\s*ساختمان\s*:?\s*", "", message.text or "").strip()
    result = await _process_gasset_form(message, "gasset_lv", city, body)
    await message.answer(result[:4000])


@dp.message(F.text.regexp(r"(?i)^\s*ثبت\s*تلفات"))
async def admin_register_losses(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    city, err = _admin_cmd_city(message)
    if not city:
        return await message.answer(err)
    result = await _process_gasset_form(message, "gasset_loss", city, message.text or "")
    await message.answer(result[:4000])


@dp.message(F.text.regexp(r"(?i)^\s*افزایش\s+[\d,\s]+\s*سطح"))
async def admin_free_level(message: types.Message):
    """افزایش N سطح ساختمان بدون هزینه — فقط ادمین.
    مثال: افزایش 2 سطح خزانه
         افزایش 1,2,3 سطح معدن سنگ
    شهر از گپ ست‌شده یا ریپلای/آرگومان آخر.
    """
    if not is_admin(message.from_user.id):
        return
    txt = normalize_digits((message.text or "").strip())
    m = re.match(r"افزایش\s+([\d,\s]+)\s*سطح\s+(.+)$", txt)
    if not m:
        return await message.answer(
            "مثال:\n<code>افزایش 2 سطح خزانه</code>\n"
            "<code>افزایش 1 سطح دهکده</code>\n"
            "در گپ شهر یا با نام شهر در انتها."
        )
    levels_raw, rest = m.group(1), m.group(2).strip()
    # اگر چند عدد: مجموع
    nums = [int(x) for x in re.findall(r"\d+", levels_raw)]
    levels = sum(nums) if nums else 1
    # نام ساختمان و شهر اختیاری
    city = None
    name = rest
    # اگر آخرین توکن شهر باشد
    parts = rest.rsplit(None, 1)
    if len(parts) == 2:
        maybe_city = parts[1]
        for c in all_known_cities():
            if _norm_country_token(c) == _norm_country_token(maybe_city) or c.lower() == maybe_city.lower():
                city = c
                name = parts[0]
                break
    if not city and message.chat.type in ("group", "supergroup"):
        grp = GROUPS.get(message.chat.id)
        if grp:
            city = grp.get("city")
    if not city:
        return await message.answer("❌ شهر مشخص نیست. در گپ شهر بزنید یا نام شهر را آخر بنویسید.")
    name = _clean_item_name(name)
    ok, msg = free_level_up(city, name, levels)
    await message.answer(msg if ok else f"❌ {msg}")


@dp.message(F.text.regexp(r"(?i)^\s*اعمال\s*بازدهی\s*(رول|باف|نرف|رول\s*و\s*باف)?"))
async def admin_apply_roll_yield(message: types.Message, state: FSMContext):
    """اعمال بازدهی رول / باف ونرف — ادمین فرم را می‌فرستد."""
    if not is_admin(message.from_user.id):
        return
    txt = (message.text or "").strip()
    # اگر فقط دستور بدون بدنه باشد → بخواه فرم
    body = re.sub(r"(?i)^\s*اعمال\s*بازدهی\s*(رول|باف|نرف|رول\s*و\s*باف\s*ونرف)?\s*", "", txt).strip()
    city = None
    if message.chat.type in ("group", "supergroup"):
        grp = GROUPS.get(message.chat.id)
        if grp:
            city = grp.get("city")
    if not body or body == txt:
        await state.update_data(roll_city=city)
        await message.answer(
            "📝 فرم را بفرستید:\n"
            "<code>اعمال بازدهی رول و باف ونرف های شهر:\n"
            "بازدهی رول {سکه}: 500\n"
            "بازدهی باف 50%+ خزانه\n"
            "بازدهی نرف 30%- دهکده</code>\n\n"
            "یا تکی:\n<code>اعمال بازدهی سکه +800</code>\n"
            + (f"🏙 شهر فعلی گپ: <b>{e(city)}</b>" if city else "نام شهر را در خط اول بنویسید."),
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.adm_set_timing)  # reuse free-text capture next msg via fallback
        # store pending mode
        pending_confirms[message.from_user.id] = {"kind": "roll_form", "data": {"city": city}, "chat_id": message.chat.id}
        return
    # بدنه همراه دستور
    data = parse_roll_buff_form(body)
    if not city:
        # try first line as city
        first = body.splitlines()[0].strip()
        for c in all_known_cities():
            if _norm_country_token(c) == _norm_country_token(first):
                city = c
                break
    if not city:
        return await message.answer("❌ شهر مشخص نیست.")
    block = apply_extra_yields_to_city(city, data)
    await message.answer(f"✅ ثبت شد برای <b>{e(city)}</b>:\n<pre>{e(block)}</pre>")
