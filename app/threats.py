"""هشدار تهدید به شهر هدف."""
import asyncio
import logging

from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import ADMIN_ID, DIV
from app.loader import bot
from app.utils import e
from app.factions import match_registered_cities
from app.players import groups_of_city, mention, players_of_city
from app.keyboards import _btn


def _threat_title(kind: str) -> str:
    return {
        "campaign": "🚨 هشدار لشکرکشی به سوی شما",
        "siege": "🚨 هشدار محاصره",
        "war": "🚨 هشدار اعلان جنگ",
    }.get(kind, "🚨 هشدار نظامی")


async def notify_target_threat(
    kind: str,
    attacker_id: int,
    attacker_city: str,
    target_raw: str,
    origin: str = "",
    extra: str = "",
    action_id: str = "",
):
    """
    پس از ثبت لشکرکشی/محاصره/جنگ، به فرمانده و گروه شهر هدف هشدار می‌دهد.
    """
    matched = match_registered_cities(target_raw)
    if not matched:
        logging.info("threat: no city match for %r", target_raw)
        return
    title = _threat_title(kind)
    who = mention(attacker_id, attacker_city or "فرمانده")
    notified_uids, notified_gids = set(), set()
    for city in matched:
        body = (
            f"{title}\n{DIV}\n"
            f"🏙 شهر هدف: <b>{e(city)}</b>\n"
            f"📝 مقصد ثبت‌شده: <code>{e(target_raw)}</code>\n"
            f"👑 مهاجم: {who}\n"
            f"📍 مبدأ: <b>{e(origin or attacker_city or '—')}</b>\n"
        )
        if extra:
            body += f"{extra}\n"
        body += (
            f"\n⚠️ آماده دفاع شوید. آمار مهاجم در کانال اصلی اعلام شده است."
            + (f"\n🆔 اکشن: <code>{action_id}</code>" if action_id else "")
        )
        builder = InlineKeyboardBuilder()
        builder.row(_btn("✅ دریافت شد", f"alert_ack:{action_id or 'x'}", "success"))
        builder.row(_btn("📦 دارایی شهر", "menu:assets", "primary"))
        markup = builder.as_markup()

        for uid in players_of_city(city):
            if uid == attacker_id or uid in notified_uids:
                continue
            notified_uids.add(uid)
            try:
                await bot.send_message(chat_id=uid, text=body, reply_markup=markup)
                await asyncio.sleep(0.04)
            except Exception:
                logging.exception("threat dm to %s failed", uid)

        for gid in groups_of_city(city):
            if gid in notified_gids:
                continue
            notified_gids.add(gid)
            try:
                await bot.send_message(chat_id=gid, text=body, reply_markup=markup)
                await asyncio.sleep(0.05)
            except Exception:
                logging.exception("threat group %s failed", gid)

    if notified_uids or notified_gids:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 هشدار تهدید ارسال شد.\n"
                f"🎯 {e(target_raw)} → {', '.join(e(c) for c in matched)}\n"
                f"👤 DM: {len(notified_uids)} · 👥 گروه: {len(notified_gids)}",
                disable_notification=True,
            )
        except Exception:
            pass
