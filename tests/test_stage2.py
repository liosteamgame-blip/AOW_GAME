"""مرحله ۲ فیچرها: هشدار رسیدن، کارنامه هفتگی، رتبه من، وقایع‌نامه، فرمان سریع، سهمیه xAI."""
import time
import unittest
from datetime import datetime

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, callback, message  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import ai, arrivals, state  # noqa: E402
from app.config import TZ  # noqa: E402
from app.features import set_enabled  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data  # noqa: E402

GROUP = -100500       # london_monarchist
YORK_GROUP = -100700  # york_parliamentarian (مدافع)
PLAYER = 2001
DEFENDER = 2101
NARRATOR = 5001
CHANNEL = -100111
STATS = "500 شبه نظامی محرمانه"


def fresh_world():
    apply_data({"codes": {}, "users": {}, "groups": {}})
    for d in (state.CITY_ASSETS, state.pending_confirms, state.active_actions, state.PENDING_APPROVALS,
              state.LEADER_POLLS, state.EXTRA_ROLES, state.CITY_RANKS, state.LAST_ORDERS, state.AI_CACHE,
              state.UP_SNAPSHOTS, state.AUTO_CITIES, state.CITY_BUFFS):
        d.clear()
    state.AUDIT_LOG.clear()
    state.CHRONICLE.clear()
    state.SETTINGS.update({"days_start": "", "time_start": "00:00", "time_stop": "23:59", "chronicle_since": "0"})


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        fresh_world()
        await dp.storage.close()
        self.g = dict(chat_id=GROUP, chat_type="supergroup")
        state.PLAYER_CODES.update({"AOWLON1": "london_monarchist", "AOWYRK1": "york_parliamentarian"})
        state.GROUPS[GROUP] = {"city": "london_monarchist", "code": "AOWLON1", "commanders": [PLAYER], "commander": PLAYER}
        state.GROUPS[YORK_GROUP] = {"city": "york_parliamentarian", "code": "AOWYRK1",
                                    "commanders": [DEFENDER], "commander": DEFENDER}
        for uid, city in ((PLAYER, "london_monarchist"), (DEFENDER, "york_parliamentarian")):
            state.authenticated_users[uid] = {"role": "player", "country": city, "code": "", "name": f"u{uid}"}
            state.all_players.add(uid)

    async def send(self, update):
        await dp.feed_update(bot, update)

    def alerts(self):
        return [c.text for c in self.tg.sent("AnswerCallbackQuery") if getattr(c, "text", None)]

    def to(self, chat):
        return [getattr(c, "text", None) or getattr(c, "caption", None) or "" for c in self.tg.calls
                if getattr(c, "chat_id", None) == chat and type(c).__name__ in ("SendMessage", "SendPhoto")]

    async def campaign(self, minutes="45"):
        await self.send(callback(PLAYER, "menu:campaign", **self.g))
        await self.send(callback(PLAYER, "mtype:campaign:land", **self.g))
        await self.send(message(PLAYER, "london_monarchist", **self.g))
        await self.send(message(PLAYER, "york_parliamentarian", **self.g))
        await self.send(message(PLAYER, STATS, **self.g))
        await self.send(message(PLAYER, minutes, **self.g))
        await self.send(callback(PLAYER, "confirm:yes", **self.g))
        return next(reversed(state.active_actions.items()))


