"""بسته شروع بازی (v2.1): چک‌لیست آمادگی، راهنمای بازیکن، ویژگی قلعه، تقویم قوانین."""
import json
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, callback  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
