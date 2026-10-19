"""🤝 اختیارات کمکی‌ها: فرمانده‌ی هر گپ تعیین می‌کند کمکی‌ها کدام فرمان‌ها را بدهند.

ذخیره در GROUPS[chat_id]["assistant_perms"] = {action: bool} (پیش‌فرض همه مجاز).
"""
from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.features import enabled
from app.keyboards import _btn
from app.loader import dp
from app.permissions import ASSIST_ACTIONS, can
from app.players import mention
from app.state import GROUPS, authenticated_users
from app.storage import save_data
from app.utils import norm_cmd

ASSIST_CMDS = {"اختیاراتکمکی", "اختیاراتکمکیها", "assistantperms"}


def assist_view(chat_id: int):
    g = GROUPS.get(chat_id) or {}
    perms = g.get("assistant_perms") or {}
    assts = list(g.get("assistants") or [])
    names = []
    for uid in assts:
        u = authenticated_users.get(uid) or {}
        names.append(mention(uid, u.get("name") or str(uid)))
    lines = [
        f"🤝 <b>اختیارات کمکی‌ها — {g.get('city') or '—'}</b>\n{DIV}",
        "👥 کمکی‌ها: " + ("، ".join(names) if names else "— (ادمین با «ست کمکی» تعیین می‌کند)"),
        "\nفرمانده، روی هر فرمان بزنید تا برای کمکی‌ها باز/بسته شود:",
    ]
    b = InlineKeyboardBuilder()
    for action, title in ASSIST_ACTIONS.items():
        on = bool(perms.get(action, True))
        b.row(_btn(f"{'✅' if on else '⛔️'} {title}", f"asst:tog:{action}", "success" if on else "danger"))
    b.row(_btn("🔙 منوی اصلی", "menu:home"))
    return "\n".join(lines), b.as_markup()


@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: norm_cmd(t) in ASSIST_CMDS))
async def assistant_perms_cmd(message: types.Message):
    if not enabled("assistant_perms"):
        return
    if not can(message.from_user.id, "assistants.manage", message.chat.id):
        return await message.answer("❌ فقط فرمانده‌ی همین گپ اختیارات کمکی‌ها را تعیین می‌کند.")
    if message.chat.id not in GROUPS:
        return await message.answer("❌ این گروه هنوز به شهری متصل نیست.")
    text, kb = assist_view(message.chat.id)
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("asst:"))
async def assistant_perms_cb(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id if callback.message else None
    if not enabled("assistant_perms"):
        return await callback.answer("این بخش فعلاً خاموش است.", show_alert=True)
    if chat_id not in GROUPS or not can(callback.from_user.id, "assistants.manage", chat_id):
        return await callback.answer("❌ فقط فرمانده‌ی همین گپ.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) == 3 and parts[1] == "tog" and parts[2] in ASSIST_ACTIONS:
        g = GROUPS[chat_id]
        perms = dict(g.get("assistant_perms") or {})
        perms[parts[2]] = not bool(perms.get(parts[2], True))
        g["assistant_perms"] = perms
        save_data()
        await callback.answer(f"{ASSIST_ACTIONS[parts[2]]}: {'مجاز' if perms[parts[2]] else 'بسته'}")
    else:
        await callback.answer()
    text, kb = assist_view(chat_id)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
