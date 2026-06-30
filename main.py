"""
Check Tham Gia — Bot + Userbot
Chạy: python main.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot
from aiogram.exceptions import TelegramUnauthorizedError
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


def _print_token_help() -> None:
    env_path = config.ENV_FILE.resolve()
    print(
        "\n"
        "❌ BOT_TOKEN không hợp lệ hoặc chưa cấu hình!\n"
        "\n"
        "Cách lấy token:\n"
        "  1. Mở Telegram → tìm @BotFather\n"
        "  2. Gửi /newbot (hoặc /token nếu bot đã có)\n"
        "  3. Copy token dạng: 7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
        f"  4. Dán vào file: {env_path}\n"
        "     BOT_TOKEN=7123456789:AAHxxxxxxxx\n"
        "\n"
        "Lưu ý:\n"
        "  - Không có dấu cách, không có dấu ngoặc kép\n"
        "  - Không dùng token mẫu 123456:ABC-DEF từ .env.example\n"
        "  - ADMIN_IDS = ID Telegram của bạn (lấy từ @userinfobot)\n"
    )


async def main() -> None:
    if not config.is_bot_token_configured():
        logger.error("BOT_TOKEN chưa được cấu hình đúng trong .env")
        _print_token_help()
        sys.exit(1)
    if not config.ADMIN_IDS:
        logger.error("Set ADMIN_IDS in .env (ID Telegram của bạn, lấy từ @userinfobot)")
        sys.exit(1)

    db = ClenderDB(config.DB_PATH)
    await db.init()

    bot = Bot(token=config.BOT_TOKEN)
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        logger.error("Telegram từ chối token — Unauthorized")
        _print_token_help()
        await bot.session.close()
        sys.exit(1)

    await db.set_setting("bot_username", me.username or "")
    logger.info("Bot connected: @%s", me.username or me.id)

    userbot: UserbotService | None = None
    if config.API_ID and config.API_HASH:
        userbot = UserbotService(db, bot_username=me.username or "")
        try:
            await userbot.start()
            logger.info("Userbot connected (add-bot only)")
        except Exception as e:
            logger.warning("Userbot failed to start: %s", e)
            userbot = None
    else:
        logger.warning("API_ID/API_HASH not set — chỉ chạy bot, không add bot qua folder")

    dp = create_dispatcher(db, userbot)

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
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_join_request", "chat_member"],
        )
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        if userbot and userbot.client:
            await userbot.client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
