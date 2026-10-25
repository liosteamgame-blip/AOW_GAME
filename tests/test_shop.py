"""هم‌خوانی شاپ با rules.txt: کاتالوگ، بازدهی هفتگی در برابر اعطای یک‌باره، سقف خرید، ضریب لیدربورد."""
import os
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN, FakeTelegram, message  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.loader import bot, dp  # noqa: E402
from app.storage import apply_data  # noqa: E402
from app.economy import shop_catalog as sc  # noqa: E402
from app.economy.rules import SPECIAL_UNITS  # noqa: E402
from app.economy.sheet import (  # noqa: E402
    _parse_shop_from_sheet, _parse_shop_packs, enrich_shop_packs, set_city_asset, shop_weekly_yields,
)
from app.economy.up import run_weekly_up_for_city  # noqa: E402
from app.economy.views import _LB_MIL, _LB_NAV, _LB_WEIGHT  # noqa: E402

WIN = "winchester_parliamentarian"
GROUP = -100910
RULES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules.txt")

SHEET = """🏦 ﴿ خزانه ﴾ (3)
|💰|-| موجودی | : 5000

🛡 ﴿ پادگان ﴾
|🗡|-| شبه نظامی | (5) : 500

|🛡|~| پیاده‌نظام |
|🗡|-| شبه نظامی | : 300
|❕|-| افسر | : 10
"""


def shop_section() -> str:
    t = open(RULES, encoding="utf-8").read()
    s = t[t.index("قوانین شاپ | خاکستر"):t.index("[6/11/2026 4:06 PM] information")]
    s = s[s.index("《"):]  # متن قوانین شاپ پیش از اولین پست، پک نیست
    # فقط پست‌ها (و خط قیمت‌شان)؛ پیام‌های کانال بین پست‌ها («خریداری شد»، اطلاعیه‌ها) پک نیستند
    out, inside = [], False
    for ln in s.splitlines():
        if ln.startswith(">"):  # نقل‌قول پیام «خریداری شد»
            continue
        if "《" in ln:
            inside = True
        if inside:
            out.append(ln)
        if "قیمت" in ln:
            inside = False
    return "\n".join(out)


class CatalogTests(unittest.TestCase):
    def test_every_shop_post_in_rules_is_in_catalog(self):
        body, unknown = sc.collapse_shop_posts(shop_section())
        self.assertEqual(unknown, [])
        packs = enrich_shop_packs(_parse_shop_packs("شاپ:\n" + body))
        seen = {p.get("catalog") for p in packs}
        self.assertEqual([i["fa"] for i in sc.CATALOG if i["fa"] not in seen], [])
        self.assertEqual([p["name"] for p in packs if not p.get("catalog")], [])

    def test_catalog_numbers_match_rules(self):
        self.assertEqual(sc.find_item("چریک هلندی")["count"], 200)
        self.assertEqual(sc.find_item("Dutch Guerrillas")["yield"], 100)
        self.assertEqual(sc.find_item("توپ ریگای سوئدی")["yield"], 3)
        self.assertEqual(sc.find_item("گارد سایه")["yield"], 50)
        self.assertEqual(sc.find_item("پک منابع طلایی")["grant"]["باروت"], 500)
        self.assertEqual(sc.find_item("استارتر برنزی")["grant"], {"سکه": 1500})
        self.assertEqual(sc.find_item("ریچارد بلک‌ثورْن")["cat"], "hero")
        self.assertEqual(sc.LIMITS["characters"], 3)  # اعلام ۹/۲۹: سقف کاراکتر ۳

    def test_escort_and_group_counts_are_not_weekly(self):
        """قبلاً تعداد ارتش همراه هیرو و نیروی گروهک هر آپ دوباره اضافه می‌شد."""
        y = _parse_shop_from_sheet(
            "💵💵\nشاپ :\nفرمانده ویلیام کاوندیش\n5 افسر\n50 سوارنظام تفنگدار\n"
            "گروهک مزدوری سپاه هایلند اسکاتلند\nمزدور چریک هلندی\nوزیر ادوارد هاید"
        )
        self.assertEqual(y, {"چریک هلندی": 100})

    def test_explicit_admin_numbers_win_over_catalog(self):
        packs = enrich_shop_packs(_parse_shop_packs("شاپ:\nمزدور چریک هلندی 150 (80)"))
        self.assertEqual((packs[0]["count"], packs[0]["yield"]), (150, 80))
        self.assertEqual(shop_weekly_yields([{"name": "x", "yield": 0, "army": [{"unit": "a", "count": 9}]}]), {})

    def test_limit_warnings(self):
        self.assertEqual(sc.limit_warnings(["hero", "minister", "hero", "merc_group", "merc", "merc"]), [])
        self.assertTrue(sc.limit_warnings(["starter", "starter"]))
        self.assertTrue(sc.limit_warnings(["hero", "hero", "minister", "minister"]))
        self.assertTrue(sc.limit_warnings(["merc_group", "merc_group", "merc"]))
        self.assertTrue(sc.limit_warnings(["merc"] * 4))
        self.assertTrue(sc.limit_warnings(["army", "weapon"]))


