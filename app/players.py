"""نقش و شهر کاربران: پلیر، ادمین، لیدر، کمکی و دسترسی در هر گپ."""
import logging

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey

from app.config import ADMIN_ID
from app.loader import bot, dp
from app.state import GROUPS, LEADERS, all_players, authenticated_users
from app.utils import _norm_country_token, e
from app.factions import all_known_cities, country_key


def is_player(user_id):
    """پلیر = نقش player یا فرمانده/کمکی ثبت‌شده روی حداقل یک گپ."""
    if not user_id:
        return False
    u = authenticated_users.get(user_id)
    if u and u.get("role") == "player":
        return True
    for g in GROUPS.values():
        cmds = list(g.get("commanders") or [])
        if g.get("commander"):
            cmds.append(g.get("commander"))
        asst = list(g.get("assistants") or [])
        if user_id in cmds or user_id in asst:
            return True
    return False


def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    u = authenticated_users.get(user_id)
    return bool(u and u.get("role") == "admin")


def city_of(user_id):
    u = authenticated_users.get(user_id) or {}
    c = u.get("country") or ""
    if c and c != "ناشناس":
        return c
    cities = player_cities(user_id)
    return cities[0] if cities else "ناشناس"


def mention(user_id, label="فرمانده"):
    return f'<a href="tg://user?id={user_id}">{e(label)}</a>'


def code_owner(code):
    for uid, u in authenticated_users.items():
        if u.get("role") == "player" and u.get("code") == code:
            return uid
    return None


def user_fsm(user_id):
    return FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, chat_id=user_id, user_id=user_id))


def chat_fsm(chat_id, user_id):
    return FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id))


def is_group_chat(message):
    return message.chat.type in ("group", "supergroup")


def player_cities(user_id: int) -> list:
    """همه شهرهای متصل به این پلیر (رکورد + گپ‌هایی که فرمانده‌شان است)."""
    cities = []
    seen = set()

    def _add(c):
        if not c or c == "ناشناس":
            return
        key = _norm_country_token(c)
        if key in seen:
            return
        seen.add(key)
        cities.append(c)

    u = authenticated_users.get(user_id) or {}
    _add(u.get("country"))
    for c in list(u.get("cities") or []):
        _add(c)
    # از mapping گروه‌ها
    for cid, city in (u.get("groups") or {}).items():
        _add(city)
    # از GROUPS که این کاربر را commander یا کمکی دارند
    for gid, g in GROUPS.items():
        cmds = list(g.get("commanders") or [])
        if g.get("commander"):
            cmds.append(g.get("commander"))
        asst = list(g.get("assistants") or [])
        if user_id in cmds or user_id in asst:
            _add(g.get("city"))
    return cities


def link_player_to_group(user_id: int, chat_id: int, city: str, user_obj=None) -> dict:
    """
    اتصال پایدار پلیر به گپ+شهر.
    - authenticated_users[uid].cities / .groups
    - GROUPS[chat_id].commanders
    """
    city = city or ""
    u = dict(authenticated_users.get(user_id) or {})
    u["role"] = u.get("role") or "player"
    if u.get("role") not in ("player", "admin"):
        u["role"] = "player"
    u["country"] = city or u.get("country") or ""
    cities = list(u.get("cities") or [])
    if u.get("country") and u["country"] not in cities:
        cities.append(u["country"])
    if city and city not in cities:
        cities.append(city)
    # dedupe by norm
    dedup = []
    seen = set()
    for c in cities:
        k = _norm_country_token(c)
        if k and k not in seen:
            seen.add(k)
            dedup.append(c)
    u["cities"] = dedup
    groups_map = dict(u.get("groups") or {})
    groups_map[str(chat_id)] = city
    u["groups"] = groups_map
    if user_obj is not None:
        u["username"] = getattr(user_obj, "username", None) or u.get("username") or ""
        u["name"] = getattr(user_obj, "full_name", None) or u.get("name") or ""
    grp = GROUPS.get(chat_id) or {}
    if not u.get("code"):
        u["code"] = grp.get("code") or ""
    authenticated_users[user_id] = u
    all_players.add(user_id)
    # گروه
    if chat_id in GROUPS or grp:
        g = dict(GROUPS.get(chat_id) or grp)
        cmds = list(g.get("commanders") or [])
        if user_id not in cmds:
            cmds.append(user_id)
        g["commanders"] = cmds
        g["commander"] = user_id  # آخرین ست‌شده = فرمانده اصلی
        if city:
            g["city"] = city
        GROUPS[chat_id] = g
    return u


