"""هندلرهای admin_panel"""

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import state as app_state
from app.config import CHANNEL_ID, DIV, REPORT_CHANNEL_ID, TWEET_CHANNEL_ID
from app.loader import dp
from app.state import (
    CITY_ASSETS,
    GROUPS,
    LEADERS,
    MERCHANT_LIMITS,
    PLAYER_CODES,
    SETTINGS,
    active_actions,
    all_players,
    authenticated_users,
)
from app.utils import e, is_back_text, send_chunks
from app.factions import FACTIONS, FACTION_META, country_key
from app.states import GameStates
from app.players import city_of, code_owner, is_admin, mention
from app.keyboards import _btn, _player_pick_keyboard, get_admin_inline_keyboard, get_back_keyboard
from app.channel import _deliver_to_targets, _target_label


# ======================================================================
#                         عملیات‌های پنل ادمین
# ======================================================================
@dp.callback_query(F.data == "adm_stats")
async def admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()

    if not PLAYER_CODES:
        return await callback.message.answer(
            "📊 هنوز هیچ شهری ثبت نشده است.\nاز «⚙️ مدیریت» گزینه‌ی «➕ افزودن شهر» را بزنید.",
            reply_markup=get_admin_inline_keyboard(),
        )

    # گروه‌های وصل‌شده به هر شهر
    groups_by_city = {}
    for gid, g in GROUPS.items():
        c = (g.get("city") or "").lower()
        groups_by_city.setdefault(c, []).append(gid)

    blocks = [f"📊 <b>آمار شهرها</b>\n{DIV}\n"]
    # مرتب بر اساس نام شهر
    items = sorted(PLAYER_CODES.items(), key=lambda kv: str(kv[1]).lower())
    for code, city in items:
        fac = country_key(city)
        flag = {
        "monarchist": "👑",
        "parliamentarian": "🏛",
        "england": "🇬🇧",
        "france": "🇫🇷",
        "ireland": "🇮🇪",
    }.get(fac, "🏙")
        uid = code_owner(code)
        if uid:
            u = authenticated_users[uid]
            uname = f" @{e(u['username'])}" if u.get("username") else ""
            player_line = f"✅ {mention(uid, u.get('name') or 'فرمانده')}{uname}\n   🆔 <code>{uid}</code>"
        else:
            player_line = "❌ فرمانده تعیین نشده"
        n_grp = len(groups_by_city.get(str(city).lower(), []))
        grp_line = f"👥 گروه متصل: <b>{n_grp}</b>" if n_grp else "👥 گروه: —"
        blocks.append(
            f"{flag} <b>{e(city)}</b>\n"
            f"🔑 <code>{e(code)}</code>\n"
            f"👤 {player_line}\n"
            f"{grp_line}\n"
        )
    blocks.append(
        f"{DIV}\n"
        f"📈 فعال: <b>{len(all_players)}</b> / {len(PLAYER_CODES)} شهر · "
        f"گروه: <b>{len(GROUPS)}</b>"
    )
    await send_chunks(callback.message, blocks, reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "adm_msg")
