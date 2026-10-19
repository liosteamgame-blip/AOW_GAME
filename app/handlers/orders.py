"""هندلرهای orders"""

from aiogram import types
from aiogram.fsm.context import FSMContext

from app.config import DIV, ORDERS
from app.loader import dp
from app.state import pending_confirms
from app.utils import e, mtype_tag, need_text
from app.states import GameStates
from app.players import city_of, context_city
from app.keyboards import get_confirm_keyboard
from app.menus import go_menu
from app.handlers.military import _set_city_field


@dp.message(GameStates.order_target)
async def process_order_target(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "order_target", txt)


@dp.message(GameStates.order_stats)
async def process_order_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    await state.update_data(stats=txt)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {
        "kind": d.get("kind", "siege"),
        "data": dict(d),
        "chat_id": message.chat.id,
    }
    icon = "🔥" if d.get("kind") == "war" else "🏰"
    await message.answer(
        f"{icon} <b>پیش‌نویس فرمان {ORDERS[d['kind']]['noun']}</b>\n{DIV}\n"
        f"👑 فرمانده: <b>{e(context_city(message)[1] or city_of(message.from_user.id))}</b>\n"
        f"🧭 نوع: <b>{mtype_tag(d)}</b>\n"
        f"🎯 شهر هدف: <b>{e(d['target'])}</b>\n\n"
        f"📊 <b>آمار ارتش:</b>\n<blockquote expandable>{e(d['stats'])}</blockquote>\n"
        "سرورم، فرمان صادر شود؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.order_confirm)
