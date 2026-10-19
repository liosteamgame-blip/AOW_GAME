"""هندلرهای military"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext

from app.config import CAMP_ORIGIN_PROMPT, DIV, KIND_NOUN, MTYPES, MTYPE_EMOJI, ORDERS
from app.loader import dp
from app.state import pending_confirms
from app.utils import e, mtype_tag, need_text, plain
from app.factions import city_by_index
from app.states import GameStates
from app.players import city_of, context_city, is_admin, is_player, player_group_access
from app.permissions import assistant_block_text
from app.gametime import MILITARY_KINDS, military_closed_text, parse_player_time
from app.keyboards import (
    get_back_keyboard,
    get_cities_keyboard,
    get_confirm_keyboard,
    get_country_keyboard,
    get_trade_mtype_keyboard,
)
from app.menus import go_menu
from app.screens import ask_camp_time
from app.handlers.groups import _link_group_to_city


@dp.callback_query(F.data.startswith("mtype:"))
async def handle_type_pick(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    chat = callback.message.chat if callback.message else None
    ok, _city, err = player_group_access(
        uid,
        chat_id=chat.id if chat else None,
        chat_type=chat.type if chat else None,
    )
    if not ok:
        return await callback.answer(plain(err)[:190], show_alert=True)
    parts = callback.data.split(":")
    if parts[1] == "back":
        await callback.answer()
        try:
            await callback.message.delete()
        except Exception:
            pass
        return await go_menu(callback.message, state)
    if len(parts) != 3 or parts[1] not in KIND_NOUN or parts[2] not in MTYPES:
        return await callback.answer()
    kind, mtype = parts[1], parts[2]
    closed = military_closed_text(uid) if kind in MILITARY_KINDS else ""
    if closed:   # دکمه‌ی قدیمی که قبل از استاپ ارسال شده
        return await callback.answer(closed[:200], show_alert=True)
    blocked = assistant_block_text(uid, chat.id if chat else None, kind)
    if blocked:
        return await callback.answer(blocked[:200], show_alert=True)
    await callback.answer()
    try:                                     # دکمه‌ها برداشته می‌شوند و انتخاب نمایش داده می‌شود
        await callback.message.edit_text(f"✅ نوع {KIND_NOUN[kind]}: <b>{MTYPE_EMOJI[mtype]} {MTYPES[mtype]}</b>")
    except Exception:
        pass
    await state.clear()
    await state.update_data(kind=kind, mtype=mtype)
    if kind == "campaign":
        await callback.message.answer(
            CAMP_ORIGIN_PROMPT + "\n\n📋 از منوی شهر انتخاب کنید یا ورود دستی:",
            reply_markup=get_cities_keyboard("camp_origin", user_id=uid, kind=kind),
        )
        await state.set_state(GameStates.camp_origin)
    else:
        await callback.message.answer(
            ORDERS[kind]["ask_target"] + "\n\n📋 از منوی شهر انتخاب کنید یا ورود دستی:",
            reply_markup=get_cities_keyboard("order_target", user_id=uid, kind=kind),
        )
        await state.set_state(GameStates.order_target)


async def _set_city_field(message: types.Message, state: FSMContext, field: str, value: str):
    """اعمال شهر انتخاب‌شده/دستی در فلوی لشکرکشی، هدف، تجارت، ست‌گپ."""
    if field == "grp_city":
        return await _link_group_to_city(message, state, value)
    if field == "camp_origin":
        await state.update_data(origin=value)
        await message.answer(
            f"✅ مبدا: <b>{e(value)}</b>\n\n🎯 حالا <b>مقصد</b> را انتخاب کنید:",
            reply_markup=get_cities_keyboard("camp_dest"),
        )
        await state.set_state(GameStates.camp_dest)
    elif field == "camp_dest":
        await state.update_data(dest=value)
        await message.answer(
            f"✅ مقصد: <b>{e(value)}</b>\n\n📊 آمار لشکریان را <b>تفکیک‌شده</b> بنویسید "
            "(ریپلای به این پیام):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.camp_stats)
    elif field == "order_target":
        await state.update_data(target=value)
        d = await state.get_data()
        await message.answer(
            f"✅ هدف: <b>{e(value)}</b>\n\n" + ORDERS[d["kind"]]["ask_stats"] + "\n\n↩️ ریپلای کنید.",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.order_stats)
    elif field == "trade_origin":
        await state.update_data(origin=value)
        await message.answer(
            f"✅ مبدا تجارت: <b>{e(value)}</b>\n\n🎯 <b>مقصد تجارت</b> را انتخاب کنید:",
            reply_markup=get_cities_keyboard("trade_dest"),
        )
        await state.set_state(GameStates.trade_dest)
    elif field == "trade_dest":
        await state.update_data(dest=value)
        await message.answer(
            f"✅ مقصد: <b>{e(value)}</b>\n\n"
            "🧭 مسیر حرکت کاروان <b>زمینی</b> است یا <b>دریایی</b>؟",
            reply_markup=get_trade_mtype_keyboard(),
        )
        await state.set_state(GameStates.trade_mtype)


@dp.callback_query(F.data.startswith("cityfac:"))
async def handle_city_faction(callback: types.CallbackQuery, state: FSMContext):
    """انتخاب کشور → نمایش شهرهای همان کشور (ویرایش همان پیام)."""
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer()
    field, faction = parts[1], parts[2]
    # ست‌گپ فقط ادمین؛ بقیه فقط پلیر
    if field == "grp_city":
        if not is_admin(callback.from_user.id):
            return await callback.answer("❌ فقط ادمین.", show_alert=True)
    elif not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    await callback.answer()
    titles = {
        "camp_origin": "📍 مبدا — شهر را انتخاب کنید",
        "camp_dest": "🎯 مقصد — شهر را انتخاب کنید",
        "order_target": "🎯 هدف — شهر را انتخاب کنید",
        "trade_origin": "📍 مبدا تجارت — شهر را انتخاب کنید",
        "trade_dest": "🎯 مقصد تجارت — شهر را انتخاب کنید",
        "grp_city": "🏙 شهر این گروه را انتخاب کنید",
    }
    try:
        await callback.message.edit_text(
            titles.get(field, "شهر را انتخاب کنید:"),
            reply_markup=get_cities_keyboard(field, faction=faction, page=0),
        )
    except Exception:
        await callback.message.answer(
            titles.get(field, "شهر را انتخاب کنید:"),
            reply_markup=get_cities_keyboard(field, faction=faction, page=0),
        )


@dp.callback_query(F.data.startswith("cityfacback:"))
async def handle_city_fac_back(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    await callback.answer()
    kb = get_country_keyboard(field, user_id=callback.from_user.id, kind=(await state.get_data()).get("kind"))
    try:
        await callback.message.edit_text("🌍 ابتدا <b>کشور</b> را انتخاب کنید:", reply_markup=kb)
    except Exception:
        await callback.message.answer("🌍 کشور را انتخاب کنید:", reply_markup=kb)


@dp.callback_query(F.data.startswith("citypick:"))
async def handle_city_pick(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    # citypick:field:faction:idx
    if len(parts) != 4:
        return await callback.answer()
    field, faction, idx_s = parts[1], parts[2], parts[3]
    if field == "grp_city":
        if not is_admin(callback.from_user.id):
            return await callback.answer("❌ فقط ادمین.", show_alert=True)
    elif not is_player(callback.from_user.id):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    try:
        idx = int(idx_s)
    except ValueError:
        return await callback.answer()
    name = city_by_index(idx, faction)
    if not name:
        return await callback.answer("شهر پیدا نشد.", show_alert=True)
    await callback.answer(f"✅ {name}")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _set_city_field(callback.message, state, field, name)


@dp.callback_query(F.data.startswith("citypage:"))
async def handle_city_page(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    # citypage:field:faction:page
    if len(parts) != 4:
        return await callback.answer()
    field, faction, page_s = parts[1], parts[2], parts[3]
    try:
        page = int(page_s)
    except ValueError:
        return await callback.answer()
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=get_cities_keyboard(field, faction=faction, page=page)
        )
    except Exception:
        await callback.message.answer(
            "📋 انتخاب شهر:",
            reply_markup=get_cities_keyboard(field, faction=faction, page=page),
        )


@dp.callback_query(F.data.startswith("citymanual:"))
async def handle_city_manual(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split(":", 1)[1]
    await callback.answer()
    prompts = {
        "camp_origin": "📍 مبدا را دستی بنویسید (مثال: <code>london_england</code>) — ریپلای کنید:",
        "camp_dest": "🎯 مقصد را دستی بنویسید — ریپلای کنید:",
        "order_target": "🎯 شهر هدف را دستی بنویسید — ریپلای کنید:",
        "trade_origin": "📍 مبدا تجارت را دستی بنویسید — ریپلای کنید:",
        "trade_dest": "🎯 مقصد تجارت را دستی بنویسید — ریپلای کنید:",
        "grp_city": "🏙 نام شهر را دستی بنویسید (مثال: <code>کمبریج_انگلیس</code>) — ریپلای کنید:",
    }
    try:
        await callback.message.edit_text(prompts.get(field, "متن را بنویسید:"))
    except Exception:
        pass
    await callback.message.answer(prompts.get(field, "متن را بنویسید:"), reply_markup=get_back_keyboard())


@dp.callback_query(F.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer()


@dp.message(GameStates.camp_origin)
async def process_camp_origin(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "camp_origin", txt)


@dp.message(GameStates.camp_dest)
async def process_camp_dest(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await _set_city_field(message, state, "camp_dest", txt)


@dp.message(GameStates.camp_stats)
async def process_camp_stats(message: types.Message, state: FSMContext):
    txt = await need_text(message, 1500)
    if txt is None:
        return
    if txt == "__BACK__":
        return await go_menu(message, state)
    await state.update_data(stats=txt)
    await ask_camp_time(message, state)


@dp.message(GameStates.camp_time)
async def process_camp_time(message: types.Message, state: FSMContext):
    txt = await need_text(message)
    if txt is None:
        return
    if txt == "__BACK__":
        pending_confirms.pop(message.from_user.id, None)
        return await go_menu(message, state)
    parsed, err = parse_player_time(txt)
    if err:
        return await message.answer(
            f"❌ {err}\n\nمثال: <code>12:00</code> یا <code>45</code> (یعنی ۴۵ دقیقه دیگر)\n"
            "چند زمان: <code>12:00,14:30</code>"
        )
    await state.update_data(time=parsed)
    d = await state.get_data()
    # ذخیره مستقل از FSM تا دکمه تایید حتماً کار کند
    pending_confirms[message.from_user.id] = {
        "kind": "campaign",
        "data": dict(d),
        "chat_id": message.chat.id,
    }
    await message.answer(
        f"⚔️ <b>پیش‌نویس فرمان اعزام</b>\n{DIV}\n"
        f"👑 فرمانده: <b>{e(context_city(message)[1] or city_of(message.from_user.id))}</b>\n"
        f"🧭 نوع: <b>{mtype_tag(d)}</b>\n"
        f"📍 مبدا: <b>{e(d['origin'])}</b>\n"
        f"🎯 مقصد: <b>{e(d['dest'])}</b>\n"
        f"⏳ زمان رسیدن: <b>{e(d['time'])}</b>\n\n"
        f"📊 <b>آمار لشکر:</b>\n<blockquote expandable>{e(d['stats'])}</blockquote>\n"
        "سرورم، فرمان صادر شود؟",
        reply_markup=get_confirm_keyboard(),
    )
    await state.set_state(GameStates.camp_confirm)
