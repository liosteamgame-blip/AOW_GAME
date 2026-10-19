"""منوی اصلی فرمانده."""
import logging

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV, KIND_NOUN, MENU_TEXT, PV_PLAYER_TEXT
from app.state import SETTINGS, pending_confirms
from app.utils import e
from app.factions import FACTION_META, country_key
from app.states import GameStates
from app.players import player_group_access
from app.gametime import game_time_status
from app.keyboards import _btn, get_back_keyboard, get_main_menu_keyboard, get_pv_menu_keyboard, get_type_keyboard
from app.channel import send_report


def build_menu_text(uid, message) -> str:
    """هدر منوی اصلی: شهر و فکشن فرمانده + وضعیت تایم."""
    lines = ["🏰 <b>دربار فرماندهی</b>", DIV]
    city = None
    if uid:
        try:
            _ok, city, _err = player_group_access(uid, message.chat.id, message.chat.type)
        except Exception:
            logging.exception("build_menu_text")
    if city and city != "ناشناس":
        flag, title = FACTION_META.get(country_key(city), ("🏙", ""))
        lines.append(f"{flag} شهر: <b>{e(city)}</b>" + (f" · {title}" if title else ""))
    lines.append(game_time_status())
    lines.append("")
    lines.append("سرورم، دستور خود را از میان دکمه‌ها انتخاب کنید 👇")
    return "\n".join(lines)


async def go_menu(message: types.Message, state: FSMContext, text=MENU_TEXT, user_id=None):
    """
    منوی اصلی — ترجیحاً همان پیام قبلی ویرایش می‌شود تا منو تکرار نشود.
    اگر photo_menu تنظیم شده باشد، با عکس ارسال می‌شود.
    """
    uid = user_id or (message.from_user.id if message.from_user and not getattr(message.from_user, "is_bot", False) else None)
    if uid:
        pending_confirms.pop(uid, None)
    await state.clear()
    if message.chat.type == "private":
        pv_markup = get_pv_menu_keyboard(uid)
        await message.answer(
            text if text != MENU_TEXT else PV_PLAYER_TEXT,
            reply_markup=pv_markup or ReplyKeyboardRemove(),
        )
        return
    await state.set_state(GameStates.main_menu)
    body = text if text != MENU_TEXT else build_menu_text(uid, message)
    markup = get_main_menu_keyboard(uid, chat_id=message.chat.id)
    photo_id = (SETTINGS.get("photo_menu") or "").strip()

    # اگر پیام از خود ربات است (مثلاً callback.message) → ویرایش همان پیام
    is_bot_msg = bool(message.from_user and getattr(message.from_user, "is_bot", False))
    if is_bot_msg and not photo_id:
        try:
            await message.edit_text(body, reply_markup=markup)
            return
        except Exception:
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            try:
                await message.delete()
            except Exception:
                pass

    if photo_id:
        try:
            await message.answer_photo(photo=photo_id, caption=body, reply_markup=markup)
            return
        except Exception:
            logging.exception("ارسال عکس منو ناموفق")
    await message.answer(body, reply_markup=markup)


async def channel_failed(message: types.Message, state: FSMContext, ex, what):
    logging.exception("خطا در ارسال به کانال (%s)", what)
    await send_report(f"⚠️ <b>خطا در ارسال به کانال</b>\n{DIV}\n🛠 عملیات: {e(what)}\n❗️ خطا: <code>{e(str(ex)[:300])}</code>")
    await go_menu(message, state, "❌ ارسال به کانال ناموفق بود. ادمین مطلع شد؛ کمی بعد دوباره تلاش کنید.")


# ======================================================================
#                           ۱. لشکرکشی
# ======================================================================
async def ask_type(message: types.Message, kind):
    await message.answer(f"🧭 سرورم لطفا <b>نوع {KIND_NOUN[kind]}</b> خود را تعیین کنید. 👇", reply_markup=get_type_keyboard(kind))


async def start_campaign(message: types.Message, state: FSMContext):
    await ask_type(message, "campaign")


async def start_siege(message: types.Message, state: FSMContext):
    await ask_type(message, "siege")


async def start_war(message: types.Message, state: FSMContext):
    await ask_type(message, "war")


# ======================================================================
#                              ۴. بیانیه
# ======================================================================
async def start_announcement(message: types.Message, state: FSMContext):
    await message.answer(
        "📜 سرورم بیانیه خود را به یکی از این روش‌ها بفرستید:\n\n"
        "1️⃣ فقط <b>متن</b>\n"
        "2️⃣ <b>عکس یا ویدیو همراه کپشن</b> (متن روی همان فایل)\n"
        "3️⃣ فقط <b>عکس یا ویدیو</b> — بعد متن را جداگانه می‌پرسد\n\n"
        "↩️ برای انصراف «بازگشت» را بزنید.",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.ann_media)


# ======================================================================
#                              ۵. تجارت
# ======================================================================
async def start_trade(message: types.Message, state: FSMContext):
    """انتخاب نوع تجارت: با بازیکن یا با تجار."""
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🤝 تجارت با بازیکن", "trade_kind:player", "primary"))
    builder.row(_btn("🛒 تجارت با تجار", "trade_kind:merchant", "success"))
    builder.row(_btn("🔙 بازگشت", "menu:home"))
    await message.answer(
        f"🐪 <b>تجارت</b>\n{DIV}\nنوع تجارت را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )
