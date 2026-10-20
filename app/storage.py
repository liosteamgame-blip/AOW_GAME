"""ذخیره محلی + پشتیبان پین‌شده در تلگرام + بازیابی."""
import asyncio
import io
import json
import logging
import os
from datetime import datetime

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InputMediaDocument

from app import state as app_state
from app.config import ADMIN_ID, BACKUP_CHAT_ID, BACKUP_NAME, DATA_FILE, DIV, MAX_LEADERS, TZ
from app.loader import bot
from app.state import (
    AI_CACHE,
    AUDIT_LOG,
    AUTO_CITIES,
    CITY_ASSETS,
    CHRONICLE,
    CHRONICLE_MAX,
    CITY_BUFFS,
    CITY_RANKS,
    DEFAULT_MERCHANT_LIMITS,
    EXTRA_ROLES,
    GROUPS,
    LAST_ORDERS,
    LEADERS,
    LEADER_POLLS,
    MERCHANT_LIMITS,
    MERCHANT_PRICES,
    PENDING_APPROVALS,
    PENDING_TRADES,
    PLAYER_CODES,
    SETTINGS,
    UP_HISTORY_MAX,
    UP_SNAPSHOTS,
    WORLD_EVENTS,
    _backup_flags,
    active_actions,
    all_players,
    authenticated_users,
    backup_state,
    spawn,
)
from app.utils import e, fmt_num
from app.features import restore_features
from app.players import rebuild_player_links


def snapshot():
    recent = sorted(active_actions.items(), key=lambda kv: kv[1].get("time_created", 0), reverse=True)[:300]
    return {
        "codes": PLAYER_CODES,
        "users": {str(uid): u for uid, u in authenticated_users.items() if u.get("role") in ("player", "admin")},
        "actions": dict(recent),
        "groups": {str(cid): g for cid, g in GROUPS.items()},
        "settings": dict(SETTINGS),
        "asset_admin_id": app_state.ASSET_ADMIN_ID,
        "merchant_limits": dict(MERCHANT_LIMITS),
        "merchant_buff_default": app_state.MERCHANT_BUFF_DEFAULT,
        "merchant_list_text": app_state.MERCHANT_LIST_TEXT,
        "merchant_buy_price": app_state.MERCHANT_BUY_PRICE,
        "merchant_sell_price": app_state.MERCHANT_SELL_PRICE,
        "merchant_prices": {k: dict(v) for k, v in MERCHANT_PRICES.items()},
        "merchant_enabled": bool(app_state.MERCHANT_ENABLED),
        "leaders": {k: list(v) for k, v in LEADERS.items()},
        "city_assets": {k: dict(v) for k, v in CITY_ASSETS.items()},
        "auto_cities": {str(k): bool(v) for k, v in AUTO_CITIES.items()},
        "pending_trades": {str(k): dict(v) for k, v in list(PENDING_TRADES.items())[-80:]},
        "up_snapshots": {str(k): v for k, v in UP_SNAPSHOTS.items() if isinstance(v, dict)},
        "city_buffs": {
            str(c): [dict(x) for x in (lst or [])]
            for c, lst in CITY_BUFFS.items()
        },
        "extra_roles": {str(uid): list(r) for uid, r in EXTRA_ROLES.items() if r},
        "audit_log": list(AUDIT_LOG),
        "pending_approvals": {
            k: dict(v) for k, v in list(PENDING_APPROVALS.items())[-50:]
        },
        "leader_polls": {k: dict(v) for k, v in list(LEADER_POLLS.items())[-30:]},
        "chronicle": list(CHRONICLE[-CHRONICLE_MAX:]),
        "city_ranks": {k: dict(v) for k, v in CITY_RANKS.items()},
        "last_orders": {k: dict(v) for k, v in LAST_ORDERS.items()},
        "ai_cache": {k: dict(v) for k, v in list(AI_CACHE.items())[-30:]},
        "world_events": {k: dict(v) for k, v in list(WORLD_EVENTS.items())[-50:]},
    }