# ---------------- ⏳ هشدار رسیدن ----------------
class ArrivalTests(Base):
    def test_parse_arrivals(self):
        base = datetime(2026, 10, 19, 10, 0, tzinfo=TZ).timestamp()
        p = arrivals.parse_arrivals
        self.assertEqual(p("12:00", base), [base + 2 * 3600])
        self.assertEqual(p("09:00", base), [base + 23 * 3600], "ساعت گذشته = فردا")
        self.assertEqual(p("12:00, 11:00", base), [base + 2 * 3600, base + 25 * 3600], "موج دوم بعد از موج اول")
        self.assertEqual(p("-", base), [])

    def test_arrival_skips_non_game_days(self):
        """چهارشنبه شب ثبت → شنبه می‌رسد، نه پنجشنبه (days_start = شنبه تا چهارشنبه)."""
        state.SETTINGS["days_start"] = "5,6,0,1,2"
        try:
            wed = datetime(2026, 10, 21, 23, 0, tzinfo=TZ)
            self.assertEqual(wed.weekday(), 2)
            p = arrivals.parse_arrivals
            [ts] = p("08:15", wed.timestamp())
            got = datetime.fromtimestamp(ts, TZ)
            self.assertEqual((got.weekday(), got.day, got.hour, got.minute), (5, 24, 8, 15))
            # همان شب چهارشنبه هنوز مجاز است
            [ts2] = p("23:30", wed.timestamp())
            self.assertEqual(datetime.fromtimestamp(ts2, TZ).day, 21)
            # دو موج: موج دوم هم از روزهای تعطیل رد می‌شود
            a, b = p("23:40, 09:00", wed.timestamp())
            self.assertEqual(datetime.fromtimestamp(a, TZ).day, 21)
            self.assertEqual(datetime.fromtimestamp(b, TZ).day, 24)
            # جمعه ثبت شود (روز تعطیل) → همان ساعت، شنبه
            fri = datetime(2026, 10, 23, 10, 0, tzinfo=TZ)
            [ts3] = p("12:00", fri.timestamp())
            self.assertEqual(datetime.fromtimestamp(ts3, TZ).day, 24)
        finally:
            state.SETTINGS["days_start"] = ""

    async def test_countdown_and_arrival_messages(self):
        aid, act = await self.campaign("45")
        arr = act["arrival"]
        self.assertEqual(len(arr["times"]), 1)
        self.assertEqual(arr["origin_chat"], GROUP)
        t = arr["times"][0]
        self.tg.clear()
        self.assertEqual(await arrivals.tick(now=t - 25 * 60), 0)
        edits = self.tg.sent("EditMessageText") + self.tg.sent("EditMessageCaption")
        self.assertEqual(len(edits), 1)
        body = getattr(edits[0], "text", None) or edits[0].caption
        self.assertIn("تا رسیدن", body)
        self.assertNotIn(STATS, body)
        # همان آستانه دوباره ویرایش نمی‌شود
        self.tg.clear()
        await arrivals.tick(now=t - 24 * 60)
        self.assertFalse(self.tg.sent("EditMessageText") + self.tg.sent("EditMessageCaption"))
        # رسیدن
        self.assertEqual(await arrivals.tick(now=t + 5), 1)
        mine, theirs = self.to(GROUP), self.to(YORK_GROUP)
        self.assertTrue(any("لشکریان شما به مقصد رسیدند" in x for x in mine), mine)
        self.assertTrue(any("london_monarchist" in x and "رسید" in x for x in theirs), theirs)
        self.assertFalse(any(STATS in x for x in mine + theirs), "آمار لشکر نباید در پیام رسیدن باشد")
        self.assertTrue(act["arrival"]["done"])
        self.tg.clear()
        self.assertEqual(await arrivals.tick(now=t + 600), 0, "دوباره اعلام نشود")

    async def test_redirect_and_back_reschedule(self):
        aid, act = await self.campaign("45")
        now = time.time()
        later = datetime.fromtimestamp(now + 3600, TZ).strftime("%H:%M")
        arrivals.reschedule(aid, later, mode="go", dest="york_parliamentarian")
        t = act["arrival"]["times"][0]
        self.assertGreater(t, now + 3000)
        arrivals.reschedule(aid, later, mode="back")
        self.tg.clear()
        await arrivals.tick(now=act["arrival"]["times"][0] + 1)
        self.assertTrue(any("به مبدأ بازگشت" in x for x in self.to(GROUP)))
        self.assertEqual(self.to(YORK_GROUP), [], "بازگشت فقط برای گروه خودی")

    async def test_feature_off(self):
        aid, act = await self.campaign("45")
        set_enabled("arrival_alerts", False)
        try:
            self.assertEqual(await arrivals.tick(now=act["arrival"]["times"][0] + 1), 0)
        finally:
            set_enabled("arrival_alerts", True)


