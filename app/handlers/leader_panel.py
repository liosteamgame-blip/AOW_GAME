"""🏴 پنل لیدر جناح: خلاصه قدرت شهرهای جناح · پیام به گروه‌های جناح · نظرسنجی.

قانون دید: لیدر فقط شهرهای جناح خودش را می‌بیند (ادمین همه را، با انتخاب جناح).
"""
import asyncio
import logging
import secrets
import time

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DIV
from app.factions import FACTIONS, FACTION_META, cities_for_side_assets, country_key
from app.features import enabled
from app.keyboards import _btn, get_back_keyboard
from app.loader import bot, dp
from app.players import is_admin, leader_side, mention
from app.state import GROUPS, LEADER_POLLS
from app.states import GameStates
from app.storage import save_data
from app.utils import e, fmt_num, is_back_text
from app.economy.views import city_power_scores

MSG_MAX = 1500
POLL_OPT_MAX = 10


def may_lead(uid: int, side: str) -> bool:
    return side in FACTIONS and (is_admin(uid) or leader_side(uid) == side)


def faction_groups(side: str) -> list:
    return [gid for gid, g in GROUPS.items() if country_key(g.get("city") or "") == side]


def _title(side: str) -> str:
    flag, title = FACTION_META.get(side, ("🏴", side))
    return f"{flag} {title}"


def panel_keyboard(side: str):
    b = InlineKeyboardBuilder()
    b.row(_btn("📊 خلاصه قدرت شهرها", f"ldr:sum:{side}", "primary"))
    b.row(
        _btn("📯 پیام به گروه‌های جناح", f"ldr:msg:{side}", "success"),
        _btn("🗳 نظرسنجی", f"ldr:poll:{side}", "success"),
    )
    b.row(_btn("📈 نتایج نظرسنجی‌ها", f"ldr:polls:{side}"))
    return b.as_markup()


def panel_text(side: str) -> str:
    return (
        f"🏴 <b>پنل لیدر — {_title(side)}</b>\n{DIV}\n"
        f"🏙 شهرهای جناح: <b>{fmt_num(len(cities_for_side_assets(side)))}</b>\n"
        f"👥 گروه‌های متصل: <b>{fmt_num(len(faction_groups(side)))}</b>\n\n"
        "سرورم، فرمان خود را انتخاب کنید."
    )


def summary_text(side: str) -> str:
    rows = []
    for city in cities_for_side_assets(side):
        sc = city_power_scores(city)
        bag = sc.get("bag") or {}
        total = sc["econ"] + sc["mil"] + sc["nav"]
        rows.append((total, city, sc, bag))
    rows.sort(key=lambda r: r[0], reverse=True)
    lines = [f"📊 <b>قدرت شهرهای {_title(side)}</b>\n{DIV}"]
    if not rows:
        lines.append("📭 هنوز دارایی برای شهرهای این جناح ثبت نشده.")
        return "\n".join(lines)
    sums = {"econ": 0.0, "mil": 0.0, "nav": 0.0}
    for i, (total, city, sc, bag) in enumerate(rows, 1):
        for k in sums:
            sums[k] += sc[k]
        lines.append(
            f"{i}. <b>{e(city)}</b> — Σ {fmt_num(total)}\n"
            f"   💰 {fmt_num(sc['econ'])} · ⚔️ {fmt_num(sc['mil'])} · ⚓️ {fmt_num(sc['nav'])}\n"
            f"   🪙 سکه {fmt_num(bag.get('سکه') or 0)} · 🍽 غذا {fmt_num(bag.get('غذا') or 0)}"
            f" · 🪖 سرباز {fmt_num(bag.get('سربازان') or 0)}"
        )
    lines.append(
        f"\n{DIV}\nجمع جناح: 💰 {fmt_num(sums['econ'])} · ⚔️ {fmt_num(sums['mil'])} · ⚓️ {fmt_num(sums['nav'])}"
        "\n<i>محرمانه — فقط برای لیدر جناح.</i>"
    )
    return "\n".join(lines)


