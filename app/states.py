"""وضعیت‌های FSM فرم‌ها."""

from aiogram.fsm.state import State, StatesGroup


class GameStates(StatesGroup):
    waiting_for_code = State()
    main_menu = State()
    admin_broadcast = State()
    admin_broadcast_target = State()
    admin_dm = State()
    admin_add_city = State()
    admin_transfer = State()
    group_set_city = State()

    # تنظیمات ادمین
    adm_set_timing = State()       # ورودی کلید=مقدار برای تایم/پیام
    adm_set_photo = State()        # دریافت عکس استارت یا استاپ | menu
    adm_set_merchant = State()     # لیست سقف تجار
    adm_set_buff = State()         # باف پیش‌فرض
    adm_set_price = State()        # قیمت خرید/فروش تجار
    adm_set_asset_text = State()   # متن دارایی شهر
    adm_set_asset_city = State()   # تایید شهر برای دارایی
    adm_set_leader_side = State()  # انتخاب ساید برای لیدر
    adm_buff_add = State()         # ثبت باف/نرف

    # لشکرکشی
    camp_origin = State()
    camp_dest = State()
    camp_stats = State()
    camp_time = State()
    camp_confirm = State()

    # محاصره و اعلان جنگ (فرم مشترک)
    order_target = State()
    order_stats = State()
    order_confirm = State()

    # بیانیه
    ann_media = State()
    ann_confirm = State()

    # تجارت با بازیکن
    trade_origin = State()
    trade_dest = State()
    trade_mtype = State()
    trade_route = State()
    trade_guard = State()
    trade_recv = State()
    trade_send = State()
    trade_time = State()
    trade_confirm = State()
    # کمین کاروان
    trade_ambush_stats = State()
    trade_ambush_confirm = State()

    # تجارت با تجار
    mtrade_mode = State()   # buy | sell
    mtrade_list = State()
    mtrade_buff = State()
    mtrade_confirm = State()

    # مشاهده دارایی لیدر
    asset_view_menu = State()

    # مشاور ارتقا — چت کوتاه سلیقه/پلن (حداکثر ۲ پیام)
    advise_pref = State()

    # ثبت شاپ (فوروارد پک‌ها)
    adm_shop_collect = State()

    # دکمه‌های پست لشکرکشی در کانال
    ambush_stats = State()
    ambush_confirm = State()
    redirect_target = State()
    redirect_time = State()
    redirect_confirm = State()
    back_time = State()
    back_confirm = State()

    # پنل لیدر جناح
    ldr_msg = State()
    ldr_poll = State()

    # راهنمای بازیکن (ادمین)
    guide_edit = State()
