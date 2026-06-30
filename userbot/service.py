"""Userbot: chỉ dùng để mời bot vào kênh qua folder / addlist Telegram."""

from __future__ import annotations

import logging

from telethon import TelegramClient
from telethon.tl.functions.channels import EditAdminRequest, InviteToChannelRequest
from telethon.tl.functions.chatlists import CheckChatlistInviteRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import Channel, ChatAdminRights
from telethon.tl.types.chatlists import ChatlistInvite, ChatlistInviteAlready

import config
from clender.database import ClenderDB
from utils.chatlist import parse_addlist_slug

logger = logging.getLogger(__name__)

# Quyền tối thiểu để bot duyệt join request
_BOT_ADMIN_RIGHTS = ChatAdminRights(
    change_info=False,
    post_messages=False,
    edit_messages=False,
    delete_messages=False,
    ban_users=True,
    invite_users=True,
    pin_messages=False,
    add_admins=False,
    anonymous=False,
    manage_call=False,
    other=False,
    manage_topics=True,
)


def normalize_channel_id(entity) -> int:
    if isinstance(entity, Channel):
        return int(f"-100{entity.id}")
    return entity.id


def _chat_kind(ch: Channel) -> str:
    if getattr(ch, "broadcast", False):
        return "channel"
    if getattr(ch, "megagroup", False):
        return "supergroup"
    return "unknown"


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

    async def _invite_bot_to_entity(self, entity, bot) -> None:
        """Channel → invite. Supergroup → promote admin (bot không add được như member)."""
        assert self.client
        if isinstance(entity, Channel) and getattr(entity, "broadcast", False):
            await self.client(InviteToChannelRequest(entity, [bot]))
            return
        if isinstance(entity, Channel) and getattr(entity, "megagroup", False):
            await self.client(
                EditAdminRequest(entity, bot, _BOT_ADMIN_RIGHTS, rank="Approved Bot")
            )
            return
        raise ValueError("Chỉ hỗ trợ Channel/Supergroup — không phải group thường")

    async def _invite_one(
        self,
        entity,
        bot,
        folder_name: str,
        gate_id: int,
        *,
        register: bool = True,
    ) -> str:
        title = getattr(entity, "title", str(entity))
        cid = normalize_channel_id(entity) if isinstance(entity, Channel) else entity.id
        kind = _chat_kind(entity) if isinstance(entity, Channel) else "?"

        if cid == gate_id:
            return f"⏭️ {title} (gate)"

        await self._invite_bot_to_entity(entity, bot)
        if register:
            await self.db.add_channel(cid, title, "target", folder_name, gate_id)
        return f"✅ {title} [{kind}]"

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
            await self._invite_bot_to_entity(gate_ent, bot)
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
                line = await self._invite_one(ch, bot, folder_name, gate_id)
                if line.startswith("✅"):
                    ok += 1
                lines.append(line)
            except Exception as e:
                fail += 1
                kind = _chat_kind(ch)
                err = str(e).split("(")[0].strip()
                lines.append(f"❌ {ch.title} [{kind}]: {err}")

        await self.db.apply_folder_gate_to_targets(folder_name)

        header = (
            f"📂 {folder_name}\n"
            f"🔑 Gate: {gate_id}\n"
            f"📁 ✅ {ok} | ❌ {fail} | ⏭️ {skipped}\n"
            f"(channel + supergroup OK | group thường không hỗ trợ)\n"
        )
        return header + "\n".join(gate_lines + lines[:35])

    async def add_from_addlist(self, addlist_url: str, gate_channel_id: int) -> str:
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

    async def invite_bot_to_all_managed(self) -> str:
        assert self.client
        folders = await self.db.list_folders()
        if not folders:
            return "❌ Chưa có folder nào.\nDùng `/add` hoặc Mời bot (folder) trước."

        bot = await self._ensure_bot()
        lines: list[str] = ["🚀 Mời bot vào tất cả folder đang quản lý\n"]
        total_ok, total_fail = 0, 0

        for folder in folders:
            folder_name = folder["folder_name"]
            gate_id = folder["gate_channel_id"]
            targets = await self.db.list_targets_by_folder(folder_name)

            chat_ids: list[int] = []
            seen: set[int] = set()

            def add_id(cid: int) -> None:
                if cid and cid not in seen:
                    seen.add(cid)
                    chat_ids.append(cid)

            add_id(gate_id)
            for t in targets:
                add_id(t["chat_id"])

            f_ok, f_fail = 0, 0
            f_errors: list[str] = []
            for chat_id in chat_ids:
                ch = await self.db.get_channel(chat_id)
                name = (ch or {}).get("title", chat_id)
                try:
                    ent = await self.client.get_entity(chat_id)
                    await self._invite_bot_to_entity(ent, bot)
                    f_ok += 1
                except Exception as e:
                    f_fail += 1
                    err = str(e).split("(")[0].strip()
                    f_errors.append(f"  ❌ {name}: {err}")

            total_ok += f_ok
            total_fail += f_fail
            gate_title = folder.get("gate_title") or gate_id
            lines.append(
                f"📂 {folder_name} (gate: {gate_title})\n"
                f"   ✅ {f_ok} | ❌ {f_fail} kênh"
            )
            lines.extend(f_errors[:5])

        lines.append(f"\nTổng: ✅ {total_ok} | ❌ {total_fail}")
        return "\n".join(lines)
