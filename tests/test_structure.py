"""ساختار پروژه: ترتیب ثبت هندلرها باید با فایل تکی اصلی (main-104-optimized.py) یکی باشد.

در aiogram اولین هندلری که فیلترش بخورد اجرا می‌شود؛ پس جابه‌جایی ترتیب می‌تواند رفتار را عوض کند.
تنها جابه‌جایی مجاز: هندلرهایی که فقط به یک State اختصاصی گوش می‌دهند (با هم تداخل ندارند).
"""
import json
import os
import unittest

from tests.fakebot import setup_env

setup_env()

from aiogram.fsm.state import State  # noqa: E402

import app.handlers  # noqa: E402,F401
from app.loader import dp  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "original_handler_order.json")


def registered():
    out = {}
    for name, obs in dp.observers.items():
        out[name] = list(obs.handlers)
    return out


def state_only(h):
    return any(isinstance(f.callback, State) for f in h.filters or [])


class StructureTests(unittest.TestCase):
    def test_all_original_handlers_present_in_order(self):
        expected = json.load(open(FIXTURE, encoding="utf-8"))
        current = registered()
        for kind, names in expected.items():
            handlers = current.get(kind, [])
            got = [h.callback.__name__ for h in handlers]
            self.assertEqual(sorted(got), sorted(names), f"{kind}: هندلر کم/زیاد شده")
            # ترتیب، با چشم‌پوشی از هندلرهای state-اختصاصی
            fixed = {h.callback.__name__ for h in handlers if not state_only(h)}
            self.assertEqual(
                [n for n in got if n in fixed],
                [n for n in names if n in fixed],
                f"{kind}: ترتیب هندلرهای عمومی عوض شده",
            )


if __name__ == "__main__":
    unittest.main()
