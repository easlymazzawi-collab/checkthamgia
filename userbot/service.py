"""Userbot: mời bot vào kênh qua folder, tự duyệt tham gia khi vào kênh chỉ định."""

from __future__ import annotations

import logging
from typing import Callable, Awaitable

from telethon import TelegramClient, events
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest, InviteToChannelRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest, HideChatJoinRequest
from telethon.tl.types import Channel

import config
from clender.database import ClenderDB, _now

logger = logging.getLogger(__name__)

NotifyFn = Callable[[str], Awaitable[None]]


def normalize_channel_id(entity) -> int:
    if isinstance(entity, Channel):
        return int(f"-100{entity.id}")
    return entity.id


class UserbotService:
    def __init__(self, db: ClenderDB, bot_username: str = "", notify: NotifyFn | None = None):
        self.db = db
        self.bot_username = bot_username
        self.notify = notify
        self.client: TelegramClient | None = None

    async def _send_notify(self, text: str) -> None:
        if self.notify:
            try:
                await self.notify(text)
            except Exception as e:
                logger.warning("Notify failed: %s", e)

    async def start(self) -> TelegramClient:
        self.client = TelegramClient(
            str(config.SESSION_PATH),
            config.API_ID,
            config.API_HASH,
        )
        await self.client.start()
        me = await self.client.get_me()
        logger.info("Userbot started as %s", me.username or me.id)
        self._register_handlers()
        return self.client

    def _register_handlers(self) -> None:
        assert self.client

        @self.client.on(events.ChatAction)
        async def on_chat_action(event: events.ChatAction.Event) -> None:
            # Join request vào kênh đích
            if getattr(event, "user_join_request", False):
                target_ids = await self.db.get_target_channel_ids()
                chat_id = event.chat_id
                if chat_id not in target_ids:
                    return
                user = await event.get_user()
                if not user or user.bot:
                    return
                await self.db.add_pending_request(user.id, chat_id)
                gate_id = await self.db.get_gate_channel_id()
                if gate_id and await self._user_in_channel(user.id, gate_id):
                    await self._approve_user(user.id, chat_id, user.username or "")
                return

            # Member vào kênh gate
            if not event.user_joined and not event.user_added:
                return
            gate_id = await self.db.get_gate_channel_id()
            if not gate_id or event.chat_id != gate_id:
                return
            user = await event.get_user()
            if not user or user.bot:
                return
            await self._handle_gate_join(user.id, user.username or "", user)

    async def _user_in_channel(self, user_id: int, channel_id: int) -> bool:
        assert self.client
        try:
            entity = await self.client.get_entity(channel_id)
            await self.client(GetParticipantRequest(entity, user_id))
            return True
        except UserNotParticipantError:
            return False
        except Exception as e:
            logger.error("Check participant failed: %s", e)
            return False

    async def _handle_gate_join(self, user_id: int, username: str, user) -> None:
        await self.db.upsert_user(
            user_id,
            username=username,
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
            joined_gate_at=_now(),
        )
        gate_id = await self.db.get_gate_channel_id()
        await self.db.log_event(user_id, "gate_join", username, gate_id, "gate")

        pending = await self.db.get_pending_for_user(user_id)
        approved_any = False
        for req in pending:
            if await self._approve_user(user_id, req["target_channel_id"], username):
                approved_any = True

        if not pending:
            for tid in await self.db.get_target_channel_ids():
                if await self._approve_user(user_id, tid, username):
                    approved_any = True

        msg = (
            f"✅ Người dùng vào kênh chỉ định\n"
            f"👤 {username or user_id} (`{user_id}`)\n"
            f"{'🔓 Đã tự duyệt join request' if approved_any else '⏳ Chưa có yêu cầu join'}"
        )
        await self._send_notify(msg)

    async def _approve_user(self, user_id: int, target_channel_id: int, username: str = "") -> bool:
        assert self.client
        try:
            entity = await self.client.get_entity(target_channel_id)
            await self.client(
                HideChatJoinRequest(peer=entity, user_id=user_id, approved=True)
            )
            await self.db.remove_pending_request(user_id, target_channel_id)
            await self.db.upsert_user(
                user_id,
                username=username or None,
                approved_at=_now(),
                target_channel_id=target_channel_id,
            )
            await self.db.log_event(
                user_id, "approved", username, target_channel_id, getattr(entity, "title", "")
            )
            logger.info("Approved user %s for channel %s", user_id, target_channel_id)
            return True
        except Exception as e:
            logger.warning("Approve failed user=%s channel=%s: %s", user_id, target_channel_id, e)
            return False

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

    async def scan_pending_and_approve(self) -> str:
        """Quét thành viên kênh chỉ định và duyệt pending requests."""
        gate_id = await self.db.get_gate_channel_id()
        if not gate_id:
            return "❌ Chưa set kênh chỉ định"
        assert self.client
        entity = await self.client.get_entity(gate_id)
        approved = 0
        async for user in self.client.iter_participants(entity):
            if user.bot:
                continue
            pending = await self.db.get_pending_for_user(user.id)
            for req in pending:
                if await self._approve_user(user.id, req["target_channel_id"], user.username or ""):
                    approved += 1
        return f"🔍 Đã duyệt {approved} yêu cầu"
