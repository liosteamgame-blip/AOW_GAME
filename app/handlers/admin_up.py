"""هندلرهای admin_up"""
import re
import secrets

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.loader import dp
from app.state import AUTO_CITIES, CITY_ASSETS, CITY_BUFFS, GROUPS, PENDING_TRADES, UP_SNAPSHOTS
from app.utils import _norm_country_token, e, fmt_num, format_goods, is_back_text, normalize_digits
from app.factions import FACTION_META, all_known_cities, country_key
from app.states import GameStates
from app.players import is_admin
from app.keyboards import _btn, get_admin_inline_keyboard, get_back_keyboard
from app.storage import save_data
from app.economy.assets import is_auto_city
from app.economy.up import restore_city_up
from app.castles import castle_trait_line
from app.economy.upflow import is_held, run_up_all, run_up_one, up_all_running, up_one_running


@dp.callback_query(F.data == "adm_auto")
async def admin_auto_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    cities = sorted(all_known_cities(), key=lambda s: s.lower())
    builder = InlineKeyboardBuilder()
    for i, city in enumerate(cities[:40]):
        on = is_auto_city(city)
        mark = "✅" if on else "❌"
        short = city.rsplit("_", 1)[0] if "_" in city else city
        builder.row(_btn(f"{mark} {short}", f"auto_tog:{i}"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    n_on = sum(1 for c in cities if is_auto_city(c))
    await callback.message.answer(
        f"🤖 <b>شهرهای فول‌اتو (تست)</b>\n{DIV}\n"
        f"فعال: <b>{n_on}</b> / {len(cities)}\n"
        "فقط روی شهرهای ✅ ارتقا/آپ/تلفات از بات اعمال می‌شود.\n"
        "برای تولید روی تیک بزنید:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("auto_tog:"))
async def admin_auto_toggle(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    try:
        idx = int(callback.data.split(":")[1])
    except ValueError:
        return await callback.answer()
    cities = sorted(all_known_cities(), key=lambda s: s.lower())
    if idx < 0 or idx >= len(cities):
        return await callback.answer("نامعتبر", show_alert=True)
    city = cities[idx]
    if is_auto_city(city):
        # خاموش
        for k in list(AUTO_CITIES.keys()):
            if _norm_country_token(k) == _norm_country_token(city):
                AUTO_CITIES.pop(k, None)
        AUTO_CITIES.pop(city, None)
        save_data(critical=True)
        await callback.answer(f"خاموش: {city}")
    else:
        AUTO_CITIES[city] = True
        save_data(critical=True)
        await callback.answer(f"روشن: {city}")
    # رفرش منو
    return await admin_auto_menu(callback)


@dp.callback_query(F.data == "adm_run_up")
async def admin_run_up_menu(callback: types.CallbackQuery):
    """منوی آپ: کلی / تکی (ساید→شهر) / بازگردانی."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("♻️ آپ کلی — همه اتو", "up_all", "success"))
    builder.row(_btn("🏙 آپ تکی — ساید سپس شهر", "up_pick", "primary"))
    builder.row(_btn("⏪ بازگردانی آپ یک شهر", "up_rollback_menu", "danger"))
    builder.row(_btn("🏠 پنل اصلی", "back_to_admin"))
    auto_n = sum(1 for v in AUTO_CITIES.values() if v)
    snap_n = len(UP_SNAPSHOTS)
    await callback.message.answer(
        f"♻️ <b>اجرای آپ</b>\n{DIV}\n"
        f"شهر اتو: <b>{auto_n}</b> · بکاپ آپ: <b>{snap_n}</b>\n\n"
        "• <b>آپ کلی</b>: همه شهرهای اتو\n"
        "• <b>آپ تکی</b>: اول ساید → بعد شهر\n"
        "• در <b>گروه شهر</b> بنویسید <code>آپ</code> و تأیید کنید\n"
        "• <b>بازگردانی</b>: دارایی همان شهر به قبل از آخرین آپ",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "up_all")
async def admin_up_all(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    if up_all_running():
        return await callback.answer("⏳ آپ کلی در حال اجراست؛ دوباره نزنید.", show_alert=True)
    await callback.answer("آپ کلی…")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    body = await run_up_all(reason="up_all")
    if body is None:
        return await callback.message.answer("⏳ آپ کلی همین الان در حال اجراست.")
    await callback.message.answer(body, reply_markup=get_admin_inline_keyboard())


@dp.callback_query(F.data == "up_pick")
async def admin_up_pick(callback: types.CallbackQuery):
    """قدم ۱ آپ تکی: انتخاب ساید."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    for key, (flag, title) in FACTION_META.items():
        builder.row(_btn(f"{flag} {title}", f"up_side:{key}", "primary"))
    builder.row(_btn("🔙 بازگشت", "adm_run_up"))
    await callback.message.answer(
        f"🏙 <b>آپ تکی</b> — اول <b>ساید</b> را انتخاب کنید:\n{DIV}",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("up_side:"))
async def admin_up_side(callback: types.CallbackQuery):
    """قدم ۲: شهرهای همان ساید."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    side = callback.data.split(":", 1)[1]
    await callback.answer()
    cities = sorted(
        {c for c in all_known_cities() if country_key(c) == side}
        | {c for c in CITY_ASSETS if country_key(c) == side}
        | {c for c, v in AUTO_CITIES.items() if v and country_key(c) == side},
        key=lambda s: s.lower(),
    )
    if not cities:
        return await callback.message.answer(
            f"شهری برای ساید «{side}» نیست.",
            reply_markup=get_admin_inline_keyboard(),
        )
    builder = InlineKeyboardBuilder()
    for c in cities[:40]:
        flag = "🤖" if is_auto_city(c) else "📦"
        short = c.rsplit("_", 1)[0] if "_" in c else c
        builder.row(_btn(f"{flag} {short}", f"up_confirm:{c}"))
    builder.row(_btn("🔙 بازگشت به سایدها", "up_pick"))
    title = (FACTION_META.get(side) or ("🏙", side))[1]
    await callback.message.answer(
        f"🏙 <b>آپ تکی — {e(title)}</b>\n{DIV}\n"
        "شهر را انتخاب کنید (سپس تأیید):\n🤖 اتو · 📦 فقط دارایی",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("up_confirm:"))
async def admin_up_confirm(callback: types.CallbackQuery):
    """تأیید قبل از آپ تکی."""
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    city = callback.data.split(":", 1)[1]
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ تأیید آپ", f"up_one:{city}", "success"),
        _btn("❌ لغو", "up_pick", "danger"),
    )
    has_asset = bool((CITY_ASSETS.get(city) or {}).get("text") or (CITY_ASSETS.get(city) or {}).get("stats"))
    await callback.message.answer(
        f"♻️ <b>تأیید آپ تکی</b>\n{DIV}\n"
        f"🏙 شهر: <b>{e(city)}</b>\n"
        f"🤖 اتو: {'بله' if is_auto_city(city) else 'خیر (با force ادمین)'}\n"
        f"📦 دارایی: {'دارد' if has_asset else 'خالی'}\n"
        + (f"{castle_trait_line(city)}\n" if castle_trait_line(city) else "")
        + "\nپس از تأیید، بکاپ گرفته و بازدهی‌ها اعمال می‌شوند.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("up_one:"))
async def admin_up_one(callback: types.CallbackQuery):
    await _do_up_one(callback, allow_suspicious=False)


@dp.callback_query(F.data.startswith("up_force:"))
async def admin_up_force(callback: types.CallbackQuery):
    """تأیید ادمین برای آپی که به‌خاطر عدد مشکوک متوقف شده بود."""
    await _do_up_one(callback, allow_suspicious=True)


async def _do_up_one(callback: types.CallbackQuery, allow_suspicious: bool):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    city = callback.data.split(":", 1)[1]
    if up_one_running(city):
        return await callback.answer("⏳ آپ همین شهر در حال اجراست؛ دوباره نزنید.", show_alert=True)
    # بدنه‌ی run_up_one تا اولین await خودش هم‌زمان اجرا می‌شود → قفل قبل از هر تعویض گرفته می‌شود
    log = await run_up_one(city, allow_suspicious=allow_suspicious)
    held = is_held(log)
    try:
        await callback.answer(
            "⏸ متوقف شد — عدد مشکوک" if held else (f"آپ {city} انجام شد" if log else "در حال اجراست")
        )
    except Exception:
        pass
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if log is None:
        return await callback.message.answer("⏳ آپ همین شهر یا آپ کلی همین الان در حال اجراست.")
    if held:
        builder = InlineKeyboardBuilder()
        builder.row(
            _btn("⚠️ تأیید و اجرا", f"up_force:{city}", "danger"),
            _btn("❌ لغو", "up_cancel"),
        )
        builder.row(_btn("🏠 پنل اصلی", "back_to_admin"))
        return await callback.message.answer(
            f"⏸ <b>آپ متوقف شد — {e(city)}</b>\n{DIV}\n{e(log)}",
            reply_markup=builder.as_markup(),
        )
    builder = InlineKeyboardBuilder()
    builder.row(_btn("⏪ بازگردانی این شهر", f"up_rb:{city}", "danger"))
    builder.row(_btn("🏠 پنل اصلی", "back_to_admin"))
    await callback.message.answer(
        f"♻️ <b>آپ تکی — {e(city)}</b>\n{DIV}\n{e(log)}\n\n🗄 بکاپ قدیم+جدید ذخیره شد",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "up_rollback_menu")
async def admin_up_rollback_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    if not UP_SNAPSHOTS:
        return await callback.message.answer(
            "📭 بکاپ آپی نیست.",
            reply_markup=get_admin_inline_keyboard(),
        )
    builder = InlineKeyboardBuilder()
    for city, snap in sorted(UP_SNAPSHOTS.items(), key=lambda x: x[0].lower())[:40]:
        ts = (snap or {}).get("ts") or "—"
        short = city.rsplit("_", 1)[0] if "_" in city else city
        builder.row(_btn(f"⏪ {short} ({ts})", f"up_rb:{city}", "danger"))
    builder.row(_btn("🔙 بازگشت", "adm_run_up"))
    await callback.message.answer(
        f"⏪ <b>بازگردانی آپ — شخصی هر شهر</b>\n{DIV}\n"
        "با انتخاب، دارایی همان شهر به قبل از آخرین آپ برمی‌گردد.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("up_rb:"))
async def admin_up_rollback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    city = callback.data.split(":", 1)[1]
    ok, msg = restore_city_up(city)
    await callback.answer("بازگشت" if ok else "خطا", show_alert=not ok)
    await callback.message.answer(msg, reply_markup=get_admin_inline_keyboard())


@dp.message(F.text.regexp(r"(?i)^\s*آپ\s*$"))
async def handle_group_up_command(message: types.Message):
    """در گروه شهر: نوشتن «آپ» → دکمه تأیید (فقط ادمین)."""
    if not is_admin(message.from_user.id):
        return
    city = None
    if message.chat.type in ("group", "supergroup"):
        grp = GROUPS.get(message.chat.id)
        if grp:
            city = grp.get("city")
    if not city:
        return await message.answer(
            "❌ «آپ» را در <b>گروه شهر</b> بزنید یا از پنل ادمین آپ تکی استفاده کنید."
        )
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("✅ تأیید آپ این شهر", f"up_one:{city}", "success"),
        _btn("❌ لغو", "up_cancel", "danger"),
    )
    await message.answer(
        f"♻️ <b>آپ تکی</b>\n{DIV}\n"
        f"🏙 شهر این گپ: <b>{e(city)}</b>\n"
        f"🤖 اتو: {'بله' if is_auto_city(city) else 'خیر'}\n"
        + (f"{castle_trait_line(city)}\n" if castle_trait_line(city) else "")
        + "\nبا تأیید، بکاپ گرفته و بازدهی‌ها اعمال می‌شود.",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "up_cancel")
async def up_cancel(callback: types.CallbackQuery):
    await callback.answer("لغو شد")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@dp.callback_query(F.data == "adm_pending_trades")
async def admin_pending_trades(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    pending = [(k, v) for k, v in PENDING_TRADES.items() if v.get("status") == "pending"]
    if not pending:
        return await callback.message.answer(
            "📭 معامله معلقی نیست.",
            reply_markup=get_admin_inline_keyboard(),
        )
    for tid, tr in pending[:15]:
        builder = InlineKeyboardBuilder()
        builder.row(
            _btn("✅ تأیید", f"trade_ok:{tid}", "success"),
            _btn("❌ رد", f"trade_no:{tid}", "danger"),
        )
        await callback.message.answer(
            f"🛒 <code>{tid}</code> · {e(tr.get('city'))}\n"
            f"{'خرید' if tr.get('mode') == 'buy' else 'فروش'} · "
            f"{format_goods(tr.get('after') or {})[:200]}",
            reply_markup=builder.as_markup(),
        )


@dp.callback_query(F.data == "adm_buffs")
async def admin_buffs_menu(callback: types.CallbackQuery, state: FSMContext = None):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    try:
        await callback.answer()
    except Exception:
        pass
    lines = [f"🎛 <b>باف / نرف ثبت‌شده</b>\n{DIV}"]
    total = 0
    for city, lst in sorted(CITY_BUFFS.items()):
        for i, bf in enumerate(lst):
            total += 1
            on = "✅آپ" if bf.get("apply_on_up") else "❌آپ"
            lines.append(
                f"• <code>{e(city)}</code> [{bf.get('id','?')}] "
                f"{bf.get('kind')} {e(bf.get('target'))} {bf.get('pct')}% {on}"
            )
    if not total:
        lines.append("هنوز چیزی ثبت نشده.")
    lines.append(
        "\nثبت جدید — یک خط بفرست:\n"
        "<code>شهر | buff یا nerf | هدف | درصد | متن اختیاری</code>\n"
        "مثال:\n<code>york_monarchist | nerf | دهکده | 10 | بازده ۱۰٪ کمتر</code>\n"
        "<code>london_parliamentarian | buff | اقتدار | 5</code>\n\n"
        "تیک اعمال در آپ: دکمه زیر هر مورد."
    )
    await callback.message.answer("\n".join(lines)[:4000])
    # دکمه‌های تیک
    builder = InlineKeyboardBuilder()
    nbtn = 0
    for city, lst in list(CITY_BUFFS.items())[:20]:
        for i, bf in enumerate(lst):
            if nbtn >= 30:
                break
            on = "✅" if bf.get("apply_on_up") else "❌"
            bid = bf.get("id") or f"{i}"
            short = f"{on} {city.split('_')[0][:8]} {bf.get('target','')[:10]}"
            builder.row(_btn(short, f"buff_tog:{city}:{bid}", "primary"))
            nbtn += 1
    builder.row(_btn("➕ ثبت جدید", "buff_add_start", "success"))
    builder.row(_btn("🔙 بازگشت", "back_to_admin"))
    await callback.message.answer("تیک «اعمال در آپ»:", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "buff_add_start")
async def buff_add_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    await callback.message.answer(
        "🎛 <b>ثبت باف/نرف</b> (جدا از ارتقا — اینجا لول ساختمان عوض نمی‌شود)\n"
        f"{DIV}\n"
        "فرمت:\n<code>شهر | buff یا nerf | هدف | درصد | توضیح</code>\n\n"
        "هدف = نام ساختمان/کمپ یا منبع:\n"
        "خزانه · دهکده · چوب بری · آشپزخانه · شبه نظامی · اقتدار · …\n\n"
        "• پیش‌فرض <b>اطلاعی</b> است (اعمال در آپ ❌)\n"
        "• تیک <b>اعمال در آپ</b> → روی بازدهی آپ\n"
        "• <b>باف هزینه (وزیر):</b> هدف را با «هزینه» شروع کنید\n"
        "<code>london | buff | هزینه معدن سنگ | 10 | وزیر</code>\n"
        "<code>paris | buff | هزینه همه | 15 | وزیر اقتصاد</code>\n"
        "مثال بازدهی:\n"
        "<code>london_monarchist | buff | آشپزخانه | 30 | +۳۰٪ بازدهی</code>\n"
        "<code>york_parliamentarian | nerf | چوب بری | 10 | −۱۰٪ چوب</code>",
        reply_markup=get_back_keyboard(),
    )
    await state.set_state(GameStates.adm_buff_add)


@dp.message(GameStates.adm_buff_add)
async def buff_add_save(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or ""):
        await state.clear()
        return await message.answer("⚡️ پنل:", reply_markup=get_admin_inline_keyboard())
    parts = [p.strip() for p in re.split(r"[|｜]", message.text or "")]
    if len(parts) < 4:
        return await message.answer("❌ حداقل: شهر | نوع | هدف | درصد")
    city, kind, target, pct_s = parts[0], parts[1].lower(), parts[2], parts[3]
    text = parts[4] if len(parts) > 4 else ""
    kind = "nerf" if "nerf" in kind or "نرف" in kind else "buff"
    try:
        pct = float(normalize_digits(pct_s).replace("%", "").strip())
    except ValueError:
        return await message.answer("❌ درصد نامعتبر")
    # resolve city name
    resolved = None
    for c in all_known_cities():
        if _norm_country_token(c) == _norm_country_token(city) or c.lower() == city.lower():
            resolved = c
            break
    if not resolved:
        resolved = city
    bid = secrets.token_hex(3)
    # تشخیص باف هزینه ارتقا (وزیر و …)
    effect = ""
    if "هزینه" in target or "هزینه" in (text or "") or "cost" in target.lower():
        effect = "cost"
    entry = {
        "id": bid,
        "kind": kind,
        "target": target,
        "pct": pct,
        "text": text,
        "apply_on_up": False,
        "effect": effect,
    }
    CITY_BUFFS.setdefault(resolved, []).append(entry)
    save_data(critical=True)
    await state.clear()
    note = ""
    if effect == "cost":
        note = "\n🏗 <b>باف هزینه ارتقا</b> — روی هزینه ساخت/ارتقا همان هدف اعمال می‌شود (نیازی به تیک آپ نیست)."
    else:
        note = "\nاعمال در آپ: فعلاً ❌ — از منوی باف/نرف تیک بزن."
    await message.answer(
        f"✅ ثبت شد روی <b>{e(resolved)}</b>\n"
        f"{kind} · {e(target)} · {fmt_num(pct)}%"
        + note,
        reply_markup=get_admin_inline_keyboard(),
    )


@dp.callback_query(F.data.startswith("buff_tog:"))
async def buff_toggle_up(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer()
    city, bid = parts[1], parts[2]
    lst = CITY_BUFFS.get(city) or []
    found = False
    for bf in lst:
        if str(bf.get("id")) == bid:
            bf["apply_on_up"] = not bool(bf.get("apply_on_up"))
            found = True
            await callback.answer(
                "آپ: ✅" if bf["apply_on_up"] else "آپ: ❌"
            )
            break
    if not found:
        return await callback.answer("یافت نشد", show_alert=True)
    CITY_BUFFS[city] = lst
    save_data(critical=True)
    return await admin_buffs_menu(callback)