def rebuild_player_links():
    """پس از load_data: cities/groups را از روی GROUPS ترمیم می‌کند."""
    for gid, g in list(GROUPS.items()):
        city = g.get("city") or ""
        cmds = list(g.get("commanders") or [])
        if g.get("commander") and g["commander"] not in cmds:
            cmds.append(g["commander"])
        g["commanders"] = cmds
        GROUPS[gid] = g
        for uid in cmds:
            if not uid:
                continue
            u = authenticated_users.get(uid)
            if not u:
                authenticated_users[uid] = {
                    "role": "player",
                    "country": city,
                    "cities": [city] if city else [],
                    "groups": {str(gid): city} if city else {},
                    "code": g.get("code") or "",
                }
                all_players.add(uid)
                continue
            cities = list(u.get("cities") or [])
            if city and city not in cities:
                cities.append(city)
            u["cities"] = cities
            if not u.get("country") or u.get("country") == "ناشناس":
                u["country"] = city
            gm = dict(u.get("groups") or {})
            gm[str(gid)] = city
            u["groups"] = gm
            if u.get("role") != "admin":
                u["role"] = "player"
            authenticated_users[uid] = u
            all_players.add(uid)


def player_group_access(user_id: int, chat_id: int | None = None, chat_type: str | None = None) -> tuple:
    """
    تشخیص دسترسی و شهر فعال.
    اولویت شهر فعال در گپ:
      1) اگر فرمانده همین گپ است → شهر گپ
      2) اگر شهر گپ در لیست شهرهایش است → شهر گپ
      3) پی‌وی → شهر اصلی
    یک‌بار ست کافی است؛ ثبت‌نام مجدد لازم نیست.
    """
    if is_admin(user_id):
        if chat_id and GROUPS.get(chat_id):
            return True, GROUPS[chat_id].get("city"), ""
        return True, resolve_player_city(user_id) or city_of(user_id), ""

    if not is_player(user_id):
        return False, None, (
            "❌ شما هنوز به‌عنوان فرمانده ثبت نشده‌اید.\n"
            "ادمین باید در گپ شهر روی پیام شما ریپلای کند و «ست پلیر» بزند.\n"
            "یا در پی‌وی ربات کد ورود را بفرستید."
        )

    cities = player_cities(user_id)
    primary = resolve_player_city(user_id) or city_of(user_id)
    if primary == "ناشناس":
        primary = cities[0] if cities else None
    if not primary and not cities:
        return False, None, "❌ شهر شما مشخص نیست. ادمین «ست پلیر» را در گپ بزند."

    in_group = chat_type in ("group", "supergroup")
    if not in_group:
        return True, primary or (cities[0] if cities else None), ""

    if chat_id is None:
        return True, primary, ""

    grp = GROUPS.get(chat_id)
    if not grp:
        # گپ ست‌نشده: در پی‌وی‌گونه با شهر اصلی کار کند ولی هشدار
        return True, primary, ""

    gcity = grp.get("city") or ""
    cmds = list(grp.get("commanders") or [])
    if grp.get("commander"):
        cmds.append(grp.get("commander"))
    asst = list(grp.get("assistants") or [])

    # ۱) فرمانده یا کمکی همین گپ → همیشه شهر همین گپ (قاطی نشود)
    if user_id in cmds or user_id in asst:
        return True, gcity or primary, ""

    # ۲) mapping groups: فقط اگر این chat_id به همین شهر وصل باشد
    u = authenticated_users.get(user_id) or {}
    mapped = (u.get("groups") or {}).get(str(chat_id))
    if mapped:
        return True, gcity or mapped or primary, ""

    # ۳) شهر گپ دقیقاً جزو شهرهای پلیر (نه فقط هم‌ساید)
    gn = _norm_country_token(gcity)
    for c in cities:
        cn = _norm_country_token(c)
        if cn == gn:
            return True, gcity or c, ""
        # فقط اگر پایه شهر یکی باشد (norwich_x ≈ norwich_y) — نه celtic با norwich
        gb = gn.split("_")[0] if gn else ""
        cb = cn.split("_")[0] if cn else ""
        if gb and cb and gb == cb and len(gb) > 3:
            return True, gcity or c, ""

    # ۴) لیدر ساید
    side = country_key(gcity)
    if side and is_leader(user_id):
        try:
            if side_of_user(user_id) == side or leader_side(user_id) == side:
                return True, gcity, ""
        except Exception:
            if side in (LEADERS or {}) and user_id in (LEADERS.get(side) or []):
                return True, gcity, ""

    return False, primary, (
        f"❌ این گپ مربوط به شهر <b>{e(gcity)}</b> است.\n"
        f"شهرهای متصل شما: <b>{e('، '.join(cities) if cities else (primary or '—'))}</b>\n"
        "برای این گپ، ادمین یک‌بار روی پیام شما «ست پلیر» بزند."
    )


def city_from_message(message, user_id=None):
    """شهر فعال برای این پیام؛ (ok, city, err)."""
    uid = user_id if user_id is not None else message.from_user.id
    return player_group_access(uid, message.chat.id, message.chat.type)


