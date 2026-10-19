"""نقش‌ها و جدول مجوزها — یک‌جا.

قبلاً هر هندلر خودش is_admin/is_player را چک می‌کرد و یک چک جاافتاده (افزایش لول/ثبت تلفات)
به پلیر عادی اجازه‌ی سکه و لول مجانی می‌داد. حالا:
  • نقش هر کاربر با roles_of ساخته می‌شود
  • هر قابلیت یک «مجوز» دارد (PERMS) و با can() چک می‌شود
  • یک لایه‌ی محافظ سراسری (AclMiddleware) دکمه‌های ادمینی را قبل از رسیدن به هندلر می‌بندد
"""
import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from app import state as app_state
from app.config import ADMIN_ID
from app.features import enabled
from app.players import is_admin, is_player, leader_side
from app.state import EXTRA_ROLES, GROUPS

ROLE_TITLES = {
    "owner": "👑 مالک",
    "admin": "⚡️ ادمین",
    "asset_admin": "📦 ادمین دارایی",
    "narrator": "🎭 راوی",
    "leader": "🏴 لیدر جناح",
    "commander": "🛡 فرمانده",
    "assistant": "🤝 کمکی",
    "player": "🙂 بازیکن",
}

# نقش‌هایی که مالک می‌تواند از پنل بدهد/بگیرد (ادمین و لیدر روش‌های قبلی خودشان را دارند)
GRANTABLE = ("narrator",)

# مجوز → نقش‌های مجاز
PERMS = {
    "panel.admin": {"owner", "admin"},
    "roles.manage": {"owner"},
    "features.manage": {"owner"},
    "assets.edit": {"owner", "admin"},
    "audit.view": {"owner", "admin"},
    "audit.undo": {"owner"},
    "approve.sensitive": {"owner"},
    "events.run": {"owner", "admin", "narrator"},
    "chronicle.publish": {"owner", "admin", "narrator"},
    "lb.announce": {"owner", "admin", "narrator"},
    "dashboard": {"owner", "admin"},
    "up.schedule": {"owner", "admin"},
    "leader.panel": {"owner", "admin", "leader"},
    "assistants.manage": {"owner", "admin", "commander"},
    "narrator.panel": {"owner", "admin", "narrator"},
}

# کارهای کمکی که فرمانده می‌تواند ببندد/باز کند
ASSIST_ACTIONS = {
    "campaign": "⚔️ لشکرکشی",
    "war": "🛡️ اعلان جنگ",
    "siege": "🏰 محاصره",
    "trade": "🐪 تجارت",
    "statement": "📜 بیانیه",
}


def _group_members(chat_id):
    g = GROUPS.get(chat_id) or {}
    cmds = set(g.get("commanders") or [])
    if g.get("commander"):
        cmds.add(g.get("commander"))
    asst = set(g.get("assistants") or [])
    return cmds - asst, asst


def roles_of(user_id: int, chat_id: int | None = None) -> set:
    roles = set()
    if not user_id:
        return roles
    if user_id == ADMIN_ID:
        roles.add("owner")
    if is_admin(user_id):
        roles.add("admin")
    if app_state.ASSET_ADMIN_ID and user_id == app_state.ASSET_ADMIN_ID:
        roles.add("asset_admin")
    for r in EXTRA_ROLES.get(user_id) or []:
        roles.add(r)
    if leader_side(user_id):
        roles.add("leader")
    if is_player(user_id):
        roles.add("player")
        if chat_id is not None and chat_id in GROUPS:
            cmds, asst = _group_members(chat_id)
            if user_id in asst:
                roles.add("assistant")
            elif user_id in cmds:
                roles.add("commander")
        else:
            # در پی‌وی: اگر حداقل در یک گپ فرمانده اصلی است
            for gid in GROUPS:
                cmds, asst = _group_members(gid)
                if user_id in cmds:
                    roles.add("commander")
                    break
    return roles


def can(user_id: int, perm: str, chat_id: int | None = None) -> bool:
    allowed = PERMS.get(perm)
    if not allowed:
        logging.warning("مجوز ناشناخته: %s", perm)
        return False
    return bool(roles_of(user_id, chat_id) & allowed)


def role_badges(user_id: int, chat_id: int | None = None) -> str:
    rs = roles_of(user_id, chat_id)
    order = list(ROLE_TITLES)
    return " · ".join(ROLE_TITLES[r] for r in sorted(rs, key=order.index)) or "—"


