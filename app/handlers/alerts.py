"""هندلرهای alerts"""

from aiogram import F, types

from app.loader import dp


@dp.callback_query(F.data.startswith("alert_ack:"))
async def handle_alert_ack(callback: types.CallbackQuery):
    await callback.answer("ثبت شد — هوشیار بمانید.", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