def apply_data(raw):
    codes = {str(k).upper(): str(v) for k, v in (raw.get("codes") or {}).items()}
    users = {}
    for k, u in (raw.get("users") or {}).items():
        try:
            uid = int(k)
        except ValueError:
            continue
        if not isinstance(u, dict):
            continue
        if u.get("role") == "admin":
            users[uid] = u
        elif u.get("role") == "player" and u.get("code") in codes:   # کاربری که کدش باطل شده حذف می‌شود
            users[uid] = u
    actions = {str(k): v for k, v in (raw.get("actions") or {}).items() if isinstance(v, dict) and "owner_id" in v}
    groups = {}
    for k, g in (raw.get("groups") or {}).items():
        try:
            cid = int(k)
        except ValueError:
            continue
        if isinstance(g, dict) and g.get("city"):
            groups[cid] = g

    PLAYER_CODES.clear()
    PLAYER_CODES.update(codes)
    authenticated_users.clear()
    authenticated_users.update(users)
    active_actions.clear()
    active_actions.update(actions)
    all_players.clear()
    all_players.update(uid for uid, u in users.items() if u.get("role") == "player")
    GROUPS.clear()
    GROUPS.update(groups)

    # تنظیمات و داده‌های تکمیلی
    st = raw.get("settings") or {}
    if isinstance(st, dict):
        for k in (
            "time_start", "time_stop", "days_start", "days_stop",
            "msg_start", "msg_stop", "allowed",
            "photo_start", "photo_stop", "photo_menu",
            "lb_intro_all", "lb_intro_econ", "lb_intro_mil", "lb_intro_nav",
            "lb_place_1", "lb_place_2", "lb_place_3", "lb_place_mid", "lb_place_low", "lb_footer",
            "lb_ranks", "lb_max",
            "guide_commander", "guide_leader",
        ):
            if st.get(k) is not None:
                SETTINGS[k] = str(st[k])
    # کلیدهای فیچر (dict) و تنظیمات تکمیلی — بکاپ قدیمی بدون آن‌ها هم پیش‌فرض می‌گیرد
    restore_features(st if isinstance(st, dict) else {})
    _apply_stage1_data(raw)
    AUTO_CITIES.clear()
    ac = raw.get("auto_cities") or {}
    if isinstance(ac, dict):
        for ck, cv in ac.items():
            if cv:
                AUTO_CITIES[str(ck)] = True
    
    UP_SNAPSHOTS.clear()
    for ck, sv in (raw.get("up_snapshots") or {}).items():
        if not isinstance(sv, dict):
            continue
        if ck == "__meta__" or "latest" in sv or "history" in sv:
            if isinstance(sv.get("history"), list):
                sv["history"] = sv["history"][:UP_HISTORY_MAX]   # بکاپ‌های قدیمی با ۵ نسخه هم کوتاه می‌شوند
            UP_SNAPSHOTS[str(ck)] = sv
        else:
            UP_SNAPSHOTS[str(ck)] = {
                "latest": {
                    "text": sv.get("text") or "",
                    "stats": dict(sv.get("stats") or {}),
                    "levels": dict(sv.get("levels") or {}),
                    "yields": dict(sv.get("yields") or {}),
                    "unlocked": list(sv.get("unlocked") or []),
                    "shop": dict(sv.get("shop") or {}),
                    "shop_packs": list(sv.get("shop_packs") or []),
                    "changes": list(sv.get("changes") or []),
                    "ts": sv.get("ts") or "",
                },
                "history": [],
                "ts": sv.get("ts") or "",
            }

    PENDING_TRADES.clear()
    pt = raw.get("pending_trades") or {}
    if isinstance(pt, dict):
        for tid, tv in pt.items():
            if isinstance(tv, dict):
                PENDING_TRADES[str(tid)] = tv
    CITY_BUFFS.clear()
    cb = raw.get("city_buffs") or {}
    if isinstance(cb, dict):
        for cname, lst in cb.items():
            if isinstance(lst, list):
                CITY_BUFFS[str(cname)] = [dict(x) for x in lst if isinstance(x, dict)]
    try:
        app_state.ASSET_ADMIN_ID = int(raw["asset_admin_id"]) if raw.get("asset_admin_id") else None
    except (TypeError, ValueError):
        app_state.ASSET_ADMIN_ID = None
    ml = raw.get("merchant_limits") or {}
    MERCHANT_LIMITS.clear()
    if isinstance(ml, dict) and ml:
        for name, lim in ml.items():
            try:
                MERCHANT_LIMITS[str(name).strip()] = float(lim)
            except (TypeError, ValueError):
                continue
    if not MERCHANT_LIMITS:
        MERCHANT_LIMITS.update(DEFAULT_MERCHANT_LIMITS)
    try:
        app_state.MERCHANT_BUFF_DEFAULT = float(raw.get("merchant_buff_default") or 0)
    except (TypeError, ValueError):
        app_state.MERCHANT_BUFF_DEFAULT = 0
    if raw.get("merchant_list_text"):
        app_state.MERCHANT_LIST_TEXT = str(raw["merchant_list_text"])
    try:
        app_state.MERCHANT_BUY_PRICE = float(raw.get("merchant_buy_price", app_state.MERCHANT_BUY_PRICE))
    except (TypeError, ValueError):
        pass
    try:
        app_state.MERCHANT_SELL_PRICE = float(raw.get("merchant_sell_price", app_state.MERCHANT_SELL_PRICE))
    except (TypeError, ValueError):
        pass
    MERCHANT_PRICES.clear()
    for name, pr in (raw.get("merchant_prices") or {}).items():
        if not isinstance(pr, dict):
            continue
        try:
            MERCHANT_PRICES[str(name).strip()] = {
                "buy": float(pr.get("buy", app_state.MERCHANT_BUY_PRICE)),
                "sell": float(pr.get("sell", app_state.MERCHANT_SELL_PRICE)),
            }
        except (TypeError, ValueError):
            continue
    app_state.MERCHANT_ENABLED = bool(raw.get("merchant_enabled", True))
    try:
        rebuild_player_links()
    except Exception:
        logging.exception("rebuild_player_links")
    LEADERS.clear()
    LEADERS.update({
        "monarchist": [],
        "parliamentarian": [],
        "france": [],
        "ireland": [],
    })
    raw_leaders = dict(raw.get("leaders") or {})
    # مهاجرت: england قدیمی → monarchist
    if "england" in raw_leaders and "monarchist" not in raw_leaders:
        raw_leaders["monarchist"] = raw_leaders.pop("england")
    for side, ids in raw_leaders.items():
        key = str(side).lower()
        if key not in LEADERS:
            continue
        cleaned = []
        for x in (ids or []):
            try:
                cleaned.append(int(x))
            except (TypeError, ValueError):
                continue
        LEADERS[key] = cleaned[:MAX_LEADERS]
    CITY_ASSETS.clear()
    for city, items in (raw.get("city_assets") or {}).items():
        if not isinstance(items, dict):
            continue
        # فرمت جدید: {text, stats}
        if "text" in items or "stats" in items:
            text = str(items.get("text") or "")
            stats = {}
            for n, v in (items.get("stats") or {}).items():
                try:
                    stats[str(n).strip()] = float(v)
                except (TypeError, ValueError):
                    continue
            if text or stats:
                # بقیه فیلدها (levels, yields, unlocked, shop, changes, trade_cap_used, …) هم حفظ می‌شوند
                entry = {k: v for k, v in items.items() if k not in ("text", "stats")}
                entry["text"] = text
                entry["stats"] = stats
                CITY_ASSETS[str(city)] = entry
            continue
        # فرمت قدیمی: فقط اعداد
        bag = {}
        for n, v in items.items():
            try:
                bag[str(n).strip()] = float(v)
            except (TypeError, ValueError):
                continue
        if bag:
            CITY_ASSETS[str(city)] = {
                "text": "\n".join(f"{k}: {int(v) if float(v)==int(v) else v}" for k, v in bag.items()),
                "stats": bag,
            }
    purged = app_state.purge_junk_asset_keys()
    if purged:
        logging.warning("کلیدهای زباله‌ی دارایی پاک شد: %s", purged)


