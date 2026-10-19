"""هندلرهای auth"""

from aiogram import F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from app.config import ADMIN_CODE, BTN_BACK, MENU_TEXT
from app.loader import dp
from app.state import GROUPS, PLAYER_CODES, all_players, authenticated_users
from app.utils import _norm_country_token, e
from app.states import GameStates
from app.players import code_owner, is_admin, is_player
from app.keyboards import get_admin_inline_keyboard
from app.storage import save_data
from app.menus import go_menu


@dp.message(StateFilter(None), F.chat.type.in_({"group", "supergroup"}), F.text == BTN_BACK)
async def group_fallback_handler(message: types.Message, state: FSMContext):
    """بعد از ری‌استارت ربات، وضعیت فرمانده‌ی گروه را دوباره برقرار می‌کند."""
    if is_player(message.from_user.id):
        await go_menu(message, state)


@dp.message(GameStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    code = (message.text or "").strip().upper()
    if not code:
        return await message.answer("❌ لطفاً کد را به صورت متن ارسال کنید:")

    if code == ADMIN_CODE and is_admin(user_id):
        prev = dict(authenticated_users.get(user_id) or {})
        authenticated_users[user_id] = {**prev, "role": "admin", "country": prev.get("country") or "مدیریت کل"}
        await message.answer("⚡️ سلام رئیس! پنل مدیریت ادمین فعال شد.", reply_markup=get_admin_inline_keyboard())
        await state.clear()
    elif code in PLAYER_CODES:
        owner = code_owner(code)
        if owner and owner != user_id:
            return await message.answer("🚫 این کد قبلاً توسط فرمانده دیگری فعال شده است.\nبا ادمین تماس بگیرید:")
        city = PLAYER_CODES[code]
        prev = dict(authenticated_users.get(user_id) or {})
        cities = list(prev.get("cities") or [])
        if city not in cities:
            cities.append(city)
        authenticated_users[user_id] = {
            **prev,
            "role": "player",
            "country": city,
            "cities": cities,
            "groups": dict(prev.get("groups") or {}),
            "code": code,
            "username": message.from_user.username or prev.get("username") or "",
            "name": message.from_user.full_name or prev.get("name") or "",
        }
        all_players.add(user_id)
        for gid, g in list(GROUPS.items()):
            if _norm_country_token(g.get("city") or "") == _norm_country_token(city):
                cmds = list(g.get("commanders") or [])
                if user_id not in cmds:
                    cmds.append(user_id)
                g["commanders"] = cmds
                if not g.get("commander"):
                    g["commander"] = user_id
                GROUPS[gid] = g
                gm = dict(authenticated_users[user_id].get("groups") or {})
                gm[str(gid)] = city
                authenticated_users[user_id]["groups"] = gm
        save_data(critical=True)
        await go_menu(
            message, state,
            f"✅ <b>کد شما تایید شد!</b>\n"
            f"👑 مدیریت شهر <b>{e(city)}</b> فعال است.\n"
            f"🏙 شهرهای شما: <b>{e('، '.join(cities))}</b>\n\n{MENU_TEXT}",
        )

    else:
        await message.answer("🚫 این کد معتبر نیست یا باطل شده است!\nمجدداً تلاش کنید:")


@dp.message(F.text == BTN_BACK)
async def global_back(message: types.Message, state: FSMContext):
    user_data = authenticated_users.get(message.from_user.id)
    if not user_data:
        return
    if user_data["role"] == "admin":
        await state.clear()
        await message.answer("⚡️ منوی اصلی مدیریت:", reply_markup=get_admin_inline_keyboard())
    else:
        await go_menu(message, state)
