"""هندلرهای admin_transfer"""
import re

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import BTN_BACK, DIV
from app.loader import dp
from app.state import pending_confirms
from app.utils import _norm_country_token, e, is_back_text
from app.factions import FACTIONS, FACTION_META, all_known_cities, cities_by_faction, country_key
from app.states import GameStates
from app.players import is_admin
from app.keyboards import _btn, _timing_menu_keyboard, get_admin_inline_keyboard, get_back_keyboard
from app.channel import _broadcast_timing_to_groups
from app.approvals import do_transfer, needs_approval, request_approval


async def _transfer_or_request(uid: int, src: str, dst: str) -> str:
    """واگذاری مستقیم، یا اگر تایید دونفره روشن و کاربر مالک نیست → درخواست برای مالک."""
    if needs_approval(uid):
        await request_approval(
            "transfer", {"src": src, "dst": dst}, uid,
            f"واگذاری <b>{e(src)}</b> → <b>{e(dst)}</b>",
        )
        return "🔐 واگذاری شهر نیاز به تایید مالک دارد؛ درخواست فرستاده شد."
    return do_transfer(src, dst)


@dp.callback_query(F.data == "adm_transfer")
async def admin_transfer_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await state.clear()
    builder = InlineKeyboardBuilder()
    for s in FACTIONS:
        flag, title = FACTION_META[s]
        builder.row(_btn(f"{flag} مبدأ از {title}", f"trf_from_side:{s}"))
    builder.row(_btn("✍️ ورود دستی", "trf_manual", "primary"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"🏙 <b>واگذاری شهر</b>\n{DIV}\n"
        "۱) ساید/شهر <b>مبدأ</b> را انتخاب کنید\n"
        "۲) سپس شهر <b>مقصد</b>\n"
        "دارایی، گروه و فرمانده به مقصد منتقل می‌شود.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "trf_manual")
async def admin_transfer_manual(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "فرمت:\n<code>واگذاری شهر_مبدأ شهر_مقصد</code>",
        reply_markup=get_back_keyboard(),
    )
    # state اختصاصی — قبلاً adm_set_timing بود و متن به‌عنوان تنظیمات تایم خوانده می‌شد
    pending_confirms.pop(callback.from_user.id, None)
    await state.set_state(GameStates.admin_transfer)


@dp.callback_query(F.data.startswith("trf_from_side:"))
async def admin_transfer_from_side(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    side = callback.data.split(":")[1]
    await callback.answer()
    cities = cities_by_faction(side) if side in FACTIONS else []
    if not cities:
        cities = [c for c in all_known_cities() if country_key(c) == side]
    builder = InlineKeyboardBuilder()
    for i, c in enumerate(cities[:30]):
        short = c.rsplit("_", 1)[0] if "_" in c else c
        builder.row(_btn(short, f"trf_from_city:{i}:{side}"))
    builder.row(_btn("🔙 بازگشت", "adm_transfer"))
    await state.update_data(trf_side=side, trf_cities=cities)
    await callback.message.answer("مبدأ را انتخاب کنید:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("trf_from_city:"))
async def admin_transfer_from_city(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    idx, side = int(parts[1]), parts[2]
    d = await state.get_data()
    cities = d.get("trf_cities") or cities_by_faction(side)
    if idx < 0 or idx >= len(cities):
        return await callback.answer("نامعتبر", show_alert=True)
    src = cities[idx]
    await state.update_data(trf_src=src)
    await callback.answer()
    builder = InlineKeyboardBuilder()
    for s in FACTIONS:
        flag, title = FACTION_META[s]
        builder.row(_btn(f"{flag} مقصد در {title}", f"trf_to_side:{s}"))
    builder.row(_btn("🔙 بازگشت", "adm_transfer"))
    await callback.message.answer(
        f"مبدأ: <b>{e(src)}</b>\nحالا ساید مقصد را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("trf_to_side:"))
async def admin_transfer_to_side(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    side = callback.data.split(":")[1]
    await callback.answer()
    cities = cities_by_faction(side) if side in FACTIONS else []
    builder = InlineKeyboardBuilder()
    for i, c in enumerate(cities[:30]):
        short = c.rsplit("_", 1)[0] if "_" in c else c
        builder.row(_btn(short, f"trf_to_city:{i}:{side}"))
    builder.row(_btn("🔙 بازگشت", "adm_transfer"))
    await state.update_data(trf_to_side=side, trf_to_cities=cities)
    await callback.message.answer("مقصد را انتخاب کنید:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("trf_to_city:"))
async def admin_transfer_to_city(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    idx = int(parts[1])
    d = await state.get_data()
    cities = d.get("trf_to_cities") or []
    src = d.get("trf_src")
    if idx < 0 or idx >= len(cities) or not src:
        return await callback.answer("نامعتبر", show_alert=True)
    dst = cities[idx]
    await callback.answer()
    msg = await _transfer_or_request(callback.from_user.id, src, dst)
    await state.clear()
    await callback.message.answer(msg, reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data.startswith("adm_broadcast_ts:"))
async def admin_broadcast_timing(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    kind = callback.data.split(":")[1]
    await callback.answer("در حال ارسال…")
    ok, fail, ch_ok = await _broadcast_timing_to_groups(kind, to_channel=True)
    label = "استارت" if kind == "start" else "استاپ"
    await callback.message.answer(
        f"📢 پیام {label} ارسال شد.\n"
        f"✅ گروه موفق: <b>{ok}</b> · ❌ ناموفق: <b>{fail}</b>\n"
        f"📣 کانال اصلی: {'✅' if ch_ok else '❌'}",
        reply_markup=_timing_menu_keyboard(),
    )


@dp.message(GameStates.admin_transfer)
async def admin_transfer_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    txt = (message.text or "").strip()
    txt = re.sub(r"^(واگذاری|transfer)\s*", "", txt, flags=re.I).strip()
    parts = re.split(r"\s+به\s+|\s+->\s+|\s+→\s+|\s+", txt)
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return await message.answer("❌ فرمت: <code>شهر_مبدا شهر_مقصد</code>")
    src, dst = parts[0], parts[1]
    known = {_norm_country_token(c) for c in all_known_cities()}
    if _norm_country_token(src) not in known:
        return await message.answer(
            f"❌ شهر مبدأ <b>{e(src)}</b> پیدا نشد. نام دقیق را بنویسید یا «{BTN_BACK}» بزنید."
        )
    msg = await _transfer_or_request(message.from_user.id, src, dst)
    await state.clear()
    await message.answer(msg, reply_markup=get_admin_inline_keyboard())
