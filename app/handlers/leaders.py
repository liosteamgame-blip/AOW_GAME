"""هندلرهای leaders"""

from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import MAX_LEADERS
from app.utils import fmt_num
from app.loader import bot, dp
from app.state import LEADERS
from app.factions import FACTIONS, FACTION_META, _parse_leader_cmd
from app.players import is_admin, mention, side_of_user
from app.keyboards import _btn
from app.storage import save_data


@dp.message(F.text.func(lambda t: _parse_leader_cmd(t)[0] is not None))
async def handle_set_leader(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    action, side = _parse_leader_cmd(message.text or "")
    target_msg = message.reply_to_message
    if not target_msg or not target_msg.from_user or getattr(target_msg.from_user, "is_bot", False):
        return await message.answer("❌ روی پیام کاربر ریپلای کنید.")
    target = target_msg.from_user
    if action == "del":
        removed_from = []
        for s, ids in LEADERS.items():
            if target.id in ids:
                ids.remove(target.id)
                removed_from.append(s)
        save_data(critical=True)
        if not removed_from:
            return await message.answer("ℹ️ این کاربر لیدر هیچ سایدی نبود.")
        return await message.answer(
            f"✅ {mention(target.id, target.full_name)} از لیدری "
            f"{', '.join(FACTION_META.get(s, ('', s))[1] for s in removed_from)} حذف شد."
        )
    # set — اگر ساید نبود از شهر کاربر، وگرنه دکمه‌های انتخاب
    if not side or side not in FACTIONS:
        side = side_of_user(target.id)
    if not side or side not in FACTIONS:
        builder = InlineKeyboardBuilder()
        for s in FACTIONS:
            flag, title = FACTION_META[s]
            builder.row(_btn(f"{flag} {title}", f"set_leader_side:{s}:{target.id}"))
        return await message.answer(
            f"❌ ساید مشخص نیست برای {mention(target.id, target.full_name)}.\n"
            "یکی را انتخاب کنید یا این‌ها را بزنید:\n"
            "<code>ست لیدر مونارشیست</code>\n"
            "<code>ست لیدر پارلمانری</code>\n"
            "<code>ست لیدر فرانسه</code>\n"
            "<code>ست لیدر ایرلند</code>",
            reply_markup=builder.as_markup(),
        )
    ids = LEADERS.setdefault(side, [])
    if target.id in ids:
        return await message.answer(f"ℹ️ از قبل لیدر {FACTION_META[side][1]} است.")
    if len(ids) >= MAX_LEADERS:
        return await message.answer(f"❌ ظرفیت لیدر {FACTION_META[side][1]} پر است (حداکثر {fmt_num(MAX_LEADERS)} نفر).")
    ids.append(target.id)
    save_data(critical=True)
    flag, title = FACTION_META[side]
    await message.answer(
        f"✅ {mention(target.id, target.full_name)} لیدر {flag}<b>{title}</b> شد "
        f"({fmt_num(len(ids))}/{fmt_num(MAX_LEADERS)}).\nمشاهده دارایی از منوی اصلی در دسترس است."
    )
    try:
        await bot.send_message(
            chat_id=target.id,
            text=f"👑 شما لیدر ساید {flag}<b>{title}</b> شدید.\nاز منوی ربات «📦 مشاهده دارایی» را بزنید.",
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("set_leader_side:"))
async def handle_set_leader_side_btn(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    side, uid_s = parts[1], parts[2]
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر", show_alert=True)
    try:
        uid = int(uid_s)
    except ValueError:
        return await callback.answer("آیدی نامعتبر", show_alert=True)
    ids = LEADERS.setdefault(side, [])
    if uid in ids:
        return await callback.answer("از قبل لیدر است.", show_alert=True)
    if len(ids) >= MAX_LEADERS:
        return await callback.answer(f"ظرفیت لیدر این ساید پر است ({fmt_num(len(ids))}/{fmt_num(MAX_LEADERS)}).", show_alert=True)
    ids.append(uid)
    save_data(critical=True)
    flag, title = FACTION_META[side]
    await callback.answer("ثبت شد")
    await callback.message.answer(
        f"✅ کاربر <code>{uid}</code> لیدر {flag}<b>{title}</b> شد ({fmt_num(len(ids))}/{fmt_num(MAX_LEADERS)})."
    )
    try:
        await bot.send_message(
            chat_id=uid,
            text=f"👑 شما لیدر ساید {flag}<b>{title}</b> شدید.\nاز منوی ربات «📦 مشاهده دارایی» را بزنید.",
        )
    except Exception:
        pass
