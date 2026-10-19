"""هندلرهای confirm"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app.config import ORDERS
from app.loader import dp
from app.state import pending_confirms
from app.utils import e
from app.states import GameStates
from app.permissions import assistant_block_text
from app.gametime import MILITARY_KINDS, military_closed_text
from app.menus import go_menu
from app.flows import (
    _finish_ambush,
    _finish_ann,
    _finish_back,
    _finish_campaign,
    _finish_mtrade,
    _finish_order,
    _finish_redirect,
    _finish_trade,
    _finish_trade_ambush,
    cancel_order,
)


_confirm_inflight = set()


@dp.callback_query(F.data.startswith("confirm:"))
async def process_universal_confirm(callback: types.CallbackQuery, state: FSMContext):
    # جلوگیری از دابل‌کلیک: تا تایید قبلی تمام نشده، کلیک دوم نادیده گرفته می‌شود
    # (وگرنه از روی FSM دوباره pending ساخته می‌شد → پست تکراری در کانال / کسر دوباره سکه)
    uid = callback.from_user.id
    if uid in _confirm_inflight:
        return await callback.answer("⏳ در حال پردازش…")
    _confirm_inflight.add(uid)
    try:
        await _process_universal_confirm(callback, state)
    finally:
        _confirm_inflight.discard(uid)


async def _process_universal_confirm(callback: types.CallbackQuery, state: FSMContext):
    """
    تایید واحد — وابسته به pending_confirms است تا اگر FSM از بین رفت
    (ری‌استارت / باگ گروه) دکمه تایید همچنان کار کند.
    """
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]
    pending = pending_confirms.pop(uid, None)

    # اگر pending نبود از state بخوان
    if not pending:
        st = await state.get_state()
        d = await state.get_data()
        if st == GameStates.camp_confirm.state and d.get("origin"):
            pending = {"kind": "campaign", "data": d}
        elif st == GameStates.order_confirm.state and d.get("target"):
            pending = {"kind": d.get("kind", "siege"), "data": d}
        elif st == GameStates.ann_confirm.state and d.get("ann"):
            pending = {"kind": "ann", "data": d}
        elif st == GameStates.ambush_confirm.state and d.get("action_id"):
            pending = {"kind": "ambush", "data": d}
        elif st == GameStates.redirect_confirm.state and d.get("new_dest"):
            pending = {"kind": "redirect", "data": d}
        elif st == GameStates.back_confirm.state and d.get("back_time"):
            pending = {"kind": "back", "data": d}
        elif st == GameStates.trade_confirm.state and d.get("origin") and d.get("dest"):
            pending = {"kind": "trade", "data": d}
        elif st == GameStates.trade_ambush_confirm.state and d.get("action_id"):
            pending = {"kind": "trade_ambush", "data": d}
        elif st == GameStates.mtrade_confirm.state and d.get("mtrade_order"):
            pending = {
                "kind": "mtrade",
                "data": {
                    "order": d.get("mtrade_order"),
                    "buff": d.get("mtrade_buff", 0),
                    "after": d.get("mtrade_after"),
                    "cost": d.get("mtrade_cost", 0),
                    "mode": d.get("mtrade_mode", "buy"),
                },
            }

    if not pending:
        return await callback.answer(
            "این تایید منقضی شده. دوباره از منو شروع کنید.",
            show_alert=True,
        )

    await callback.answer()
    kind = pending["kind"]
    d = pending["data"]
    # state تایید مصرف شد — کلیک بعدی روی همین دکمه‌ی قدیمی دوباره pending نمی‌سازد
    await state.set_state(None)

    if action in ("no", "back"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        cancel_msgs = {
            "campaign": "❌ سرورم اعزام لشکرکشی شما <b>لغو</b> شد.",
            "siege": ORDERS["siege"]["cancelled"],
            "war": ORDERS["war"]["cancelled"],
            "ann": "❌ سرورم صدور بیانیه شما <b>لغو</b> شد.",
            "ambush": "❌ سرورم دستور کمین شما <b>لغو</b> شد.",
            "redirect": "❌ سرورم تغییر مسیر لشکریان شما <b>لغو</b> شد.",
            "back": "❌ سرورم دستور بازگشت لشکریان شما <b>لغو</b> شد.",
            "trade": "❌ سرورم تجارت شما <b>لغو</b> شد.",
            "trade_ambush": "❌ کمین کاروان <b>لغو</b> شد.",
            "mtrade": "❌ تجارت با تجار <b>لغو</b> شد.",
        }
        return await go_menu(callback.message, state, cancel_msgs.get(kind, "❌ لغو شد."))

    if action != "yes":
        return

    # فرمی که قبل از استاپ شروع شده ولی بعد از استاپ تایید می‌شود
    chat_id = callback.message.chat.id if callback.message else None
    blocked = assistant_block_text(callback.from_user.id, chat_id, kind)
    if blocked:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await go_menu(callback.message, state, e(blocked))

    if kind in MILITARY_KINDS:
        closed = military_closed_text(callback.from_user.id)
        if closed:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return await go_menu(callback.message, state, e(closed))

    if kind == "campaign":
        return await _finish_campaign(callback, state, d)
    if kind in ("siege", "war"):
        return await _finish_order(callback, state, d)
    if kind == "ann":
        return await _finish_ann(callback, state, d)
    if kind == "ambush":
        return await _finish_ambush(callback, state, d)
    if kind == "redirect":
        return await _finish_redirect(callback, state, d)
    if kind == "back":
        return await _finish_back(callback, state, d)
    if kind == "trade":
        return await _finish_trade(callback, state, d)
    if kind == "trade_ambush":
        return await _finish_trade_ambush(callback, state, d)
    if kind == "mtrade":
        return await _finish_mtrade(callback, state, d)
    await callback.message.answer("⚠️ نوع تایید ناشناخته. از منو دوباره شروع کنید.")


@dp.callback_query(F.data.startswith("chan_cancelsiege:"))
async def handle_cancel_siege(callback: types.CallbackQuery):
    await cancel_order(callback, "chan_cancelsiege:", "siege")


@dp.callback_query(F.data.startswith("chan_cancelwar:"))
async def handle_cancel_war(callback: types.CallbackQuery):
    await cancel_order(callback, "chan_cancelwar:", "war")