def assistant_allowed(user_id: int, chat_id: int | None, action: str) -> bool:
    """آیا کمکیِ این گپ اجازه‌ی این کار را دارد؟ (فرمانده/ادمین همیشه بله)."""
    if not enabled("assistant_perms"):
        return True
    if chat_id is None or chat_id not in GROUPS:
        return True
    _cmds, asst = _group_members(chat_id)
    if user_id not in asst or is_admin(user_id):
        return True
    perms = (GROUPS.get(chat_id) or {}).get("assistant_perms") or {}
    return bool(perms.get(action, True))


# نوع فرمان در تایید نهایی → کلید اختیار کمکی
CONFIRM_KIND_ACTION = {"campaign": "campaign", "siege": "siege", "war": "war",
                       "ann": "statement", "trade": "trade", "mtrade": "trade"}


def assistant_block_text(user_id: int, chat_id: int | None, action: str) -> str:
    """متن خطا اگر فرمانده این فرمان را برای کمکی‌ها بسته باشد؛ در غیر این صورت ''."""
    action = CONFIRM_KIND_ACTION.get(action, action)
    if action not in ASSIST_ACTIONS or assistant_allowed(user_id, chat_id, action):
        return ""
    return f"⛔️ سرورم، فرمانده‌ی این شهر «{ASSIST_ACTIONS[action]}» را برای کمکی‌ها بسته است."


def grant_role(user_id: int, role: str) -> bool:
    if role not in GRANTABLE:
        return False
    lst = list(EXTRA_ROLES.get(user_id) or [])
    if role in lst:
        return False
    lst.append(role)
    EXTRA_ROLES[user_id] = lst
    return True


def revoke_role(user_id: int, role: str) -> bool:
    lst = list(EXTRA_ROLES.get(user_id) or [])
    if role not in lst:
        return False
    lst.remove(role)
    if lst:
        EXTRA_ROLES[user_id] = lst
    else:
        EXTRA_ROLES.pop(user_id, None)
    return True


# ---------------- لایه‌ی محافظ سراسری دکمه‌ها ----------------
# پیشوند callback_data → مجوز لازم. هندلرها همچنان چک خودشان را دارند؛ این لایه
# تضمین می‌کند اگر یک هندلر جدید چک را فراموش کرد، دکمه‌ی ادمینی باز هم بسته بماند.
CALLBACK_ACL = (
    ("adm_", "panel.admin"),
    ("back_to_admin", "panel.admin"),
    ("up_", "panel.admin"),
    ("auto_tog:", "panel.admin"),
    ("buff_", "panel.admin"),
    ("trf_", "panel.admin"),
    ("flv_", "panel.admin"),
    ("lb:", "panel.admin"),
    ("lb_ranks_cfg", "panel.admin"),
    ("lb_announce:", "panel.admin"),
    ("revoke", "panel.admin"),
    ("delcity", "panel.admin"),
    ("aedit:", "panel.admin"),
    ("restore_", "panel.admin"),
    ("trade_ok:", "panel.admin"),
    ("trade_no:", "panel.admin"),
    ("set_leader_side:", "panel.admin"),
    ("inq_delplayer:", "panel.admin"),
    ("inq_unlink:", "panel.admin"),
    ("asset_confirm_city:", "panel.admin"),
    ("asset_pick_other", "panel.admin"),
    ("feat:", "features.manage"),
    ("role:", "roles.manage"),
    ("audit_undo:", "audit.undo"),
    ("appr:", "approve.sensitive"),
    ("ldr:", "leader.panel"),
    ("asst:", "assistants.manage"),
)
# مسیرهای gasset که فقط ادمین است (تازه‌سازی برای پلیر آزاد است)
GASSET_ADMIN = ("gasset:edit:", "gasset:shop:", "gasset:lv:", "gasset:loss:", "gasset:buff:")


def callback_perm(data: str) -> str | None:
    if not data:
        return None
    if data.startswith(GASSET_ADMIN):
        return "panel.admin"
    for prefix, perm in CALLBACK_ACL:
        if data.startswith(prefix):
            return perm
    return None


class AclMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery):
            perm = callback_perm(event.data or "")
            if perm:
                chat_id = event.message.chat.id if event.message else None
                if not can(event.from_user.id, perm, chat_id):
                    try:
                        await event.answer("⛔️ این بخش برای شما باز نیست.", show_alert=True)
                    except Exception:
                        pass
                    return None
        return await handler(event, data)
