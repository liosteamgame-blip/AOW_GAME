"""هندلرهای orders"""

from aiogram import types
from aiogram.fsm.context import FSMContext

from app.loader import dp
from app.state import pending_confirms
from app.utils import need_text
from app.states import GameStates
from app.menus import go_menu
from app.screens import show_order_confirm
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
    await show_order_confirm(message, state, message.from_user.id)
