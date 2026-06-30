"""
Mời bot vào kênh — port tool_tauto_bot.py + xử lý RightForbidden.

Userbot phải là admin và có quyền "Thêm admin" (add_admins).
Chỉ cấp quyền bot thực sự cần, giao với quyền userbot đang có.
"""

from __future__ import annotations

import asyncio
import logging

from telethon.errors import UserAlreadyParticipantError
from telethon.tl.functions.channels import EditAdminRequest, GetParticipantRequest, InviteToChannelRequest
from telethon.tl.types import (
    Channel,
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChatAdminRights,
)

logger = logging.getLogger(__name__)

ALL_FALSE = ChatAdminRights(
    change_info=False,
    post_messages=False,
    edit_messages=False,
    delete_messages=False,
    ban_users=False,
    invite_users=False,
    pin_messages=False,
    add_admins=False,
    anonymous=False,
    manage_call=False,
    other=False,
    manage_topics=False,
)

# Các combo thử — từ tối thiểu → rộng hơn (giống tool_tauto broadcast fallback)
RIGHTS_COMBOS: list[ChatAdminRights] = [
    # Chỉ duyệt join
    ChatAdminRights(
        change_info=False,
        post_messages=False,
        edit_messages=False,
        delete_messages=False,
        ban_users=False,
        invite_users=True,
        pin_messages=False,
        add_admins=False,
        anonymous=False,
        manage_call=False,
        other=False,
        manage_topics=False,
    ),
    ChatAdminRights(
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
        manage_topics=False,
    ),
    # Fallback kiểu tool_tauto (kênh broadcast đăng bài + admin)
    ChatAdminRights(
        change_info=False,
        post_messages=True,
        edit_messages=True,
        delete_messages=True,
        ban_users=False,
        invite_users=True,
        pin_messages=False,
        add_admins=False,
        anonymous=False,
        manage_call=False,
        other=False,
        manage_topics=False,
    ),
]


def is_broadcast_channel(entity) -> bool:
    return isinstance(entity, Channel) and getattr(entity, "broadcast", False)


def cap_rights(desired: ChatAdminRights, mine: ChatAdminRights | None) -> ChatAdminRights:
    """Chỉ cấp quyền mà userbot cũng có (creator → mine=None = full)."""
    if mine is None:
        return desired
    return ChatAdminRights(
        change_info=desired.change_info and mine.change_info,
        post_messages=desired.post_messages and mine.post_messages,
        edit_messages=desired.edit_messages and mine.edit_messages,
        delete_messages=desired.delete_messages and mine.delete_messages,
        ban_users=desired.ban_users and mine.ban_users,
        invite_users=desired.invite_users and mine.invite_users,
        pin_messages=desired.pin_messages and mine.pin_messages,
        add_admins=False,
        anonymous=False,
        manage_call=desired.manage_call and mine.manage_call,
        other=desired.other and mine.other,
        manage_topics=desired.manage_topics and mine.manage_topics,
    )


def rights_useful(r: ChatAdminRights) -> bool:
    return any(
        (
            r.invite_users,
            r.ban_users,
            r.post_messages,
            r.edit_messages,
            r.delete_messages,
            r.manage_topics,
        )
    )


async def get_userbot_participant(client, entity, my_id: int):
    try:
        result = await client(GetParticipantRequest(entity, my_id))
        return result.participant
    except Exception:
        return None


async def check_userbot_can_promote(client, entity, my_id: int) -> str | None:
    """None = OK, else lỗi mô tả."""
    p = await get_userbot_participant(client, entity, my_id)
    if isinstance(p, ChannelParticipantCreator):
        return None
    if isinstance(p, ChannelParticipantAdmin):
        ar = p.admin_rights
        if ar.add_admins:
            return None
        return (
            "userbot admin nhưng THIẾU quyền 'Thêm quản trị viên' — "
            "vào kênh → Sửa admin userbot → bật Thêm admin"
        )
    return "userbot CHƯA là admin kênh này — add userbot làm admin trước"


async def bot_is_admin(client, entity, bot_id: int) -> bool:
    try:
        result = await client(GetParticipantRequest(entity, bot_id))
        p = result.participant
        return isinstance(p, (ChannelParticipantAdmin, ChannelParticipantCreator))
    except Exception:
        return False


async def _promote_with_combos(
    client, entity, bot, my_id: int
) -> str | None:
    p = await get_userbot_participant(client, entity, my_id)
    if isinstance(p, ChannelParticipantCreator):
        mine = None
    elif isinstance(p, ChannelParticipantAdmin):
        mine = p.admin_rights
    else:
        return "userbot không phải admin"

    last_err = "không cấp được quyền"
    for combo in RIGHTS_COMBOS:
        rights = cap_rights(combo, mine)
        if not rights_useful(rights):
            continue
        try:
            await client(
                EditAdminRequest(entity, bot, rights, rank="Approved Bot")
            )
            return None
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:90]}"
            if "RightForbidden" not in type(e).__name__:
                return f"cấp admin: {last_err}"

    return (
        f"cấp admin: {last_err}\n"
        f"   → Userbot cần quyền: Thêm admin + Mời user (invite)"
    )


async def _invite_bot(client, entity, bot) -> str | None:
    try:
        await client(InviteToChannelRequest(entity, [bot]))
        return None
    except UserAlreadyParticipantError:
        return None
    except Exception as e:
        return f"mời bot: {type(e).__name__}: {str(e)[:100]}"


async def install_bot_as_admin(
    client, entity, bot, bot_username: str = "", my_id: int | None = None
) -> str | None:
    if my_id is None:
        me = await client.get_me()
        my_id = me.id

    if await bot_is_admin(client, entity, bot.id):
        return None

    pre = await check_userbot_can_promote(client, entity, my_id)
    if pre:
        return pre

    if is_broadcast_channel(entity):
        err = await _promote_with_combos(client, entity, bot, my_id)
        if err is None:
            return None
        if bot_username:
            try:
                named = await client.get_entity(bot_username.lstrip("@"))
                err2 = await _promote_with_combos(client, entity, named, my_id)
                if err2 is None:
                    return None
            except Exception:
                pass
        return err

    err = await _promote_with_combos(client, entity, bot, my_id)
    if err is None:
        return None

    invite_err = await _invite_bot(client, entity, bot)
    if invite_err:
        upper = invite_err.upper()
        if "USER_BOT" not in upper and "USERBOT" not in upper:
            return invite_err

    return await _promote_with_combos(client, entity, bot, my_id)


async def install_with_retry(
    client, entity, bot, bot_username: str = "", delay: float = 0.4
) -> str | None:
    err = await install_bot_as_admin(client, entity, bot, bot_username)
    if err and "FloodWait" in err:
        await asyncio.sleep(2)
        err = await install_bot_as_admin(client, entity, bot, bot_username)
    await asyncio.sleep(delay)
    return err
