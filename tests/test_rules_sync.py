"""هم‌خوانی جدول‌های اقتصادی، مصرف غذا و ۳۰ قلعه/لرد با rules.txt."""
import unittest

from tests.fakebot import setup_env

setup_env()

from tests.fakebot import ADMIN  # noqa: E402

import app.handlers  # noqa: E402,F401
from app import state  # noqa: E402
from app.storage import apply_data  # noqa: E402
from app.castles import CASTLE_META, CASTLE_TRAITS, CHARACTER_TRAITS, castle_trait_block  # noqa: E402
from app.factions import cities_by_faction, seed_default_cities  # noqa: E402
from app.economy.costs import army_food_need  # noqa: E402
from app.economy.rules import SPECIAL_UNITS, UPGRADE_TABLE  # noqa: E402
from app.economy.sheet import set_city_asset  # noqa: E402
from app.economy.up import run_weekly_up_for_city  # noqa: E402

# نام ساختمان → (هزینه، بازدهی، لول مکس) دقیقاً طبق rules.txt (None = در قوانین ذکر نشده)
RULES = {
    "خزانه": ({"coin": 1500, "wood": 25, "stone": 50, "iron": 25, "pop": 50}, 1000, 20),
    "تجارتخانه": ({"coin": 700, "wood": 50, "pop": 25}, 150, 15),
    "بندر": ({"coin": 1000, "wood": 50, "iron": 50, "pop": 50}, 500, 20),
    "آشپزخانه": ({"coin": 600, "stone": 50, "pop": 50}, 500, 25),
    "دهکده": ({"coin": 400, "wood": 25, "stone": 25}, 100, 40),
    "چوب بری": ({"coin": 500, "stone": 50, "pop": 25}, 100, 10),
    "معدن سنگ": ({"coin": 600, "wood": 50, "pop": 25}, 100, 10),
    "معدن آهن": ({"coin": 600, "wood": 25, "stone": 25, "pop": 25}, 100, 10),
    "پوشاک سازی": ({"coin": 700, "wood": 25, "pop": 50}, 100, 10),
    "باروت سازی": ({"coin": 800, "stone": 50, "iron": 25, "pop": 50}, 100, 10),
    "انبار": ({"coin": 500, "stone": 25, "pop": 25}, 500, None),
    "دانشکده افسری": ({"coin": 600}, 5, None),
    "مجمع نخبگان": ({"coin": 700}, 2, None),
    "دانشگاه پزشکی": ({"coin": 800}, 3, None),
    "اصطبل": ({"coin": 400, "wood": 50}, 100, 10),
    "شبه نظامی": ({"coin": 500, "wood": 50, "pop": 50, "cloth": 25}, 150, 10),
    "شمشیرزن": ({"coin": 600, "iron": 60, "pop": 60, "cloth": 50}, 100, 10),
    "نیزه دار": ({"coin": 700, "wood": 70, "pop": 70, "cloth": 50}, 75, 10),
    "رایفلدار": ({"coin": 800, "powder": 80, "pop": 80, "cloth": 50}, 50, 10),   # تفنگدار
    "افسر": ({"coin": 600, "wood": 60, "pop": 60, "cloth": 25}, 25, 10),
    "سواره نظام شمشیرزن": ({"coin": 500, "wood": 50, "pop": 50, "horse": 100}, 150, 10),
    "سواره‌نظام زره پوش": ({"coin": 600, "iron": 60, "pop": 60, "cloth": 50, "horse": 100}, 100, 10),
    "سواره‌نظام تفنگدار": ({"coin": 700, "powder": 70, "pop": 70, "cloth": 50, "horse": 100}, 50, 10),
    "ویژه": ({"coin": 900, "wood": 100, "pop": 100, "cloth": 50, "powder": 100}, 50, 10),
    "توپ سبک": ({"coin": 700, "powder": 70, "iron": 50, "pop": 50}, 8, 10),
    "توپ محاصره": ({"coin": 800, "powder": 80, "iron": 60, "pop": 60}, 4, 10),
    "توپ سنگین": ({"coin": 900, "powder": 90, "iron": 70, "pop": 70}, 2, 10),
    "قایق": ({"coin": 500, "pop": 60, "cloth": 25, "iron": 40}, 5, 10),
    "کشتی جنگی": ({"coin": 600, "pop": 60, "cloth": 25, "iron": 40, "powder": 50}, 3, 10),
    "ناو جنگی": ({"coin": 700, "pop": 70, "cloth": 50, "iron": 40, "powder": 60}, 2, 10),
    "کشتی سلطنتی": ({"coin": 800, "pop": 80, "cloth": 50, "iron": 60, "powder": 80}, 1, 10),
}
_RES = ("coin", "wood", "stone", "iron", "pop", "cloth", "powder", "horse")

