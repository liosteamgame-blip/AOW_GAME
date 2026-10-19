"""هندلرهای start"""
import logging
import secrets
import time

from aiogram import F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import BACKUP_NAME
from app.loader import dp
from app.state import GROUPS, PLAYER_CODES, all_players, authenticated_users
from app.utils import e
from app.states import GameStates
from app.players import is_admin, is_group_chat, is_player
from app.keyboards import _btn, get_admin_inline_keyboard
from app.storage import apply_restore, load_backup_document, push_backup, restore_preview_text
from app.menus import go_menu


# ======================================================================
#                          هسته احراز هویت
# ======================================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    if is_group_chat(message):
        return await group_start(message, state)
    await state.clear()
    user_id = message.from_user.id
    user_data = authenticated_users.get(user_id)
    if user_data:
        if user_data["role"] == "admin":
            await message.answer("⚡️ سلام رئیس! به پنل مدیریت شیشه‌ای خوش آمدید.", reply_markup=get_admin_inline_keyboard())
        else:
            await go_menu(message, state)
    else:
        await message.answer("⚔️ سلام فرمانده! به بازی <b>خاکستر جنگ</b> خوش آمدید.\n\n🔑 لطفاً <b>کد ورود اختصاصی</b> شهر خود را ارسال کنید:")
        await state.set_state(GameStates.waiting_for_code)


@dp.message(Command("backup"))
async def cmd_backup(message: types.Message):
    """ادمین: پشتیبان فوری بگیر و پین کن."""
    if not is_admin(message.from_user.id):
        return
    try:
        await push_backup()
        await message.answer(
            f"✅ پشتیبان گرفته شد و در چت پشتیبان ارسال/به‌روز شد.\n"
            f"🏙 {len(PLAYER_CODES)} · 👤 {len(all_players)} · 👥 {len(GROUPS)}\n"
            f"پیام <code>{BACKUP_NAME}</code> را <b>پین</b> نگه دارید."
        )
    except Exception as ex:
        logging.exception("cmd_backup")
        await message.answer(f"❌ پشتیبان ناموفق: <code>{e(str(ex)[:200])}</code>")


# بازیابی‌های منتظر تایید: token -> {"raw", "uid", "ts"}
_pending_restores = {}
RESTORE_CONFIRM_TTL = 600


async def ask_restore_confirm(message: types.Message, document):
    """فایل را می‌خواند، پیش‌نمایش می‌دهد و فقط بعد از دکمه تایید اعمال می‌کند."""
    raw, err = await load_backup_document(document)
    if raw is None:
        return await message.answer(f"❌ {err}")
    now = time.time()
    for k in [k for k, v in _pending_restores.items() if now - v["ts"] > RESTORE_CONFIRM_TTL]:
        _pending_restores.pop(k, None)
    token = secrets.token_hex(4)
    _pending_restores[token] = {"raw": raw, "uid": message.from_user.id, "ts": now}
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ تایید بازیابی", f"restore_ok:{token}", "danger"),
        _btn("❌ انصراف", f"restore_no:{token}"),
    )
    await message.answer(restore_preview_text(raw), reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("restore_ok:") | F.data.startswith("restore_no:"))
async def handle_restore_confirm(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ فقط ادمین.", show_alert=True)
    action, token = callback.data.split(":", 1)
    pend = _pending_restores.get(token)
    if not pend or time.time() - pend["ts"] > RESTORE_CONFIRM_TTL:
        _pending_restores.pop(token, None)
        return await callback.answer("این درخواست منقضی شده؛ فایل را دوباره بفرستید.", show_alert=True)
    if pend["uid"] != callback.from_user.id:
        return await callback.answer("❌ فقط کسی که فایل را فرستاده می‌تواند تایید کند.", show_alert=True)
    _pending_restores.pop(token, None)   # پیش از await — دابل‌کلیک دو بار اعمال نمی‌کند
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if action == "restore_no":
        await callback.answer("لغو شد")
        return await callback.message.answer("❌ بازیابی لغو شد؛ داده‌ها تغییری نکردند.")
    await callback.answer("در حال بازیابی…")
    ok, info = await apply_restore(pend["raw"])
    if ok:
        await callback.message.answer(
            f"{info}\nبرای اطمینان <code>/backup</code> بزنید تا پین به‌روز شود.",
            reply_markup=get_admin_inline_keyboard(),
        )
    else:
        await callback.message.answer(info)


@dp.message(Command("restore"))
async def cmd_restore(message: types.Message):
    """ادمین: /restore را با فایل aof_data.json بفرست یا ریپلای روی فایل."""
    if not is_admin(message.from_user.id):
        return
    doc = None
    if message.document:
        doc = message.document
    elif message.reply_to_message and message.reply_to_message.document:
        doc = message.reply_to_message.document
    if not doc:
        return await message.answer(
            "📥 فایل <code>aof_data.json</code> را ضمیمه کنید یا روی همان فایل ریپلای کنید و "
            "<code>/restore</code> بزنید.\n"
            "همچنین می‌توانید فقط فایل را بدون دستور برای ربات بفرستید."
        )
    await ask_restore_confirm(message, doc)


@dp.message(F.document, F.chat.type == "private")
async def admin_document_restore(message: types.Message, state: FSMContext):
    """اگر ادمین در پی‌وی فایل json پشتیبان بفرستد → بازیابی."""
    if not is_admin(message.from_user.id):
        return
    if not message.document:
        return
    fname = (message.document.file_name or "").lower()
    if not (fname.endswith(".json") or fname == BACKUP_NAME.lower()):
        return
    # اگر وسط فرم دیگری است دست نزن
    st = await state.get_state()
    if st and st not in (None, GameStates.main_menu.state):
        return
    await ask_restore_confirm(message, message.document)


# ---------------- ثبت گروه به‌جای پی‌وی («ست گپ» / «ست پلیر») ----------------
async def group_start(message: types.Message, state: FSMContext):
    if is_player(message.from_user.id):
        return await go_menu(message, state)
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    grp = GROUPS.get(message.chat.id)
    builder = InlineKeyboardBuilder()
    if grp:
        builder.button(text="🔄 تغییر شهر گروه", callback_data="grp_setcity")
        text = (
            f"🏙 این گروه به شهر <b>{e(grp['city'])}</b> متصل است.\n\n"
            "برای تعیین یا تغییر فرمانده‌ی این گروه، روی پیام او ریپلای کرده و بنویسید: <code>ست پلیر</code> یا <code>/set player</code>"
        )
    else:
        builder.button(text="🏙 ست گپ", callback_data="grp_setcity")
        text = "این گروه هنوز به هیچ شهری متصل نیست."
    await message.answer(text, reply_markup=builder.as_markup())