def _apply_stage1_data(raw):
    """نقش‌های اضافه، لاگ ممیزی، تاییدهای معلق و نظرسنجی‌های لیدر."""
    EXTRA_ROLES.clear()
    for k, roles in (raw.get("extra_roles") or {}).items():
        try:
            uid = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(roles, list):
            clean = [str(r) for r in roles if r]
            if clean:
                EXTRA_ROLES[uid] = clean
    AUDIT_LOG.clear()
    AUDIT_LOG.extend(x for x in (raw.get("audit_log") or []) if isinstance(x, dict) and x.get("id"))
    PENDING_APPROVALS.clear()
    for k, v in (raw.get("pending_approvals") or {}).items():
        if isinstance(v, dict):
            PENDING_APPROVALS[str(k)] = v
    LEADER_POLLS.clear()
    for k, v in (raw.get("leader_polls") or {}).items():
        if isinstance(v, dict):
            LEADER_POLLS[str(k)] = v
    # مرحله ۲
    CHRONICLE.clear()
    CHRONICLE.extend(x for x in (raw.get("chronicle") or []) if isinstance(x, dict))
    del CHRONICLE[:-CHRONICLE_MAX]
    for target, key in ((CITY_RANKS, "city_ranks"), (LAST_ORDERS, "last_orders"), (AI_CACHE, "ai_cache"),
                        (WORLD_EVENTS, "world_events")):
        target.clear()
        for k, v in (raw.get(key) or {}).items():
            if isinstance(v, dict):
                target[str(k)] = v


