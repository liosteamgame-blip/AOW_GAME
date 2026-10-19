"""هندلرها — ترتیب import همان ترتیب ثبت در Dispatcher است و نباید عوض شود.

هندلرهای جدید قبل از fallback اضافه می‌شوند (fallback همه پیام‌های پی‌وی بدون state را می‌گیرد).
"""
from app.audit import ActorMiddleware
from app.loader import dp
from app.permissions import AclMiddleware

# لایه‌های سراسری: تشخیص انجام‌دهنده برای لاگ ممیزی + بستن مرکزی دکمه‌های ادمینی
dp.update.outer_middleware(ActorMiddleware())
dp.callback_query.outer_middleware(AclMiddleware())

from app.handlers import (  # noqa: E402
    alerts,
    start,
    groups,
    admin_levels,
    leaders,
    group_assets,
    auth,
    admin_panel,
    admin_timing,
    admin_up,
    admin_transfer,
    admin_merchant,
    admin_leaderboard,
    admin_manage,
    military,
    menu,
    economy,
    orders,
    confirm,
    statement,
    trade,
    channel_buttons,
    admin_features,
    leader_panel,
    commander,
    fallback,
)

__all__ = [
    "alerts",
    "start",
    "groups",
    "admin_levels",
    "leaders",
    "group_assets",
    "auth",
    "admin_panel",
    "admin_timing",
    "admin_up",
    "admin_transfer",
    "admin_merchant",
    "admin_leaderboard",
    "admin_manage",
    "military",
    "menu",
    "economy",
    "orders",
    "confirm",
    "statement",
    "trade",
    "channel_buttons",
    "admin_features",
    "leader_panel",
    "commander",
    "fallback",
]
