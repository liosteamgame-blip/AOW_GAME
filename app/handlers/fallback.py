"""هندلرهای fallback"""

from aiogram import F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.loader import dp
from app.state import GROUPS, authenticated_users
from app.players import is_admin
from app.keyboards import _btn, get_admin_inline_keyboard
from app.channel import UPDATE_CHANGELOG, notify_groups_updated
from app.menus import go_menu


# ======================================================================
#        پیام‌های بدون وضعیت (مثلاً بعد از ری‌استارت ربات)
# ======================================================================
@dp.message(StateFilter(None), F.chat.type == "private")
async def fallback_handler(message: types.Message, state: FSMContext):
    u = authenticated_users.get(message.from_user.id)
    if u and u.get("role") == "player":
        await go_menu(message, state)
    elif u and u.get("role") == "admin":
        await message.answer("⚡️ پنل مدیریت:", reply_markup=get_admin_inline_keyboard())
    else:
        await message.answer("👋 برای شروع /start را بزنید.")


@dp.callback_query(F.data == "adm_send_update")
async def admin_send_update(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("✅ بله، به گروه‌ها بفرست", "adm_send_update_yes", "success"))
    builder.row(_btn("❌ انصراف", "back_to_admin"))
    await callback.message.answer(
        f"پیش‌نمایش پیام آپدیت:\n{DIV}\n{UPDATE_CHANGELOG}\n{DIV}\n"
        f"گروه‌های هدف: <b>{len(GROUPS)}</b>\nارسال شود؟",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "adm_send_update_yes")
async def admin_send_update_yes(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer("در حال ارسال…")
    await notify_groups_updated()
    await callback.message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
