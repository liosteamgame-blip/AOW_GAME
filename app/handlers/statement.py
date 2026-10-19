"""هندلرهای statement"""

from aiogram import types
from aiogram.fsm.context import FSMContext

from app.config import DIV
from app.loader import dp
from app.state import pending_confirms
from app.utils import e, is_back_text
from app.states import GameStates
from app.players import city_of
from app.keyboards import get_back_keyboard, get_confirm_keyboard
from app.menus import go_menu


@dp.message(GameStates.ann_media)
async def process_ann_media(message: types.Message, state: FSMContext):
    if message.text and is_back_text(message.text):
        return await go_menu(message, state)
    if message.photo or message.video:
        caption = (message.caption or "").strip()
        if message.photo:
            kind, file_id = "photo", message.photo[-1].file_id
        else:
            kind, file_id = "video", message.video.file_id
        if caption:
            if len(caption) > 850:
                return await message.answer("❌ متن بیانیه برای عکس/ویدیو خیلی طولانی است (حداکثر ۸۵۰ کاراکتر). کوتاه‌تر کنید.")
            media = {"kind": kind, "file_id": file_id, "caption": caption}
        else:
            await state.update_data(ann_pending={"kind": kind, "file_id": file_id})
            await message.answer(
                "📝 حالا <b>متن بیانیه</b> را بفرستید (حداکثر ۸۵۰ کاراکتر).\n↩️ به این پیام <b>ریپلای</b> کنید.",
                reply_markup=get_back_keyboard(),
            )
            return
    elif message.text:
        d = await state.get_data()
        pending = d.get("ann_pending")
        if pending:
            if len(message.text) > 850:
                return await message.answer("❌ متن خیلی طولانی است (حداکثر ۸۵۰ کاراکتر). کوتاه‌تر کنید.")
            media = {"kind": pending["kind"], "file_id": pending["file_id"], "caption": message.text.strip()}
            await state.update_data(ann_pending=None)
        else:
            if len(message.text) > 3500:
                return await message.answer("❌ متن بیانیه خیلی طولانی است. کوتاه‌تر کنید.")
            media = {"kind": "text", "file_id": None, "caption": message.text.strip()}
    else:
        return await message.answer("❌ لطفاً متن، عکس یا ویدیو ارسال کنید (به پیام ربات ریپلای کنید).")

    await state.update_data(ann=media)
    pending_confirms[message.from_user.id] = {
        "kind": "ann",
        "data": {"ann": media},
        "chat_id": message.chat.id,
    }
    preview = e(media["caption"][:200]) + ("…" if len(media["caption"]) > 200 else "")
    extra = "🖼 همراه تصویر/ویدیو" if media["kind"] != "text" else "📝 فقط متن"
    await message.answer(
        f"📜 فرمانده <b>{e(city_of(message.from_user.id))}</b> آیا از <b>صدور بیانیه</b> خود مطمئن هستید؟\n"
        f"{DIV}\n{extra}\n<blockquote>{preview}</blockquote>",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.ann_confirm)
