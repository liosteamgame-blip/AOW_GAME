"""🌍 رویدادهای جهانی: قالب → دامنه → درصد و تعداد آپ → پیش‌نمایش → تایید (+ اعلام اختیاری در کانال)."""
import logging

from aiogram import F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.audit import record
from app.chronicle import record_event
from app.config import CHANNEL_ID, DIV
from app.events import (
    EVENT_TEMPLATES,
    MAX_UPS,
    active_events,
    end_event,
    public_text,
    scope_cities,
    scope_title,
    start_event,
    ups_left,
)
from app.factions import FACTIONS
from app.features import enabled
from app.keyboards import _btn
from app.loader import bot, dp
from app.permissions import can
from app.storage import save_data
from app.utils import e, fmt_num


def _menu():
    b = InlineKeyboardBuilder()
    for key, (title, kind, target, pct, ups, _t) in EVENT_TEMPLATES.items():
        sign = "+" if kind == "buff" else "−"
        b.row(_btn(f"{title} ({target} {sign}{fmt_num(pct)}٪)", f"ev:t:{key}"))
    b.row(_btn("📋 رویدادهای فعال", "ev:list"))
    b.row(_btn("🔙 پنل", "back_to_admin"))
    return b.as_markup()


def _draft_view(d: dict):
    title, kind, target, _p, _u, _t = EVENT_TEMPLATES[d["tpl"]]
    sign = "+" if kind == "buff" else "−"
    n = len(scope_cities(d["scope"]))
    text = (
        f"🌍 <b>پیش‌نمایش رویداد</b>\n{DIV}\n"
        f"{title}\n"
        f"🎯 اثر: <b>{'باف' if kind == 'buff' else 'نرف'} {e(target)} {sign}{fmt_num(d['pct'])}٪</b> روی بازدهی آپ\n"
        f"🗺 دامنه: <b>{scope_title(d['scope'])}</b> ({fmt_num(n)} شهر)\n"
        f"⏳ مدت: <b>{fmt_num(d['ups'])}</b> آپ (بعد خودکار حذف می‌شود)\n"
        f"📣 اعلام در کانال: <b>{'بله' if d['ann'] else 'خیر'}</b>\n\n"
        "<i>با تایید، روی CITY_BUFFS همان شهرها ثبت می‌شود و در آپ‌های بعدی اعمال می‌شود.</i>"
    )
    b = InlineKeyboardBuilder()
    scopes = ["all"] + list(FACTIONS)
    b.row(*[_btn(("✅ " if d["scope"] == s else "") + scope_title(s).split(" ", 1)[0], f"ev:s:{s}") for s in scopes])
    b.row(_btn("−۱۰٪", "ev:p:-10"), _btn("−۵٪", "ev:p:-5"), _btn("+۵٪", "ev:p:5"), _btn("+۱۰٪", "ev:p:10"))
    b.row(*[_btn(("✅ " if d["ups"] == n_ else "") + f"{fmt_num(n_)} آپ", f"ev:u:{n_}") for n_ in range(1, MAX_UPS + 1)])
    b.row(_btn(f"📣 اعلام در کانال: {'روشن' if d['ann'] else 'خاموش'}", "ev:ann"))
    b.row(_btn("✅ تایید و شروع رویداد", "ev:ok", "success"), _btn("❌ انصراف", "ev:menu", "danger"))
    return text, b.as_markup()


async def _edit(callback: types.CallbackQuery, text: str, markup):
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)


@dp.callback_query(F.data.startswith("ev:"))
async def world_events_cb(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    if not can(uid, "events.run"):
        return await callback.answer("⛔️ فقط ادمین یا راوی.", show_alert=True)
    if not enabled("world_events"):
        return await callback.answer("🌍 رویدادهای جهانی فعلاً خاموش است.", show_alert=True)
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"

    if action == "menu":
        await callback.answer()
        await state.update_data(ev_draft=None)
        return await _edit(callback, f"🌍 <b>رویداد جهانی</b>\n{DIV}\nقالب را انتخاب کنید:", _menu())

    if action == "list":
        await callback.answer()
        evs = active_events()
        b = InlineKeyboardBuilder()
        lines = [f"📋 <b>رویدادهای فعال</b>\n{DIV}"]
        for eid, ev in evs:
            lines.append(f"• {ev['title']} — {scope_title(ev['scope'])} · {fmt_num(ups_left(eid))} آپ مانده")
            b.row(_btn(f"🗑 پایان {ev['title']}", f"ev:end:{eid}", "danger"))
        if not evs:
            lines.append("رویداد فعالی نیست.")
        b.row(_btn("🔙 رویدادها", "ev:menu"))
        return await _edit(callback, "\n".join(lines), b.as_markup())

    if action == "end" and len(parts) > 2:
        ok = end_event(parts[2])
        if ok:
            record("پایان دستی رویداد جهانی", "", parts[2], admin_only=False)
            save_data(critical=True)
        await callback.answer("رویداد پایان یافت" if ok else "پیدا نشد", show_alert=not ok)
        return await _edit(callback, f"🌍 <b>رویداد جهانی</b>\n{DIV}\nقالب را انتخاب کنید:", _menu())

    d = (await state.get_data()).get("ev_draft") or None
    if action == "t" and len(parts) > 2 and parts[2] in EVENT_TEMPLATES:
        _title, _k, _tg, pct, ups, _t = EVENT_TEMPLATES[parts[2]]
        d = {"tpl": parts[2], "scope": "all", "pct": float(pct), "ups": int(ups), "ann": True}
    elif not d:
        return await callback.answer("پیش‌نویس پیدا نشد؛ دوباره قالب را انتخاب کنید.", show_alert=True)
    elif action == "s" and len(parts) > 2 and (parts[2] == "all" or parts[2] in FACTIONS):
        d["scope"] = parts[2]
    elif action == "p" and len(parts) > 2:
        d["pct"] = max(5.0, min(100.0, float(d["pct"]) + float(parts[2])))
    elif action == "u" and len(parts) > 2:
        d["ups"] = max(1, min(MAX_UPS, int(parts[2])))
    elif action == "ann":
        d["ann"] = not d["ann"]
    elif action == "ok":
        await state.update_data(ev_draft=None)   # قبل از await — دابل‌کلیک دوبار ثبت نمی‌کند
        ev = start_event(d["tpl"], d["scope"], d["pct"], d["ups"], by=uid)
        record("شروع رویداد جهانی", "", f"{ev['title']} · {scope_title(ev['scope'])} · {fmt_num(ev['pct'])}٪ · {ev['ups']} آپ",
               admin_only=False)
        save_data(critical=True)
        await callback.answer("رویداد شروع شد")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        if d.get("ann") and CHANNEL_ID:
            try:
                await bot.send_message(CHANNEL_ID, f"🌍 <b>رویداد جهانی</b>\n{DIV}\n{public_text(ev)}\n#رویداد")
                record_event("event", city="", via=ev["title"])
            except Exception:
                logging.exception("اعلام رویداد جهانی در کانال")
        return await callback.message.answer(
            f"✅ {ev['title']} روی {fmt_num(len(ev['cities']))} شهر ثبت شد و تا {fmt_num(ev['ups'])} آپ اعمال می‌شود."
        )
    else:
        return await callback.answer()
    await state.update_data(ev_draft=d)
    await callback.answer()
    text, kb = _draft_view(d)
    return await _edit(callback, text, kb)
