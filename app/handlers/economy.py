"""هندلرهای economy"""
import logging
import re
import secrets
import time

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import ADMIN_ID, ADVISE_MODES, DIV
from app.loader import bot, dp
from app.state import CITY_ASSETS, CITY_RANKS, GROUPS, pending_upgrades
from app.features import enabled
from app.economy.views import RANK_CATS, RANK_TITLES, city_ranks, rank_arrow
from app.utils import _tier_label, e, fmt_num, is_back_text, send_chunks
from app.factions import FACTIONS, FACTION_META, cities_for_side_assets, country_key
from app.states import GameStates
from app.players import (
    city_for_callback,
    city_of,
    is_admin,
    is_leader,
    is_plain_player,
    is_player,
    leader_side,
    mention,
    resolve_player_city,
    side_of_user,
)
from app.keyboards import _btn, get_back_keyboard, get_inline_back_row
from app.storage import save_data
from app.ai import ai_available, remaining_today
from app.menus import go_menu
from app.economy.rules import (
    AUTHORITY_TIERS,
    LEGITIMACY_TIERS,
    SPECIAL_UNITS,
    TECH_UNLOCK_COST,
    UPGRADE_SECTIONS,
    _RES_MAP,
)
from app.economy.sheet import (
    _parse_multi_asset_edit,
    get_city_asset_stats,
    get_city_asset_text,
    normalize_stats_keys,
)
from app.economy.costs import (
    _bag_stock,
    cost_for_levels,
    format_cost_dict,
    guess_current_level,
    max_affordable_levels,
)
from app.economy.assets import (
    _append_change,
    _city_change_log,
    _commit_shop_text,
    _locked_units,
    apply_stat_delta,
    apply_upgrade_levels,
    is_auto_city,
    is_building_locked,
)
from app.economy.views import format_city_asset_view, format_realm_view
from app.economy.advisor import build_upgrade_advice


