"""
Check Tham Gia — Bot + Userbot
Chạy: python main.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
from bot.handlers import create_dispatcher
from clender.database import ClenderDB
from services.backup import send_backup_to_admins
from userbot.service import UserbotService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not config.BOT_TOKEN:
        logger.error("Set BOT_TOKEN in .env")
        sys.exit(1)
    if not config.ADMIN_IDS:
        logger.error("Set ADMIN_IDS in .env")
        sys.exit(1)

    db = ClenderDB(config.DB_PATH)
    await db.init()

    bot = Bot(token=config.BOT_TOKEN)
    me = await bot.get_me()
    await db.set_setting("bot_username", me.username or "")

    async def notify_admins(text: str) -> None:
        for admin_id in config.ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text, parse_mode="Markdown")
            except Exception as e:
                logger.warning("Notify admin %s: %s", admin_id, e)

    userbot: UserbotService | None = None
    if config.API_ID and config.API_HASH:
        userbot = UserbotService(db, bot_username=me.username or "", notify=notify_admins)
        try:
            await userbot.start()
            logger.info("Userbot connected")
        except Exception as e:
            logger.warning("Userbot failed to start (bot-only mode): %s", e)
            userbot = None
    else:
        logger.warning("API_ID/API_HASH not set — running bot-only mode")

    dp = create_dispatcher(db, userbot)

    # Scheduler backup
    scheduler = AsyncIOScheduler()
    hours_str = await db.get_setting("backup_interval_hours", str(config.BACKUP_INTERVAL_HOURS))
    hours = int(hours_str)

    async def job_backup() -> None:
        logger.info("Running scheduled backup")
        await send_backup_to_admins(bot, db)

    scheduler.add_job(
        job_backup,
        trigger=IntervalTrigger(hours=hours),
        id="clender_backup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Backup scheduler: every %s hours", hours)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        if userbot and userbot.client:
            await userbot.client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
