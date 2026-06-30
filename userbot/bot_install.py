"""
Mời bot vào kênh — port logic từ tool_tauto_bot.py (frwdbot2).

Kênh broadcast: bot CHỈ được là admin → EditAdmin, không InviteToChannel.
Supergroup: promote trước → invite (bỏ qua USER_BOT) → promote lại.
"""

from __future__ import annotations

import asyncio
import logging

from telethon.errors import UserAlreadyParticipantError
from telethon.tl.functions.channels import EditAdminRequest, InviteToChannelRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import Channel, ChatAdminRights, ChannelParticipantAdmin, ChannelParticipantCreator

logger = logging.getLogger(__name__)

# Quyền bot duyệt join request
BOT_ADMIN_RIGHTS = ChatAdminRights(
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


def is_broadcast_channel(entity) -> bool:
    return isinstance(entity, Channel) and getattr(entity, "broadcast", False)


def is_megagroup(entity) -> bool:
    return isinstance(entity, Channel) and getattr(entity, "megagroup", False)


async def bot_is_admin(client, entity, bot_id: int) -> bool:
    try:
        result = await client(GetParticipantRequest(entity, bot_id))
        p = result.participant
        return isinstance(p, (ChannelParticipantAdmin, ChannelParticipantCreator))
    except Exception:
        return False


async def _promote_bot(client, entity, bot) -> str | None:
    try:
        await client(
            EditAdminRequest(entity, bot, BOT_ADMIN_RIGHTS, rank="Approved Bot")
        )
        return None
    except Exception as e:
        return f"cấp admin: {type(e).__name__}: {str(e)[:100]}"


async def _invite_bot(client, entity, bot) -> str | None:
    try:
        await client(InviteToChannelRequest(entity, [bot]))
        return None
    except UserAlreadyParticipantError:
        return None
    except Exception as e:
        return f"mời bot: {type(e).__name__}: {str(e)[:100]}"


async def install_bot_as_admin(client, entity, bot, bot_username: str = "") -> str | None:
    """
    Thêm bot làm admin — giống _install_bot_as_admin trong tool_tauto_bot.py.
    Trả None nếu OK, else chuỗi lỗi.
    """
    bot_id = bot.id

    if await bot_is_admin(client, entity, bot_id):
        return None

    if is_broadcast_channel(entity):
        err = await _promote_bot(client, entity, bot)
        if err is None:
            return None
        if bot_username:
            try:
                named = await client.get_entity(bot_username.lstrip("@"))
                err = await _promote_bot(client, entity, named)
                if err is None:
                    return None
            except Exception:
                pass
        return err

    # Supergroup / megagroup
    err = await _promote_bot(client, entity, bot)
    if err is None:
        return None

    invite_err = await _invite_bot(client, entity, bot)
    if invite_err:
        upper = invite_err.upper()
        if "USER_BOT" not in upper and "USERBOT" not in upper:
            return invite_err

    return await _promote_bot(client, entity, bot)


async def install_with_retry(
    client, entity, bot, bot_username: str = "", delay: float = 0.4
) -> str | None:
    err = await install_bot_as_admin(client, entity, bot, bot_username)
    if err and "FloodWait" in err:
        await asyncio.sleep(2)
        err = await install_bot_as_admin(client, entity, bot, bot_username)
    await asyncio.sleep(delay)
    return err