def context_city(message) -> tuple:
    """میانبر: از روی message شهر فعال را برمی‌گرداند."""
    return player_group_access(
        message.from_user.id,
        message.chat.id,
        message.chat.type,
    )


def city_for_callback(callback, user_id=None) -> tuple:
    """
    شهر فعال بر اساس گپی که دکمه در آن زده شده.
    هر گپ → دارایی همان گپ؛ پی‌وی → شهر اصلی.
    """
    uid = user_id if user_id is not None else callback.from_user.id
    msg = callback.message
    if msg is None:
        return player_group_access(uid, None, None)
    return player_group_access(uid, msg.chat.id, msg.chat.type)


def action_city(callback, user_id=None) -> str:
    """شهر فعال برای ثبت یک فرمان: شهرِ گپی که دکمه در آن زده شده؛ در پی‌وی شهر اصلی."""
    uid = user_id if user_id is not None else callback.from_user.id
    try:
        ok, c, _err = city_for_callback(callback, uid)
        if ok and c and c != "ناشناس":
            return c
    except Exception:
        logging.exception("action_city")
    return city_of(uid)


def faction_of_user(user_id):
    """فکشن بازیکن از روی شهر ثبت‌شده‌اش."""
    return country_key(city_of(user_id))


def side_of_user(user_id):
    """فکشن بازیکن از روی شهر ثبت‌شده."""
    return country_key(city_of(user_id))


def is_leader(user_id):
    if is_admin(user_id):
        return True
    for ids in LEADERS.values():
        if user_id in ids:
            return True
    return False


def leader_side(user_id):
    """ساید لیدر؛ None اگر لیدر نباشد."""
    for side, ids in LEADERS.items():
        if user_id in ids:
            return side
    return None


def is_plain_player(user_id):
    """فرمانده عادی — نه ادمین، نه لیدر ساید."""
    return is_player(user_id) and not is_admin(user_id) and leader_side(user_id) is None


def resolve_player_city(user_id) -> str | None:
    """
    شهر ثبت‌شده پلیر را به کلید CITY_ASSETS / PLAYER_CODES منطبق می‌کند.
    """
    my = city_of(user_id)
    if not my or my == "ناشناس":
        return None
    mn = _norm_country_token(my)
    mb = mn.split("_")[0] if "_" in mn else mn
    # تطبیق دقیق
    for c in all_known_cities():
        cn = _norm_country_token(c)
        if cn == mn:
            return c
    # تطبیق پایه نام شهر
    for c in all_known_cities():
        cn = _norm_country_token(c)
        cb = cn.split("_")[0] if "_" in cn else cn
        if cb == mb or mb in cn or cn in mn:
            return c
    return my


def players_of_city(city: str) -> list:
    """فرمانده‌های متصل به یک شهر."""
    if not city:
        return []
    cn = _norm_country_token(city)
    base = cn.split("_")[0] if "_" in cn else cn
    uids = []
    for uid, u in authenticated_users.items():
        if u.get("role") not in ("player", "admin"):
            continue
        uc = _norm_country_token(u.get("country") or "")
        if not uc:
            continue
        ub = uc.split("_")[0] if "_" in uc else uc
        if uc == cn or ub == base or city.lower() == (u.get("country") or "").lower():
            uids.append(uid)
    return uids


def groups_of_city(city: str) -> list:
    if not city:
        return []
    cn = _norm_country_token(city)
    base = cn.split("_")[0] if "_" in cn else cn
    gids = []
    for gid, g in GROUPS.items():
        gc = _norm_country_token(g.get("city") or "")
        gb = gc.split("_")[0] if "_" in gc else gc
        if gc == cn or gb == base:
            gids.append(gid)
    return gids


def _admin_cmd_city(message) -> tuple:
    """شهر هدف دستورهای ادمینی: اول شهر گپ ست‌شده، بعد شهر خود ادمین. برمی‌گرداند (city, err)."""
    city = None
    if message.chat.type in ("group", "supergroup"):
        city = (GROUPS.get(message.chat.id) or {}).get("city")
    if not city:
        ok, city, err = city_from_message(message)
        if not ok:
            return None, err or "❌ دسترسی ندارید."
    if not city or city == "ناشناس":
        return None, "❌ شهر مشخص نیست."
    return city, ""


def _players_of_city(city_name: str):
    """فرمانده(های) یک شهر."""
    out = []
    for uid, u in authenticated_users.items():
        if u.get("role") == "player" and (u.get("country") or "").lower() == (city_name or "").lower():
            out.append((uid, u))
    return out


def player_ids_for_city(city: str) -> list:
    """آیدی فرمانده(های) یک شهر."""
    ids = []
    for uid, u in authenticated_users.items():
        if u.get("role") != "player":
            continue
        if (u.get("country") or "") == city:
            try:
                ids.append(int(uid))
            except (TypeError, ValueError):
                continue
    return ids