# ---------------- 🧾 کارنامه + 🏆 رتبه من ----------------
class CardAndRankTests(Base):
    def city_assets(self):
        state.CITY_ASSETS["london_monarchist"] = {
            "text": "", "stats": {"سکه": 100, "چوب": 1000, "سنگ": 1000, "آهن": 1000, "جمعیت": 1000},
            "yields": {"خزانه": 1500}, "levels": {"قلعه": 1, "خزانه": 1},
        }
        state.CITY_ASSETS["york_parliamentarian"] = {"text": "", "stats": {"سکه": 999999}, "yields": {}}

    async def test_report_card_after_up(self):
        self.city_assets()
        await self.send(callback(ADMIN, "up_one:london_monarchist"))
        card = [x for x in self.to(GROUP) if "کارنامه هفتگی" in x]
        self.assertEqual(len(card), 1, self.to(GROUP))
        self.assertIn("+1,500", card[0])
        self.assertIn("اولین کارنامه", card[0])
        self.assertIn("از 2", card[0])            # رتبه از ۲ شهر
        self.assertNotIn("york", card[0])         # اسم/عدد شهر دیگر نیست
        self.assertNotIn("999,999", card[0])
        self.assertFalse(any("رسید آپ هفتگی" in x for x in self.to(GROUP)), "رسید خام فقط برای ادمین")
        self.assertTrue(any("رسید آپ هفتگی" in x for x in self.to(ADMIN)))
        # هفته‌ی بعد: یک ارتقا → در کارنامه بیاید
        state.CITY_ASSETS["london_monarchist"]["levels"]["خزانه"] = 2
        self.tg.clear()
        await self.send(callback(ADMIN, "up_one:london_monarchist"))
        card2 = [x for x in self.to(GROUP) if "کارنامه هفتگی" in x][0]
        self.assertIn("خزانه: 1 → <b>2</b>", card2)
        self.assertIn("＝", card2)                 # رتبه عوض نشده

    async def test_card_off_sends_raw_receipt(self):
        self.city_assets()
        set_enabled("report_card", False)
        try:
            await self.send(callback(ADMIN, "up_one:london_monarchist"))
            self.assertTrue(any("رسید آپ هفتگی" in x for x in self.to(GROUP)))
        finally:
            set_enabled("report_card", True)

    async def test_my_rank_only_own_city(self):
        self.city_assets()
        await self.send(callback(PLAYER, "eco:rank", **self.g))
        txt = self.tg.last_text()
        self.assertIn("رتبه london_monarchist", txt)
        self.assertIn("از 2", txt)
        self.assertNotIn("york", txt)
        self.assertNotIn("999", txt)


# ---------------- 📖 وقایع‌نامه ----------------
class ChronicleTests(Base):
    async def test_preview_publish_and_reset(self):
        await self.campaign("45")
        self.assertTrue(state.CHRONICLE)
        self.assertFalse(any(STATS in str(ev) for ev in state.CHRONICLE), "آمار نباید ذخیره شود")
        self.tg.clear()
        await self.send(callback(ADMIN, "chr:menu"))
        preview = self.tg.last_text()
        self.assertIn("york_parliamentarian", preview)
        self.assertNotIn(STATS, preview)
        self.assertFalse(self.to(CHANNEL), "بدون تایید منتشر نشود")
        await self.send(callback(ADMIN, "chr:pub"))
        self.assertTrue(any("وقایع‌نامه" in x for x in self.to(CHANNEL)))
        self.tg.clear()
        await self.send(callback(ADMIN, "chr:pub"))            # دابل‌کلیک
        self.assertFalse(self.to(CHANNEL))
        await self.send(callback(ADMIN, "chr:menu"))
        self.assertIn("رویداد عمومی‌ای ثبت نشده", self.tg.last_text())

    async def test_destination_switch_to_tweet_channel(self):
        await self.campaign("45")
        state.EXTRA_ROLES[NARRATOR] = ["narrator"]
        try:
            await self.send(callback(NARRATOR, "chr:dest"))          # راوی نمی‌تواند مقصد را عوض کند
            self.assertEqual(state.SETTINGS.get("chronicle_dest"), "main")
            await self.send(callback(ADMIN, "chr:menu"))
            self.assertIn("chr:dest", self.tg.buttons())
            await self.send(callback(ADMIN, "chr:dest"))
            self.assertEqual(state.SETTINGS["chronicle_dest"], "tweet")
            self.tg.clear()
            await self.send(callback(ADMIN, "chr:pub"))
            self.assertTrue(any("وقایع‌نامه" in x for x in self.to(-100333)))
            self.assertFalse(self.to(CHANNEL))
        finally:
            state.SETTINGS["chronicle_dest"] = "main"

    async def test_narrator_can_player_cannot(self):
        await self.campaign("45")
        state.EXTRA_ROLES[NARRATOR] = ["narrator"]
        self.tg.clear()
        await self.send(message(NARRATOR, "وقایع‌نامه"))
        self.assertTrue(any("پیش‌نمایش وقایع‌نامه" in t for t in self.tg.texts()))
        self.tg.clear()
        await self.send(callback(PLAYER, "chr:menu", **self.g))
        self.assertTrue(any("⛔️" in a for a in self.alerts()))


