"""Userbot: mời bot vào kênh — logic từ tool_tauto_bot.py (frwdbot2)."""

from __future__ import annotations

import logging

from telethon import TelegramClient
from telethon.tl.functions.chatlists import CheckChatlistInviteRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import Channel
from telethon.tl.types.chatlists import ChatlistInvite, ChatlistInviteAlready

import config
from clender.database import ClenderDB
from userbot.bot_install import bot_is_admin, install_with_retry, is_broadcast_channel
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


def _raw_chat_to_dict(chat) -> dict | None:
    title = getattr(chat, "title", "") or ""
    username = getattr(chat, "username", "") or ""
    raw_id = getattr(chat, "id", None)
    if not raw_id or not title:
        return None
    tg_id = int(f"-100{raw_id}") if raw_id > 0 else raw_id
    return {"id": tg_id, "title": title, "username": username}


class UserbotService:
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

    async def _install_one(
        self,
        chat_id: int,
        bot,
        folder_name: str,
        gate_id: int,
        *,
        register: bool = True,
    ) -> tuple[str, str]:
        """Returns (status, line) — status: ok|already|fail|skip"""
        assert self.client
        if chat_id == gate_id:
            return "skip", f"⏭️ gate {chat_id}"

        try:
            entity = await self.client.get_entity(chat_id)
        except Exception as e:
            return "fail", f"❌ {chat_id}: không resolve — {e}"

        title = getattr(entity, "title", str(chat_id))
        kind = "channel" if is_broadcast_channel(entity) else "supergroup"

        if await bot_is_admin(self.client, entity, bot.id):
            if register:
                await self.db.add_channel(chat_id, title, "target", folder_name, gate_id)
            return "already", f"⚡ {title} [{kind}] (đã admin)"

        err = await install_with_retry(
            self.client, entity, bot, self.bot_username
        )
        if err:
            return "fail", f"❌ {title} [{kind}]: {err}"

        if not await bot_is_admin(self.client, entity, bot.id):
            return "fail", f"❌ {title} [{kind}]: chưa có quyền admin sau promote"

        if register:
            await self.db.add_channel(chat_id, title, "target", folder_name, gate_id)
        return "ok", f"✅ {title} [{kind}]"

    async def _botadd_channel_dicts(
        self,
        channel_list: list[dict],
        folder_name: str,
        gate_id: int,
    ) -> str:
        assert self.client
        bot = await self._ensure_bot()

        # Gate trước
        gate_line = ""
        try:
            gate_ent = await self.client.get_entity(gate_id)
            err = await install_with_retry(self.client, gate_ent, bot, self.bot_username)
            gate_title = getattr(gate_ent, "title", str(gate_id))
            await self.db.set_folder_gate(folder_name, gate_id, gate_title)
            gate_line = f"🔑 Gate: {gate_title}" + (f" ⚠️ {err}" if err else " ✅")
        except Exception as e:
            gate_line = f"⚠️ Gate {gate_id}: {e}"

        ok, already, fail = 0, 0, 0
        lines: list[str] = []

        for ch in channel_list:
            cid = ch["id"]
            status, line = await self._install_one(cid, bot, folder_name, gate_id)
            lines.append(line)
            if status == "ok":
                ok += 1
            elif status == "already":
                already += 1
            elif status == "fail":
                fail += 1

        await self.db.apply_folder_gate_to_targets(folder_name)

        header = (
            f"📂 {folder_name}\n"
            f"{gate_line}\n"
            f"🤖 @{self.bot_username} — ✅ {ok} | ⚡ {already} | ❌ {fail}\n"
            f"(logic: tool_tauto_bot — channel=promote admin, group=invite+promote)\n"
        )
        return header + "\n".join(lines[:40])

    async def _channels_from_entities(self, chats) -> list[dict]:
        out: list[dict] = []
        for chat in chats:
            d = _raw_chat_to_dict(chat)
            if d:
                out.append(d)
        return out

    async def add_from_addlist(self, addlist_url: str, gate_channel_id: int) -> str:
        assert self.client
        slug = parse_addlist_slug(addlist_url)
        if not slug:
            return "❌ Link addlist không hợp lệ"

        try:
            invite = await self.client(CheckChatlistInviteRequest(slug=slug))
        except Exception as e:
            return f"❌ Không đọc được addlist: {e}"

        if isinstance(invite, ChatlistInvite):
            folder_name = _folder_title_from_invite(invite)
            chats = invite.chats
        elif isinstance(invite, ChatlistInviteAlready):
            folder_name = f"addlist_{slug[:10]}"
            chats = invite.chats
        else:
            return "❌ Addlist không hợp lệ"

        channel_list = await self._channels_from_entities(chats)
        if not channel_list:
            return "❌ Folder trống"

        return await self._botadd_channel_dicts(channel_list, folder_name, gate_channel_id)

    async def invite_bot_to_folder(
        self, folder_name: str, gate_channel_id: int | None = None
    ) -> str:
        assert self.client
        if not folder_name:
            return "❌ Phải nhập tên folder"

        gate_id = gate_channel_id or await self.db.get_folder_gate(folder_name)
        if not gate_id:
            return "NO_GATE"

        channels: list[dict] = []
        resolved_folder = folder_name

        result = await self.client(GetDialogFiltersRequest())
        for f in result.filters:
            if getattr(f, "title", "") != folder_name:
                continue
            resolved_folder = getattr(f, "title", folder_name)
            for peer in getattr(f, "include_peers", []) or []:
                try:
                    ent = await self.client.get_entity(peer)
                    d = _raw_chat_to_dict(ent)
                    if d:
                        channels.append(d)
                except Exception:
                    continue
            break

        if not channels:
            return f"❌ Không tìm thấy folder `{folder_name}`"

        return await self._botadd_channel_dicts(channels, resolved_folder, gate_id)

    async def invite_bot_to_all_managed(self) -> str:
        assert self.client
        folders = await self.db.list_folders()
        if not folders:
            return "❌ Chưa có folder — dùng /add trước"

        bot = await self._ensure_bot()
        lines: list[str] = ["🚀 /all — mời bot (tool_tauto_bot logic)\n"]
        total_ok, total_already, total_fail = 0, 0, 0

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

            f_ok, f_al, f_fail = 0, 0, 0
            for cid in chat_ids:
                status, line = await self._install_one(
                    cid, bot, folder_name, gate_id, register=False
                )
                if status == "ok":
                    f_ok += 1
                elif status == "already":
                    f_al += 1
                elif status == "fail":
                    f_fail += 1
                    lines.append(f"  {line}")

            total_ok += f_ok
            total_already += f_al
            total_fail += f_fail
            gate_title = folder.get("gate_title") or gate_id
            lines.append(
                f"📂 {folder_name} (gate: {gate_title})\n"
                f"   ✅ {f_ok} | ⚡ {f_al} | ❌ {f_fail}"
            )

        lines.append(f"\nTổng: ✅ {total_ok} | ⚡ {total_already} | ❌ {total_fail}")
        return "\n".join(lines)
