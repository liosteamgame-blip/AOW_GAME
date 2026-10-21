"""تست دود: چند مسیر اصلی ربات از ابتدا تا انتها با آپدیت جعلی."""
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, callback, message  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data  # noqa: E402

GROUP = -100500
PLAYER = 2001


def fresh_world():
    apply_data({"codes": {}, "users": {}, "groups": {}})
    state.CITY_ASSETS.clear()
    state.pending_confirms.clear()
    state.active_actions.clear()


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        fresh_world()
        await dp.storage.close()

    async def send(self, update):
        await dp.feed_update(bot, update)

    async def link_group_and_player(self, city="london_monarchist"):
        # ادمین: /start در گروه → ست گپ → انتخاب دستی شهر
        await self.send(message(ADMIN, "/start", chat_id=GROUP, chat_type="supergroup", title="گپ لندن"))
        await self.send(callback(ADMIN, "grp_setcity", chat_id=GROUP, chat_type="supergroup"))
        await self.send(message(ADMIN, city, chat_id=GROUP, chat_type="supergroup"))
        self.assertIn(GROUP, state.GROUPS)
        # ست پلیر با ریپلای
        target = message(PLAYER, "سلام", chat_id=GROUP, chat_type="supergroup").message
        await self.send(message(ADMIN, "ست پلیر", chat_id=GROUP, chat_type="supergroup", reply_to=target))
        self.assertIn(PLAYER, state.GROUPS[GROUP].get("commanders", []))


class SmokeTests(Base):
    async def test_admin_panel_opens(self):
        await self.send(message(ADMIN, "/start"))
        await self.send(message(ADMIN, "ADMIN"))   # کد ورود ادمین
        self.assertTrue(any("پنل" in t or "رئیس" in t for t in self.tg.texts()), self.tg.texts())

    async def test_group_link_and_player(self):
        await self.link_group_and_player()
        self.assertEqual(state.GROUPS[GROUP]["city"], "london_monarchist")

    async def test_campaign_flow_posts_to_channel(self):
        await self.link_group_and_player()
        state.SETTINGS["days_start"] = ""
        state.SETTINGS["time_start"] = "00:00"
        state.SETTINGS["time_stop"] = "23:59"
        self.tg.clear()
        g = dict(chat_id=GROUP, chat_type="supergroup")
        await self.send(callback(PLAYER, "menu:campaign", **g))
        await self.send(callback(PLAYER, "mtype:campaign:land", **g))
        await self.send(message(PLAYER, "london_monarchist", **g))
        await self.send(message(PLAYER, "york_parliamentarian", **g))
        await self.send(message(PLAYER, "500 شبه نظامی", **g))
        await self.send(message(PLAYER, "45", **g))
        await self.send(callback(PLAYER, "confirm:yes", **g))
        posts = [c for c in self.tg.calls if getattr(c, "chat_id", None) == -100111]
        self.assertTrue(posts, [type(c).__name__ for c in self.tg.calls])
        self.assertEqual(len(state.active_actions), 1)

    async def test_plain_player_cannot_free_level(self):
        await self.link_group_and_player()
        self.tg.clear()
        await self.send(message(PLAYER, "افزایش لول ساختمان\nخزانه 5", chat_id=GROUP, chat_type="supergroup"))
        self.assertFalse(self.tg.texts(), "پلیر عادی نباید هیچ پاسخی از فرم ادمین بگیرد")


if __name__ == "__main__":
    unittest.main()


class ArtTests(unittest.TestCase):
    def test_removed_art_is_never_loaded(self):
        """صاحب ربات خواست art_campaign_land_england_2.jpg کلاً حذف شود و در هیچ پستی استفاده نشود."""
        from app.art import ART, load_art
        load_art()
        names = [path for group in ART.values() for arts in group.values() for _src, path in arts]
        self.assertTrue(names, "art.zip باید لود شود")
        self.assertFalse([n for n in names if n.endswith("art_campaign_land_england_2.jpg")])
        self.assertEqual(len(ART[("campaign", "land")]["england"]), 5)