# ---------------- 🔁 فرمان سریع ----------------
class QuickOrderTests(Base):
    async def test_same_as_last_time(self):
        await self.campaign("45")
        self.assertEqual(state.LAST_ORDERS[str(PLAYER)]["campaign"]["stats"], STATS)
        self.tg.clear()
        await self.send(callback(PLAYER, "menu:campaign", **self.g))
        await self.send(callback(PLAYER, "mtype:campaign:land", **self.g))
        self.assertIn("quick:last:campaign", self.tg.buttons())
        self.assertIn("mycity:camp_origin", self.tg.buttons())
        await self.send(callback(PLAYER, "quick:last:campaign", **self.g))
        self.assertIn("زمان رسیدن", self.tg.last_text())
        await self.send(message(PLAYER, "30", **self.g))
        self.assertIn("پیش‌نویس فرمان اعزام", self.tg.last_text())
        await self.send(callback(PLAYER, "confirm:yes", **self.g))
        self.assertEqual(len(state.active_actions), 2)

    async def test_my_cities_picks_origin(self):
        await self.send(callback(PLAYER, "menu:campaign", **self.g))
        await self.send(callback(PLAYER, "mtype:campaign:land", **self.g))
        await self.send(callback(PLAYER, "mycity:camp_origin", **self.g))
        self.assertIn("mycityp:camp_origin:0", self.tg.buttons())
        await self.send(callback(PLAYER, "mycityp:camp_origin:0", **self.g))
        self.assertIn("مبدا: <b>london_monarchist</b>", self.tg.last_text())

    async def test_buttons_hidden_when_off(self):
        state.LAST_ORDERS[str(PLAYER)] = {"campaign": {"origin": "a", "dest": "b", "stats": "x"}}
        set_enabled("quick_order", False)
        try:
            await self.send(callback(PLAYER, "menu:campaign", **self.g))
            await self.send(callback(PLAYER, "mtype:campaign:land", **self.g))
            self.assertNotIn("quick:last:campaign", self.tg.buttons())
            self.assertNotIn("mycity:camp_origin", self.tg.buttons())
        finally:
            set_enabled("quick_order", True)


# ---------------- 🤖 سهمیه و کش xAI ----------------
class AiQuotaTests(Base):
    async def test_cache_and_daily_cap(self):
        calls = []
        old_key, old_post = ai.XAI_API_KEY, ai._post_sync
        ai.XAI_API_KEY = "test"
        ai._post_sync = lambda body: calls.append(body) or {"choices": [{"message": {"content": "متن گروک"}}]}
        state.SETTINGS.update({"ai_daily_limit": "1", "ai_used_count": "0", "ai_used_date": ""})
        try:
            t1, _ = await ai.ask("k1", "s", "p")
            t2, note = await ai.ask("k1", "s", "p")
            self.assertEqual((t1, t2), ("متن گروک", "متن گروک"))
            self.assertIn("کش", note)
            self.assertEqual(len(calls), 1)
            t3, note3 = await ai.ask("k2", "s", "p")
            self.assertIsNone(t3)
            self.assertIn("سقف روزانه", note3)
            self.assertEqual(len(calls), 1)
        finally:
            ai.XAI_API_KEY, ai._post_sync = old_key, old_post

    async def test_advisor_does_not_call_ai_without_button(self):
        from app.economy.advisor import build_upgrade_advice
        old_key, old_post = ai.XAI_API_KEY, ai._post_sync
        ai.XAI_API_KEY = "test"

        def boom(body):
            raise AssertionError("xAI نباید بدون دکمه صدا زده شود")
        ai._post_sync = boom
        try:
            state.CITY_ASSETS["london_monarchist"] = {"text": "", "stats": {"سکه": 5000}}
            text = await build_upgrade_advice("london_monarchist")
            self.assertNotIn("Grok", text)
        finally:
            ai.XAI_API_KEY, ai._post_sync = old_key, old_post


if __name__ == "__main__":
    unittest.main()
