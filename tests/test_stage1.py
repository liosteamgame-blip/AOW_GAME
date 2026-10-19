"""مرحله ۱ فیچرها: فیچرها، ACL، لاگ ممیزی + برگشت، تایید دونفره، پنل لیدر، اختیارات کمکی."""
import unittest

from tests.fakebot import setup_env

setup_env()

from aiogram.types import PollAnswer, Update  # noqa: E402

from tests.fakebot import ADMIN, FakeTelegram, callback, message, user  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.features import enabled, set_enabled  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data, snapshot  # noqa: E402

GROUP = -100500
FR_GROUP = -100600
PLAYER = 2001
ASSIST = 2002
SUBADMIN = 3001
LEADER = 4001


def fresh_world():
    apply_data({"codes": {}, "users": {}, "groups": {}})
    for d in (state.CITY_ASSETS, state.pending_confirms, state.active_actions, state.PENDING_APPROVALS,
              state.APPROVAL_BLOBS, state.LEADER_POLLS, state.EXTRA_ROLES):
        d.clear()
    state.AUDIT_LOG.clear()
    for side in state.LEADERS:
        state.LEADERS[side] = []


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        fresh_world()
        await dp.storage.close()

    async def send(self, update):
        await dp.feed_update(bot, update)

    def world(self):
        state.PLAYER_CODES.update({"AOWLON1": "london_monarchist", "AOWPAR1": "paris_france"})
        state.GROUPS[GROUP] = {"city": "london_monarchist", "code": "AOWLON1", "commanders": [PLAYER, ASSIST],
                               "commander": PLAYER, "assistants": [ASSIST]}
        state.GROUPS[FR_GROUP] = {"city": "paris_france", "code": "AOWPAR1"}
        for uid, city in ((PLAYER, "london_monarchist"), (ASSIST, "london_monarchist"), (LEADER, "oxford_monarchist")):
            state.authenticated_users[uid] = {"role": "player", "country": city, "code": "", "name": f"u{uid}"}
            state.all_players.add(uid)
        state.authenticated_users[SUBADMIN] = {"role": "admin", "country": "مدیریت کل", "name": "sub"}
        state.CITY_ASSETS["london_monarchist"] = {"text": "", "stats": {"سکه": 1000, "سربازان": 300}}
        state.CITY_ASSETS["paris_france"] = {"text": "", "stats": {"سکه": 9999}}
        state.LEADERS["monarchist"] = [LEADER]

    def alerts(self):
        return [c.text for c in self.tg.sent("AnswerCallbackQuery") if getattr(c, "text", None)]


class FeatureTests(Base):
    async def test_features_persist_and_old_backup_defaults(self):
        set_enabled("dual_approval", True)
        raw = snapshot()
        apply_data({"codes": {}, "users": {}, "groups": {}, "settings": {"time_start": "08:00"}})
        self.assertFalse(enabled("dual_approval"), "بکاپ قدیمی → پیش‌فرض (خاموش)")
        self.assertTrue(enabled("audit_log"))
        apply_data(raw)
        self.assertTrue(enabled("dual_approval"))
        set_enabled("dual_approval", False)

    async def test_acl_blocks_player_on_admin_buttons(self):
        self.world()
        await self.send(callback(PLAYER, "adm_features", chat_id=GROUP, chat_type="supergroup"))
        self.assertTrue(any("⛔️" in a for a in self.alerts()), self.alerts())
        self.assertFalse(self.tg.sent("SendMessage"))
        self.assertFalse(self.tg.sent("EditMessageText"))

    async def test_only_owner_toggles_features(self):
        self.world()
        await self.send(callback(SUBADMIN, "feat:tog:dual_approval"))
        self.assertFalse(enabled("dual_approval"))
        await self.send(callback(ADMIN, "feat:tog:dual_approval"))
        self.assertTrue(enabled("dual_approval"))
        set_enabled("dual_approval", False)


