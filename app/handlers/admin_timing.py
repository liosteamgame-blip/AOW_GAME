"""هندلرهای admin_timing"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app.config import DIV
from app.loader import bot, dp
from app.state import GROUPS, SETTINGS, pending_confirms
from app.utils import _parse_hhmm, e, format_days_setting, is_back_text
from app.states import GameStates
from app.players import is_admin
from app.keyboards import (
    _timing_menu_keyboard,
    get_admin_inline_keyboard,
    get_back_keyboard,
    get_main_menu_keyboard,
)
from app.storage import save_data
from app.economy.assets import _process_gasset_form


@dp.callback_query(F.data == "adm_timing")
async def admin_timing_menu(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await state.clear()
    text = (
        f"⏰ <b>تایم استارت / استاپ</b>\n{DIV}\n"
        f"▶️ استارت: <code>{SETTINGS.get('time_start')}</code>\n"
        f"⏹ استاپ: <code>{SETTINGS.get('time_stop')}</code>\n"
        f"📅 روزهای مجاز: <b>{e(format_days_setting(SETTINGS.get('days_start', '')))}</b>\n"
        f"💬 پیام استارت:\n<blockquote>{e(SETTINGS.get('msg_start', ''))}</blockquote>\n"
        f"💬 پیام استاپ:\n<blockquote>{e(SETTINGS.get('msg_stop', ''))}</blockquote>\n"
        f"✅ موارد مجاز:\n<blockquote>{e(SETTINGS.get('allowed', ''))}</blockquote>\n"
        f"🖼 عکس استارت: {'✅' if SETTINGS.get('photo_start') else '—'}\n"
        f"🖼 عکس استاپ: {'✅' if SETTINGS.get('photo_stop') else '—'}\n"
        f"🖼 عکس منو: {'✅' if SETTINGS.get('photo_menu') else '—'}"
    )
    await callback.message.answer(text, reply_markup=_timing_menu_keyboard())


@dp.callback_query(F.data == "adm_timing_edit")
async def admin_timing_edit(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "برای تغییر، یک یا چند خط بفرستید:\n"
        "<code>time_start=08:00</code>\n"
        "<code>time_stop=23:00</code>\n"
        "<code>days_start=شنبه,یکشنبه,دوشنبه,سه‌شنبه,چهارشنبه</code>\n"
        "<code>days_start=5,6,0,1,2</code> (۰=دوشنبه … ۶=یکشنبه)\n"
        "<code>msg_start=متن پیام</code>\n"
        "<code>msg_stop=متن پیام</code>\n"
        "<code>allowed=لشکرکشی،محاصره،جنگ،تجارت</code>\n\n"
        "خالی گذاشتن days_start = همه روزها",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_timing)


@dp.message(GameStates.adm_set_timing)
async def admin_set_timing(message: types.Message, state: FSMContext):
    if is_back_text(message.text or ""):
        pending_confirms.pop(message.from_user.id, None)
        await state.clear()
        return await message.answer("⚡️ لغو شد.", reply_markup=get_admin_inline_keyboard() if is_admin(message.from_user.id) else get_main_menu_keyboard(message.from_user.id))
    txt = (message.text or "").strip()
    # ---- فرم‌های دارایی از منوی گپ (تلفات / لول / باف / ویرایش) ----
    pend = pending_confirms.get(message.from_user.id) or {}
    pkind = pend.get("kind") or ""
    if pkind in ("gasset_edit", "gasset_lv", "gasset_loss", "gasset_buff", "roll_form"):
        city = (pend.get("data") or {}).get("city") or ""
        if not city and message.chat.type in ("group", "supergroup"):
            grp = GROUPS.get(message.chat.id)
            city = (grp or {}).get("city") or ""
        if not city:
            pending_confirms.pop(message.from_user.id, None)
            await state.clear()
            return await message.answer("❌ شهر مشخص نیست.")
        if not is_admin(message.from_user.id):
            pending_confirms.pop(message.from_user.id, None)
            await state.clear()
            return await message.answer("❌ فقط ادمین.")
        result = await _process_gasset_form(message, pkind, city, txt)
        pending_confirms.pop(message.from_user.id, None)
        await state.clear()
        return await message.answer(result[:4000])
    if not is_admin(message.from_user.id):
        return
    changed = []
    mapping = {
        "time_start": "time_start", "timestart": "time_start", "استارت": "time_start",
        "time_stop": "time_stop", "timestop": "time_stop", "استاپ": "time_stop",
        "days_start": "days_start", "days": "days_start", "روزها": "days_start", "روز": "days_start",
        "days_stop": "days_stop",
        "msg_start": "msg_start", "msgstart": "msg_start", "پیام_استارت": "msg_start",
        "msg_stop": "msg_stop", "msgstop": "msg_stop", "پیام_استاپ": "msg_stop",
        "lb_ranks": "lb_ranks", "lbranks": "lb_ranks",
        "lb_max": "lb_max", "lbmax": "lb_max",
        "lb_place_1": "lb_place_1", "lb_place_2": "lb_place_2", "lb_place_3": "lb_place_3",
        "lb_footer": "lb_footer",
        "allowed": "allowed", "مجاز": "allowed",
    }
    # پشتیبانی پیام چندخطی: msg_start=خط اول\nادامه متن...
    # یا فقط کلید در خط اول و بقیه متن پیام
    lines = txt.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or "=" not in line:
            i += 1
            continue
        key, _, val = line.partition("=")
        key = key.strip().lower().replace(" ", "_")
        sk = mapping.get(key)
        if not sk:
            i += 1
            continue
        val = val.strip()
        # برای پیام استارت/استاپ بقیه خطوط تا کلید بعدی را هم بگیر
        if sk in ("msg_start", "msg_stop", "allowed"):
            extra = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if "=" in nxt:
                    k2 = nxt.split("=", 1)[0].strip().lower().replace(" ", "_")
                    if k2 in mapping:
                        break
                extra.append(nxt)
                j += 1
            if extra:
                val = (val + "\n" + "\n".join(extra)).strip()
            i = j
        else:
            i += 1
        if sk in ("time_start", "time_stop") and not _parse_hhmm(val):
            await message.answer(f"❌ ساعت «{e(val)}» برای {sk} نامعتبر است.")
            continue
        SETTINGS[sk] = val
        changed.append(sk)
    if not changed:
        return await message.answer(
            "❌ چیزی تغییر نکرد.\n"
            "مثال:\n<code>time_start=08:00\ntime_stop=23:00\n"
            "msg_start=پیام کامل استارت\nخط دوم پیام\n"
            "msg_stop=پیام کامل استاپ</code>"
        )
    save_data(critical=True)
    await state.clear()
    await message.answer(
        f"✅ ذخیره شد: <b>{', '.join(changed)}</b>\n"
        f"استارت <code>{SETTINGS['time_start']}</code> · استاپ <code>{SETTINGS['time_stop']}</code>\n\n"
        f"💬 استارت:\n<blockquote>{e(SETTINGS.get('msg_start', ''))[:500]}</blockquote>\n"
        f"💬 استاپ:\n<blockquote>{e(SETTINGS.get('msg_stop', ''))[:500]}</blockquote>",
        reply_markup=_timing_menu_keyboard(),
    )


@dp.callback_query(F.data.startswith("adm_photo:"))
async def admin_photo_prompt(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    which = callback.data.split(":")[1]  # start | stop | menu
    await callback.answer()
    await state.update_data(photo_which=which)
    label = {"start": "استارت", "stop": "استاپ", "menu": "منوی کاربری"}.get(which, which)
    await callback.message.answer(
        f"🖼 عکس <b>{label}</b> را همین الان بفرستید (یک عکس).\n"
        "برای حذف عکس فعلی بنویسید: <code>-</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_set_photo)


@dp.message(GameStates.adm_set_photo)
async def admin_set_photo(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    d = await state.get_data()
    which = d.get("photo_which", "start")
    key = {"start": "photo_start", "stop": "photo_stop", "menu": "photo_menu"}.get(which, "photo_start")
    label = {"start": "استارت", "stop": "استاپ", "menu": "منوی کاربری"}.get(which, which)
    back_kb = _timing_menu_keyboard() if which in ("start", "stop") else get_admin_inline_keyboard()
    if message.text and message.text.strip() in ("-", "—", "حذف", "delete", "none"):
        SETTINGS[key] = ""
        save_data(critical=True)
        await state.clear()
        return await message.answer(f"🗑 عکس {label} حذف شد.", reply_markup=back_kb)
    if not message.photo:
        return await message.answer("❌ لطفاً یک <b>عکس</b> بفرستید یا <code>-</code> برای حذف.")
    file_id = message.photo[-1].file_id
    SETTINGS[key] = file_id
    save_data(critical=True)
    await state.clear()
    await message.answer(f"✅ عکس {label} ذخیره شد.", reply_markup=back_kb)
    try:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=file_id,
            caption=f"🖼 پیش‌نمایش عکس {label}",
        )
    except Exception:
        pass