def read_local():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        logging.exception("خواندن فایل داده ناموفق بود.")
        return None


def write_local():
    try:
        folder = os.path.dirname(DATA_FILE)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        # بدون indent = سریع‌تر و فایل کوچک‌تر
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot(), f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, DATA_FILE)
    except Exception:
        logging.exception("ذخیره‌ی فایل داده ناموفق بود.")


def has_data():
    return bool(PLAYER_CODES or authenticated_users or active_actions or GROUPS)


def backup_chat():
    return BACKUP_CHAT_ID or ADMIN_ID


def _mid_file():
    """فایل کوچک برای نگه داشتن message_id پشتیبان بین ری‌استارت‌های کوتاه."""
    return DATA_FILE + ".mid"


def _save_mid(mid):
    try:
        with open(_mid_file(), "w", encoding="utf-8") as f:
            f.write(str(int(mid)))
    except Exception:
        pass


def _load_mid():
    try:
        with open(_mid_file(), encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


async def find_backup_message():
    """
    ترتیب جستجو:
    1) پیام پین‌شده با نام aof_data.json
    2) message_id ذخیره‌شده — با forward سند را می‌گیریم (کپی موقت)
    """
    chat_id = backup_chat()
    # 1) پین
    try:
        chat = await bot.get_chat(chat_id)
        pm = getattr(chat, "pinned_message", None)
        if pm and getattr(pm, "document", None):
            fname = (pm.document.file_name or "").lower()
            if fname == BACKUP_NAME.lower() or fname.endswith(".json"):
                return pm
            logging.warning("پین هست ولی نام فایل %s است (انتظار: %s)",
                            pm.document.file_name, BACKUP_NAME)
    except Exception:
        logging.exception("خواندن پین پشتیبان از چت %s ناموفق بود.", chat_id)

    # 2) mid محلی — فوروارد موقت برای دسترسی به document
    mid = backup_state.get("mid") or _load_mid()
    if mid:
        try:
            fwd = await bot.forward_message(
                chat_id=chat_id, from_chat_id=chat_id, message_id=mid, disable_notification=True,
            )
            if fwd and getattr(fwd, "document", None):
                backup_state["mid"] = mid
                # علامت می‌زنیم که این پیام موقت است تا بعد از دانلود پاک شود
                try:
                    fwd._aof_temp_fwd = True  # noqa: SLF001
                except Exception:
                    pass
                return fwd
        except Exception:
            logging.warning("forward mid=%s برای بازیابی ناموفق بود", mid)
            backup_state["mid"] = mid
    return None


async def _download_backup_doc(document) -> dict:
    buf = io.BytesIO()
    await bot.download(document, destination=buf)
    return json.loads(buf.getvalue().decode("utf-8"))


_backup_lock = asyncio.Lock()


async def push_backup():
    """داده‌ها را به‌صورت فایل داخل تلگرام (پیام پین‌شده) نگه می‌دارد تا با Deploy مجدد از بین نرود."""
    # قفل: دو آپلود هم‌زمان (worker + critical) دو پیام پشتیبان جدا نسازند
    async with _backup_lock:
        await _push_backup_impl()


async def _push_backup_impl():
    chat = backup_chat()
    payload = json.dumps(snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    caption = (
        f"🗄 پشتیبان داده‌های ربات — این پیام را <b>حذف/آن‌پین نکنید</b>\n"
        f"🏙 شهر: {len(PLAYER_CODES)} | 👤 فرمانده: {len(all_players)} | 👥 گروه: {len(GROUPS)}\n"
        f"🕒 {datetime.now(TZ).strftime('%Y-%m-%d %H:%M') if TZ else datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    mid = backup_state.get("mid") or _load_mid()
    if mid:
        try:
            doc = BufferedInputFile(payload, filename=BACKUP_NAME)
            await bot.edit_message_media(
                media=InputMediaDocument(media=doc, caption=caption),
                chat_id=chat, message_id=mid,
            )
            backup_state["mid"] = mid
            _save_mid(mid)
            return
        except TelegramBadRequest as ex:
            if "not modified" in str(ex).lower():
                return
            logging.warning("ویرایش پیام پشتیبان ناموفق بود؛ پیام جدید ساخته می‌شود: %s", ex)
            backup_state["mid"] = None
        except Exception as ex:
            logging.warning("ویرایش پشتیبان ناموفق: %s", ex)
            backup_state["mid"] = None

    doc = BufferedInputFile(payload, filename=BACKUP_NAME)
    sent = await bot.send_document(chat_id=chat, document=doc, caption=caption, disable_notification=True)
    backup_state["mid"] = sent.message_id
    _save_mid(sent.message_id)
    try:
        await bot.pin_chat_message(chat_id=chat, message_id=sent.message_id, disable_notification=True)
    except Exception:
        logging.exception(
            "پین کردن پیام پشتیبان ناموفق بود. mid=%s — پیام را دستی در پی‌وی ربات پین کنید!",
            sent.message_id,
        )
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "⚠️ <b>پین پشتیبان ناموفق بود</b>\n"
                    "لطفاً در پی‌وی ربات، آخرین فایل <code>aof_data.json</code> را "
                    "<b>پین</b> کنید تا بعد از ری‌استارت داده از بین نرود."
                ),
                disable_notification=True,
            )
        except Exception:
            pass


async def _backup_worker():
    try:
        await asyncio.sleep(1.5)
        while _backup_flags["dirty"]:
            _backup_flags["dirty"] = False
            try:
                await push_backup()
            except Exception:
                logging.exception("پشتیبان‌گیری در تلگرام ناموفق بود.")
            if _backup_flags["dirty"]:
                await asyncio.sleep(2)
    finally:
        _backup_flags["running"] = False


def save_data(critical=False):
    """
    ذخیره محلی فوری + پشتیبان تلگرام در پس‌زمینه.
    critical=True → آپلود تلگرام را فوری هم صف می‌کند (برای ست پلیر/گپ).
    """
    try:
        write_local()
    except Exception:
        logging.exception("write_local در save_data ناموفق بود.")
    _backup_flags["dirty"] = True
    if not _backup_flags["running"]:
        try:
            _backup_flags["running"] = True
            spawn(_backup_worker())
        except RuntimeError:
            _backup_flags["running"] = False
    if critical:
        # تلاش فوری اضافه (بدون بلاک کردن event loop طولانی)
        try:
            spawn(push_backup())
        except RuntimeError:
            pass


async def load_backup_document(document) -> tuple:
    """فقط دانلود و اعتبارسنجی — چیزی اعمال نمی‌شود. برمی‌گرداند (raw | None, err)."""
    try:
        fname = (document.file_name or "").lower()
        if not (fname.endswith(".json") or fname == BACKUP_NAME.lower()):
            return None, "فایل باید json باشد (aof_data.json)."
        raw = await _download_backup_doc(document)
        if not isinstance(raw, dict) or not isinstance(raw.get("codes"), dict):
            return None, "محتوای فایل نامعتبر است (کلید codes ندارد)."
        return raw, ""
    except Exception as ex:
        logging.exception("load_backup_document")
        return None, f"❌ خطا در خواندن فایل: <code>{e(str(ex)[:200])}</code>"


def restore_preview_text(raw: dict) -> str:
    """مقایسه‌ی داده‌ی فعلی با فایل، برای تایید قبل از بازیابی."""
    def n(key):
        v = raw.get(key)
        return len(v) if isinstance(v, (dict, list)) else 0

    f_players = sum(1 for u in (raw.get("users") or {}).values() if isinstance(u, dict) and u.get("role") == "player")
    rows = [
        ("🏙 شهر", len(PLAYER_CODES), n("codes")),
        ("👤 فرمانده", len(all_players), f_players),
        ("👥 گروه", len(GROUPS), n("groups")),
        ("📦 دارایی شهر", len(CITY_ASSETS), n("city_assets")),
        ("⚔️ عملیات", len(active_actions), n("actions")),
    ]
    lines = [f"♻️ <b>تایید بازیابی داده</b>\n{DIV}", "<code>مورد          فعلی → فایل</code>"]
    for label, cur, new in rows:
        warn = " ⚠️" if new < cur else ""
        lines.append(f"{label}: <b>{fmt_num(cur)}</b> → <b>{fmt_num(new)}</b>{warn}")
    lines.append(
        "\n⚠️ با تایید، <b>همه داده‌های فعلی</b> با محتوای فایل جایگزین می‌شود و قابل برگشت نیست "
        "(مگر با فایل پشتیبان فعلی)."
    )
    return "\n".join(lines)


async def apply_restore(raw: dict) -> tuple:
    """اعمال داده‌ی اعتبارسنجی‌شده. برمی‌گرداند (ok, msg)."""
    try:
        apply_data(raw)
        write_local()
        try:
            await push_backup()
        except Exception:
            logging.exception("پس از بازیابی، پشتیبان جدید ناموفق بود.")
        return True, (
            f"✅ بازیابی شد.\n"
            f"🏙 شهر: <b>{len(PLAYER_CODES)}</b>\n"
            f"👤 فرمانده: <b>{len(all_players)}</b>\n"
            f"👥 گروه: <b>{len(GROUPS)}</b>"
        )
    except Exception as ex:
        logging.exception("apply_restore")
        return False, f"❌ خطا در بازیابی: <code>{e(str(ex)[:200])}</code>"


async def init_storage():
    """
    روی Railway رایگان دیسک پاک می‌شود → منبع حقیقت = پیام پین‌شده تلگرام.
    همیشه اول از تلگرام بازیابی می‌کنیم (اگر باشد).
    """
    restored = False
    try:
        pm = await find_backup_message()
        if pm and getattr(pm, "document", None):
            # اگر از پین آمده mid همان پین است؛ اگر فوروارد موقت باشد mid اصلی را نگه می‌داریم
            is_temp = bool(getattr(pm, "_aof_temp_fwd", False))
            if not is_temp:
                backup_state["mid"] = pm.message_id
                _save_mid(pm.message_id)
            raw = await _download_backup_doc(pm.document)
            apply_data(raw)
            write_local()
            restored = True
            if is_temp:
                try:
                    await bot.delete_message(chat_id=backup_chat(), message_id=pm.message_id)
                except Exception:
                    pass
            logging.info(
                "✅ بازیابی از پشتیبان تلگرام: %s شهر، %s فرمانده، %s گروه",
                len(PLAYER_CODES), len(all_players), len(GROUPS),
            )
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        f"✅ ربات روشن شد و داده بازیابی شد.\n"
                        f"🏙 شهر: <b>{len(PLAYER_CODES)}</b>\n"
                        f"👤 فرمانده: <b>{len(all_players)}</b>\n"
                        f"👥 گروه: <b>{len(GROUPS)}</b>"
                    ),
                    disable_notification=True,
                )
            except Exception:
                pass
        else:
            logging.warning("⚠️ پشتیبان پین‌شده پیدا نشد.")
            if has_data():
                logging.info("داده محلی موجود است: %s شهر — آپلود پشتیبان…", len(PLAYER_CODES))
                try:
                    await push_backup()
                except Exception:
                    logging.exception("آپلود پشتیبان اولیه ناموفق")
            else:
                # هیچ داده‌ای نیست — هشدار جدی به ادمین
                try:
                    await bot.send_message(
                        chat_id=ADMIN_ID,
                        text=(
                            "⚠️ <b>هشدار: داده پیدا نشد</b>\n"
                            f"{DIV}\n"
                            "پشتیبان پین‌شده در تلگرام یافت نشد و دیسک هم خالی است.\n\n"
                            "<b>بازیابی دستی:</b>\n"
                            "۱) در پی‌وی ربات فایل <code>aof_data.json</code> قدیمی را پیدا کنید "
                            "(یا از فوروارد/سیو شده)\n"
                            "۲) همان فایل را برای ربات بفرستید\n"
                            "۳) یا بنویسید <code>/restore</code> و فایل را ضمیمه کنید\n\n"
                            "بعد از ست دوباره پلیر/گپ، پیام پشتیبان را <b>پین</b> نگه دارید."
                        ),
                        disable_notification=True,
                    )
                except Exception:
                    pass
    except Exception:
        logging.exception("بازیابی از پشتیبان تلگرام ناموفق بود.")
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text="❌ بازیابی خودکار ناموفق بود. فایل <code>aof_data.json</code> را برای ربات بفرستید.",
            )
        except Exception:
            pass
    return restored