class AuditTests(Base):
    async def test_admin_edit_logged_and_undone(self):
        self.world()
        await self.send(message(ADMIN, "ویرایش دارایی سکه +500", chat_id=GROUP, chat_type="supergroup"))
        self.assertEqual(state.CITY_ASSETS["london_monarchist"]["stats"]["سکه"], 1500)
        entries = [x for x in state.AUDIT_LOG if x.get("city") == "london_monarchist"]
        self.assertEqual(len(entries), 1, state.AUDIT_LOG)
        self.assertEqual(entries[0]["actor"], ADMIN)
        self.assertIn("before", entries[0])
        # زیرادمین نمی‌تواند برگرداند
        await self.send(callback(SUBADMIN, f"audit_undo:y:{entries[0]['id']}"))
        self.assertEqual(state.CITY_ASSETS["london_monarchist"]["stats"]["سکه"], 1500)
        # مالک برمی‌گرداند
        await self.send(callback(ADMIN, f"audit_undo:y:{entries[0]['id']}"))
        self.assertEqual(state.CITY_ASSETS["london_monarchist"]["stats"]["سکه"], 1000)
        self.assertTrue(entries[0].get("undone"))

    async def test_player_actions_not_logged(self):
        self.world()
        from app.audit import CURRENT_ACTOR
        from app.economy.assets import apply_stat_delta
        tok = CURRENT_ACTOR.set(PLAYER)
        try:
            apply_stat_delta("london_monarchist", {"سکه": 10})
        finally:
            CURRENT_ACTOR.reset(tok)
        self.assertEqual(state.AUDIT_LOG, [])


class ApprovalTests(Base):
    async def test_subadmin_delete_needs_owner_approval(self):
        self.world()
        set_enabled("dual_approval", True)
        try:
            await self.send(callback(SUBADMIN, "delcityyes:AOWPAR1"))
            self.assertIn("AOWPAR1", state.PLAYER_CODES, "قبل از تایید مالک نباید حذف شود")
            self.assertEqual(len(state.PENDING_APPROVALS), 1)
            to_owner = [c for c in self.tg.sent("SendMessage") if c.chat_id == ADMIN]
            self.assertTrue(to_owner and "تایید مالک" in to_owner[-1].text)
            aid = next(iter(state.PENDING_APPROVALS))
            await self.send(callback(ADMIN, f"appr:ok:{aid}"))
            self.assertNotIn("AOWPAR1", state.PLAYER_CODES)
            self.assertEqual(state.PENDING_APPROVALS[aid]["status"], "done")
            self.assertTrue(any(c.chat_id == SUBADMIN for c in self.tg.sent("SendMessage")), "درخواست‌دهنده خبردار شود")
            # دوباره زدن تایید بی‌اثر
            await self.send(callback(ADMIN, f"appr:ok:{aid}"))
            self.assertTrue(any("قبلاً" in a for a in self.alerts()))
        finally:
            set_enabled("dual_approval", False)

    async def test_owner_and_feature_off_act_directly(self):
        self.world()
        await self.send(callback(SUBADMIN, "delcityyes:AOWPAR1"))   # فیچر خاموش
        self.assertNotIn("AOWPAR1", state.PLAYER_CODES)
        set_enabled("dual_approval", True)
        try:
            await self.send(callback(ADMIN, "delcityyes:AOWLON1"))  # مالک
            self.assertNotIn("AOWLON1", state.PLAYER_CODES)
            self.assertEqual(state.PENDING_APPROVALS, {})
        finally:
            set_enabled("dual_approval", False)

    async def test_subadmin_transfer_waits(self):
        self.world()
        set_enabled("dual_approval", True)
        try:
            from app.handlers.admin_transfer import _transfer_or_request
            msg = await _transfer_or_request(SUBADMIN, "london_monarchist", "york_parliamentarian")
            self.assertIn("تایید مالک", msg)
            self.assertIn("london_monarchist", state.CITY_ASSETS)
            aid = next(iter(state.PENDING_APPROVALS))
            await self.send(callback(ADMIN, f"appr:ok:{aid}"))
            self.assertIn("york_parliamentarian", state.CITY_ASSETS)
            self.assertNotIn("london_monarchist", state.CITY_ASSETS)
        finally:
            set_enabled("dual_approval", False)


