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


class CastleTraitTests(Base):
    async def test_commander_sees_trait_under_sheet(self):
        await self.send(message(PLAYER, "دارایی", **self.g))
        txt = "\n".join(self.tg.texts())
        self.assertIn("ویژگی قلعه", txt)
        self.assertIn("۲۵٪ وضعیت اقتصاد بهتر", txt)          # london
        self.assertLess(txt.index("شیت لندن"), txt.index("ویژگی قلعه"), "زیر شیت")

    def test_visibility(self):
        from app.economy.views import format_city_asset_view
        state.LEADERS["monarchist"] = [LEADER]
        state.LEADERS["parliamentarian"] = [OTHER]
        see = lambda uid: "ویژگی قلعه" in format_city_asset_view(LONDON, viewer=uid)  # noqa: E731
        self.assertTrue(see(PLAYER), "فرمانده همان شهر")
        self.assertTrue(see(LEADER), "لیدر همان جناح")
        self.assertTrue(see(ADMIN), "ادمین")
        self.assertFalse(see(OTHER), "لیدر/فرمانده جناح دیگر")
        self.assertFalse(see(None))

    def test_amiens_marked_unverified(self):
        from app.castles import castle_trait_block, castle_trait_line
        self.assertIn("تأیید نشده", castle_trait_block("amiens_france", ADMIN))
        self.assertIn("توپ صحرایی", castle_trait_block("amiens_france", ADMIN))
        self.assertIn("تأیید نشده", castle_trait_line("amiens_france"))
        self.assertNotIn("تأیید نشده", castle_trait_line(LONDON))

    async def test_up_preview_reminder_and_no_effect_on_calc(self):
        state.CITY_ASSETS[LONDON] = {"text": "", "stats": {"سکه": 0}, "yields": {"خزانه": 1000}}
        await self.send(callback(ADMIN, f"up_confirm:{LONDON}"))
        self.assertIn("یادآوری ویژگی قلعه", self.tg.last_text())
        await self.send(callback(ADMIN, f"up_one:{LONDON}"))
        self.assertEqual(state.CITY_ASSETS[LONDON]["stats"]["سکه"], 1000, "باف قلعه (+۲۵٪) نباید اعمال شود")
        self.assertFalse(any(b.get("source") == "castle" for b in state.CITY_BUFFS.get(LONDON, [])))


class RulesCalendarTests(Base):
    """دوشنبه ۲۰۲۶/۱۰/۱۹: ارتقا (سه‌شنبه/چهارشنبه) و تجارت پلیر (شنبه/یکشنبه) غیرمجاز، تجار (دوشنبه) مجاز."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        from datetime import datetime
        from app import rulecal
        from app.config import TZ
        self.rulecal = rulecal
        self._old_now = rulecal._now
        monday = datetime(2026, 10, 19, 12, 0, tzinfo=TZ)
        rulecal._now = lambda now=None: now or monday
        state.AUTO_CITIES[LONDON] = True
        state.CITY_ASSETS[LONDON] = {"text": "", "stats": {"سکه": 10000, "چوب": 1000, "سنگ": 1000, "آهن": 1000,
                                                           "جمعیت": 1000}, "levels": {"قلعه": 1, "خزانه": 1}}
        state.SETTINGS.update({"days_start": "", "time_start": "00:00", "time_stop": "23:59"})

    async def asyncTearDown(self):
        self.rulecal._now = self._old_now
        state.SETTINGS.update({"rules_calendar": "off", "days_upgrade": "1,2", "days_trade": "5,6", "days_merchant": "0"})

    async def upgrade(self, uid=PLAYER):
        from app.economy.rules import UPGRADE_SECTIONS
        idx = UPGRADE_SECTIONS["econ"][1].index("خزانه")
        await self.send(callback(uid, f"upg:do:econ:{idx}:1", **self.g))
        ok = [b for b in self.tg.buttons() if b.startswith("upg:ok:")]
        if ok:
            await self.send(callback(uid, ok[0], **self.g))
        return bool(ok)

    def player_texts(self):
        return [getattr(c, "text", None) or "" for c in self.tg.calls
                if getattr(c, "chat_id", None) in (GROUP, PLAYER) and type(c).__name__ == "SendMessage"] + self.alerts()

    async def test_default_off(self):
        self.assertEqual(state.SETTINGS["rules_calendar"], "off")
        self.assertTrue(await self.upgrade())
        self.assertLess(state.CITY_ASSETS[LONDON]["stats"]["سکه"], 10000)
        self.assertFalse(any("روز مجاز" in t for t in self.tg.texts()))

    async def test_warn_tags_admin_only(self):
        state.SETTINGS["rules_calendar"] = "warn"
        self.assertTrue(await self.upgrade())
        self.assertLess(state.CITY_ASSETS[LONDON]["stats"]["سکه"], 10000, "در حالت هشدار درخواست انجام می‌شود")
        admin = [c.text for c in self.tg.sent("SendMessage") if c.chat_id == ADMIN]
        self.assertTrue(any("خارج از روز مجاز" in t for t in admin), admin)
        self.assertFalse(any("روز مجاز" in t for t in self.player_texts()), "به بازیکن چیزی گفته نشود")

    async def test_block_polite_message_and_admin_bypass(self):
        state.SETTINGS["rules_calendar"] = "block"
        self.assertFalse(await self.upgrade())
        self.assertEqual(state.CITY_ASSETS[LONDON]["stats"]["سکه"], 10000)
        self.assertTrue(any("روز مجاز بعدی" in a and "سه‌شنبه" in a for a in self.alerts()), self.alerts())
        # تجارت پلیر مسدود، تجار (دوشنبه) آزاد
        self.tg.clear()
        await self.send(callback(PLAYER, "trade_kind:player", **self.g))
        self.assertIn("شنبه", self.tg.last_text())
        self.assertIn("روز مجاز بعدی", self.tg.last_text())
        self.tg.clear()
        await self.send(callback(PLAYER, "trade_kind:merchant", **self.g))
        self.assertFalse(any("روز مجاز بعدی" in t for t in self.tg.texts()))
        # ادمین مستثناست
        self.tg.clear()
        self.assertTrue(await self.upgrade(ADMIN))

    async def test_days_configurable_and_persist(self):
        state.SETTINGS["rules_calendar"] = "block"
        await self.send(callback(ADMIN, "feat:calday:upgrade:0"))     # دوشنبه را مجاز کن
        self.assertEqual(state.SETTINGS["days_upgrade"], "0,1,2")
        apply_data(json.loads(json.dumps(snapshot(), ensure_ascii=False, default=str)))   # ری‌استارت
        self.assertEqual(state.SETTINGS["days_upgrade"], "0,1,2")
        self.assertEqual(state.SETTINGS["rules_calendar"], "block")
        self.assertTrue(await self.upgrade())
        # راهنما هم روزهای تازه را نشان می‌دهد
        await self.send(message(PLAYER, "راهنما", **self.g))
        self.assertIn("دوشنبه، سه‌شنبه، چهارشنبه", self.tg.last_text())

    async def test_only_owner_changes_calendar(self):
        state.authenticated_users[3001] = {"role": "admin", "country": "مدیریت کل"}
        await self.send(callback(3001, "feat:calmode:block"))
        self.assertEqual(state.SETTINGS["rules_calendar"], "off")


if __name__ == "__main__":
    unittest.main()
