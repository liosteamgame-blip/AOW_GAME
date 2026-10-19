"""ساختار پروژه: ترتیب ثبت هندلرها باید با فایل تکی اصلی (main-104-optimized.py) یکی باشد.

در aiogram اولین هندلری که فیلترش بخورد اجرا می‌شود؛ پس جابه‌جایی ترتیب می‌تواند رفتار را عوض کند.
تنها جابه‌جایی مجاز: هندلرهایی که فقط به یک State اختصاصی گوش می‌دهند (با هم تداخل ندارند).

هندلرهای جدید (فیچرها) باید آگاهانه در fixtures/added_handlers.json ثبت شوند؛
هندلرهای اصلی همه باید باشند و ترتیب نسبی‌شان عوض نشود.
"""
import ast
import json
import os
import pathlib
import unittest

from tests.fakebot import setup_env

setup_env()

from aiogram.fsm.state import State  # noqa: E402

import app.handlers  # noqa: E402,F401
from app.loader import dp  # noqa: E402

HERE = os.path.dirname(__file__)
FIXTURE = os.path.join(HERE, "fixtures", "original_handler_order.json")
ADDED = os.path.join(HERE, "fixtures", "added_handlers.json")
ROOT = pathlib.Path(HERE).parent


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
        added = json.load(open(ADDED, encoding="utf-8"))
        current = registered()
        for kind in set(expected) | set(added) | {k for k, v in current.items() if v}:
            names = expected.get(kind, [])
            handlers = current.get(kind, [])
            got = [h.callback.__name__ for h in handlers]
            extra = sorted(set(got) - set(names))
            self.assertEqual(sorted(set(names) - set(got)), [], f"{kind}: هندلر اصلی حذف شده")
            self.assertEqual(extra, sorted(added.get(kind, [])),
                             f"{kind}: هندلر جدید باید در added_handlers.json ثبت شود")
            fixed = {h.callback.__name__ for h in handlers if not state_only(h)}
            self.assertEqual(
                [n for n in got if n in fixed and n in names],
                [n for n in names if n in fixed],
                f"{kind}: ترتیب هندلرهای عمومی عوض شده",
            )

    def test_new_message_handlers_before_fallback(self):
        got = [h.callback.__name__ for h in dp.observers["message"].handlers]
        self.assertEqual(got[-1], "fallback_handler", "fallback باید آخرین هندلر پیام باشد")

    def test_import_layers(self):
        """هر ماژول app فقط از ماژول‌های قبل از خودش در docs/module_order.txt import می‌کند."""
        order = [ln.strip() for ln in (ROOT / "docs" / "module_order.txt").read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        pos = {m: i for i, m in enumerate(order)}
        problems = []
        for path in (ROOT / "app").rglob("*.py"):
            mod = ".".join(path.relative_to(ROOT).with_suffix("").parts)
            if mod.endswith(".__init__") or mod not in pos:
                if not mod.endswith("__init__"):
                    problems.append(f"{mod}: در module_order.txt نیست")
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                targets = []
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
                    targets = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                elif isinstance(node, ast.Import):
                    targets = [a.name for a in node.names if a.name.startswith("app")]
                for t in targets:
                    if t in pos and pos[t] >= pos[mod]:
                        problems.append(f"{mod} → {t}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
