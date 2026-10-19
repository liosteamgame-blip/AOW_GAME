"""ساخت Bot و Dispatcher مشترک (همه ماژول‌ها از همین نمونه استفاده می‌کنند)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import TOKEN


class RetryAfterMiddleware(BaseRequestMiddleware):
    """FloodWait تلگرام: به‌جای شکست، صبر و تکرار (برای ارسال‌های گروهی/همگانی حیاتی است)."""

    async def __call__(self, make_request, bot, method):
        for attempt in range(3):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as ex:
                if attempt == 2 or ex.retry_after > 60:
                    raise
                logging.warning("FloodWait %ss روی %s", ex.retry_after, type(method).__name__)
                await asyncio.sleep(ex.retry_after + 0.5)


bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
bot.session.middleware(RetryAfterMiddleware())
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)
