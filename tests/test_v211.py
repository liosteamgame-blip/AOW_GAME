"""v2.1.1: کرش تگ باز <b> در «دارایی شخصی»، پارس شیت/شاپ، بازسازی yields، محافظ آپ مشکوک، پاک‌سازی کلید زباله."""
import re
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, callback, message  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data, snapshot  # noqa: E402
from app.utils import html_chunks, html_cut  # noqa: E402
from app.keyboards import get_admin_inline_keyboard, get_main_menu_keyboard  # noqa: E402
from app.economy.sheet import (  # noqa: E402
    _parse_shop_from_sheet, _patch_sheet_level_yield, extract_asset_stats, set_city_asset,
)
from app.economy.up import run_weekly_up_for_city  # noqa: E402
from app.economy.upflow import run_up_all  # noqa: E402
from app.economy.views import format_city_asset_view  # noqa: E402

WIN = "winchester_parliamentarian"
GROUP = -100900

# شیت نمونه به سبک شیت VIP (بدون بخش شاپ) — همان الگوی خطوطی که در آپ وینچستر زباله شدند
SHEET = """🏦 ﴿ خزانه ﴾ (3)
|💰|-| موجودی | : 5000
|📥|-| بازدهی | (3) : 3000

🍽 ﴿ آشپزخانه ﴾ (3)
|🥣|-| موجودی | : 2000
|📥|-| بازدهی | (3) : 3600

🍽 ﴿ قلعه﴾ (1)

🏗 ﴿ کارگاه تولیدی ﴾
|🪚|-| چوب بری | (1) : 100

🛡 ﴿ پادگان ﴾
|🗡|-| شبه نظامی | (5) : 500
|⚔️|-| شمشیرزن | (2) : 200
|🐴|-| سواره‌نظام زره پوش | (1) : 50

|🛡|~| پیاده‌نظام |
|🗡|-| شبه نظامی | : 300
|⚔️|-| شمشیرزن | : 250
|🐴|~| سواره‌نظام زره پوش | : 75
"""

_TAG = re.compile(r"<(/?)(b|i|u|s|code|pre|a|tg-spoiler|blockquote)(?:\s[^<>]*)?>")


def html_problem(txt: str):
    """مثل پارسر HTML تلگرام: «<» خام یا تگ بسته‌نشده/نامتوازن → متن خطا؛ سالم → None."""
    stack, pos = [], 0
    while True:
        i = txt.find("<", pos)
        if i < 0:
            break
        m = _TAG.match(txt, i)
        if not m:
            return f"«<» خام در {i}: {txt[i:i + 20]!r}"
        closing, name = m.group(1), m.group(2)
        if closing:
            if not stack or stack[-1] != name:
                return f"تگ بسته‌ی نامتوازن </{name}>"
            stack.pop()
        else:
            stack.append(name)
        pos = m.end()
    return f"Can't find end tag for {stack}" if stack else None


def fresh_world():
    apply_data({"codes": {}, "users": {}, "groups": {}})
    for d in (state.CITY_ASSETS, state.pending_confirms, state.UP_SNAPSHOTS, state.AUTO_CITIES,
              state.CITY_BUFFS, state.PENDING_TRADES):
        d.clear()


def stats():
    return state.CITY_ASSETS[WIN]["stats"]


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        fresh_world()
        await dp.storage.close()
        state.PLAYER_CODES["AOWWIN1"] = WIN
        state.GROUPS[GROUP] = {"city": WIN, "code": "AOWWIN1", "commanders": [], "commander": None}

    async def send(self, update):
        await dp.feed_update(bot, update)

    def assert_all_html_ok(self):
        for t in self.tg.texts():
            self.assertIsNone(html_problem(t), t[-300:])
            self.assertLessEqual(len(t), 4096)


