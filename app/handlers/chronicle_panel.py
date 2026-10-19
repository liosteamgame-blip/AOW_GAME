"""📖 وقایع‌نامه: پیش‌نمایش → تایید ادمین/راوی → انتشار در کانال اصلی.

متن پیش‌فرض با قالب محلی ساخته می‌شود. «بازنویسی با گروک» فقط با دکمه است و از سهمیه‌ی روزانه
و کش app/ai.py استفاده می‌کند. ورودی گروک فقط همان متن عمومی است.
"""
import time

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.ai import ai_available, ask as ai_ask, cache_key, remaining_today
from app.audit import record
from app.chronicle import build_local_text, events_since
from app.config import CHANNEL_ID, DIV
from app.features import enabled
from app.keyboards import _btn
from app.loader import bot, dp
from app.permissions import can
from app.state import SETTINGS
from app.storage import save_data
from app.utils import e, fmt_num, norm_cmd

CHRONICLE_CMDS = {"وقایعنامه", "وقایع‌نامه", "chronicle"}


def _kb(has_ai: bool):
    b = InlineKeyboardBuilder()
    b.row(_btn("✅ انتشار در کانال", "chr:pub", "success"))
    if has_ai:
        b.row(_btn(f"🤖 بازنویسی با گروک ({fmt_num(remaining_today())} باقی امروز)", "chr:ai", "primary"))
    b.row(_btn("🔄 ساخت دوباره (قالب محلی)", "chr:menu"), _btn("❌ بستن", "chr:close"))
    return b.as_markup()


async def _preview(target: types.Message, state: FSMContext, uid: int):
    if not enabled("chronicle"):
        return await target.answer("📖 وقایع‌نامه فعلاً خاموش است (🧪 فیچرها).")
    events = events_since()
    text = build_local_text(events)
    if not text:
        return await target.answer("📭 از آخرین وقایع‌نامه تاکنون رویداد عمومی‌ای ثبت نشده.")
    await state.update_data(chr_text=text, chr_count=len(events), chr_until=time.time())
    await target.answer(
        f"👁 <b>پیش‌نمایش وقایع‌نامه</b> — {fmt_num(len(events))} رویداد\n{DIV}\n<i>هنوز منتشر نشده.</i>"
    )
    await target.answer(text, reply_markup=_kb(ai_available()))


@dp.message(F.text.func(lambda t: norm_cmd(t) in CHRONICLE_CMDS))
async def chronicle_cmd(message: types.Message, state: FSMContext):
    if not can(message.from_user.id, "chronicle.publish"):
        return
    await _preview(message, state, message.from_user.id)


@dp.callback_query(F.data.startswith("chr:"))
async def chronicle_cb(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not can(uid, "chronicle.publish"):
        return await callback.answer("⛔️ فقط ادمین یا راوی.", show_alert=True)
    action = callback.data.split(":", 1)[1]
    if action == "close":
        await callback.answer()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    if action == "menu":
        await callback.answer()
        return await _preview(callback.message, state, uid)

    d = await state.get_data()
    text = d.get("chr_text")
    if not text:
        return await callback.answer("پیش‌نمایش پیدا نشد؛ دوباره «📖 وقایع‌نامه» را بزنید.", show_alert=True)

    if action == "ai":
        await callback.answer("🤖 در حال بازنویسی…")
        prompt = (
            "این وقایع‌نامه‌ی هفتگی یک بازی نقش‌آفرینی جنگ داخلی انگلیس است. آن را با لحن یک کاتب درباری "
            "و فارسی ادبی و روان بازنویسی کن. هیچ رویداد، عدد یا نامی اضافه نکن و چیزی را حذف نکن. "
            "فقط متن ساده (بدون HTML) بده، حداکثر ۳۵۰۰ کاراکتر.\n\n" + text
        )
        out, note = await ai_ask(cache_key("chronicle", text), "Persian court chronicler. Never invent facts.", prompt,
                                 max_tokens=1500, temperature=0.7)
        if not out:
            return await callback.message.answer(f"🤖 {e(note)}")
        new_text = f"📖 <b>وقایع‌نامه خاکستر جنگ</b>\n{DIV}\n{e(out)[:3600]}\n\n#وقایع_نامه"
        await state.update_data(chr_text=new_text)
        await callback.message.answer(f"🤖 <i>{e(note)}</i>")
        return await callback.message.answer(new_text, reply_markup=_kb(False))

    if action == "pub":
        until = float(d.get("chr_until") or time.time())
        await state.update_data(chr_text=None)   # قبل از await — دابل‌کلیک دوبار منتشر نمی‌کند
        await callback.answer("در حال انتشار…")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        try:
            await bot.send_message(CHANNEL_ID, text)
        except Exception as ex:
            await state.update_data(chr_text=text)
            return await callback.message.answer(f"❌ انتشار ناموفق: <code>{e(str(ex)[:200])}</code>")
        SETTINGS["chronicle_since"] = str(until)
        record("انتشار وقایع‌نامه", "", f"{d.get('chr_count') or 0} رویداد", admin_only=False)
        save_data()
        return await callback.message.answer("✅ وقایع‌نامه در کانال منتشر شد؛ وقایع‌نامه‌ی بعدی از همین لحظه شروع می‌شود.")
    await callback.answer()
