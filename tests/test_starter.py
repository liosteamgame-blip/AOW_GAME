"""بسته شروع بازی (v2.1): چک‌لیست آمادگی، راهنمای بازیکن، ویژگی قلعه، تقویم قوانین."""
import json
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, callback, message  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data, snapshot  # noqa: E402

GROUP = -100500
YORK_GROUP = -100700
PLAYER = 2001
OTHER = 2101
LEADER = 4001
LONDON = "london_monarchist"
YORK = "york_parliamentarian"


def fresh_world():
    apply_data({"codes": {}, "users": {}, "groups": {}})
    for d in (state.CITY_ASSETS, state.pending_confirms, state.active_actions, state.EXTRA_ROLES,
              state.UP_SNAPSHOTS, state.AUTO_CITIES, state.CITY_BUFFS, state.PENDING_TRADES):
        d.clear()
    for side in state.LEADERS:
        state.LEADERS[side] = []


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        fresh_world()
        await dp.storage.close()
        self.g = dict(chat_id=GROUP, chat_type="supergroup")
        state.PLAYER_CODES.update({"AOWLON1": LONDON, "AOWYRK1": YORK})
        state.GROUPS[GROUP] = {"city": LONDON, "code": "AOWLON1", "commanders": [PLAYER], "commander": PLAYER}
        state.GROUPS[YORK_GROUP] = {"city": YORK, "code": "AOWYRK1", "commanders": [OTHER], "commander": OTHER}
        for uid, city in ((PLAYER, LONDON), (OTHER, YORK), (LEADER, "oxford_monarchist")):
            state.authenticated_users[uid] = {"role": "player", "country": city, "code": "", "name": f"u{uid}"}
            state.all_players.add(uid)
        state.CITY_ASSETS[LONDON] = {"text": "شیت لندن\nسکه: 1000", "stats": {"سکه": 1000}}

    async def send(self, update):
        await dp.feed_update(bot, update)

    def alerts(self):
        return [c.text for c in self.tg.sent("AnswerCallbackQuery") if getattr(c, "text", None)]


class ReadinessTests(Base):
    async def test_report_counts_incomplete_first_and_read_only(self):
        state.LEADERS["monarchist"] = [LEADER]
        before = json.dumps(snapshot(), ensure_ascii=False, sort_keys=True, default=str)
        await self.send(callback(ADMIN, "adm_ready"))
        txt = "\n".join(self.tg.texts())
        self.assertIn("آماده: 1 از 2", txt)
        self.assertLess(txt.index(YORK), txt.index(LONDON), "ناقص‌ها (york بدون شیت) اول")
        york_line = next(ln for ln in txt.split("\n") if YORK in ln)
        self.assertIn("🔴", york_line)
        self.assertIn("📦❌", york_line)
        self.assertIn("مونارشیست: <b>1</b>", txt)
        self.assertIn("پارلمانری: <b>0</b>", txt)
        after = json.dumps(snapshot(), ensure_ascii=False, sort_keys=True, default=str)
        self.assertEqual(before, after, "چک‌لیست نباید هیچ داده‌ای را تغییر دهد")

    async def test_player_denied(self):
        await self.send(callback(PLAYER, "adm_ready", **self.g))
        self.assertTrue(any("⛔️" in a for a in self.alerts()))
        self.assertFalse(self.tg.sent("SendMessage"))


class GuideTests(Base):
    async def asyncTearDown(self):
        state.SETTINGS["guide_commander"] = ""
        state.SETTINGS["guide_leader"] = ""

    async def test_auto_once_on_first_menu(self):
        await self.send(message(PLAYER, "/start", **self.g))
        guides = [t for t in self.tg.texts() if "راهنمای" in t]
        self.assertEqual(len(guides), 1, self.tg.texts())
        self.assertTrue(state.authenticated_users[PLAYER].get("guide_seen"))
        self.assertIn("guide:show", self.tg.buttons())
        self.tg.clear()
        await self.send(message(PLAYER, "/start", **self.g))
        self.assertFalse([t for t in self.tg.texts() if "راهنمای" in t], "فقط یک‌بار خودکار")

    async def test_command_texts_short_rule_based_no_secrets(self):
        state.CITY_ASSETS[LONDON]["stats"].update({"سکه": 987654, "شبه نظامی": 4321})
        await self.send(message(PLAYER, "راهنما", **self.g))
        cmd = self.tg.last_text()
        self.assertIn("راهنمای 👑 فرمانده", cmd)
        self.assertIn("سه‌شنبه، چهارشنبه", cmd)        # ارتقا طبق قوانین
        self.assertIn("شنبه، یکشنبه", cmd)               # تجارت پلیر
        self.assertIn("دوشنبه", cmd)                      # تجار
        self.assertLessEqual(len(cmd.splitlines()), 15)
        for secret in ("987,654", "987654", "4321", "4,321", LONDON):
            self.assertNotIn(secret, cmd)
        state.LEADERS["monarchist"] = [LEADER]
        await self.send(message(LEADER, "راهنما"))
        ldr = self.tg.last_text()
        self.assertIn("راهنمای 🏴 لیدر جناح", ldr)
        self.assertIn("پنل جناح", ldr)
        self.assertLessEqual(len(ldr.splitlines()), 15)

    async def test_admin_edits_text_and_it_survives_restart(self):
        await self.send(callback(ADMIN, "adm_guide:edit:commander"))
        await self.send(message(ADMIN, "\n".join(f"خط {i}" for i in range(20))))
        self.assertIn("حداکثر", self.tg.last_text())
        await self.send(message(ADMIN, "سرورم، فقط در روزهای بازی فرمان بدهید.\nموفق باشید."))
        self.assertEqual(state.SETTINGS["guide_commander"], "سرورم، فقط در روزهای بازی فرمان بدهید.\nموفق باشید.")
        apply_data(json.loads(json.dumps(snapshot(), ensure_ascii=False, default=str)))   # ری‌استارت
        self.assertEqual(state.SETTINGS["guide_commander"], "سرورم، فقط در روزهای بازی فرمان بدهید.\nموفق باشید.")
        self.tg.clear()
        await self.send(message(PLAYER, "راهنما", **self.g))
        self.assertIn("موفق باشید", self.tg.last_text())
        await self.send(callback(ADMIN, "adm_guide:reset:commander"))
        self.assertEqual(state.SETTINGS["guide_commander"], "")


if __name__ == "__main__":
    unittest.main()
