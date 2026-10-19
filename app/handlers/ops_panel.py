"""پنل عملیات ادمین: 📊 داشبورد زنده (dash:) و 🗓 آپ زمان‌بندی‌شده (upsch:)."""
from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.dashboard import build_text, install, installed, uninstall
from app.features import enabled
from app.keyboards import _btn
from app.loader import dp
from app.permissions import can
from app.state import SETTINGS
from app.storage import save_data
from app.utils import _DAY_FA, e, fmt_num
from app.upschedule import confirm, describe, next_run, offset_min, up_day


async def _edit(callback: types.CallbackQuery, text: str, markup):
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)


# ---------------- 📊 داشبورد زنده ----------------
@dp.callback_query(F.data.startswith("dash:"))
async def dashboard_cb(callback: types.CallbackQuery):
    if not can(callback.from_user.id, "dashboard"):
        return await callback.answer("⛔️ فقط ادمین.", show_alert=True)
    action = callback.data.split(":", 1)[1]
    if action == "install":
        if not enabled("live_dashboard"):
            return await callback.answer("📊 داشبورد زنده خاموش است (🧪 فیچرها).", show_alert=True)
        await callback.answer("در حال نصب…")
        await install(callback.message.chat.id)
        return await callback.message.answer("✅ داشبورد در همین چت نصب و پین شد؛ هر ۵ دقیقه به‌روز می‌شود.")
    if action == "off":
        uninstall()
        await callback.answer("داشبورد غیرفعال شد")
    else:
        await callback.answer()
    chat, mid = installed()
    where = f"<code>{chat}</code>" if chat else "— نصب نشده"
    b = InlineKeyboardBuilder()
    b.row(_btn("📌 نصب در همین چت", "dash:install", "success"))
    if chat:
        b.row(_btn("🗑 غیرفعال کردن", "dash:off", "danger"))
    b.row(_btn("🔙 پنل", "back_to_admin"))
    await _edit(
        callback,
        f"📊 <b>داشبورد زنده</b>\n{DIV}\n📍 محل فعلی: {where}\n"
        "⚠️ فقط در چت ادمین‌ها (پی‌وی یا گروه مدیریت) نصب کنید؛ آمار کلی بازی در آن است.\n\n"
        f"<b>پیش‌نمایش:</b>\n{build_text()}",
        b.as_markup(),
    )


# ---------------- 🗓 آپ زمان‌بندی‌شده ----------------
def _sched_view():
    on = enabled("scheduled_up")
    b = InlineKeyboardBuilder()
    days = [5, 6, 0, 1, 2, 3, 4]
    b.row(*[_btn(("✅" if up_day() == d else "") + _DAY_FA[d][:3], f"upsch:day:{d}") for d in days[:4]])
    b.row(*[_btn(("✅" if up_day() == d else "") + _DAY_FA[d][:3], f"upsch:day:{d}") for d in days[4:]])
    b.row(*[_btn(("✅ " if offset_min() == m else "") + f"+{fmt_num(m)}′", f"upsch:off:{m}") for m in (0, 15, 30, 60)])
    b.row(_btn("🔙 پنل", "back_to_admin"))
    text = (
        f"🗓 <b>آپ زمان‌بندی‌شده</b>\n{DIV}\n"
        f"وضعیت: <b>{'✅ روشن' if on else '❌ خاموش'}</b> (کلید در 🧪 فیچرها)\n"
        f"🕰 زمان: <b>{describe()}</b>\n"
        f"⏭ اجرای بعدی: <b>{next_run().strftime('%m/%d %H:%M')}</b>\n\n"
        "یک ساعت قبل، پیش‌نمایش با دکمه‌ی تایید برای مالک می‌آید. "
        "<b>بدون تایید همان روز، آپ اجرا نمی‌شود.</b>\n"
        "<i>پیش‌فرض قوانین: چهارشنبه بعد از استاپ.</i>"
    )
    return text, b.as_markup()


@dp.callback_query(F.data.startswith("upsch:"))
async def up_schedule_cb(callback: types.CallbackQuery):
    if not can(callback.from_user.id, "up.schedule"):
        return await callback.answer("⛔️ فقط ادمین.", show_alert=True)
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"
    if action in ("ok", "no") and len(parts) > 2:
        msg = confirm(parts[2], callback.from_user.id, yes=(action == "ok"))
        await callback.answer("ثبت شد")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await callback.message.answer(e(msg))
    if action == "day" and len(parts) > 2 and parts[2].isdigit() and 0 <= int(parts[2]) <= 6:
        SETTINGS["up_day"] = parts[2]
        save_data()
    elif action == "off" and len(parts) > 2 and parts[2].isdigit():
        SETTINGS["up_offset_min"] = parts[2]
        save_data()
    await callback.answer()
    text, kb = _sched_view()
    await _edit(callback, text, kb)