SIDES = {
    "monarchist": {"london", "pembroke", "leicester", "nottingham", "bristol",
                   "colchester", "oxford", "liverpool", "cambridge", "edinburgh"},
    "parliamentarian": {"norwich", "york", "dover", "gloucester", "leeds",
                        "newcastle", "bridgwater", "winchester", "exeter", "manchester"},
    "france": {"paris", "caen", "nantes", "brest", "amiens"},
    "ireland": {"armagh", "cork", "dublin", "waterford", "limerick"},
}


class EconomyTableTests(unittest.TestCase):
    def test_costs_yields_and_max_levels_match_rules(self):
        for name, (cost, y, mx) in RULES.items():
            t = UPGRADE_TABLE[name]
            got = {k: t[k] for k in _RES if t.get(k)}
            self.assertEqual(got, cost, f"هزینه {name}")
            self.assertEqual(t["yield"], y, f"بازدهی {name}")
            if mx is not None:
                self.assertEqual(t.get("max"), mx, f"لول مکس {name}")
        self.assertEqual(UPGRADE_TABLE["تجارتخانه"]["limit"], "۳۰۰۰ سکه / ۳۰۰ منبع")
        self.assertEqual(UPGRADE_TABLE["بندر"]["limit"], "۱۵ کشتی")

    def test_special_camp_cost_and_yields(self):
        camp = RULES["ویژه"][0]
        want_y = {"inf": 100, "cav": 50, "arty": 5, "ship": 2}
        for name, meta in SPECIAL_UNITS.items():
            t = UPGRADE_TABLE[name]
            self.assertEqual({k: t[k] for k in _RES if t.get(k)}, camp, f"هزینه کمپ ویژه {name}")
            self.assertEqual(t["yield"], want_y[meta["cat"]], f"بازدهی کمپ ویژه {name}")


class FoodTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        apply_data({"codes": {}, "users": {}, "groups": {}})
        state.CITY_ASSETS.clear()
        state.CITY_BUFFS.clear()

    def test_food_by_unit_type(self):
        need = army_food_need({
            "شبه نظامی": 200, "افسر": 100,                     # پیاده ×۱
            "سواره‌نظام زره پوش": 75,                          # سواره ×۲
            "ویژه": 10, "کلداستریم گارد": 20, "کیوراسیرها": 5,  # ویژه ×۳
            "توپ سبک": 8, "قایق": 5, "اسب": 300, "سکه": 9000,   # غذا نمی‌خورند
        })
        self.assertEqual((need["inf"], need["cav"], need["elite"]), (300, 75, 35))
        self.assertEqual(need["food"], 300 + 150 + 105)

    def test_only_soldier_total_falls_back_to_infantry(self):
        self.assertEqual(army_food_need({"سربازان": 400})["food"], 400)

    async def test_up_deducts_rules_food(self):
        city = "york_parliamentarian"
        set_city_asset(city, "|🥣|-| موجودی | : 2000\n"
                             "|🛡|~| پیاده‌نظام |\n"
                             "|🗡|-| شبه نظامی | : 300\n"
                             "|🐴|~| سواره‌نظام زره پوش | : 75\n")
        state.CITY_ASSETS[city]["stats"]["غذا"] = 2000
        run_weekly_up_for_city(city, force=True)
        self.assertEqual(state.CITY_ASSETS[city]["stats"]["غذا"], 2000 - 300 - 150)
        self.assertIn("سواره 75×۲", state.CITY_ASSETS[city]["changes"][-1])


class CastleTests(unittest.TestCase):
    def test_thirty_castles_per_side(self):
        seed_default_cities()
        self.assertEqual(set(CHARACTER_TRAITS), set().union(*SIDES.values()))
        self.assertEqual(set(CASTLE_TRAITS), set(CHARACTER_TRAITS))
        for side, bases in SIDES.items():
            have = {c.rsplit("_", 1)[0] for c in cities_by_faction(side)}
            self.assertTrue(bases <= have, f"{side}: {bases - have}")

    def test_lords_from_character_list(self):
        self.assertEqual(CHARACTER_TRAITS["winchester"]["lord"], "John Desborough")
        self.assertEqual(CHARACTER_TRAITS["liverpool"]["lord"], "Prince Rupert of the Rhine")
        self.assertEqual(CHARACTER_TRAITS["dover"]["lord"], "Sir William Waller")
        self.assertEqual(CHARACTER_TRAITS["limerick"]["lord"], "Sir George Hamilton")
        self.assertEqual(CASTLE_META["nantes_france"]["char"], "Marguerite, Duchess of Rohan")
        vip = {k for k, v in CHARACTER_TRAITS.items() if v["tier"].startswith("VIP")}
        self.assertEqual(vip, {"london", "pembroke", "norwich", "york", "paris", "armagh"})
        for k, v in CHARACTER_TRAITS.items():
            self.assertTrue(v["buff"] and v["nerf"] and v["role"], k)

    def test_lord_shown_under_sheet_only_to_allowed_viewers(self):
        block = castle_trait_block("armagh_ireland", ADMIN)
        self.assertIn("لرد: Owen Roe O'Neill", block)
        self.assertIn("🌟 باف ویژه", block)
        self.assertEqual(castle_trait_block("armagh_ireland", None), "")
