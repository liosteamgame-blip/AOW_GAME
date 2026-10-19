"""
شبیه‌ساز تلگرام برای تست: آپدیت جعلی به Dispatcher واقعی داده می‌شود و هر درخواستی که
ربات به تلگرام می‌فرستد (sendMessage، editMessageText، …) ضبط می‌شود — بدون اینترنت.

استفاده:
    from tests.fakebot import setup_env; setup_env()   # قبل از import app
    from tests.fakebot import FakeTelegram
"""
import asyncio
import itertools
import os
import tempfile
from datetime import datetime

_TMP = None


def setup_env():
    """متغیرهای محیطی تست — باید قبل از import پکیج app صدا زده شود."""
    global _TMP
    if _TMP is None:
        _TMP = tempfile.mkdtemp(prefix="aow_test_")
    os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN_abcdefghijklmnopqrstuvwxyz")
    os.environ["ADMIN_ID"] = os.environ.get("ADMIN_ID", "1000")
    os.environ["CHANNEL_ID"] = "-100111"
    os.environ["REPORT_CHANNEL_ID"] = "-100222"
    os.environ["TWEET_CHANNEL_ID"] = "-100333"
    os.environ["DATA_FILE"] = os.path.join(_TMP, "data.json")
    os.environ.pop("XAI_API_KEY", None)
    os.environ.pop("GROK_API_KEY", None)
    os.environ["AOW_RAISE_ERRORS"] = "1"   # هندلر خطا در تست، خطا را پنهان نکند
    return _TMP


ADMIN = 1000


class FakeTelegram:
    """جایگزین session ربات؛ همه‌ی متدها را ضبط می‌کند و پاسخ معتبر برمی‌گرداند."""

    def __init__(self, bot):
        from aiogram.client.session.base import BaseSession

        self.calls = []
        self._ids = itertools.count(5000)
        outer = self

        class _Session(BaseSession):
            async def make_request(self, bot, method, timeout=None):
                # مثل شبکه‌ی واقعی کنترل را به event loop برگردان تا رقابت دابل‌کلیک قابل تست باشد
                await asyncio.sleep(0)
                outer.calls.append(method)
                return outer._result(method)

            async def stream_content(self, *a, **k):
                if False:
                    yield b""

            async def close(self):
                pass

        self.bot = bot
        self._orig = bot.session
        bot.session = _Session()
        # id ربات برای StorageKey
        bot._me = None

    # ---------------- پاسخ‌ها ----------------
    def _result(self, method):
        from aiogram import methods as M
        from aiogram.types import Chat, Message, User

        name = type(method).__name__
        if isinstance(method, M.GetMe):
            return User(id=999, is_bot=True, first_name="AOW", username="aow_test_bot")
        if isinstance(method, M.GetChat):
            return Chat(id=getattr(method, "chat_id", 0), type="private")
        if name in ("SendMessage", "SendPhoto", "SendVideo", "SendDocument", "CopyMessage",
                    "ForwardMessage", "EditMessageText", "EditMessageCaption", "EditMessageMedia",
                    "EditMessageReplyMarkup", "SendPoll"):
            cid = getattr(method, "chat_id", None) or 0
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                cid = 0
            ctype = "private" if cid > 0 else ("channel" if str(cid).startswith("-100") and cid in (-100111, -100222, -100333) else "supergroup")
            mid = getattr(method, "message_id", None) or next(self._ids)
            if name == "CopyMessage":
                from aiogram.types import MessageId
                return MessageId(message_id=next(self._ids))
            return Message(
                message_id=mid,
                date=datetime.now(),
                chat=Chat(id=cid, type=ctype),
                from_user=User(id=999, is_bot=True, first_name="AOW"),
                text=getattr(method, "text", None),
                caption=getattr(method, "caption", None),
            )
        return True

    # ---------------- کمک‌ها ----------------
    def sent(self, kind=None):
        return [c for c in self.calls if kind is None or type(c).__name__ == kind]

    def texts(self):
        out = []
        for c in self.calls:
            t = getattr(c, "text", None) or getattr(c, "caption", None)
            if t:
                out.append(t)
        return out

    def last_text(self):
        t = self.texts()
        return t[-1] if t else ""

    def clear(self):
        self.calls.clear()

    def buttons(self, call=None):
        """همه‌ی callback_dataهای آخرین پیام (یا پیام داده‌شده)."""
        calls = [call] if call else list(reversed(self.calls))
        for c in calls:
            mk = getattr(c, "reply_markup", None)
            if mk is not None and getattr(mk, "inline_keyboard", None):
                return [b.callback_data for row in mk.inline_keyboard for b in row if b.callback_data]
        return []


_uid = itertools.count(1)


def user(uid, name="کاربر", username=None):
    from aiogram.types import User
    return User(id=uid, is_bot=False, first_name=name, username=username)


def message(uid, text, chat_id=None, chat_type="private", reply_to=None, title=None, **extra):
    from aiogram.types import Chat, Message, Update
    chat_id = chat_id if chat_id is not None else uid
    m = Message(
        message_id=next(_uid) + 100,
        date=datetime.now(),
        chat=Chat(id=chat_id, type=chat_type, title=title),
        from_user=user(uid),
        text=text,
        reply_to_message=reply_to,
        **extra,
    )
    return Update(update_id=next(_uid), message=m)


def callback(uid, data, chat_id=None, chat_type="private", msg_text="منو"):
    from aiogram.types import CallbackQuery, Chat, Message, Update
    chat_id = chat_id if chat_id is not None else uid
    msg = Message(
        message_id=next(_uid) + 100,
        date=datetime.now(),
        chat=Chat(id=chat_id, type=chat_type),
        from_user=user(999, "AOW"),
        text=msg_text,
    )
    cq = CallbackQuery(id=str(next(_uid)), from_user=user(uid), chat_instance="ci", data=data, message=msg)
    return Update(update_id=next(_uid), callback_query=cq)
