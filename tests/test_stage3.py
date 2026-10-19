"""مرحله ۳ فیچرها: داشبورد زنده، رویدادهای جهانی، آپ زمان‌بندی‌شده، گزارش خطا، قفل آپ کلی."""
import asyncio
import os
import unittest
from datetime import datetime

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, callback  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import dashboard, errorlog, state, upschedule  # noqa: E402
from app.config import TZ  # noqa: E402
from app.features import set_enabled  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data  # noqa: E402

GROUP = -100500
PLAYER = 2001
NARRATOR = 5001
CHANNEL = -100111
LONDON = "london_monarchist"
YORK = "york_parliamentarian"


def fresh_world():
    apply_data({"codes": {}, "users": {}, "groups": {}})
    for d in (state.CITY_ASSETS, state.pending_confirms, state.active_actions, state.PENDING_APPROVALS,
              state.EXTRA_ROLES, state.CITY_RANKS, state.UP_SNAPSHOTS, state.AUTO_CITIES, state.CITY_BUFFS,
              state.WORLD_EVENTS, state.PENDING_TRADES):
        d.clear()
    state.AUDIT_LOG.clear()
    state.CHRONICLE.clear()
    errorlog.reset()


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        fresh_world()
        await dp.storage.close()
        state.PLAYER_CODES.update({"AOWLON1": LONDON, "AOWYRK1": YORK})
        state.GROUPS[GROUP] = {"city": LONDON, "code": "AOWLON1", "commanders": [PLAYER], "commander": PLAYER}
        state.authenticated_users[PLAYER] = {"role": "player", "country": LONDON, "code": "", "name": "p"}
        state.all_players.add(PLAYER)
        for city in (LONDON, YORK):
            state.CITY_ASSETS[city] = {"text": "", "stats": {"سکه": 0, "غذا": 0},
                                       "yields": {"خزانه": 1000, "آشپزخانه": 1000}, "levels": {"قلعه": 1}}
            state.AUTO_CITIES[city] = True

    async def send(self, update):
        await dp.feed_update(bot, update)

    def alerts(self):
        return [c.text for c in self.tg.sent("AnswerCallbackQuery") if getattr(c, "text", None)]

    def to(self, chat):
        return [getattr(c, "text", None) or "" for c in self.tg.sent("SendMessage") if c.chat_id == chat]

    def coins(self, city=LONDON):
        return state.CITY_ASSETS[city]["stats"].get("سکه")


# ---------------- 🌍 رویداد جهانی ----------------
class WorldEventTests(Base):
    async def test_faction_famine_applies_then_expires(self):
        for data in ("ev:menu", "ev:t:famine", "ev:s:monarchist", "ev:u:1"):
            await self.send(callback(ADMIN, data))
        self.assertIn("پیش‌نمایش رویداد", self.tg.last_text())
        self.assertEqual(state.WORLD_EVENTS, {}, "قبل از تایید چیزی ثبت نشود")
        await self.send(callback(ADMIN, "ev:ok"))
        self.assertTrue(any(b.get("source") == "event" for b in state.CITY_BUFFS.get(LONDON, [])))
        self.assertFalse(state.CITY_BUFFS.get(YORK), "پارلمانری در دامنه نبود")
        self.assertTrue(any("قحطی" in t for t in self.to(CHANNEL)))
        await self.send(callback(ADMIN, "ev:ok"))   # دابل‌کلیک
        self.assertEqual(len(state.WORLD_EVENTS), 1)
        # آپ اول: غذا ۱۰۰۰ − ۴۰٪ = ۶۰۰ و رویداد تمام می‌شود
        await self.send(callback(ADMIN, f"up_one:{LONDON}"))
        self.assertEqual(state.CITY_ASSETS[LONDON]["stats"]["غذا"], 600)
        self.assertFalse(any(b.get("source") == "event" for b in state.CITY_BUFFS.get(LONDON, [])))
        self.assertFalse(next(iter(state.WORLD_EVENTS.values()))["active"])
        # آپ دوم: بدون نرف
        await self.send(callback(ADMIN, f"up_one:{LONDON}"))
        self.assertEqual(state.CITY_ASSETS[LONDON]["stats"]["غذا"], 1600)

    async def test_narrator_allowed_player_denied(self):
        state.EXTRA_ROLES[NARRATOR] = ["narrator"]
        await self.send(callback(NARRATOR, "ev:menu"))
        self.assertIn("ev:t:plague", self.tg.buttons())
        self.tg.clear()
        await self.send(callback(PLAYER, "ev:menu", chat_id=GROUP, chat_type="supergroup"))
        self.assertTrue(any("⛔️" in a for a in self.alerts()))

    async def test_manual_end(self):
        from app.events import start_event
        ev = start_event("plague", "all", 30, 3)
        self.assertEqual(len([c for c, l in state.CITY_BUFFS.items() if l]), 2)
        await self.send(callback(ADMIN, f"ev:end:{ev['eid']}"))
        self.assertFalse(any(state.CITY_BUFFS.values()))


# ---------------- ♻️ قفل آپ کلی ----------------
class UpAllLockTests(Base):
    async def test_double_click_up_all_runs_once(self):
        await asyncio.gather(self.send(callback(ADMIN, "up_all")), self.send(callback(ADMIN, "up_all")))
        self.assertEqual(self.coins(), 1000, "آپ کلی نباید دوبار اجرا شود")
        self.assertEqual(self.coins(YORK), 1000)


