"""📘 راهنمای بازیکن: دستور «راهنما»، دکمه‌ی منو، و ویرایش متن توسط ادمین از پنل."""
from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.guide import ROLES, default_text, guide_text, mark_seen, validate_custom
from app.keyboards import _btn, get_back_keyboard
from app.loader import dp
from app.players import is_admin
from app.state import SETTINGS
from app.states import GameStates
from app.storage import save_data
from app.utils import is_back_text, norm_cmd

GUIDE_CMDS = {"راهنما", "راهنمایبازی", "help"}


@dp.message(F.text.func(lambda t: norm_cmd(t) in GUIDE_CMDS))
async def guide_cmd(message: types.Message):
    uid = message.from_user.id
    mark_seen(uid)
    await message.answer(guide_text(uid))


@dp.callback_query(F.data == "guide:show")
async def guide_btn(callback: types.CallbackQuery):
    uid = callback.from_user.id
    await callback.answer()
    mark_seen(uid)
    await callback.message.answer(guide_text(uid))


# ---------------- ادمین: ویرایش متن ----------------
def _panel():
    b = InlineKeyboardBuilder()
    for role, title in ROLES.items():
        custom = bool((SETTINGS.get(f"guide_{role}") or "").strip())
        b.row(_btn(f"👁 {title} ({'سفارشی' if custom else 'پیش‌فرض'})", f"adm_guide:view:{role}"))
        b.row(_btn(f"✏️ متن {title}", f"adm_guide:edit:{role}", "primary"),
              _btn("♻️ پیش‌فرض", f"adm_guide:reset:{role}", "danger"))
    b.row(_btn("🔙 پنل", "back_to_admin"))
    return b.as_markup()


@dp.callback_query(F.data.startswith("adm_guide"))
async def admin_guide_cb(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"
    role = parts[2] if len(parts) > 2 and parts[2] in ROLES else None
    await callback.answer()
    if action == "view" and role:
        return await callback.message.answer(guide_text(role=role), reply_markup=_panel())
    if action == "reset" and role:
        SETTINGS[f"guide_{role}"] = ""
        save_data()
        return await callback.message.answer(f"♻️ راهنمای {ROLES[role]} به متن پیش‌فرض برگشت.", reply_markup=_panel())
    if action == "edit" and role:
        await state.set_state(GameStates.guide_edit)
        await state.update_data(guide_role=role)
        return await callback.message.answer(
            f"✏️ متن تازه‌ی راهنمای {ROLES[role]} را بفرستید (حداکثر ۱۳ خط، بدون آمار مخفی).\n"
            "عنوان خودکار اضافه می‌شود.\n\nمتن پیش‌فرض فعلی برای الگو:\n" + default_text(role),
            reply_markup=get_back_keyboard(),
        )
    await callback.message.answer(
        f"📘 <b>راهنمای بازیکن</b>\n{DIV}\n"
        "یک‌بار خودکار برای هر فرمانده (اولین باز کردن منو) + دستور «راهنما» و دکمه‌ی 📘.\n"
        "متن پیش‌فرض از قوانین و روزهای تنظیم‌شده ساخته می‌شود.",
        reply_markup=_panel(),
    )


@dp.message(GameStates.guide_edit)
async def admin_guide_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    role = (await state.get_data()).get("guide_role")
    if is_back_text(message.text or "") or role not in ROLES:
        await state.clear()
        return await message.answer("❌ لغو شد.", reply_markup=_panel())
    text = (message.text or "").strip()
    err = validate_custom(text)
    if err:
        return await message.answer(f"❌ {err}")
    SETTINGS[f"guide_{role}"] = text
    save_data(critical=True)
    await state.clear()
    await message.answer(guide_text(role=role))
    await message.answer(f"✅ راهنمای {ROLES[role]} ذخیره شد.", reply_markup=_panel())
