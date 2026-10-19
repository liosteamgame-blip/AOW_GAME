"""نقطه‌ی شروع ربات خاکستر جنگ.

Railway این فایل را با Procfile اجرا می‌کند:  worker: python main.py
همه‌ی منطق در پکیج app/ است.
"""
import asyncio

from app.bootstrap import main

if __name__ == "__main__":
    asyncio.run(main())
