"""تست باگ‌های بخش «باگ‌های پیداشده» در NOTES."""
import asyncio
import pathlib
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, callback, message  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data  # noqa: E402
from app.economy.up import run_weekly_up_for_city  # noqa: E402
from app.economy.costs import cost_for_levels  # noqa: E402
from app.economy.rules import UPGRADE_SECTIONS  # noqa: E402

GROUP = -100500
APP =pathlib.Path(__file__).resolve().parent.parent / "app"


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        apply_data({"codes": {}, "users": {}, "groups": {}})
        state.CITY_ASSETS.clear()
        state.CITY_BUFFS.clear()
        state.PENDING_TRADES.clear()
        state.pending_upgrades.clear()
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

    def _upgrade_city(self):
        city = "london_monarchist"
        state.GROUPS[GROUP] = {"city": city, "code": "AOWTEST1"}
        state.CITY_ASSETS[city] = {
            "text": "",
            "stats": {"سکه": 10000, "چوب": 1000, "سنگ": 1000, "آهن": 1000, "جمعیت": 1000},
            "levels": {"قلعه": 1, "خزانه": 1},
        }
        return city

    async def test_bug3_7_upgrade_needs_confirm_and_applies_once(self):
        city = self._upgrade_city()
        g = dict(chat_id=GROUP, chat_type="supergroup")
        idx = UPGRADE_SECTIONS["econ"][1].index("خزانه")
        await dp.feed_update(bot, callback(ADMIN, f"upg:do:econ:{idx}:1", **g))
        # باگ ۷: فقط پیش‌نویس — هنوز چیزی کسر نشده
        self.assertEqual(state.CITY_ASSETS[city]["stats"]["سکه"], 10000)
        ok_btn = [b for b in self.tg.buttons() if b.startswith("upg:ok:")]
        self.assertEqual(len(ok_btn), 1, self.tg.buttons())
        # باگ ۳: دابل‌کلیک روی تایید → فقط یک‌بار کسر
        await asyncio.gather(
            dp.feed_update(bot, callback(ADMIN, ok_btn[0], **g)),
            dp.feed_update(bot, callback(ADMIN, ok_btn[0], **g)),
        )
        cost = cost_for_levels("خزانه", 1, city=city)["coin"]
        self.assertEqual(state.CITY_ASSETS[city]["stats"]["سکه"], 10000 - cost)

    async def test_bug4_caravan_double_approve_posts_once(self):
        city = self._upgrade_city()
        state.PENDING_TRADES["t1"] = {
            "kind": "player", "status": "pending", "city": city, "units": 10,
            "user_id": 2001, "origin": city, "dest": "york_parliamentarian", "mtype": "land",
        }
        self.tg.clear()
        await asyncio.gather(
            dp.feed_update(bot, callback(ADMIN, "trade_ok:t1")),
            dp.feed_update(bot, callback(ADMIN, "trade_ok:t1")),
        )
        posts = [c for c in self.tg.calls if getattr(c, "chat_id", None) == -100111]
        self.assertEqual(len(posts), 1)
        self.assertEqual(state.CITY_ASSETS[city].get("trade_cap_used"), 10)
        self.assertEqual(state.PENDING_TRADES["t1"]["status"], "approved")

    def test_bug6_leader_capacity_text(self):
        src = (APP / "handlers" / "leaders.py").read_text(encoding="utf-8")
        self.assertNotIn("۳/۳", src)
        self.assertNotIn("/3)", src)


if __name__ == "__main__":
    unittest.main()