async def _show(callback: types.CallbackQuery, text: str, markup):
    """پنل همیشه در پی‌وی نمایش داده می‌شود (اطلاعات جناح محرمانه است)."""
    msg = callback.message
    if msg and msg.chat.type == "private":
        try:
            return await msg.edit_text(text, reply_markup=markup)
        except Exception:
            return await msg.answer(text, reply_markup=markup)
    try:
        await bot.send_message(callback.from_user.id, text, reply_markup=markup)
        note = "🏴 پنل جناح در پی‌وی ربات فرستاده شد."
    except Exception:
        note = "❌ اول ربات را در پی‌وی استارت کنید، بعد دوباره بزنید."
    try:
        await callback.answer(note, show_alert=True)
    except Exception:
        pass   # اگر قبلاً پاسخ داده شده بود


@dp.callback_query(F.data.startswith("ldr:"))
async def leader_panel_router(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not enabled("leader_panel"):
        return await callback.answer("🏴 پنل جناح فعلاً خاموش است.", show_alert=True)
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"

    if action == "menu":
        side = leader_side(uid)
        if side:
            if callback.message and callback.message.chat.type == "private":
                await callback.answer()   # در گروه، _show خودش پاپ‌آپ «در پی‌وی فرستاده شد» می‌دهد
            return await _show(callback, panel_text(side), panel_keyboard(side))
        if is_admin(uid):
            await callback.answer()
            b = InlineKeyboardBuilder()
            for s in FACTIONS:
                b.row(_btn(_title(s), f"ldr:side:{s}"))
            b.row(_btn("🔙 پنل", "back_to_admin"))
            return await callback.message.answer("🏴 جناح را انتخاب کنید:", reply_markup=b.as_markup())
        return await callback.answer("❌ شما لیدر جناحی نیستید.", show_alert=True)

    side = parts[2] if len(parts) > 2 else ""
    if action != "pres" and not may_lead(uid, side):
        return await callback.answer("❌ فقط لیدر همین جناح.", show_alert=True)

    if action == "side":
        await callback.answer()
        return await _show(callback, panel_text(side), panel_keyboard(side))

    if action == "sum":
        await callback.answer()
        b = InlineKeyboardBuilder()
        b.row(_btn("🔙 پنل جناح", f"ldr:side:{side}"))
        return await _show(callback, summary_text(side), b.as_markup())

    if action == "msg":
        await callback.answer()
        await state.clear()
        await state.update_data(ldr_side=side)
        await state.set_state(GameStates.ldr_msg)
        return await bot.send_message(
            uid,
            f"📯 <b>پیام به گروه‌های {_title(side)}</b>\n{DIV}\n"
            f"متن پیام را بفرستید (حداکثر {fmt_num(MSG_MAX)} کاراکتر).\n"
            f"به {fmt_num(len(faction_groups(side)))} گروه ارسال می‌شود.",
            reply_markup=get_back_keyboard(),
        )

    if action == "poll":
        await callback.answer()
        await state.clear()
        await state.update_data(ldr_side=side)
        await state.set_state(GameStates.ldr_poll)
        return await bot.send_message(
            uid,
            f"🗳 <b>نظرسنجی برای {_title(side)}</b>\n{DIV}\n"
            "خط اول = سؤال، خطوط بعد = گزینه‌ها (۲ تا ۱۰ گزینه).\nمثال:\n"
            "<code>به کدام شهر حمله کنیم؟\nلندن\nآکسفورد\nفعلاً صبر</code>",
            reply_markup=get_back_keyboard(),
        )

    if action == "send":
        d = await state.get_data()
        text = d.get("ldr_draft")
        if not text or d.get("ldr_side") != side:
            return await callback.answer("پیش‌نویس پیدا نشد؛ دوباره شروع کنید.", show_alert=True)
        await state.clear()   # قبل از await ارسال — دابل‌کلیک دوبار نمی‌فرستد
        await callback.answer("در حال ارسال…")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        body = (
            f"📯 <b>فرمان لیدر جناح {_title(side)}</b>\n{DIV}\n{e(text)}\n\n"
            f"— {mention(uid, callback.from_user.full_name)}"
        )
        ok = fail = 0
        for gid in faction_groups(side):
            try:
                await bot.send_message(gid, body)
                ok += 1
                await asyncio.sleep(0.05)
            except Exception:
                fail += 1
        return await callback.message.answer(
            f"✅ پیام به {fmt_num(ok)} گروه رسید" + (f" · ❌ {fmt_num(fail)} ناموفق" if fail else "") + ".",
            reply_markup=panel_keyboard(side),
        )

    if action == "psend":
        d = await state.get_data()
        q, opts = d.get("ldr_poll_q"), d.get("ldr_poll_opts") or []
        if not q or len(opts) < 2 or d.get("ldr_side") != side:
            return await callback.answer("پیش‌نویس پیدا نشد؛ دوباره شروع کنید.", show_alert=True)
        await state.clear()
        await callback.answer("در حال ارسال…")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        key = secrets.token_hex(3)
        rec = {"side": side, "leader": uid, "question": q, "options": opts,
               "poll_ids": [], "votes": {}, "ts": time.time()}
        fail = 0
        for gid in faction_groups(side):
            try:
                sent = await bot.send_poll(gid, question=q[:300], options=[o[:100] for o in opts], is_anonymous=False)
                if sent and getattr(sent, "poll", None):
                    rec["poll_ids"].append(sent.poll.id)
                else:
                    rec["poll_ids"].append(f"{gid}:{getattr(sent, 'message_id', 0)}")
                await asyncio.sleep(0.05)
            except Exception:
                logging.exception("ارسال نظرسنجی لیدر به %s", gid)
                fail += 1
        LEADER_POLLS[key] = rec
        save_data()
        b = InlineKeyboardBuilder()
        b.row(_btn("📈 نتیجه", f"ldr:pres:{side}:{key}"))
        b.row(_btn("🔙 پنل جناح", f"ldr:side:{side}"))
        return await callback.message.answer(
            f"🗳 نظرسنجی به {fmt_num(len(rec['poll_ids']))} گروه فرستاده شد"
            + (f" · ❌ {fmt_num(fail)} ناموفق" if fail else "") + ".",
            reply_markup=b.as_markup(),
        )

    if action == "polls":
        await callback.answer()
        mine = [(k, v) for k, v in LEADER_POLLS.items() if v.get("side") == side]
        b = InlineKeyboardBuilder()
        for k, v in mine[-8:]:
            b.row(_btn(f"📈 {v.get('question', '')[:40]}", f"ldr:pres:{side}:{k}"))
        b.row(_btn("🔙 پنل جناح", f"ldr:side:{side}"))
        text = "🗳 <b>نظرسنجی‌های جناح</b>" if mine else "🗳 هنوز نظرسنجی‌ای فرستاده نشده."
        return await _show(callback, text, b.as_markup())

    if action == "pres":
        key = parts[3] if len(parts) > 3 else ""
        rec = LEADER_POLLS.get(key)
        if not rec or not may_lead(uid, rec.get("side") or ""):
            return await callback.answer("❌ نظرسنجی پیدا نشد یا مال جناح شما نیست.", show_alert=True)
        await callback.answer()
        return await _show(callback, poll_result_text(rec), panel_keyboard(rec["side"]))

    await callback.answer()


def poll_result_text(rec: dict) -> str:
    opts = rec.get("options") or []
    counts = [0] * len(opts)
    for choices in (rec.get("votes") or {}).values():
        for i in choices or []:
            if 0 <= int(i) < len(counts):
                counts[int(i)] += 1
    total = sum(counts)
    lines = [f"📈 <b>نتیجه نظرسنجی</b>\n{DIV}\n❓ {e(rec.get('question'))}\n"]
    for opt, c in zip(opts, counts):
        pct = (c * 100 / total) if total else 0
        bar = "█" * int(round(pct / 10)) + "░" * (10 - int(round(pct / 10)))
        lines.append(f"{bar} {fmt_num(pct, decimals=0)}% · {e(opt)} ({fmt_num(c)})")
    lines.append(f"\n👥 مجموع رأی‌ها: <b>{fmt_num(total)}</b> (از همه گروه‌های جناح)")
    return "\n".join(lines)


@dp.message(GameStates.ldr_msg)
async def leader_msg_draft(message: types.Message, state: FSMContext):
    d = await state.get_data()
    side = d.get("ldr_side") or ""
    if is_back_text(message.text or "") or not may_lead(message.from_user.id, side):
        await state.clear()
        return await message.answer("❌ لغو شد.", reply_markup=panel_keyboard(side) if side in FACTIONS else None)
    text = (message.text or "").strip()
    if not text:
        return await message.answer("❌ فقط متن بفرستید.")
    if len(text) > MSG_MAX:
        return await message.answer(f"❌ متن طولانی است (حداکثر {fmt_num(MSG_MAX)} کاراکتر).")
    await state.update_data(ldr_draft=text)
    b = InlineKeyboardBuilder()
    b.row(_btn("✅ ارسال", f"ldr:send:{side}", "success"), _btn("❌ انصراف", f"ldr:side:{side}", "danger"))
    await message.answer(
        f"👁 <b>پیش‌نمایش</b> — به {fmt_num(len(faction_groups(side)))} گروه {_title(side)}\n{DIV}\n{e(text)}",
        reply_markup=b.as_markup(),
    )


@dp.message(GameStates.ldr_poll)
async def leader_poll_draft(message: types.Message, state: FSMContext):
    d = await state.get_data()
    side = d.get("ldr_side") or ""
    if is_back_text(message.text or "") or not may_lead(message.from_user.id, side):
        await state.clear()
        return await message.answer("❌ لغو شد.", reply_markup=panel_keyboard(side) if side in FACTIONS else None)
    lines = [ln.strip() for ln in (message.text or "").splitlines() if ln.strip()]
    if len(lines) < 3 or len(lines) - 1 > POLL_OPT_MAX:
        return await message.answer("❌ خط اول سؤال و بعد ۲ تا ۱۰ گزینه، هر کدام در یک خط.")
    q, opts = lines[0], lines[1:]
    await state.update_data(ldr_poll_q=q, ldr_poll_opts=opts)
    b = InlineKeyboardBuilder()
    b.row(_btn("✅ ارسال نظرسنجی", f"ldr:psend:{side}", "success"), _btn("❌ انصراف", f"ldr:side:{side}", "danger"))
    await message.answer(
        f"👁 <b>پیش‌نمایش نظرسنجی</b> — {_title(side)}\n{DIV}\n❓ {e(q)}\n"
        + "\n".join(f"▫️ {e(o)}" for o in opts),
        reply_markup=b.as_markup(),
    )


@dp.poll_answer()
async def leader_poll_vote(poll_answer: types.PollAnswer):
    """رأی‌ها برای جمع‌بندی همه گروه‌های جناح ثبت می‌شوند."""
    voter = poll_answer.user.id if poll_answer.user else None
    if voter is None:
        return
    for rec in LEADER_POLLS.values():
        if poll_answer.poll_id in (rec.get("poll_ids") or []):
            votes = rec.setdefault("votes", {})
            if poll_answer.option_ids:
                votes[str(voter)] = list(poll_answer.option_ids)
            else:
                votes.pop(str(voter), None)   # رأی پس گرفته شد
            save_data()
            return
