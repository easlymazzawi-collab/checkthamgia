"""Userbot: chỉ dùng để mời bot vào kênh qua folder Telegram."""

from __future__ import annotations

import logging

from telethon import TelegramClient
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import Channel

import config
from clender.database import ClenderDB

logger = logging.getLogger(__name__)


def normalize_channel_id(entity) -> int:
    if isinstance(entity, Channel):
        return int(f"-100{entity.id}")
    return entity.id


class UserbotService:
    """Chỉ add bot vào kênh cần quản lý — không duyệt thành viên."""

    def __init__(self, db: ClenderDB, bot_username: str = ""):
        self.db = db
        self.bot_username = bot_username
        self.client: TelegramClient | None = None

    async def start(self) -> TelegramClient:
        self.client = TelegramClient(
            str(config.SESSION_PATH),
            config.API_ID,
            config.API_HASH,
        )
        await self.client.start()
        me = await self.client.get_me()
        logger.info("Userbot started as %s (add-bot only)", me.username or me.id)
        return self.client

    async def invite_bot_to_folder(self, folder_id: int | None = None, folder_name: str = "") -> str:
        """Mời bot vào tất cả kênh trong folder Telegram."""
        assert self.client
        if not self.bot_username:
            bot_username = await self.db.get_setting("bot_username")
            if not bot_username:
                return "❌ Chưa cấu hình bot username"
            self.bot_username = bot_username.lstrip("@")

        bot = await self.client.get_entity(self.bot_username)
        channels: list[Channel] = []

        if folder_id is not None or folder_name:
            result = await self.client(GetDialogFiltersRequest())
            for f in result.filters:
                if folder_id is not None and getattr(f, "id", None) != folder_id:
                    continue
                if folder_name and getattr(f, "title", "") != folder_name:
                    continue
                for peer in getattr(f, "include_peers", []) or []:
                    try:
                        ent = await self.client.get_entity(peer)
                        if isinstance(ent, Channel):
                            channels.append(ent)
                    except Exception:
                        continue
                break
        else:
            async for dialog in self.client.iter_dialogs():
                if isinstance(dialog.entity, Channel) and dialog.entity.broadcast:
                    channels.append(dialog.entity)

        if not channels:
            return "❌ Không tìm thấy kênh trong folder"

        ok, fail = 0, 0
        lines: list[str] = []
        for ch in channels:
            try:
                await self.client(InviteToChannelRequest(ch, [bot]))
                cid = normalize_channel_id(ch)
                await self.db.add_channel(cid, ch.title or str(ch.id), "target", folder_name)
                ok += 1
                lines.append(f"✅ {ch.title}")
            except Exception as e:
                fail += 1
                lines.append(f"❌ {ch.title}: {e}")

        return f"📁 Mời bot vào {ok} kênh, lỗi {fail}\n" + "\n".join(lines[:30])