@dp.callback_query(F.data.startswith("eco:"))
async def handle_economy_extra(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    action = callback.data.split(":", 1)[1]
    if action == "shop_admin" and not is_admin(uid):
        return await callback.answer("❌ فقط ادمین.", show_alert=True)
    # همان منطق شهر handle_unlock_do — تا ایندکس دکمه‌ها با همان شهر بخواند
    ok, city, _err = city_for_callback(callback)
    if not ok or not city:
        city = (await state.get_data()).get("upg_city") or resolve_player_city(uid) or city_of(uid)
    await callback.answer()

    if action == "help":
        text = (
            f"❓ <b>راهنمای منوی اقتصادی</b>\n{DIV}\n"
            "• <b>مشاهده دارایی</b> — شیت شخصی / کل قلمرو\n"
            "• <b>ارتقا</b> — فقط شهر اتو: بخش → ساختمان → سطح → تایید\n"
            "• <b>مشاور</b> — پلن بهینه با منابع (اعمال جداست)\n"
            "• <b>بازکردن قفل</b> — یونیت‌های 🔒 با هزینه قوانین\n"
            "• <b>باف/نرف آپ</b> — انتخاب اثرهایی که با آپ عددی شوند "
            "(باف نبرد روی دارایی اعمال نمی‌شود)\n"
            "• <b>تغییرات اخیر</b> — لاگ ارتقا/آپ/ویرایش\n"
            "• <b>ویرایش</b> — ادمین: فرمول یا شیت کامل\n\n"
            "دستور متنی:\n<code>اعمال ارتقا: بندر 2, خزانه 1</code>\n"
            "ویرایش ادمین:\n<code>ویرایش دارایی سکه +500</code>\n"
            "<code>ویرایش دارایی چوب -100</code>"
        )
        return await callback.message.answer(text, reply_markup=get_inline_back_row("menu:economy"))

    if action == "rank":
        if not enabled("my_rank"):
            return await callback.message.answer("🏆 «رتبه من» فعلاً خاموش است.")
        if not city or city == "ناشناس":
            return await callback.message.answer("شهر شما مشخص نیست.", reply_markup=get_inline_back_row("menu:economy"))
        ranks = city_ranks(city)
        if not ranks:
            return await callback.message.answer(
                "📭 هنوز دارایی این شهر ثبت نشده؛ رتبه‌ای ندارد.", reply_markup=get_inline_back_row("menu:economy")
            )
        prev = CITY_RANKS.get(city) or {}
        lines = [f"🏆 <b>رتبه {e(city)}</b>\n{DIV}"]
        for cat in RANK_CATS:
            r, total = ranks[cat]
            arrow = rank_arrow(prev.get(cat), r) if prev else ""
            lines.append(f"{RANK_TITLES[cat]}: <b>{fmt_num(r)}</b> از {fmt_num(total)} {arrow}".rstrip())
        lines.append("\n<i>فقط رتبه‌ی شهر شما نمایش داده می‌شود؛ ▲▼ نسبت به کارنامه‌ی هفته‌ی قبل.</i>")
        return await callback.message.answer("\n".join(lines), reply_markup=get_inline_back_row("menu:economy"))

    if action == "changes":
        if not city:
            return await callback.message.answer("شهر؟", reply_markup=get_inline_back_row("menu:economy"))
        logs = _city_change_log(city)
        body = "\n".join(f"• {e(x)}" for x in logs) if logs else "هنوز تغییری ثبت نشده."
        return await callback.message.answer(
            f"📜 <b>تغییرات اخیر — {e(city)}</b>\n{DIV}\n{body}",
            reply_markup=get_inline_back_row("menu:economy"),
        )

    if action == "unlock":
        if not city:
            return await callback.message.answer("شهر؟")
        if not is_auto_city(city) and not is_admin(uid):
            return await callback.message.answer("فقط شهر اتو / ادمین.", reply_markup=get_inline_back_row("menu:economy"))
        builder = InlineKeyboardBuilder()
        locked = _locked_units(city)
        if not locked:
            return await callback.message.answer(
                "✅ قفل فعالی در لیست پیش‌فرض نیست.",
                reply_markup=get_inline_back_row("menu:economy"),
            )
        for i, name in enumerate(locked):
            builder.row(_btn(f"🔓 {name}", f"unlock:do:{i}", "success"))
        builder.row(_btn("🔙", "menu:economy"))
        return await callback.message.answer(
            f"🔓 <b>بازکردن قفل — {e(city)}</b>\n{DIV}\n"
            "هزینه ≈ یک سطح ساخت (قوانین). پس از آنلاک، ارتقا و آپ مجاز است.",
            reply_markup=builder.as_markup(),
        )

    if action == "buffpick":
        return await callback.message.answer(
            f"🎛 <b>باف / نرف آپ</b>\n{DIV}\n"
            "باف‌های <b>نبرد</b> (روحیه، مقاومت و…) روی عدد دارایی اعمال نمی‌شوند.\n"
            "فقط اثرهایی که ادمین مشخص کند با آپ عددی می‌شوند.\n\n"
            "فعلاً: باف/نرف در شیت فقط <b>نمایش</b> است.\n"
            "برای اعمال عددی ادمین از «ویرایش دارایی» استفاده کند.\n"
            "مثال: <code>ویرایش دارایی اقتدار -3</code>",
            reply_markup=get_inline_back_row("menu:economy"),
        )

    if action == "shop_admin":
        return await callback.message.answer(
            f"🛒 <b>ثبت شاپ</b>\n{DIV}\n"
            "در گروه شهر بنویسید:\n"
            "<code>ست شاپ\n"
            "استارتر طلایی (50)\n"
            "توپ ویرانگر (2) : 7\n"
            "وزیر شارل</code>\n\n"
            "عدد داخل <b>پرانتز = بازدهی آپ</b>.\n"
            "عدد بعد از : = موجودی فعلی (اختیاری).\n"
            "با آپ، بازدهی شاپ به دارایی اضافه می‌شود.",
            reply_markup=get_inline_back_row("menu:economy"),
        )

    if action == "politics":
        bag = normalize_stats_keys(get_city_asset_stats(city)) if city else {}
        auth = bag.get("اقتدار")
        leg = bag.get("مشروعیت")
        try:
            auth_f = float(auth) if auth is not None else None
        except (TypeError, ValueError):
            auth_f = None
        try:
            leg_f = float(leg) if leg is not None else None
        except (TypeError, ValueError):
            leg_f = None
        auth_s = f"{fmt_num(auth_f)}" if auth_f is not None else "—"
        leg_s = f"{fmt_num(leg_f)}" if leg_f is not None else "—"
        auth_tier = _tier_label(auth_f, AUTHORITY_TIERS)
        leg_tier = _tier_label(leg_f, LEGITIMACY_TIERS)
        text = (
            f"🗡🛡 <b>اقتدار و مشروعیت</b>\n{DIV}\n"
            f"🏙 <b>{e(city or '—')}</b>\n"
            f"🗡 اقتدار: <b>{auth_s}</b> — <i>{e(auth_tier)}</i>\n"
            f"🛡 مشروعیت: <b>{leg_s}</b> — <i>{e(leg_tier)}</i>\n\n"
            f"<b>🗡 اقتدار</b>\n"
            "اعتبار میان مردم و جهانیان. با بخشندگی، پیروزی، ارتش قوی و اقتصاد خوب بالا می‌رود؛ "
            "روحیه ارتش را بالا می‌برد. پیش‌فرض قوانین: <b>۴۰</b>.\n"
            "• ۰–۲۰: بی‌اعتبار — شورش ارتش / خواهان برکناری\n"
            "• ۲۰–۴۰: ضعیف — مردم منتظر جرقه\n"
            "• ۴۰–۶۰: متوسط — حاکم قابل‌قبول\n"
            "• ۶۰–۸۰: بالا — جان‌فشانی در جنگ\n"
            "• ۸۰–۱۰۰: اوج — مردم هفتگی <b>۲۵۰ سکه</b> · کاهش اثر جاسوسی/خرابکاری\n\n"
            f"<b>🛡 مشروعیت</b>\n"
            "پذیرش حکومت نزد مردم، اشراف، فرماندهان و نیروها — برحق و سزاوار اطاعت بودن. "
            "از عدالت، ثبات، پیروزی/شکست، وفاداری اشراف و اجرای قانون اثر می‌پذیرد. "
            "برخلاف اقتدار (هیبت و انگیزه ارتش)، مشروعیت <b>پایه ثبات حکومت</b> است.\n"
            "• ۰–۲۰: <b>بحران</b> — خطر شورش، کودتا، نافرمانی، فکر استقلال استان‌ها\n"
            "• ۲۰–۴۰: <b>ضعیف</b> — نارضایتی؛ شکست کوچک می‌تواند آشوب کند\n"
            "• ۴۰–۶۰: <b>متوسط</b> — قابل قبول؛ در بحران ریسک نارضایتی\n"
            "• ۶۰–۸۰: <b>بالا</b> — ثبات داخلی و وفاداری نیروها\n"
            "• ۸۰–۱۰۰: <b>مطلق</b> — حمایت گسترده؛ خطر کودتا/شورش بسیار کم\n\n"
            f"<b>آپ و تغییر اعداد</b>\n"
            "• آپ هفتگی این دو را <b>خودکار عوض نمی‌کند</b>.\n"
            "• تغییر با رول، رویداد، کودتا، مالیات سنگین، یا دستور ادمین:\n"
            "<code>ویرایش دارایی اقتدار -5</code>\n"
            "<code>ویرایش دارایی مشروعیت +3</code>\n"
            "• مالیات جمعیت ۶–۱۰ → معمولاً −۵ اقتدار · ۱۱–۱۵ → −۱۰ اقتدار و مشروعیت (ادمین/رول)\n"
            "• نرف شخصیت/قلعه هر آپ تکرار نمی‌شود.\n\n"
            "<i>شاخص سیاسی‌اند؛ موجودی سکه یا نیرو نیستند.</i>"
        )
        return await callback.message.answer(
            text, reply_markup=get_inline_back_row("menu:economy")
        )


@dp.message(F.text.regexp(r"(?i)^\s*ست\s*شاپ"))
async def handle_set_shop(message: types.Message, state: FSMContext):
    """شروع ثبت شاپ — ادمین پک‌ها را فوروارد/ارسال می‌کند."""
    if not is_admin(message.from_user.id):
        return
    city = None
    if message.chat.type in ("group", "supergroup"):
        grp = GROUPS.get(message.chat.id)
        if grp:
            city = grp.get("city")
    if not city:
        city = resolve_player_city(message.from_user.id)
    if not city:
        return await message.answer("❌ در گروه شهر بزنید یا اول ست گپ کنید.")
    body = re.sub(r"(?i)^\s*ست\s*شاپ\s*:?\s*", "", message.text or "").strip()
    if body:
        # متن هم‌زمان با دستور — ثبت مستقیم
        return await _commit_shop_text(message, city, body)
    await state.clear()
    await state.update_data(shop_city=city, shop_chunks=[])
    await state.set_state(GameStates.adm_shop_collect)
    await message.answer(
        f"🛒 <b>ثبت شاپ — {e(city)}</b>\n{DIV}\n"
        "📦 پک‌ها را <b>فوروارد</b> یا کپی کنید و بفرستید.\n"
        "می‌توانید چند پیام پشت‌سرهم بفرستید.\n\n"
        "انواع قابل‌تشخیص:\n"
        "• <b>گروهک مزدوری</b> — نوع و تعداد یونیت\n"
        "• <b>مزدور / جاسوس / گارد</b> — تعداد و بازدهی\n"
        "• <b>وزیر</b> — فقط اسم\n"
        "• <b>هیرو / فرمانده</b> — اسم + ارتش همراه\n"
        "• پک عمومی — <code>نام (بازدهی)</code>\n\n"
        "وقتی تمام شد بنویسید: <code>تمام</code> یا <code>ثبت</code>\n"
        "لغو: <code>لغو</code>"
    )

@dp.message(GameStates.adm_shop_collect)
async def handle_shop_collect(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if is_back_text(message.text or "") or re.match(r"(?i)^\s*لغو\s*$", message.text or ""):
        await state.clear()
        return await message.answer("❌ ثبت شاپ لغو شد.")
    data = await state.get_data()
    city = data.get("shop_city")
    chunks = list(data.get("shop_chunks") or [])
    txt = (message.text or message.caption or "").strip()
    # فوروارد: متن پیام اصلی
    if not txt and message.reply_to_message:
        txt = (message.reply_to_message.text or message.reply_to_message.caption or "").strip()
    if re.match(r"(?i)^\s*(تمام|ثبت|پایان|done)\s*$", txt or ""):
        if not chunks:
            return await message.answer("هنوز پکی نفرستادید. فوروارد کنید یا <code>لغو</code>.")
        body = "\n".join(chunks)
        await state.clear()
        return await _commit_shop_text(message, city, body)
    if not txt:
        return await message.answer("متن پک را بفرستید یا فوروارد کنید.")
    chunks.append(txt)
    await state.update_data(shop_chunks=chunks)
    await message.answer(
        f"✅ پک دریافت شد ({len(chunks)} پیام).\n"
        "پک بعدی را بفرستید یا <code>تمام</code> بزنید."
    )


@dp.callback_query(F.data.startswith("unlock:do:"))
async def handle_unlock_do(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_player(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    ok, city, _e = city_for_callback(callback)
    if not ok or not city:
        city = (await state.get_data()).get("upg_city") or resolve_player_city(uid) or city_of(uid)
    if city:
        await state.update_data(upg_city=city)
    if not city:
        return await callback.answer("شهر؟", show_alert=True)
    if not is_auto_city(city) and not is_admin(uid):
        return await callback.answer("اتو؟", show_alert=True)
    locked = _locked_units(city)
    try:
        idx = int(callback.data.split(":")[2])
        name = locked[idx]
    except (ValueError, IndexError):
        return await callback.answer("نامعتبر", show_alert=True)
    # فناوری نظامی لازم (طبق قوانین) + هزینه ساخت لول ۱
    bag = normalize_stats_keys(get_city_asset_stats(city))
    need_tech = TECH_UNLOCK_COST.get(name)
    if need_tech:
        mil_tech = float(bag.get("فناوری نظامی") or bag.get("نظامی") or 0)
        if mil_tech < need_tech and not is_admin(uid):
            return await callback.answer(
                f"فناوری نظامی ≥ {need_tech} لازم است (الان {fmt_num(mil_tech)})",
                show_alert=True,
            )
    stock = _bag_stock(bag)
    if max_affordable_levels(name, stock, city=city) < 1:
        return await callback.answer("موجودی کافی نیست", show_alert=True)
    cd = cost_for_levels(name, 1, city=city)
    deltas = {}
    for key, lab in _RES_MAP:
        need = cd.get(key, 0)
        if need and lab != "جمعیت":
            deltas[lab if lab != "سکه" else "سکه"] = -need
    apply_stat_delta(city, deltas, note=f"آنلاک {name}")
    entry = CITY_ASSETS.setdefault(city, {"text": "", "stats": {}, "unlocked": []})
    un = list(entry.get("unlocked") or [])
    if name not in un:
        un.append(name)
    entry["unlocked"] = un
    # حذف قفل از متن در صورت وجود
    text = entry.get("text") or ""
    if name in text and "🔒" in text:
        new_lines = []
        for ln in text.splitlines():
            if name in ln:
                ln = ln.replace("🔒", "🔓")
            new_lines.append(ln)
        entry["text"] = "\n".join(new_lines)
    CITY_ASSETS[city] = entry
    _append_change(city, f"آنلاک {name}")
    save_data(critical=True)
    await callback.answer("✅ باز شد")
    await callback.message.answer(
        f"🔓 <b>{e(name)}</b> باز شد.\nهزینه: {e(format_cost_dict(cd))}",
        reply_markup=get_inline_back_row("menu:economy"),
    )


UPGRADE_CONFIRM_TTL = 600  # ثانیه


@dp.callback_query(F.data.startswith("upg:"))
async def handle_upgrade_nav(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_player(uid) or is_admin(uid) or is_leader(uid)):
        return await callback.answer("❌", show_alert=True)
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    okc, cctx, _ = city_for_callback(callback)
    city = (await state.get_data()).get("upg_city") or cctx or resolve_player_city(uid) or city_of(uid)
    if city:
        await state.update_data(upg_city=city)
    if not city:
        return await callback.answer("شهر؟", show_alert=True)
    if not is_auto_city(city) and not is_admin(uid):
        return await callback.answer("اتو غیرفعال", show_alert=True)

    if action == "text":
        await callback.answer()
        return await callback.message.answer(
            "بنویسید:\n<code>اعمال ارتقا: بندر 2, خزانه 1</code>",
            reply_markup=get_inline_back_row("menu:upgrade"),
        )

    if action == "sec" and len(parts) >= 3:
        await callback.answer()
        sec = parts[2]
        meta = UPGRADE_SECTIONS.get(sec)
        if not meta:
            return
        title, items = meta
        builder = InlineKeyboardBuilder()
        for i, name in enumerate(items):
            lock = "🔒" if is_building_locked(city, name) else ""
            builder.row(_btn(f"{lock}{name}", f"upg:b:{sec}:{i}", "primary"))
        builder.row(_btn("🔙 بخش‌ها", "menu:upgrade"))
        text = f"{title}\n{DIV}\nساختمان را انتخاب کنید:"
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
        except Exception:
            await callback.message.answer(text, reply_markup=builder.as_markup())
        return

    if action == "b" and len(parts) >= 4:
        sec, idx_s = parts[2], parts[3]
        meta = UPGRADE_SECTIONS.get(sec)
        if not meta:
            return await callback.answer()
        _title, items = meta
        try:
            idx = int(idx_s)
            name = items[idx]
        except (ValueError, IndexError):
            return await callback.answer("نامعتبر", show_alert=True)
        if is_building_locked(city, name):
            return await callback.answer("قفل است — اول بازکردن قفل", show_alert=True)
        await callback.answer()
        bag = normalize_stats_keys(get_city_asset_stats(city))
        stock = _bag_stock(bag)
        aff = max_affordable_levels(name, stock, city=city)
        cost1 = format_cost_dict(cost_for_levels(name, 1, city=city))
        builder = InlineKeyboardBuilder()
        for lv in (1, 2, 3):
            if lv <= max(aff, 1):
                c = format_cost_dict(cost_for_levels(name, lv, city=city))
                builder.row(_btn(f"+{lv} سطح · {c[:40]}", f"upg:do:{sec}:{idx}:{lv}", "success"))
        builder.row(_btn("🔙", f"upg:sec:{sec}"))
        sheet = get_city_asset_text(city) or ""
        cur = guess_current_level(name, bag, sheet)
        cur_s = str(cur) if cur is not None else "?"
        text = (
            f"🏢 <b>{e(name)}</b> — {e(city)}\n{DIV}\n"
            f"🔹 لول کنونی: <b>{cur_s}</b>\n"
            f"🧮 هزینه هر سطح: <code>{e(cost1)}</code>\n"
            f"📊 حداکثر قابل‌پرداخت الان: <b>{aff}</b> سطح\n\n"
            "تعداد سطح را انتخاب کنید:"
        )
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
        except Exception:
            await callback.message.answer(text, reply_markup=builder.as_markup())
        return

    if action == "do" and len(parts) >= 5:
        # مرحله ۱: فقط پیش‌نویس + دکمه تایید (چیزی کسر نمی‌شود)
        sec, idx_s, lv_s = parts[2], parts[3], parts[4]
        meta = UPGRADE_SECTIONS.get(sec)
        if not meta:
            return await callback.answer()
        _title, items = meta
        try:
            name = items[int(idx_s)]
            levels = int(lv_s)
        except (ValueError, IndexError):
            return await callback.answer("نامعتبر", show_alert=True)
        await callback.answer()
        now = time.time()
        for k in [k for k, v in pending_upgrades.items() if now - v["ts"] > UPGRADE_CONFIRM_TTL]:
            pending_upgrades.pop(k, None)
        token = secrets.token_hex(4)
        pending_upgrades[token] = {"uid": uid, "city": city, "name": name, "levels": levels, "ts": now}
        bag = normalize_stats_keys(get_city_asset_stats(city))
        cur = guess_current_level(name, bag, get_city_asset_text(city) or "")
        cur_s = fmt_num(cur) if cur is not None else "?"
        to_s = fmt_num(cur + levels) if cur is not None else f"?+{levels}"
        cost = format_cost_dict(cost_for_levels(name, levels, city=city))
        builder = InlineKeyboardBuilder()
        builder.row(
            _btn("✅ تایید ارتقا", f"upg:ok:{token}", "success"),
            _btn("❌ انصراف", f"upg:no:{token}", "danger"),
        )
        text = (
            f"⬆️ <b>پیش‌نویس فرمان ارتقا</b>\n{DIV}\n"
            f"🏙 شهر: <b>{e(city)}</b>\n"
            f"🏢 ساختمان: <b>{e(name)}</b>\n"
            f"🔹 لول: <b>{cur_s}</b> → <b>{to_s}</b> (+{fmt_num(levels)})\n"
            f"🧮 هزینه: <code>{e(cost)}</code>\n\n"
            "سرورم، هزینه پس از تایید از خزانه کسر می‌شود. تایید می‌کنید؟"
        )
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup())
        except Exception:
            await callback.message.answer(text, reply_markup=builder.as_markup())
        return

    if action in ("ok", "no") and len(parts) >= 3:
        # مرحله ۲: توکن قبل از هر await برداشته می‌شود → کلیک دوم چیزی پیدا نمی‌کند
        pend = pending_upgrades.pop(parts[2], None)
        if not pend or pend["uid"] != uid or time.time() - pend["ts"] > UPGRADE_CONFIRM_TTL:
            if pend and pend["uid"] != uid:
                pending_upgrades[parts[2]] = pend  # مال کس دیگری است؛ دست نزن
                return await callback.answer("❌ این فرمان مال شما نیست.", show_alert=True)
            return await callback.answer("این فرمان قبلاً انجام یا منقضی شده است.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        if action == "no":
            await callback.answer("لغو شد")
            return await callback.message.answer(
                "❌ سرورم، فرمان ارتقا لغو شد.", reply_markup=get_inline_back_row("menu:upgrade")
            )
        city, name, levels = pend["city"], pend["name"], pend["levels"]
        ok, msg = apply_upgrade_levels(city, name, levels, force=is_admin(uid))
        if ok:
            await callback.answer("✅ اعمال شد")
        else:
            await callback.answer((msg or "")[:80], show_alert=True)
        await callback.message.answer(
            f"{'✅' if ok else '❌'} <b>{e(name)}</b>\n{msg}",
            reply_markup=get_inline_back_row("menu:upgrade"),
        )
        if ok:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"⬆️ ارتقا اتو\n🏙 {e(city)}\n👤 {mention(uid, city)}\n{msg[:800]}",
                )
            except Exception:
                pass
        return
    await callback.answer()


@dp.callback_query(F.data.startswith("aedit:"))
async def handle_aedit_menu(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ ادمین", show_alert=True)
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action == "text":
        await callback.message.answer(
            "⌨️ در گروه شهر بنویسید:\n"
            "<code>ویرایش دارایی سکه +500, چوب -100</code>\n"
            "<code>ویرایش دارایی تلفات شبه نظامی 50 شمشیرزن 30</code>\n"
            "<code>ویرایش دارایی اضافه کردن ۵۰ چوب کسر ۱۰۰ سنگ</code>\n"
            "<code>ویرایش دارایی بازدهی خزانه +200</code>",
            reply_markup=get_inline_back_row("menu:asset_edit"),
        )
        return
    if action == "add_res":
        await callback.message.answer(
            "➕ مثال:\n<code>ویرایش دارایی +50 چوب +50 آهن +100 سکه</code>\n"
            "یا: <code>ویرایش دارایی اضافه کردن ۵۰ چوب ۵۰ آهن</code>",
            reply_markup=get_inline_back_row("menu:asset_edit"),
        )
        return
    if action == "sub_res":
        await callback.message.answer(
            "➖ مثال:\n<code>ویرایش دارایی -100 سنگ -1000 سکه</code>\n"
            "یا: <code>ویرایش دارایی کسر ۱۰۰ سنگ و ۱۰۰۰ سکه</code>",
            reply_markup=get_inline_back_row("menu:asset_edit"),
        )
        return
    if action == "loss":
        await callback.message.answer(
            "💀 مثال:\n<code>ویرایش دارایی تلفات شبه نظامی 50 شمشیرزن 30 نیزه دار 20</code>",
            reply_markup=get_inline_back_row("menu:asset_edit"),
        )
        return
    if action == "yield":
        await callback.message.answer(
            "📈 مثال:\n<code>ویرایش دارایی بازدهی خزانه +200</code>\n"
            "<code>ویرایش دارایی بازدهی شبه نظامی +30</code>",
            reply_markup=get_inline_back_row("menu:asset_edit"),
        )
        return
    if action == "special":
        lines = [f"🌟 <b>نیروهای ویژه ثبت‌شده</b>\n{DIV}"]
        for name, meta in SPECIAL_UNITS.items():
            cat = {"inf": "پیاده", "cav": "سواره", "arty": "توپ", "ship": "کشتی"}.get(meta.get("cat"), "?")
            lines.append(
                f"• <b>{e(name)}</b> · {cat} · ضریب {meta.get('coef')} · "
                f"بازدهی {meta.get('yield')} · {'🔒' if meta.get('lock') else '🔓'}"
            )
        lines.append(
            "\nدر شیت کمپ ویژه بنویسید:\n"
            "<code>|💂|-| کلداستریم گارد | (1) : 100</code>\n"
            "بازدهی آپ همان عدد جلوی کمپ است؛ اگر خالی باشد پیش‌فرض دسته اعمال می‌شود."
        )
        builder = InlineKeyboardBuilder()
        builder.row(_btn("🔙", "menu:asset_edit"))
        await callback.message.answer("\n".join(lines), reply_markup=builder.as_markup())
        return


@dp.message(F.text.regexp(r"(?i)^\s*ویرایش\s*دارایی"))
async def handle_asset_formula_edit(message: types.Message):
    """
    ویرایش چندعبارتی:
      ویرایش دارایی سکه +500, چوب -100
      ویرایش دارایی اضافه کردن ۵۰ چوب ۵۰ آهن کسر ۱۰۰ سنگ و ۱۰۰۰ سکه
      ویرایش دارایی تلفات شبه نظامی 50 شمشیرزن 30 نیزه دار 20
      ویرایش دارایی بازدهی خزانه +200
    """
    if not is_admin(message.from_user.id):
        return
    body = re.sub(r"(?i)^\s*ویرایش\s*دارایی\s*:?\s*", "", message.text or "").strip()
    if not body:
        return await message.answer(
            "فرمول چندعبارتی:\n"
            "<code>ویرایش دارایی سکه +500, چوب -100</code>\n"
            "<code>ویرایش دارایی اضافه کردن ۵۰ چوب ۵۰ آهن کسر ۱۰۰ سنگ و ۱۰۰۰ سکه</code>\n"
            "<code>ویرایش دارایی تلفات شبه نظامی 50 شمشیرزن 30 نیزه دار 20</code>\n"
            "<code>ویرایش دارایی +50 چوب +50 آهن -100 سنگ -1000 سکه</code>\n"
            "<code>ویرایش دارایی بازدهی خزانه +200</code>"
        )
    city = None
    if message.chat.type in ("group", "supergroup"):
        grp = GROUPS.get(message.chat.id)
        if grp:
            city = grp.get("city")
    if not city:
        city = resolve_player_city(message.from_user.id)
    if not city:
        return await message.answer("❌ شهر مشخص نیست (در گروه شهر بزنید).")

    stock_deltas, yield_deltas = _parse_multi_asset_edit(body)
    if not stock_deltas and not yield_deltas:
        return await message.answer("❌ فرمول نامعتبر. چند مورد با عدد بنویسید.")

    parts_out = []
    if stock_deltas:
        log = apply_stat_delta(city, stock_deltas, note="ویرایش ادمین · موجودی")
        parts_out.append(f"<b>موجودی الان:</b>\n{log}")
    if yield_deltas:
        entry = CITY_ASSETS.setdefault(city, {"text": "", "stats": {}, "yields": {}})
        stats = normalize_stats_keys(dict(entry.get("stats") or {}))
        ymap = dict(entry.get("yields") or {})
        ylog = []
        for k, dlt in yield_deltas.items():
            old_y = float(ymap.get(k) or stats.get(k) or 0)
            new_y = max(0, old_y + dlt)
            ymap[k] = new_y
            if k not in (
                "شبه نظامی", "شمشیرزن", "نیزه دار", "رایفلدار", "افسر",
                "سواره نظام شمشیرزن", "سواره‌نظام زره پوش", "سواره‌نظام تفنگدار",
                "توپ سبک", "توپ محاصره", "توپ سنگین", "قایق", "کشتی جنگی", "ناو جنگی", "کشتی سلطنتی",
            ):
                stats[k] = new_y
            else:
                stats[f"yield:{k}"] = new_y
            ylog.append(f"بازدهی {k}: {fmt_num(old_y)} → {fmt_num(new_y)} ({fmt_num(dlt, signed=True)})")
        entry["stats"] = stats
        entry["yields"] = ymap
        CITY_ASSETS[city] = entry
        save_data(critical=True)
        parts_out.append("<b>بازدهی (از آپ بعد):</b>\n" + "\n".join(ylog))
        _append_change(city, f"بازدهی: {yield_deltas}")

    _append_change(city, f"ویرایش ادمین: {body[:100]}")
    await message.answer(f"✅ ویرایش <b>{e(city)}</b>\n{DIV}\n" + "\n\n".join(parts_out))


@dp.callback_query(F.data.startswith("advise_mode:"))
async def handle_advise_mode(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    mode = callback.data.split(":", 1)[1]
    if mode not in ADVISE_MODES:
        return await callback.answer("نامعتبر", show_alert=True)
    await callback.answer()
    await state.update_data(advise_mode=mode, advise_notes="", advise_msg_count=0)

    # پلیر عادی → فقط شهر خودش، بدون لیست
    if is_plain_player(uid):
        my = resolve_player_city(uid)
        if not my:
            return await callback.message.answer(
                "❌ شهر شما ثبت نشده. اول با کد ورود وارد ربات شوید.",
                reply_markup=get_inline_back_row("menu:home"),
            )
        return await _advise_after_city_pick(callback, state, my, mode)

    # لیدر / ادمین → انتخاب از شهرهای مجاز
    side = leader_side(uid) or side_of_user(uid)
    builder = InlineKeyboardBuilder()
    if is_admin(uid) and not leader_side(uid):
        for s in FACTIONS:
            flag, title = FACTION_META[s]
            cities = [c for c in cities_for_side_assets(s) if c in CITY_ASSETS]
            for i, city in enumerate(cities[:8]):
                short = city.rsplit("_", 1)[0] if "_" in city else city
                if short.isascii():
                    short = short.replace("_", " ").title()
                builder.row(_btn(f"{flag} {short}", f"advise_ci:{s}:{i}:{mode}"))
    elif side and side in FACTIONS:
        cities = [c for c in cities_for_side_assets(side) if c in CITY_ASSETS]
        if not cities:
            # اگر دارایی نیست، باز هم شهرهای ساید را نشان بده
            cities = cities_for_side_assets(side)
        if not cities:
            return await callback.message.answer(
                "📭 شهری برای این ساید ثبت نشده.",
                reply_markup=get_inline_back_row("menu:advise"),
            )
        for i, city in enumerate(cities):
            short = city.rsplit("_", 1)[0] if "_" in city else city
            if short.isascii():
                short = short.replace("_", " ").title()
            has = "📦" if city in CITY_ASSETS else "—"
            builder.row(_btn(f"{has} {short}", f"advise_ci:{side}:{i}:{mode}"))
    else:
        my = resolve_player_city(uid)
        if my:
            return await _advise_after_city_pick(callback, state, my, mode)
        return await callback.message.answer(
            "❌ شهر/ساید مشخص نیست.",
            reply_markup=get_inline_back_row("menu:home"),
        )
    builder.row(_btn("🔙 بازگشت", "menu:advise"))
    mode_fa = ADVISE_MODES[mode][1]
    await callback.message.answer(
        f"🧠 مشاور <b>{e(mode_fa)}</b>\n{DIV}\nشهر را انتخاب کنید:",
        reply_markup=builder.as_markup(),
    )


async def _advise_after_city_pick(callback, state, city: str, mode: str):
    """بعد از انتخاب شهر: چت آزاد یا تحلیل مستقیم."""
    await state.update_data(advise_city=city, advise_mode=mode, advise_notes="", advise_msg_count=0)
    if mode == "chat":
        builder = InlineKeyboardBuilder()
        builder.row(_btn("⏭ بدون توضیح — تحلیل کن", f"advise_run:{mode}", "success"))
        builder.row(_btn("🔙 انصراف", "menu:advise", "danger"))
        await state.set_state(GameStates.advise_pref)
        return await callback.message.answer(
            f"💬 <b>چت آزاد مشاور</b> — شهر <b>{e(city)}</b>\n{DIV}\n"
            "در <b>۱ یا ۲ پیام</b> بگو:\n"
            "• هدف‌ت چیه؟ (اقتصاد / فتح / دفاع / دریا…)\n"
            "• بودجه یا محدودیت داری؟\n"
            "• سلیقه‌ت چیه؟\n\n"
            "بعد از پیام‌ها خودکار تحلیل می‌شود.\n"
            "یا دکمه «بدون توضیح» را بزن.",
            reply_markup=builder.as_markup(),
        )
    # غیر چت: مستقیم یا یک سوال کوتاه اختیاری
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🚀 تحلیل همین الان", f"advise_run:{mode}", "success"))
    builder.row(_btn("✍️ یک توضیح کوتاه می‌دهم", f"advise_want_note:{mode}", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:advise"))
    mode_fa = ADVISE_MODES.get(mode, ("", mode))[1]
    await callback.message.answer(
        f"🎯 مشاور <b>{e(mode_fa)}</b> · شهر <b>{e(city)}</b>\n{DIV}\n"
        "می‌خواهید بدون توضیح تحلیل شود یا یک پیام کوتاه درباره پلن‌تان بفرستید؟",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("advise_ci:"))
async def handle_advise_city(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    # advise_ci:side:idx:mode  یا قدیمی advise_ci:side:idx
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    side, idx_s = parts[1], parts[2]
    mode = parts[3] if len(parts) > 3 else (await state.get_data()).get("advise_mode", "balance")
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر", show_alert=True)
    if is_plain_player(uid):
        return await callback.answer("❌ فقط شهر خودتان از منوی مشاور.", show_alert=True)
    if not is_admin(uid) and leader_side(uid) and leader_side(uid) != side:
        return await callback.answer("❌ فقط ساید خودتان.", show_alert=True)
    try:
        idx = int(idx_s)
    except ValueError:
        return await callback.answer("نامعتبر", show_alert=True)
    cities = [c for c in cities_for_side_assets(side) if c in CITY_ASSETS]
    if not cities:
        cities = cities_for_side_assets(side)
    if idx < 0 or idx >= len(cities):
        return await callback.answer("شهر پیدا نشد.", show_alert=True)
    city = cities[idx]
    await callback.answer()
    await _advise_after_city_pick(callback, state, city, mode)


@dp.callback_query(F.data.startswith("advise_want_note:"))
async def handle_advise_want_note(callback: types.CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    d = await state.get_data()
    city = d.get("advise_city")
    if not city:
        return await callback.answer("شهر مشخص نیست.", show_alert=True)
    await callback.answer()
    await state.update_data(advise_mode=mode, advise_msg_count=0, advise_notes="")
    await state.set_state(GameStates.advise_pref)
    await callback.message.answer(
        f"✍️ یک یا دو پیام درباره پلن‌تان بنویسید (شهر: <b>{e(city)}</b>).\n"
        "مثال: «می‌خوام این هفته روی بندر و کشتی تمرکز کنم، بودجه حدود ۴۰۰۰ سکه»\n"
        "برای انصراف بنویس: <code>بازگشت</code>",
        reply_markup=get_back_keyboard(),
    )


@dp.callback_query(F.data.startswith("advise_run:"))
async def handle_advise_run(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    d = await state.get_data()
    city = d.get("advise_city")
    mode = callback.data.split(":", 1)[1] if ":" in callback.data else d.get("advise_mode", "balance")
    notes = d.get("advise_notes") or ""
    if not city:
        return await callback.answer("شهر مشخص نیست. دوباره از منو.", show_alert=True)
    await callback.answer("در حال تحلیل…")
    try:
        text = await build_upgrade_advice(city, mode=mode, notes=notes, user_id=uid)
    except Exception:
        logging.exception("upgrade advice")
        text = "❌ تحلیل ناموفق بود."
    await state.set_state(GameStates.main_menu)
    if len(text) > 4000:
        await send_chunks(callback.message, [text], reply_markup=_advice_markup(mode))
    else:
        await callback.message.answer(text, reply_markup=_advice_markup(mode))


def _advice_markup(mode: str):
    """زیر تحلیل محلی: دکمه بازنگری گروک (فقط اگر کلید باشد) + بازگشت."""
    builder = InlineKeyboardBuilder()
    if ai_available():
        builder.row(_btn(f"🤖 بازنگری گروک ({fmt_num(remaining_today())} باقی امروز)", f"advise_ai:{mode}", "primary"))
    builder.row(_btn("🔙 بازگشت", "menu:advise"))
    return builder.as_markup()


@dp.callback_query(F.data.startswith("advise_ai:"))
async def handle_advise_ai(callback: types.CallbackQuery, state: FSMContext):
    """گروک فقط با همین دکمه — با کش و سقف روزانه (app/ai.py)."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return await callback.answer("❌", show_alert=True)
    d = await state.get_data()
    city = d.get("advise_city")
    mode = callback.data.split(":", 1)[1] or "balance"
    if not city:
        return await callback.answer("شهر مشخص نیست. دوباره از منوی مشاور.", show_alert=True)
    await callback.answer("🤖 در حال پرسیدن از گروک…")
    try:
        text = await build_upgrade_advice(city, mode=mode, notes=d.get("advise_notes") or "", user_id=uid, use_ai=True)
    except Exception:
        logging.exception("upgrade advice ai")
        text = "❌ تحلیل ناموفق بود."
    await send_chunks(callback.message, [text], reply_markup=get_inline_back_row("menu:advise"))


@dp.message(GameStates.advise_pref)
async def process_advise_pref(message: types.Message, state: FSMContext):
    """حداکثر ۲ پیام سلیقه/پلن سپس تحلیل."""
    uid = message.from_user.id
    if not (is_leader(uid) or is_admin(uid) or is_player(uid)):
        return
    txt = (message.text or "").strip()
    if not txt:
        return await message.answer("متن بفرستید یا از منو انصراف دهید.")
    if txt in ("بازگشت", "لغو", "/cancel"):
        await state.clear()
        return await go_menu(message, state, user_id=uid)
    d = await state.get_data()
    notes = (d.get("advise_notes") or "")
    count = int(d.get("advise_msg_count") or 0) + 1
    notes = (notes + "\n" + txt).strip() if notes else txt
    await state.update_data(advise_notes=notes, advise_msg_count=count)
    city = d.get("advise_city")
    mode = d.get("advise_mode") or "chat"
    if count < 2:
        builder = InlineKeyboardBuilder()
        builder.row(_btn("🚀 همین کافی‌ست — تحلیل کن", f"advise_run:{mode}", "success"))
        return await message.answer(
            f"✅ پیام {count}/۲ ثبت شد.\n"
            "می‌توانید یک پیام دیگر بفرستید یا دکمه تحلیل را بزنید.\n"
            "مثال: <code>بندر ۳ لول و خزانه ۲ لول</code>",
            reply_markup=builder.as_markup(),
        )
    await message.answer("⏳ در حال چیدن بهترین پلن با منابع شما…")
    try:
        text = await build_upgrade_advice(city, mode=mode, notes=notes, user_id=uid)
    except Exception:
        logging.exception("upgrade advice")
        text = "❌ تحلیل ناموفق بود."
    await state.set_state(GameStates.main_menu)
    if len(text) > 4000:
        await send_chunks(message, [text], reply_markup=_advice_markup(mode))
    else:
        await message.answer(text, reply_markup=_advice_markup(mode))


@dp.callback_query(F.data.startswith("asset_view:"))
async def handle_asset_view(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    mode, side = parts[1], parts[2]
    my_side = leader_side(uid) or side_of_user(uid)
    if not is_admin(uid) and my_side != side:
        return await callback.answer("❌ فقط ساید خودتان.", show_alert=True)
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر.", show_alert=True)
    await callback.answer()
    flag, title = FACTION_META.get(side, ("", side))
    if mode == "realm":
        return await callback.message.answer(
            format_realm_view(side)[:4000],
            reply_markup=get_inline_back_row("menu:assets"),
        )
    if mode == "mine":
        # شهر همین گپ (اگر در گپ ست‌شده باشد) وگرنه شهر اصلی
        okc, city, _ = city_for_callback(callback, uid)
        if not okc or not city or city == "ناشناس":
            city = resolve_player_city(uid) or city_of(uid)
        if not city or city == "ناشناس":
            return await callback.message.answer(
                "❌ شهر شخصی شما مشخص نیست.",
                reply_markup=get_inline_back_row("menu:assets"),
            )
        body = format_city_asset_view(city, viewer=callback.from_user.id)
        if len(body) > 3500:
            await send_chunks(callback.message, [body], reply_markup=None)
            return await callback.message.answer(
                "⬆️ شیت دارایی شخصی",
                reply_markup=get_inline_back_row("menu:assets"),
            )
        await callback.message.answer(body)
        return await callback.message.answer(
            "⬆️ شیت دارایی شخصی",
            reply_markup=get_inline_back_row("menu:assets"),
        )
    # تکی ساید: لیست شهرها
    cities = cities_for_side_assets(side)
    lines = [f"🏙 <b>دارایی شخصی — {flag}{title}</b>\n{DIV}"]
    if not cities:
        lines.append("❗️ شهری ثبت نشده.")
    else:
        for i, city in enumerate(cities):
            has = "✅" if city in CITY_ASSETS and get_city_asset_text(city) else "—"
            lines.append(f"{i + 1}. {has} <code>{e(city)}</code>")
    lines.append("\nاز دکمه‌های زیر شهر را انتخاب کنید:")
    await callback.message.answer("\n".join(lines))
    builder = InlineKeyboardBuilder()
    if not cities:
        builder.row(_btn("❗️ شهری ثبت نشده", "noop"))
    else:
        for i, city in enumerate(cities):
            has = "✅" if city in CITY_ASSETS and get_city_asset_text(city) else "—"
            short = city.rsplit("_", 1)[0] if "_" in city else city
            if short.isascii():
                short = short.replace("_", " ").title()
            builder.row(_btn(f"{has} {short}", f"asset_ci:{side}:{i}"))
    builder.row(_btn("🔙 بازگشت", "menu:assets"))
    await callback.message.answer("📍 انتخاب شهر:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("asset_ci:"))
async def handle_asset_city_idx(callback: types.CallbackQuery):
    """انتخاب شهر با ایندکس — جلوگیری از باگ callback طولانی."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer("نامعتبر", show_alert=True)
    side, idx_s = parts[1], parts[2]
    if side not in FACTIONS:
        return await callback.answer("ساید نامعتبر.", show_alert=True)
    my_side = leader_side(uid) or side_of_user(uid)
    if not is_admin(uid) and my_side != side:
        return await callback.answer("❌ فقط ساید خودتان.", show_alert=True)
    try:
        idx = int(idx_s)
    except ValueError:
        return await callback.answer("نامعتبر", show_alert=True)
    cities = cities_for_side_assets(side)
    if idx < 0 or idx >= len(cities):
        return await callback.answer("شهر پیدا نشد.", show_alert=True)
    city = cities[idx]
    await callback.answer()
    body = format_city_asset_view(city, viewer=callback.from_user.id)
    # متن شیت جدا از دکمه‌ها تا محدودیت تلگرام نخورد
    if len(body) > 3500:
        await send_chunks(callback.message, [body], reply_markup=None)
        await callback.message.answer("⬆️ شیت بالا", reply_markup=get_inline_back_row("menu:assets"))
    else:
        await callback.message.answer(body)
        await callback.message.answer("⬆️ شیت دارایی", reply_markup=get_inline_back_row("menu:assets"))


@dp.callback_query(F.data.startswith("asset_city:"))
async def handle_asset_city(callback: types.CallbackQuery):
    """سازگاری با callbackهای قدیمی."""
    uid = callback.from_user.id
    if not (is_leader(uid) or is_admin(uid)):
        return await callback.answer("❌ دسترسی ندارید.", show_alert=True)
    city = callback.data.split(":", 1)[1]
    side = country_key(city)
    my_side = leader_side(uid) or side_of_user(uid)
    if not is_admin(uid):
        if not side or my_side != side:
            return await callback.answer("❌ فقط شهرهای ساید خودتان.", show_alert=True)
    await callback.answer()
    body = format_city_asset_view(city, viewer=callback.from_user.id)
    if len(body) > 4000:
        await send_chunks(callback.message, [body], reply_markup=get_inline_back_row("menu:assets"))
    else:
        await callback.message.answer(body, reply_markup=get_inline_back_row("menu:assets"))