# ---------------- 🗓 آپ زمان‌بندی‌شده ----------------
class ScheduledUpTests(Base):
    def setUp_sched(self):
        set_enabled("scheduled_up", True)
        state.SETTINGS.update({"time_stop": "23:00", "up_day": "2", "up_offset_min": "15", "up_confirmed_for": "",
                               "up_preview_sent": "", "up_last_run": "", "up_skip_notified": ""})

    async def asyncTearDown(self):
        set_enabled("scheduled_up", False)

    async def test_never_runs_without_confirmation(self):
        self.setUp_sched()
        wed = datetime(2026, 10, 21, 22, 20, tzinfo=TZ)
        self.assertEqual(await upschedule.tick(wed), "preview")
        self.assertTrue(any(b.startswith("upsch:ok:2026-10-21") for b in self.tg.buttons()))
        self.assertEqual(await upschedule.tick(wed.replace(minute=30)), "", "پیش‌نمایش یک‌بار")
        self.assertEqual(await upschedule.tick(wed.replace(hour=23, minute=20)), "skipped")
        self.assertEqual(self.coins(), 0, "بدون تایید آپ اجرا نشد")
        self.assertTrue(any("اجرا نشد" in t for t in self.to(ADMIN)))
        self.assertEqual(await upschedule.tick(wed.replace(hour=23, minute=40)), "")

    async def test_runs_once_after_confirmation(self):
        self.setUp_sched()
        wed = datetime(2026, 10, 21, 22, 20, tzinfo=TZ)
        await upschedule.tick(wed)
        await self.send(callback(ADMIN, "upsch:ok:2026-10-21"))
        self.assertEqual(state.SETTINGS["up_confirmed_for"], "2026-10-21")
        self.assertEqual(await upschedule.tick(wed.replace(hour=23, minute=10)), "", "قبل از زمان اجرا نشود")
        self.assertEqual(await upschedule.tick(wed.replace(hour=23, minute=16)), "ran")
        self.assertEqual(self.coins(), 1000)
        self.assertEqual(await upschedule.tick(wed.replace(hour=23, minute=30)), "")
        self.assertEqual(self.coins(), 1000, "دوبار اجرا نشود")

    async def test_off_by_default_and_wrong_day(self):
        self.assertEqual(await upschedule.tick(datetime(2026, 10, 21, 23, 30, tzinfo=TZ)), "", "پیش‌فرض خاموش")
        self.setUp_sched()
        self.assertEqual(await upschedule.tick(datetime(2026, 10, 22, 23, 30, tzinfo=TZ)), "", "پنجشنبه")

    async def test_subadmin_settings_and_player_denied(self):
        await self.send(callback(PLAYER, "upsch:ok:2026-10-21", chat_id=GROUP, chat_type="supergroup"))
        self.assertNotEqual(state.SETTINGS.get("up_confirmed_for"), "2026-10-21")
        await self.send(callback(ADMIN, "upsch:day:6"))
        self.assertEqual(state.SETTINGS["up_day"], "6")
        state.SETTINGS["up_day"] = "2"


# ---------------- 📊 داشبورد زنده ----------------
class DashboardTests(Base):
    async def asyncTearDown(self):
        dashboard.uninstall()

    async def test_install_pin_and_refresh(self):
        await self.send(callback(ADMIN, "dash:install"))
        self.assertTrue(self.tg.sent("PinChatMessage"))
        chat, mid = dashboard.installed()
        self.assertEqual(chat, ADMIN)
        self.tg.clear()
        self.assertTrue(await dashboard.refresh(now=1_900_000_000))
        edit = self.tg.sent("EditMessageText")[0]
        self.assertEqual(edit.message_id, mid)
        self.assertIn("داشبورد زنده", edit.text)
        self.assertIn("گروه: <b>1</b>", edit.text)
        set_enabled("live_dashboard", False)
        try:
            self.assertFalse(await dashboard.refresh(now=1_900_000_600))
        finally:
            set_enabled("live_dashboard", True)

    async def test_player_cannot_open(self):
        await self.send(callback(PLAYER, "dash:install", chat_id=GROUP, chat_type="supergroup"))
        self.assertTrue(any("⛔️" in a for a in self.alerts()))
        self.assertEqual(dashboard.installed(), (None, None))


# ---------------- 🚨 گزارش خطا ----------------
class ErrorReportTests(Base):
    async def test_error_reported_once_per_10_minutes(self):
        import app.handlers.admin_features as af
        old_view, old_env = af.features_view, os.environ.get("AOW_RAISE_ERRORS")

        def boom(uid):
            raise ValueError("خطای آزمایشی")
        af.features_view = boom
        os.environ["AOW_RAISE_ERRORS"] = "0"
        try:
            await self.send(callback(ADMIN, "adm_features"))
            reports = [t for t in self.to(ADMIN) if "خطای ربات" in t]
            self.assertEqual(len(reports), 1)
            self.assertIn("ValueError", reports[0])
            self.assertIn("admin_features.py", reports[0])
            self.assertTrue(any("خطایی رخ داد" in a for a in self.alerts()))
            self.tg.clear()
            await self.send(callback(ADMIN, "adm_features"))
            self.assertFalse([t for t in self.to(ADMIN) if "خطای ربات" in t], "تا ۱۰ دقیقه تکرار گزارش نشود")
            self.assertEqual(errorlog.recent_count(), 2)
        finally:
            af.features_view = old_view
            os.environ["AOW_RAISE_ERRORS"] = old_env or "1"

    def test_rate_limit_counts_suppressed(self):
        try:
            raise KeyError("x")
        except KeyError as ex:
            exc = ex
        self.assertEqual(errorlog.note(exc, now=1000)[:2], (True, 0))
        self.assertEqual(errorlog.note(exc, now=1100)[:2], (False, 0))
        self.assertEqual(errorlog.note(exc, now=1200)[:2], (False, 0))
        self.assertEqual(errorlog.note(exc, now=1700)[:2], (True, 2), "بعد از ۱۰ دقیقه با شمار تکرارها")


if __name__ == "__main__":
    unittest.main()