class LeaderPanelTests(Base):
    async def test_summary_only_own_faction(self):
        self.world()
        await self.send(callback(LEADER, "ldr:sum:monarchist"))
        txt = self.tg.last_text()
        self.assertIn("london_monarchist", txt)
        self.assertNotIn("paris_france", txt)
        self.tg.clear()
        await self.send(callback(LEADER, "ldr:sum:france"))
        self.assertTrue(any("فقط لیدر" in a for a in self.alerts()))
        self.assertFalse(any("paris" in t for t in self.tg.texts()))

    async def test_plain_player_has_no_panel(self):
        self.world()
        await self.send(callback(PLAYER, "ldr:menu"))
        self.assertTrue(any("⛔️" in a for a in self.alerts()), self.alerts())

    async def test_message_goes_only_to_faction_groups(self):
        self.world()
        await self.send(callback(LEADER, "ldr:msg:monarchist"))
        await self.send(message(LEADER, "همه آماده دفاع از آکسفورد باشید"))
        self.assertIn("ldr:send:monarchist", self.tg.buttons())
        self.tg.clear()
        await self.send(callback(LEADER, "ldr:send:monarchist"))
        chats = [c.chat_id for c in self.tg.sent("SendMessage")]
        self.assertIn(GROUP, chats)
        self.assertNotIn(FR_GROUP, chats)

    async def test_poll_sent_and_votes_counted(self):
        self.world()
        await self.send(callback(LEADER, "ldr:poll:monarchist"))
        await self.send(message(LEADER, "حمله کنیم؟\nبله\nخیر"))
        await self.send(callback(LEADER, "ldr:psend:monarchist"))
        polls = self.tg.sent("SendPoll")
        self.assertEqual([p.chat_id for p in polls], [GROUP])
        key, rec = next(iter(state.LEADER_POLLS.items()))
        pid = rec["poll_ids"][0]
        await self.send(Update(update_id=99001, poll_answer=PollAnswer(poll_id=pid, user=user(PLAYER), option_ids=[0])))
        await self.send(Update(update_id=99002, poll_answer=PollAnswer(poll_id=pid, user=user(ASSIST), option_ids=[1])))
        self.assertEqual(rec["votes"], {str(PLAYER): [0], str(ASSIST): [1]})
        self.tg.clear()
        await self.send(callback(LEADER, f"ldr:pres:monarchist:{key}"))
        self.assertIn("مجموع رأی‌ها: <b>2</b>", self.tg.last_text())


class AssistantTests(Base):
    async def test_commander_closes_campaign_for_assistant(self):
        self.world()
        g = dict(chat_id=GROUP, chat_type="supergroup")
        state.SETTINGS.update({"days_start": "", "time_start": "00:00", "time_stop": "23:59"})
        # کمکی نمی‌تواند اختیارات را عوض کند
        await self.send(callback(ASSIST, "asst:tog:campaign", **g))
        self.assertNotIn("assistant_perms", state.GROUPS[GROUP])
        await self.send(callback(PLAYER, "asst:tog:campaign", **g))
        self.assertFalse(state.GROUPS[GROUP]["assistant_perms"]["campaign"])
        self.tg.clear()
        await self.send(callback(ASSIST, "menu:campaign", **g))
        self.assertTrue(any("برای کمکی‌ها بسته" in a for a in self.alerts()), self.alerts())
        self.assertFalse(self.tg.sent("SendMessage"))
        # فرمانده خودش آزاد است
        await self.send(callback(PLAYER, "menu:campaign", **g))
        self.assertTrue(self.tg.sent("SendMessage"))

    async def test_commander_sees_menu_button(self):
        from app.keyboards import get_main_menu_keyboard
        self.world()
        flat = lambda kb: [b.callback_data for row in kb.inline_keyboard for b in row]  # noqa: E731
        self.assertIn("asst:menu", flat(get_main_menu_keyboard(PLAYER, chat_id=GROUP)))
        self.assertNotIn("asst:menu", flat(get_main_menu_keyboard(ASSIST, chat_id=GROUP)))
        self.assertIn("ldr:menu", flat(get_main_menu_keyboard(LEADER, chat_id=GROUP)))


if __name__ == "__main__":
    unittest.main()