class LeaderboardTests(unittest.TestCase):
    def test_military_weights_are_official_coefficients(self):
        official = {"شبه نظامی": 2, "شمشیرزن": 4, "نیزه دار": 5, "افسر": 6, "رایفلدار": 7,
                    "سواره‌نظام شمشیرزن": 3, "سواره‌نظام زره پوش": 5, "سواره‌نظام تفنگدار": 5,
                    "توپ سبک": 5, "توپ سنگین": 8, "توپ محاصره": 7,
                    "قایق": 3, "کشتی جنگی": 7, "ناو جنگی": 9, "کشتی سلطنتی": 10,
                    "کلداستریم گارد": 8, "کیوراسیرها": 9, "گاردپادشاهی فرانسه": 9, "کشتی بریگانتین": 5}
        for k, v in official.items():
            self.assertEqual(_LB_WEIGHT[k], v, k)
        for name, meta in SPECIAL_UNITS.items():
            self.assertIn(name, _LB_NAV if meta["cat"] == "ship" else _LB_MIL)


class ShopCommitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tg = FakeTelegram(bot)
        apply_data({"codes": {}, "users": {}, "groups": {}})
        for d in (state.CITY_ASSETS, state.pending_confirms, state.UP_SNAPSHOTS, state.AUTO_CITIES,
                  state.CITY_BUFFS):
            d.clear()
        await dp.storage.close()
        state.PLAYER_CODES["AOWWIN9"] = WIN
        state.GROUPS[GROUP] = {"city": WIN, "code": "AOWWIN9", "commanders": [], "commander": None}
        set_city_asset(WIN, SHEET)

    async def set_shop(self, body):
        self.tg.clear()
        await dp.feed_update(bot, message(ADMIN, "ست شاپ\n" + body, chat_id=GROUP, chat_type="supergroup"))
        return "\n".join(self.tg.texts())

    def stats(self):
        return state.CITY_ASSETS[WIN]["stats"]

    async def test_forwarded_post_grants_once_then_weekly_yield_only(self):
        post = ("《 #یونیت_مزدور 》\n\n⚜️چریک هلندی - Dutch Guerrillas\n\n"
                "⬅️نیرویی سبک … با تفنگ فتیله‌ای\n🟠تعداد یونیت ها: 200 نفر\n⚫️بازدهی: 100 نفر\n💰قیمت: 200T")
        out = await self.set_shop(post + "\nپک منابع طلایی")
        self.assertIn("اعطای یک‌باره", out)
        self.assertEqual(self.stats()["چریک هلندی"], 200)
        self.assertEqual(self.stats()["سکه"], 5000 + 4000)
        # ارسال دوباره‌ی همان لیست + یک هیرو جدید: فقط هیرو اعطا می‌شود
        await self.set_shop("مزدور چریک هلندی\nپک منابع طلایی\nفرمانده ادوارد وینچستر")
        self.assertEqual(self.stats()["چریک هلندی"], 200)
        self.assertEqual(self.stats()["سکه"], 9000)
        self.assertEqual(self.stats()["توپ ویرانگر"], 6)
        run_weekly_up_for_city(WIN, force=True)
        self.assertEqual(self.stats()["چریک هلندی"], 300)
        self.assertEqual(self.stats()["توپ ویرانگر"], 6, "ارتش همراه هیرو بازدهی هفتگی ندارد")

    async def test_legacy_packs_are_not_granted_and_stale_shop_ignored(self):
        entry = state.CITY_ASSETS[WIN]
        entry["shop_packs"] = [{"kind": "hero", "name": "جیمز باتلر",
                                "army": [{"unit": "افسر", "count": 5, "yield": 0}], "yield": 0}]
        entry["shop"] = {"افسر": 5}  # ذخیره‌ی نسخه‌ی قبل: تعداد ارتش همراه به‌عنوان بازدهی
        run_weekly_up_for_city(WIN, force=True)
        self.assertEqual(self.stats()["افسر"], 10)
        await self.set_shop("فرمانده جیمز باتلر")
        self.assertEqual(self.stats()["افسر"], 10)

    async def test_limit_warning_and_admin_note_shown(self):
        out = await self.set_shop("استارتر طلایی\nاستارتر برنزی\nکاراکتر چارلز اول")
        self.assertIn("بیش از سقف خرید", out)
        self.assertIn("لول اقتصادی", out)
        self.assertIn("+80٪", out)


if __name__ == "__main__":
    unittest.main()
