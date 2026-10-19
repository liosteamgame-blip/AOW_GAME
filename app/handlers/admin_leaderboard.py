"""هندلرهای admin_leaderboard"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app.config import CHANNEL_ID, DIV
from app.loader import bot, dp
from app.state import LEADERS, SETTINGS
from app.utils import e
from app.factions import FACTIONS, FACTION_META
from app.states import GameStates
from app.players import city_of, is_admin, mention
from app.keyboards import _leaderboard_keyboard, get_admin_inline_keyboard, get_back_keyboard
from app.economy.views import format_leaderboard


@dp.callback_query(F.data == "adm_leaderboard")
async def admin_leaderboard_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    text = format_leaderboard("city", "all")
    await callback.message.answer(
        text[:4000],
        reply_markup=_leaderboard_keyboard("city", "all"),
    )


@dp.callback_query(F.data.startswith("lb:"))
async def admin_leaderboard_filter(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer()
    scope, category = parts[1], parts[2]
    if scope not in ("city", "side") or category not in ("all", "econ", "mil", "nav"):
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer()
    text = format_leaderboard(scope, category)
    try:
        await callback.message.edit_text(text[:4000], reply_markup=_leaderboard_keyboard(scope, category))
    except Exception:
        await callback.message.answer(text[:4000], reply_markup=_leaderboard_keyboard(scope, category))


@dp.callback_query(F.data.startswith("lb_announce:"))
async def admin_leaderboard_announce(callback: types.CallbackQuery):
    """ارسال رسمی لیدربورد به کانال + درخواست مدیا از ادمین."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer()
    scope, category = parts[1], parts[2]
    if scope not in ("city", "side") or category not in ("all", "econ", "mil", "nav"):
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer("در حال ارسال…")
    text = format_leaderboard(scope, category, announce=True)
    if not CHANNEL_ID:
        return await callback.message.answer("❌ CHANNEL_ID تنظیم نشده.")
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text[:4000])
    except Exception as ex:
        return await callback.message.answer(f"❌ ارسال ناموفق: {e(str(ex)[:200])}")
    await callback.message.answer(
        "✅ لیدربورد در کانال اعلام شد.\n\n"
        "🎨 <b>مدیا / رنگ لیدربورد را جایگذاری کنید</b>\n"
        "اگر بنر یا تصویر رنگی دارید همین‌جا بفرستید (اختیاری).\n"
        "برای تنظیم رتبه: دکمه «🎛 رتبه‌ها».",
        reply_markup=_leaderboard_keyboard(scope, category),
    )


@dp.callback_query(F.data == "lb_ranks_cfg")
async def admin_lb_ranks_cfg(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        f"🎛 <b>تنظیم رتبه‌های لیدربورد</b>\n{DIV}\n"
        f"فعلی: <code>{e(SETTINGS.get('lb_ranks') or '1-10')}</code>\n"
        f"سقف: <code>{e(SETTINGS.get('lb_max') or '10')}</code>\n\n"
        "بفرستید (چندخطی مجاز):\n"
        "<code>lb_ranks=1,2,3,5</code>\n"
        "<code>lb_ranks=1-8</code>\n"
        "<code>lb_ranks=همه</code>\n"
        "<code>lb_max=10</code>\n"
        "<code>lb_place_1=متن رتبه یک</code>\n"
        "<code>lb_footer=متن پایانی</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_timing)


@dp.callback_query(F.data == "adm_leaders")
async def admin_leaders_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    lines = [f"👑 <b>لیدرهای ساید</b>\n{DIV}\n"]
    for side in FACTIONS:
        flag, title = FACTION_META[side]
        ids = LEADERS.get(side) or []
        lines.append(f"{flag} <b>{title}</b> ({len(ids)}/5)")
        if not ids:
            lines.append("  — خالی —")
        for uid in ids:
            lines.append(f"  • {mention(uid, city_of(uid))} <code>{uid}</code>")
        lines.append("")
    lines.append(
        "برای افزودن: روی پیام کاربر <b>ریپلای</b> کنید و بنویسید:\n"
        "<code>ست لیدر مونارشیست</code> / <code>ست لیدر پارلمانری</code>\n"
        "<code>/set leader france</code>\n"
        "برای حذف: <code>حذف لیدر</code> (ریپلای)"
    )
    await callback.message.answer("\n".join(lines), reply_markup=get_admin_inline_keyboard())