# ---------------------------------------------------------------- ۱. HTML
class HtmlTests(Base):
    def test_html_chunks_never_leave_open_tags(self):
        body = "\n".join(f"<b>عنوان {i}</b> <i>توضیح {'ا' * 40}</i>" for i in range(200))
        body = "<blockquote>" + body + "</blockquote>"
        parts = html_chunks(body, 1000)
        self.assertGreater(len(parts), 1)
        for p in parts:
            self.assertLessEqual(len(p), 1000)
            self.assertIsNone(html_problem(p))
        self.assertIsNone(html_problem(html_cut(body, 1000)))

    async def test_sheet_text_is_escaped(self):
        set_city_asset(WIN, SHEET + "\nیادداشت: <b> قدرت ارتش > 500 & <نامعلوم")
        txt = format_city_asset_view(WIN, viewer=ADMIN)
        self.assertIsNone(html_problem(txt))
        self.assertIn("&lt;نامعلوم", txt)

    async def test_long_group_asset_view_does_not_cut_tags(self):
        """کرش اصلی: «دارایی» در گروه، شیت بلند → body[:3500] وسط <b> بلوک ویژگی قلعه می‌برید."""
        # طول را طوری جارو می‌کنیم که برش ۳۵۰۰ از روی بلوک «🏰 <b>ویژگی قلعه</b> <i>…</i>» رد شود
        state.CITY_ASSETS[WIN] = {"text": SHEET, "stats": {}}
        trait_at = format_city_asset_view(WIN, viewer=ADMIN).index("🏰")
        for pad in range(3500 - trait_at - 150, 3500 - trait_at + 10, 7):
            self.tg.clear()
            filler = ("ا" * 60 + "\n") * (pad // 61) + "ا" * (pad % 61)
            state.CITY_ASSETS[WIN] = {"text": SHEET + filler, "stats": {}}
            await self.send(message(ADMIN, "دارایی", chat_id=GROUP, chat_type="supergroup"))
            self.assertTrue(self.tg.texts())
            self.assert_all_html_ok()
            self.assertIn("ویژگی قلعه", "".join(self.tg.texts()))

    async def test_personal_asset_callback_html_ok(self):
        state.CITY_ASSETS[WIN] = {"text": SHEET * 6 + "<script>", "stats": {}}
        await self.send(callback(ADMIN, "asset_ci:parliamentarian:0"))
        self.assert_all_html_ok()


# ---------------------------------------------------------------- ۲. پارس شیت
class SheetParseTests(Base):
    async def test_shop_not_parsed_from_sheet_body(self):
        """قبلاً بدون بخش «شاپ» کل شیت پارس می‌شد → «🍽 ﴿ قلعه﴾: +1»، «📥|-| بازدهی: +3600»."""
        self.assertEqual(_parse_shop_from_sheet(SHEET), {})
        shop = _parse_shop_from_sheet(SHEET + "\n💵💵💵💵\nشاپ :\nمزدور شمشیرزن 50 (10)")
        self.assertEqual(shop, {"شمشیرزن": 10})

    async def test_extract_has_no_junk_and_sane_levels(self):
        raw = extract_asset_stats(SHEET + "\n|🗡|-| نیزه دار | (250)")
        for k in raw:
            self.assertFalse(any(m in k for m in ("﴿", "|", "📥")), k)
        self.assertEqual(raw["شبه نظامی"], 300)
        self.assertEqual(raw["yield:شبه نظامی"], 500)
        self.assertEqual(raw["__levels__"]["شبه نظامی"], 5)
        self.assertNotIn("نیزه دار", raw["__levels__"], "لول ۲۵۰ برای کمپ با سقف ۱۰ = تعداد نیرو، نه لول")

    async def test_set_city_asset_rebuilds_yields_and_levels(self):
        state.CITY_ASSETS[WIN] = {
            "text": "", "stats": {},
            "yields": {"🍽 ﴿ قلعه﴾": 1, "📥|-| بازدهی": 3600, "ناو جنگی": 999},
            "levels": {"شبه نظامی": 250, "ناو جنگی": 3},
            "shop": {"🪚|-| چوب بری": 100},
        }
        set_city_asset(WIN, SHEET)
        entry = state.CITY_ASSETS[WIN]
        self.assertEqual(entry["yields"]["شبه نظامی"], 500)
        self.assertNotIn("ناو جنگی", entry["yields"], "بازدهی یتیم شیت قبلی باید حذف شود")
        self.assertNotIn("🍽 ﴿ قلعه﴾", entry["yields"])
        self.assertEqual(entry["levels"]["شبه نظامی"], 5)
        self.assertNotIn("ناو جنگی", entry["levels"])
        self.assertEqual(entry["shop"], {})

    async def test_camp_upgrade_does_not_overwrite_troop_stock(self):
        """«کمپ نیرو … تعداد بازدهی رو میزاره جای موجودی»: کمپ بدون خط در شیت → خط لیست نیرو بازنویسی می‌شد."""
        sheet = SHEET + "|🔱|-| نیزه دار | : 120\n"
        out = _patch_sheet_level_yield(sheet, "نیزه دار", 1, 100)
        self.assertIn("| نیزه دار | : 120", out)
        raw = extract_asset_stats(out)
        self.assertEqual(raw["نیزه دار"], 120)
        self.assertEqual(raw["yield:نیزه دار"], 100)
        # دفعه‌ی بعد همان خط کمپ به‌روز می‌شود (خط تکراری ساخته نمی‌شود)
        out2 = _patch_sheet_level_yield(out, "نیزه دار", 2, 200)
        self.assertEqual(out2.count("نیزه دار"), 2)
        self.assertEqual(extract_asset_stats(out2)["yield:نیزه دار"], 200)
        self.assertEqual(extract_asset_stats(out2)["نیزه دار"], 120)

    async def test_troop_decrease_in_sheet_is_applied(self):
        set_city_asset(WIN, SHEET)
        set_city_asset(WIN, SHEET.replace("| شبه نظامی | : 300", "| شبه نظامی | : 100"))
        self.assertEqual(stats()["شبه نظامی"], 100)
        set_city_asset(WIN, SHEET.replace("| شبه نظامی | : 300", "| شبه نظامی | : 0"))
        self.assertEqual(stats()["شبه نظامی"], 0, "صفر صریح در شیت = صفر (نه نگه‌داشتن قبلی)")


# ---------------------------------------------------------------- ۲. آپ
class UpTests(Base):
    async def test_clean_up_has_no_junk_and_correct_camp_yield(self):
        set_city_asset(WIN, SHEET)
        log = run_weekly_up_for_city(WIN, force=True)
        self.assertTrue(log.startswith("✅"), log)
        self.assertNotIn("﴿", log)
        self.assertNotIn("📥", log)
        self.assertEqual(stats()["شبه نظامی"], 800)
        self.assertEqual(stats()["شمشیرزن"], 450)
        self.assertEqual(stats()["سواره‌نظام زره پوش"], 125)
        self.assertFalse([k for k in stats() if state.is_junk_key(k)])

    async def test_corrupt_level_is_not_multiplied(self):
        """+۳۷٬۵۰۰ = بازدهی جدول ۱۵۰ × «لول» ۲۵۰ (که در واقع تعداد نیرو بود)."""
        set_city_asset(WIN, SHEET.replace("|🗡|-| شبه نظامی | (5) : 500\n", ""))
        state.CITY_ASSETS[WIN]["levels"]["شبه نظامی"] = 250
        state.CITY_ASSETS[WIN]["yields"]["🍽 ﴿ قلعه﴾"] = 1
        log = run_weekly_up_for_city(WIN, force=True)
        self.assertTrue(log.startswith("✅"), log)
        self.assertEqual(stats()["شبه نظامی"], 300)
        self.assertNotIn("37,500", log)
        self.assertNotIn("🍽 ﴿ قلعه﴾", stats())

    async def test_casualties_not_resurrected_by_sheet_max(self):
        """قبلاً max(موجودی، عدد شیت) → تلفات ثبت‌شده با آپ برمی‌گشت."""
        set_city_asset(WIN, SHEET)
        stats()["شبه نظامی"] = 50   # تلفات؛ متن شیت هنوز ۳۰۰ (مثلاً patch نخورده)
        run_weekly_up_for_city(WIN, force=True)
        self.assertEqual(stats()["شبه نظامی"], 550)

    async def test_suspicious_yield_holds_without_changes(self):
        set_city_asset(WIN, SHEET.replace("| شمشیرزن | (2) : 200", "| شمشیرزن | (2) : 30000"))
        before = dict(stats())
        log = run_weekly_up_for_city(WIN, force=True)
        self.assertTrue(log.startswith("⏸"), log)
        self.assertIn("شمشیرزن", log)
        self.assertEqual(stats(), before, "آپ متوقف‌شده نباید چیزی را عوض کند")
        self.assertNotIn(WIN, state.UP_SNAPSHOTS, "بکاپ آپ قبلی نباید با آپ متوقف‌شده جابه‌جا شود")
        log = run_weekly_up_for_city(WIN, force=True, allow_suspicious=True)
        self.assertTrue(log.startswith("✅"), log)
        self.assertEqual(stats()["شمشیرزن"], 30250)

    async def test_ratio_guard_for_resources(self):
        set_city_asset(WIN, SHEET.replace("| چوب بری | (1) : 100", "| چوب بری | (1) : 2000")
                       + "\n|🪵|~| چوب | : 100")
        log = run_weekly_up_for_city(WIN, force=True)
        self.assertTrue(log.startswith("⏸"), log)
        self.assertIn("چوب", log)


class UpFlowTests(Base):
    async def test_admin_sees_hold_and_can_force(self):
        set_city_asset(WIN, SHEET.replace("| شمشیرزن | (2) : 200", "| شمشیرزن | (2) : 30000"))
        await self.send(callback(ADMIN, f"up_one:{WIN}"))
        self.assertIn("⏸", self.tg.last_text())
        self.assertIn(f"up_force:{WIN}", self.tg.buttons())
        self.assertEqual(self.tg.buttons()[-1], "back_to_admin")
        self.assertEqual(stats()["شمشیرزن"], 250)
        self.assertFalse([c for c in self.tg.sent("SendMessage") if c.chat_id == GROUP],
                         "رسید آپ متوقف‌شده نباید به گروه شهر برود")
        self.assert_all_html_ok()
        self.tg.clear()
        await self.send(callback(ADMIN, f"up_force:{WIN}"))
        self.assertEqual(stats()["شمشیرزن"], 30250)
        self.assert_all_html_ok()

    async def test_up_all_reports_held_city(self):
        set_city_asset(WIN, SHEET.replace("| شمشیرزن | (2) : 200", "| شمشیرزن | (2) : 30000"))
        state.AUTO_CITIES[WIN] = True
        body = await run_up_all()
        self.assertIn("⏸", body)
        self.assertIsNone(html_problem(body))
        self.assertEqual(stats()["شمشیرزن"], 250)
        self.assertFalse([c for c in self.tg.sent("SendMessage") if c.chat_id == GROUP])


# ---------------------------------------------------------------- پاک‌سازی + ذخیره
class PurgeTests(Base):
    async def test_junk_keys_purged_on_load_and_snapshot_roundtrip(self):
        apply_data({"city_assets": {WIN: {
            "text": SHEET,
            "stats": {"شبه نظامی": 300, "🍽 ﴿ قلعه﴾": 1, "📥|-| بازدهی": 3600, "🪚|-| چوب بری": 100},
            "yields": {"شبه نظامی": 500, "📥|-| بازدهی": 3600},
            "levels": {"شبه نظامی": 5, "🍽 ﴿ قلعه﴾": 1},
            "shop": {"🪚|-| چوب بری": 100},
        }}})
        entry = state.CITY_ASSETS[WIN]
        self.assertEqual(entry["stats"], {"شبه نظامی": 300})
        self.assertEqual(entry["yields"], {"شبه نظامی": 500})
        self.assertEqual(entry["levels"], {"شبه نظامی": 5})
        self.assertEqual(entry["shop"], {})
        snap = snapshot()
        apply_data(snap)
        self.assertEqual(state.CITY_ASSETS[WIN]["yields"], {"شبه نظامی": 500})

    async def test_guard_settings_survive_restart(self):
        state.SETTINGS["up_guard_troop_max"] = "8000"
        snap = snapshot()
        state.SETTINGS["up_guard_troop_max"] = "5000"
        apply_data(snap)
        self.assertEqual(state.SETTINGS.get("up_guard_troop_max"), "8000")


# ---------------------------------------------------------------- ۳. کیبوردها
class KeyboardTests(unittest.TestCase):
    def test_admin_panel_layout(self):
        rows = get_admin_inline_keyboard().inline_keyboard
        self.assertEqual(len(rows[-1]), 1)
        self.assertEqual(rows[-1][0].callback_data, "adm_logout")
        self.assertTrue(all(len(r) <= 2 for r in rows))
        cbs = [b.callback_data for r in rows for b in r]
        self.assertEqual(len(cbs), len(set(cbs)))
        emojis = [b.text.split()[0] for r in rows for b in r]
        self.assertEqual(len(emojis), len(set(emojis)), "ایموجی تکراری در پنل ادمین")

    def test_main_menu_close_is_last_and_alone(self):
        rows = get_main_menu_keyboard().inline_keyboard
        self.assertEqual([b.callback_data for b in rows[-1]], ["menu:close"])
