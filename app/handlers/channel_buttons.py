"""هندلرهای channel_buttons"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app.loader import dp
from app.state import active_actions, pending_confirms
from app.utils import e, need_text
from app.states import GameStates
from app.players import city_of
from app.gametime import parse_player_time
from app.keyboards import get_back_keyboard, get_confirm_keyboard
from app.menus import go_menu
from app.flows import resolve_action, start_dm_flow


# ---------------- کمین ----------------
@dp.callback_query(F.data.startswith("chan_ambush:"))
async def handle_inline_ambush(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(callback, "chan_ambush:", owner=False)
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.ambush_stats,
        f"🪓 سرورم شما هم اکنون در حال دستور <b>کمین</b> بر لشکریان <b>{e(city_of(action['owner_id']))}</b> هستید.\n\n"
        "📊 لطفا آمار خود را با توجه به <b>قوانین کمین</b> وارد کنید.",
    )


@dp.message(GameStates.ambush_stats)
async def process_ambush_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    d = await state.get_data()
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(message, state, "این عملیات دیگر معتبر نیست.")
    await state.update_data(stats=txt)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {"kind": "ambush", "data": dict(d), "chat_id": message.chat.id}
    await message.answer(
        f"🪓 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از دستور کمین خود بر لشکریان "
        f"<b>{e(city_of(action['owner_id']))}</b> با آمار:\n<blockquote>{e(txt)}</blockquote>\nموافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.ambush_confirm)


# ---------------- کمین کاروان تجاری ----------------
@dp.callback_query(F.data.startswith("chan_trade_ambush:"))
async def handle_trade_ambush(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(
        callback, "chan_trade_ambush:", owner=False, types_ok=("trade",),
    )
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.trade_ambush_stats,
        f"🪓 سرورم در حال <b>کمین به کاروان</b> شهر <b>{e(city_of(action['owner_id']))}</b> هستید.\n\n"
        "📊 آمار نیروی کمین‌زننده را وارد کنید (ریپلای):",
    )


@dp.message(GameStates.trade_ambush_stats)
async def process_trade_ambush_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    d = await state.get_data()
    action = active_actions.get(d.get("action_id"))
    if not action:
        return await go_menu(message, state, "این کاروان دیگر معتبر نیست.")
    await state.update_data(stats=txt)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {
        "kind": "trade_ambush", "data": dict(d), "chat_id": message.chat.id,
    }
    await message.answer(
        f"🪓 کمین به کاروان <b>{e(city_of(action['owner_id']))}</b>\n"
        f"آمار شما:\n<blockquote>{e(txt)}</blockquote>\nتایید می‌کنید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.trade_ambush_confirm)


# ---------------- تغییر مسیر ----------------
@dp.callback_query(F.data.startswith("chan_redir:"))
async def handle_inline_redirect(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(callback, "chan_redir:", owner=True)
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.redirect_target,
        "🔄 سرورم قصد دارید لشکریان خود را به کدام <b>مقصد جدید</b> ارسال کنید؟\n\n🎯 (شهر و کشور مقصد را وارد کنید)",
    )


@dp.message(GameStates.redirect_target)
async def process_redir_target(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(new_dest=txt)
    await message.answer("⏳ سرورم لطفا <b>زمان رسیدن جدید</b> لشکریان خود را وارد کنید.", reply_markup=get_back_keyboard())
    await state.set_state(GameStates.redirect_time)


@dp.message(GameStates.redirect_time)
async def process_redir_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    parsed, err = parse_player_time(txt)
    if err:
        return await message.answer(f"❌ {err}\nمثال: <code>12:00</code> یا <code>45</code>")
    await state.update_data(new_time=parsed)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {"kind": "redirect", "data": dict(d), "chat_id": message.chat.id}
    await message.answer(
        f"🔄 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>تغییر مسیر</b> لشکریان خود به مقصد "
        f"<b>{e(d['new_dest'])}</b> 🎯 با زمان رسیدن <b>{e(txt)}</b> ⏳ موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.redirect_confirm)


# ---------------- بک ----------------
@dp.callback_query(F.data.startswith("chan_back:"))
async def handle_inline_back(callback: types.CallbackQuery):
    action_id, action, err = resolve_action(callback, "chan_back:", owner=True)
    if err:
        return await callback.answer(err, show_alert=True)
    await start_dm_flow(
        callback, action_id, GameStates.back_time,
        "🔙 سرورم شما هم اکنون قصد <b>بک زدن</b> ارتش خود را دارید.\n\n⏳ لطفا <b>تایم رسیدن به مبدا</b> را وارد کنید.",
    )


@dp.message(GameStates.back_time)
async def process_back_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    parsed, err = parse_player_time(txt)
    if err:
        return await message.answer(f"❌ {err}\nمثال: <code>12:00</code> یا <code>45</code>")
    await state.update_data(back_time=parsed)
    d = await state.get_data()
    pending_confirms[message.from_user.id] = {"kind": "back", "data": dict(d), "chat_id": message.chat.id}
    await message.answer(
        f"🔙 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>بازگشت</b> لشکریان خود به مبدا "
        f"با زمان رسیدن <b>{e(txt)}</b> ⏳ موافق هستید؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.back_confirm)
