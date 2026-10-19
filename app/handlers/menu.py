"""هندلرهای menu"""
import logging

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app.config import DIV
from app.loader import dp
from app.utils import plain
from app.players import is_admin, is_player, player_group_access
from app.gametime import MILITARY_KINDS, military_closed_text
from app.keyboards import get_military_menu_keyboard
from app.menus import (
    go_menu,
    start_announcement,
    start_campaign,
    start_siege,
    start_trade,
    start_war,
)
from app.screens import (
    open_asset_edit_menu,
    open_economy_menu,
    start_asset_view,
    start_auto_upgrade,
    start_upgrade_advise,
)


@dp.callback_query(F.data.startswith("menu:"))
async def handle_menu_click(callback: types.CallbackQuery, state: FSMContext):
    kind = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    if kind == "close":
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    if kind == "home":
        await callback.answer()
        return await go_menu(callback.message, state, user_id=uid)
    # منوی نظامی
    if kind == "military":
        await callback.answer()
        try:
            await callback.message.edit_text(
                f"⚔️ <b>منوی نظامی</b>\n{DIV}\nلشکرکشی · جنگ · محاصره",
                reply_markup=get_military_menu_keyboard(),
            )
        except Exception:
            await callback.message.answer(
                f"⚔️ <b>منوی نظامی</b>\n{DIV}\nلشکرکشی · جنگ · محاصره",
                reply_markup=get_military_menu_keyboard(),
            )
        return
    # منوی اقتصادی — دارایی + دکمه‌ها
    if kind == "economy":
        await callback.answer()
        return await open_economy_menu(callback, state)
    if kind == "assets":
        await callback.answer()
        return await start_asset_view(callback, state)
    if kind == "advise":
        await callback.answer()
        return await start_upgrade_advise(callback, state)
    if kind == "upgrade":
        await callback.answer()
        return await start_auto_upgrade(callback, state)
    if kind == "asset_edit":
        if not is_admin(uid):
            return await callback.answer("❌ فقط ادمین.", show_alert=True)
        await callback.answer()
        return await open_asset_edit_menu(callback)

    if not is_player(uid) and not is_admin(uid):
        return await callback.answer("❌ این دستور برای شما نیست.", show_alert=True)
    if kind in MILITARY_KINDS:
        closed = military_closed_text(uid)
        if closed:
            return await callback.answer(closed[:200], show_alert=True)
    # لشکرکشی/محاصره/جنگ/تجارت/بیانیه — دسترسی گپ/پی‌وی
    if kind in ("campaign", "siege", "war", "trade", "statement"):
        chat = callback.message.chat if callback.message else None
        ok, _c, err = player_group_access(
            uid,
            chat_id=chat.id if chat else None,
            chat_type=chat.type if chat else None,
        )
        if not ok:
            return await callback.answer(
                plain(err or "دسترسی ندارید")[:190],
                show_alert=True,
            )
    await callback.answer()
    handlers = {
        "campaign": start_campaign,
        "siege": start_siege,
        "war": start_war,
        "statement": start_announcement,
        "trade": start_trade,
    }
    fn = handlers.get(kind)
    if fn:
        try:
            await fn(callback.message, state)
        except Exception:
            logging.exception("menu handler %s failed", kind)
            try:
                await callback.message.answer("❌ خطا در اجرای دستور. دوباره تلاش کنید یا /start بزنید.")
            except Exception:
                pass
