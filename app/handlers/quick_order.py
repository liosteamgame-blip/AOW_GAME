"""🔁 فرمان سریع: «🏰 شهرهای من» در انتخاب مبدأ و «🔁 مثل دفعه قبل».

«مثل دفعه قبل» فقط فرم را پر می‌کند؛ زمان رسیدن دوباره پرسیده می‌شود و کارت تایید مثل همیشه
می‌آید (تایم استاپ و اختیارات کمکی هم در تایید نهایی چک می‌شوند).
"""
from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.features import enabled
from app.keyboards import _btn
from app.loader import dp
from app.players import is_player, player_cities
from app.state import LAST_ORDERS
from app.states import GameStates
from app.utils import e, mtype_tag
from app.screens import ask_camp_time, show_order_confirm
from app.handlers.military import _set_city_field

FIELD_STATES = {
    "camp_origin": GameStates.camp_origin.state,
    "trade_origin": GameStates.trade_origin.state,
}
KIND_STATES = {
    "campaign": GameStates.camp_origin.state,
    "siege": GameStates.order_target.state,
    "war": GameStates.order_target.state,
}


def _short(name: str) -> str:
    base = name.rsplit("_", 1)[0].replace("_", " ") if "_" in name else name
    return (base.title() if base.isascii() else base)[:30]


@dp.callback_query(F.data.startswith("mycity:") | F.data.startswith("mycityp:"))
async def my_cities(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not enabled("quick_order") or not is_player(uid):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    field = parts[1] if len(parts) > 1 else ""
    if field not in FIELD_STATES or await state.get_state() != FIELD_STATES[field]:
        return await callback.answer("این فرم دیگر باز نیست؛ از منو دوباره شروع کنید.", show_alert=True)
    cities = player_cities(uid)
    if parts[0] == "mycity":
        await callback.answer()
        b = InlineKeyboardBuilder()
        for i, c in enumerate(cities[:10]):
            b.row(_btn(f"🏰 {_short(c)}", f"mycityp:{field}:{i}", "success"))
        b.row(_btn("🔙 انتخاب کشور", f"cityfacback:{field}"))
        try:
            return await callback.message.edit_text("🏰 <b>شهرهای شما</b> — مبدأ را انتخاب کنید:", reply_markup=b.as_markup())
        except Exception:
            return await callback.message.answer("🏰 <b>شهرهای شما</b> — مبدأ را انتخاب کنید:", reply_markup=b.as_markup())
    try:
        name = cities[int(parts[2])]
    except (IndexError, ValueError):
        return await callback.answer("شهر پیدا نشد.", show_alert=True)
    await callback.answer(f"✅ {name}")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _set_city_field(callback.message, state, field, name)


@dp.callback_query(F.data.startswith("quick:last:"))
async def quick_last(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not enabled("quick_order") or not is_player(uid):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    kind = callback.data.split(":", 2)[2]
    d = await state.get_data()
    if kind not in KIND_STATES or d.get("kind") != kind or await state.get_state() != KIND_STATES[kind]:
        return await callback.answer("این فرم دیگر باز نیست؛ از منو دوباره شروع کنید.", show_alert=True)
    last = (LAST_ORDERS.get(str(uid)) or {}).get(kind) or {}
    if not last.get("stats"):
        return await callback.answer("فرمان قبلی پیدا نشد.", show_alert=True)
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    # نوع (زمینی/دریایی) همان است که الان انتخاب شده
    if kind == "campaign":
        await state.update_data(origin=last.get("origin"), dest=last.get("dest"), stats=last.get("stats"))
        d = await state.get_data()
        await callback.message.answer(
            f"🔁 <b>همان فرمان قبلی</b>\n{DIV}\n"
            f"🧭 نوع: <b>{mtype_tag(d)}</b>\n📍 مبدأ: <b>{e(last.get('origin'))}</b>\n"
            f"🎯 مقصد: <b>{e(last.get('dest'))}</b>\n📊 آمار:\n<blockquote expandable>{e(last.get('stats'))}</blockquote>"
        )
        return await ask_camp_time(callback.message, state)
    await state.update_data(target=last.get("target"), stats=last.get("stats"))
    await show_order_confirm(callback.message, state, uid)
