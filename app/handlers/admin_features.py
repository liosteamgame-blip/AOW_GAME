"""پنل ادمین: 🧪 فیچرها · 📜 لاگ ممیزی (با برگشت) · 🎭 نقش‌ها · 🔐 تاییدهای دونفره."""
from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import state as app_state
from app.audit import AUDIT_MAX, actor_label, audit_text, find, undo
from app.approvals import KIND_TITLES, execute, pending_list
from app.config import ADMIN_ID, DIV
from app.features import FEATURES, enabled, set_enabled
from app.keyboards import _btn, get_admin_inline_keyboard
from app.loader import bot, dp
from app.permissions import ROLE_TITLES, can, grant_role, revoke_role
from app.players import is_admin, mention
from app.state import AUDIT_LOG, EXTRA_ROLES, LEADERS, PENDING_APPROVALS, authenticated_users
from app.storage import save_data
from app.utils import e, fmt_num, norm_cmd

AUDIT_PAGE = 10


# ---------------- 🧪 فیچرها ----------------
def features_view(uid: int):
    owner = can(uid, "features.manage")
    lines = [f"🧪 <b>فیچرها</b>\n{DIV}"]
    builder = InlineKeyboardBuilder()
    for key, (title, _default, desc) in FEATURES.items():
        on = enabled(key)
        lines.append(f"{'✅' if on else '❌'} <b>{title}</b>\n   <i>{e(desc)}</i>")
        if owner:
            builder.row(_btn(f"{'✅' if on else '❌'} {title}", f"feat:tog:{key}", "success" if on else "danger"))
    if not owner:
        lines.append("\n<i>فقط مالک می‌تواند فیچرها را روشن/خاموش کند.</i>")
    builder.row(_btn("🔙 پنل", "back_to_admin"))
    return "\n".join(lines), builder.as_markup()


@dp.callback_query(F.data == "adm_features")
async def admin_features_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    text, kb = features_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("feat:tog:"))
async def admin_feature_toggle(callback: types.CallbackQuery):
    if not can(callback.from_user.id, "features.manage"):
        return await callback.answer("⛔️ فقط مالک.", show_alert=True)
    key = callback.data.split(":", 2)[2]
    if key not in FEATURES:
        return await callback.answer("کلید ناشناخته", show_alert=True)
    set_enabled(key, not enabled(key))
    save_data(critical=True)
    await callback.answer(f"{FEATURES[key][0]}: {'روشن' if enabled(key) else 'خاموش'}")
    text, kb = features_view(callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


# ---------------- 📜 لاگ ممیزی ----------------
def audit_view(uid: int, offset: int = 0):
    text = audit_text(limit=AUDIT_PAGE, offset=offset)
    if not enabled("audit_log"):
        text += "\n\n⚠️ <i>لاگ ممیزی الان خاموش است (🧪 فیچرها).</i>"
    builder = InlineKeyboardBuilder()
    if can(uid, "audit.undo"):
        rows = list(reversed(AUDIT_LOG))[offset:offset + AUDIT_PAGE]
        for x in rows:
            if "before" in x and not x.get("undone"):
                label = f"↩️ {x.get('action')} · {x.get('city') or '—'}"
                builder.row(_btn(label[:60], f"audit_undo:{x['id']}", "danger"))
    nav = []
    if offset > 0:
        nav.append(_btn("◀️ جدیدتر", f"adm_auditp:{max(0, offset - AUDIT_PAGE)}"))
    if offset + AUDIT_PAGE < len(AUDIT_LOG):
        nav.append(_btn("قدیمی‌تر ▶️", f"adm_auditp:{offset + AUDIT_PAGE}"))
    if nav:
        builder.row(*nav)
    builder.row(_btn("🔙 پنل", "back_to_admin"))
    return text, builder.as_markup()


@dp.callback_query((F.data == "adm_audit") | F.data.startswith("adm_auditp:"))
async def admin_audit_menu(callback: types.CallbackQuery):
    if not can(callback.from_user.id, "audit.view"):
        return await callback.answer()
    offset = 0
    if callback.data.startswith("adm_auditp:"):
        try:
            offset = max(0, min(int(callback.data.split(":", 1)[1]), AUDIT_MAX))
        except ValueError:
            offset = 0
    await callback.answer()
    text, kb = audit_view(callback.from_user.id, offset)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("audit_undo:"))
