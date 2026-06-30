"""Gửi backup định kỳ cho admin."""

from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

import config
from clender.database import ClenderDB

logger = logging.getLogger(__name__)


async def create_backup_file(db: ClenderDB) -> Path:
    """Tạo file backup JSON + copy DB."""
    tmp = Path(tempfile.mkdtemp(prefix="clender_backup_"))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = tmp / f"clender_{ts}.json"
    json_path.write_text(await db.export_json(), encoding="utf-8")

    db_copy = tmp / f"clender_{ts}.db"
    if Path(db.db_path).exists():
        shutil.copy2(db.db_path, db_copy)

    return tmp


async def send_backup_to_admins(bot: Bot, db: ClenderDB) -> None:
    tmp = await create_backup_file(db)
    try:
        files = list(tmp.iterdir())
        for admin_id in config.ADMIN_IDS:
            for f in files:
                try:
                    await bot.send_document(
                        admin_id,
                        FSInputFile(f),
                        caption=f"💾 Backup clender — {f.name}",
                    )
                except Exception as e:
                    logger.error("Backup send failed admin=%s: %s", admin_id, e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
