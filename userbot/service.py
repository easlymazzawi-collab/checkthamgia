"""Userbot: chỉ dùng để mời bot vào kênh qua folder / addlist Telegram."""

from __future__ import annotations

import logging

from telethon import TelegramClient
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.chatlists import CheckChatlistInviteRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import Channel
from telethon.tl.types.chatlists import ChatlistInvite, ChatlistInviteAlready

import config
from clender.database import ClenderDB
from utils.chatlist import parse_addlist_slug

logger = logging.getLogger(__name__)


def normalize_channel_id(entity) -> int:
    if isinstance(entity, Channel):
        return int(f"-100{entity.id}")
    return entity.id


def _folder_title_from_invite(invite: ChatlistInvite) -> str:
    title = invite.title
    if hasattr(title, "text"):
        return title.text or "addlist"
    return str(title) if title else "addlist"


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

    async def _ensure_bot(self):
        assert self.client
        if not self.bot_username:
            bot_username = await self.db.get_setting("bot_username")
            if not bot_username:
                raise RuntimeError("Chưa cấu hình bot username")
            self.bot_username = bot_username.lstrip("@")
        return await self.client.get_entity(self.bot_username)

    async def _invite_channels(
        self,
        channels: list[Channel],
        gate_id: int,
        folder_name: str,
    ) -> str:
        assert self.client
        bot = await self._ensure_bot()

        gate_lines: list[str] = []
        try:
            gate_ent = await self.client.get_entity(gate_id)
            await self.client(InviteToChannelRequest(gate_ent, [bot]))
            gate_title = getattr(gate_ent, "title", str(gate_id))
            await self.db.set_folder_gate(folder_name, gate_id, gate_title)
            gate_lines.append(f"🔑 Gate: {gate_title}")
        except Exception as e:
            gate_lines.append(f"⚠️ Gate ({gate_id}): {e}")

        ok, fail, skipped = 0, 0, 0
        lines: list[str] = []
        for ch in channels:
            cid = normalize_channel_id(ch)
            if cid == gate_id:
                skipped += 1
                continue
            try:
                await self.client(InviteToChannelRequest(ch, [bot]))
                await self.db.add_channel(
                    cid,
                    ch.title or str(ch.id),
                    "target",
                    folder_name,
                    gate_id,
                )
                ok += 1
                lines.append(f"✅ {ch.title}")
            except Exception as e:
                fail += 1
                lines.append(f"❌ {ch.title}: {e}")

        await self.db.apply_folder_gate_to_targets(folder_name)

        header = (
            f"📂 **{folder_name}**\n"
            f"🔑 Gate: `{gate_id}`\n"
            f"📁 {ok} kênh đích | bỏ qua gate {skipped} | lỗi {fail}\n"
        )
        return header + "\n".join(gate_lines + lines[:30])

    async def add_from_addlist(self, addlist_url: str, gate_channel_id: int) -> str:
        """Thêm nhanh từ link t.me/addlist/... + kênh gate."""
        assert self.client
        slug = parse_addlist_slug(addlist_url)
        if not slug:
            return "❌ Link addlist không hợp lệ\nVD: https://t.me/addlist/QYZFGBD8dRoxZWU1"

        try:
            invite = await self.client(CheckChatlistInviteRequest(slug=slug))
        except Exception as e:
            return f"❌ Không đọc được addlist: {e}"

        if isinstance(invite, ChatlistInvite):
            folder_name = _folder_title_from_invite(invite)
            channels = [c for c in invite.chats if isinstance(c, Channel)]
        elif isinstance(invite, ChatlistInviteAlready):
            folder_name = f"addlist_{slug[:10]}"
            channels = [c for c in invite.chats if isinstance(c, Channel)]
        else:
            return "❌ Addlist không hợp lệ"

        if not channels:
            return "❌ Addlist không có kênh/nhóm nào"

        return await self._invite_channels(channels, gate_channel_id, folder_name)

    async def invite_bot_to_folder(
        self, folder_name: str, gate_channel_id: int | None = None
    ) -> str:
        """Mời bot vào kênh trong folder Telegram (theo tên folder)."""
        assert self.client
        if not folder_name:
            return "❌ Phải nhập tên folder"

        gate_id = gate_channel_id or await self.db.get_folder_gate(folder_name)
        if not gate_id:
            return "NO_GATE"

        channels: list[Channel] = []
        resolved_folder = folder_name

        result = await self.client(GetDialogFiltersRequest())
        for f in result.filters:
            if getattr(f, "title", "") != folder_name:
                continue
            resolved_folder = getattr(f, "title", folder_name)
            for peer in getattr(f, "include_peers", []) or []:
                try:
                    ent = await self.client.get_entity(peer)
                    if isinstance(ent, Channel):
                        channels.append(ent)
                except Exception:
                    continue
            break

        if not channels:
            return f"❌ Không tìm thấy folder `{folder_name}` hoặc folder trống"

        return await self._invite_channels(channels, gate_id, resolved_folder)