async def admin_audit_undo(callback: types.CallbackQuery):
    if not can(callback.from_user.id, "audit.undo"):
        return await callback.answer("⛔️ فقط مالک.", show_alert=True)
    parts = callback.data.split(":")
    force = len(parts) == 3 and parts[1] == "f"
    eid = parts[-1]
    x = find(eid)
    if not x:
        return await callback.answer("مورد پیدا نشد.", show_alert=True)
    if not force:
        # مرحله‌ی تایید: نمایش و دکمه «برگشت»
        await callback.answer()
        builder = InlineKeyboardBuilder()
        builder.row(
            _btn("↩️ بله، برگردان", f"audit_undo:y:{eid}", "danger"),
            _btn("❌ انصراف", "adm_audit"),
        )
        if parts[1] != "y":
            return await callback.message.answer(
                f"↩️ <b>برگشت تغییر</b>\n{DIV}\n"
                f"📌 {e(x.get('action'))} · 🏙 {e(x.get('city') or '—')}\n"
                f"👤 {e(actor_label(x.get('actor') or 0))}\n\n"
                "دارایی این شهر به حالت قبل از این تغییر برمی‌گردد. ادامه می‌دهید؟",
                reply_markup=builder.as_markup(),
            )
    ok, msg = undo(eid, force=force)
    if ok:
        save_data(critical=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    builder = InlineKeyboardBuilder()
    if not ok and "بعد از این تغییر" in msg:
        builder.row(_btn("⚠️ برگشت اجباری", f"audit_undo:f:{eid}", "danger"))
    builder.row(_btn("📜 لاگ ممیزی", "adm_audit"))
    await callback.message.answer(msg, reply_markup=builder.as_markup())


# ---------------- 🎭 نقش‌ها ----------------
SET_NARRATOR_CMDS = {"ستراوی", "setnarrator"}
DEL_NARRATOR_CMDS = {"حذفراوی", "delnarrator", "unsetnarrator"}


def _who(uid: int) -> str:
    u = authenticated_users.get(uid) or {}
    return mention(uid, u.get("name") or u.get("username") or str(uid))


def roles_text() -> str:
    lines = [f"🎭 <b>نقش‌ها</b>\n{DIV}", f"{ROLE_TITLES['owner']}: {_who(ADMIN_ID)}"]
    admins = [uid for uid, u in authenticated_users.items() if u.get("role") == "admin" and uid != ADMIN_ID]
    lines.append(f"{ROLE_TITLES['admin']}: " + ("، ".join(_who(u) for u in admins) if admins else "—"))
    aa = app_state.ASSET_ADMIN_ID
    lines.append(f"{ROLE_TITLES['asset_admin']}: " + (_who(aa) if aa else "—"))
    leaders = [f"{side}: " + "، ".join(_who(u) for u in ids) for side, ids in LEADERS.items() if ids]
    lines.append(f"{ROLE_TITLES['leader']}: " + (" · ".join(leaders) if leaders else "—"))
    narrators = [uid for uid, rs in EXTRA_ROLES.items() if "narrator" in rs]
    lines.append(f"{ROLE_TITLES['narrator']}: " + ("، ".join(_who(u) for u in narrators) if narrators else "—"))
    lines.append(
        "\n<b>دادن/گرفتن راوی</b> (فقط مالک): در گروه روی پیام کاربر ریپلای کنید و "
        "<code>ست راوی</code> یا <code>حذف راوی</code> بزنید.\n"
        "<i>راوی به رویدادها و وقایع‌نامه دسترسی خواهد داشت (مراحل بعد).</i>"
    )
    return "\n".join(lines)


@dp.callback_query(F.data == "adm_roles")
async def admin_roles_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    builder = InlineKeyboardBuilder()
    builder.row(_btn("🔙 پنل", "back_to_admin"))
    await callback.message.answer(roles_text(), reply_markup=builder.as_markup())


@dp.message(F.text.func(lambda t: norm_cmd(t) in SET_NARRATOR_CMDS | DEL_NARRATOR_CMDS))
async def handle_narrator_role(message: types.Message):
    if not can(message.from_user.id, "roles.manage"):
        return
    target = message.reply_to_message.from_user if message.reply_to_message else None
    if not target or target.is_bot:
        return await message.answer("❌ روی پیام کاربر ریپلای کنید و دوباره بفرستید.")
    if norm_cmd(message.text) in SET_NARRATOR_CMDS:
        changed = grant_role(target.id, "narrator")
        msg = f"✅ {mention(target.id, target.full_name)} اکنون {ROLE_TITLES['narrator']} است." if changed \
            else "ℹ️ از قبل راوی است."
    else:
        changed = revoke_role(target.id, "narrator")
        msg = f"✅ نقش راوی از {mention(target.id, target.full_name)} گرفته شد." if changed \
            else "ℹ️ این کاربر راوی نیست."
    if changed:
        save_data(critical=True)
    await message.answer(msg)


# ---------------- 🔐 تاییدهای دونفره ----------------
@dp.callback_query(F.data == "adm_approvals")
async def admin_approvals_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer()
    await callback.answer()
    items = pending_list()
    builder = InlineKeyboardBuilder()
    lines = [f"🔐 <b>تاییدهای معلق</b> ({fmt_num(len(items))})\n{DIV}"]
    if not enabled("dual_approval"):
        lines.append("<i>تایید دونفره خاموش است (🧪 فیچرها).</i>")
    for aid, it in items:
        lines.append(
            f"• <b>{KIND_TITLES.get(it.get('kind'), it.get('kind'))}</b> — {it.get('summary')}\n"
            f"   👤 {e(actor_label(it.get('requester') or 0))}"
        )
        if can(callback.from_user.id, "approve.sensitive"):
            builder.row(
                _btn(f"✅ {aid}", f"appr:ok:{aid}", "success"),
                _btn(f"❌ {aid}", f"appr:no:{aid}", "danger"),
            )
    if not items:
        lines.append("موردی در انتظار نیست.")
    builder.row(_btn("🔙 پنل", "back_to_admin"))
    await callback.message.answer("\n".join(lines), reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("appr:"))
async def admin_approval_decide(callback: types.CallbackQuery):
    if not can(callback.from_user.id, "approve.sensitive"):
        return await callback.answer("⛔️ فقط مالک.", show_alert=True)
    parts = callback.data.split(":")
    if len(parts) != 3:
        return await callback.answer()
    action, aid = parts[1], parts[2]
    item = PENDING_APPROVALS.get(aid)
    if not item or item.get("status") != "pending":
        return await callback.answer("این درخواست قبلاً رسیدگی شده یا منقضی است.", show_alert=True)
    # قبل از هر await — دابل‌کلیک دوبار اجرا نمی‌کند
    item["status"] = "processing"
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    title = KIND_TITLES.get(item.get("kind"), item.get("kind"))
    if action == "no":
        item["status"] = "rejected"
        app_state.APPROVAL_BLOBS.pop(aid, None)
        save_data()
        await callback.answer("رد شد")
        result = f"❌ درخواست «{title}» رد شد."
    else:
        await callback.answer("در حال اجرا…")
        ok, msg = await execute(aid)
        item["status"] = "done" if ok else "failed"
        save_data(critical=True)
        result = f"{'✅' if ok else '❌'} «{title}»\n{msg}"
    await callback.message.answer(result, reply_markup=get_admin_inline_keyboard())
    requester = item.get("requester")
    if requester and requester != callback.from_user.id:
        try:
            await bot.send_message(requester, f"🔐 پاسخ مالک به درخواست شما:\n{result}")
        except Exception:
            pass