async def admin_msg_start(callback: types.CallbackQuery, state: FSMContext):
    """ارسال پیام: همگانی / فقط گروه‌ها / فقط فرماندهان / انتخابی / خصوصی."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("📢 همگانی (فرماندهان + گروه‌ها)", "adm_msg_scope:all", "primary"))
    builder.row(_btn("👥 فقط گروه‌ها", "adm_msg_scope:groups", "success"))
    builder.row(_btn("👑 فقط فرماندهان", "adm_msg_scope:players"))
    builder.row(_btn("📋 انتخابی (چند نفر)", "adm_msg_scope:select", "primary"))
    builder.row(_btn("🔒 خصوصی (یک نفر)", "adm_msg_scope:private", "success"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer(
        f"📨 <b>ارسال پیام</b>\n{DIV}\nنوع ارسال را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("adm_msg_scope:"))
async def admin_msg_scope(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    scope = callback.data.split(":")[1]
    await callback.answer()
    if scope in ("all", "groups", "players"):
        await state.update_data(msg_scope=scope, msg_targets=None)
        labels = {
            "all": "همگانی (فرماندهان + گروه‌ها)",
            "groups": "فقط گروه‌ها",
            "players": "فقط فرماندهان",
        }
        await callback.message.answer(
            f"📢 محتوای پیام «{labels[scope]}» را بفرستید (متن / عکس / ویدیو):",
            reply_markup=get_back_keyboard(),
        )
        await state.set_state(GameStates.admin_broadcast)
        return
    if scope == "select":
        await state.update_data(msg_scope="select", msg_targets=[])
        await callback.message.answer(
            "📋 فرماندهان مورد نظر را انتخاب کنید (چندتایی):",
            reply_markup=_player_pick_keyboard([]),
        )
        return
    # خصوصی: یک فرمانده
    players = [(uid, u) for uid, u in authenticated_users.items() if u.get("role") == "player"]
    if not players:
        return await callback.message.answer("فرماندهی نیست.", reply_markup=get_admin_inline_keyboard())
    builder = InlineKeyboardBuilder()
    for uid, u in sorted(players, key=lambda x: str(x[1].get("country", "")).lower())[:50]:
        city = u.get("country") or "?"
        builder.row(_btn(f"👤 {city} · {uid}", f"adm_msg_to:{uid}"))
    builder.row(_btn("🔙 بازگشت", "adm_msg"))
    await callback.message.answer("🔒 گیرنده خصوصی را انتخاب کنید:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("adm_msg_pick:"))
async def admin_msg_pick_toggle(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[1])
    d = await state.get_data()
    selected = list(d.get("msg_targets") or [])
    if uid in selected:
        selected.remove(uid)
    else:
        selected.append(uid)
    await state.update_data(msg_targets=selected)
    await callback.answer(f"{'حذف' if uid not in selected else 'اضافه'} شد")
    try:
        await callback.message.edit_reply_markup(reply_markup=_player_pick_keyboard(selected))
    except Exception:
        pass


@dp.callback_query(F.data == "adm_msg_pick_done")
async def admin_msg_pick_done(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    d = await state.get_data()
    targets = d.get("msg_targets") or []
    if not targets:
        return await callback.answer("حداقل یک نفر انتخاب کنید.", show_alert=True)
    await callback.answer()
    await state.update_data(msg_scope="select")
    await callback.message.answer(
        f"✉️ پیام برای <b>{len(targets)}</b> فرمانده را بفرستید (متن/عکس/ویدیو):",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.admin_broadcast)


@dp.callback_query(F.data.startswith("adm_msg_to:"))
async def admin_msg_to(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    uid = int(callback.data.split(":")[1])
    await callback.answer()
    await state.update_data(msg_scope="private", msg_targets=[uid])
    await callback.message.answer(
        f"✉️ پیام برای {mention(uid, city_of(uid))} (<code>{uid}</code>)\nمتن/عکس/ویدیو بفرستید:",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.admin_broadcast)


@dp.message(GameStates.admin_broadcast)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل مدیریت:", reply_markup=get_admin_inline_keyboard())
    if not (message.text or message.photo or message.video):
        return await message.answer("❌ فقط متن، عکس یا ویدیو:")
    d = await state.get_data()
    scope = d.get("msg_scope", "all")
    if scope in ("private", "select") and d.get("msg_targets"):
        targets = list(d["msg_targets"])
    elif scope == "groups":
        targets = list(GROUPS.keys())
    elif scope == "players":
        targets = list(all_players)
    else:
        targets = list(set(list(all_players) + list(GROUPS.keys())))
    if not targets:
        await state.clear()
        return await message.answer("❗️ گیرنده‌ای نیست.", reply_markup=get_admin_inline_keyboard())

    ok_list, fail_list = await _deliver_to_targets(message, targets)
    lines = [f"📬 <b>نتیجه ارسال</b>\n{DIV}\n"]
    lines.append(f"✅ موفق: <b>{len(ok_list)}</b>")
    for cid in ok_list[:30]:
        lines.append(f"  • {_target_label(cid)}")
    if len(ok_list) > 30:
        lines.append(f"  … و {len(ok_list) - 30} مورد دیگر")
    lines.append(f"\n❌ ناموفق: <b>{len(fail_list)}</b>")
    for cid, err in fail_list[:20]:
        lines.append(f"  • {_target_label(cid)} — <i>{e(err)}</i>")
    await message.answer("\n".join(lines), reply_markup=get_admin_inline_keyboard())
    await state.clear()


@dp.callback_query(F.data == "adm_report")
async def admin_report(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    leaders_line = " · ".join(
        f"{FACTION_META.get(s, ('', s))[0]}{len(LEADERS.get(s, []))}" for s in FACTIONS
    )
    text = (
        f"📋 <b>گزارش وضعیت ربات</b>\n{DIV}\n"
        f"🏙 شهرها: <b>{len(PLAYER_CODES)}</b>\n"
        f"👤 فرماندهان: <b>{len(all_players)}</b>\n"
        f"👥 گروه‌ها: <b>{len(GROUPS)}</b>\n"
        f"⚔️ اکشن فعال: <b>{len(active_actions)}</b>\n"
        f"👑 لیدرها: {leaders_line}\n"
        f"📦 شهر دارای دارایی: <b>{len(CITY_ASSETS)}</b>\n"
        f"🛒 کالاهای تجار: <b>{len(MERCHANT_LIMITS)}</b>\n"
        f"⏰ استارت: <code>{SETTINGS.get('time_start')}</code> · "
        f"استاپ: <code>{SETTINGS.get('time_stop')}</code>\n"
        f"🆔 کانال اصلی: <code>{CHANNEL_ID}</code>\n"
        f"🆔 کانال گزارش: <code>{REPORT_CHANNEL_ID or '—'}</code>\n"
        f"🆔 کانال توییت: <code>{TWEET_CHANNEL_ID or '—'}</code>\n"
        f"👤 ادمین دارایی: <code>{app_state.ASSET_ADMIN_ID or '—'}</code>"
    )
    await callback.message.answer(text, reply_markup=get_admin_inline_keyboard())
