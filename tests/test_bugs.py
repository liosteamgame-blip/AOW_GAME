"""تست باگ‌های بخش «باگ‌های پیداشده» در NOTES."""
import pathlib
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, message  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data  # noqa: E402
from app.economy.up import run_weekly_up_for_city  # noqa: E402

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        apply_data({"codes": {}, "users": {}, "groups": {}})
        state.CITY_ASSETS.clear()
        state.CITY_BUFFS.clear()
        await dp.storage.close()


class BugTests(Base):
    async def test_bug1_coin_building_buff_uses_own_yield(self):
        city = "london_monarchist"
        state.CITY_ASSETS[city] = {
            "text": "", "stats": {"سکه": 0},
            "yields": {"خزانه": 1000, "بندر": 500},
        }
        state.CITY_BUFFS[city] = [{"id": "t", "kind": "buff", "target": "خزانه", "pct": 10, "apply_on_up": True}]
        run_weekly_up_for_city(city, force=True)
        coins = float(state.CITY_ASSETS[city]["stats"].get("سکه") or 0)
        # ۱۰۰۰ + ۵۰۰ + ۱۰٪ فقط از خزانه = ۱۶۰۰ (نه ۱۶۵۰)
        self.assertEqual(coins, 1600)

    def test_bug2_no_orphan_adm_back(self):
        hits = [p.name for p in APP.rglob("*.py") if '"adm_back"' in p.read_text(encoding="utf-8")]
        self.assertEqual(hits, [])

    async def test_bug5_owner_start_opens_panel(self):
        state.authenticated_users.pop(ADMIN, None)
        await self.send_start()
        self.assertTrue(any("پنل" in t for t in self.tg.texts()), self.tg.texts())
        self.assertFalse(any("کد ورود" in t for t in self.tg.texts()))

    async def send_start(self):
        await dp.feed_update(bot, message(ADMIN, "/start"))

    def test_bug6_leader_capacity_text(self):
        src = (APP / "handlers" / "leaders.py").read_text(encoding="utf-8")
        self.assertNotIn("۳/۳", src)
        self.assertNotIn("/3)", src)


if __name__ == "__main__":
    unittest.main()
