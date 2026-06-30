"""Bot tự duyệt join request — hỗ trợ đa kênh, nhắn tin cho member."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import ChatJoinRequest, ChatMemberUpdated

import config
from bot.member_notify import (
    msg_approved,
    msg_gate_joined_approved,
    msg_gate_joined_wait,
    msg_need_gate,
)

from clender.database import ClenderDB, _now

logger = logging.getLogger(__name__)

router = Router()


async def _notify_member_simple(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text, parse_mode=None)
    except Exception as e:
        logger.warning("Không nhắn user %s: %s", user_id, e)


_MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
}


async def _user_in_gate(bot: Bot, gate_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(gate_id, user_id)
        return member.status in _MEMBER_STATUSES
    except Exception:
        return False


async def _approve_user(
    bot: Bot,
    db: ClenderDB,
    user_id: int,
    target_channel_id: int,
    username: str = "",
    *,
    notify_member: bool = True,
) -> bool:
    ch = await db.get_channel(target_channel_id)
    title = (ch or {}).get("title", "")
    if not title:
        try:
            title = (await bot.get_chat(target_channel_id)).title or str(target_channel_id)
        except Exception:
            title = str(target_channel_id)

    try:
        await bot.approve_chat_join_request(chat_id=target_channel_id, user_id=user_id)
        await db.remove_pending_request(user_id, target_channel_id)
        await db.upsert_user(
            user_id,
            username=username or None,
            approved_at=_now(),
            target_channel_id=target_channel_id,
        )
        await db.log_event(user_id, "approved", username, target_channel_id, title)
        logger.info("Bot approved user %s for channel %s", user_id, target_channel_id)
        if notify_member:
            await msg_approved(bot, db, user_id, title)
        return True
    except Exception as e:
        logger.warning("Bot approve failed user=%s channel=%s: %s", user_id, target_channel_id, e)
        return False


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode=None)
        except Exception as e:
            logger.warning("Notify admin %s: %s", admin_id, e)


async def _handle_gate_join(
    bot: Bot, db: ClenderDB, gate_id: int, user_id: int, username: str, first_name: str = ""
) -> None:
    gate = await db.get_channel(gate_id)
    gate_title = (gate or {}).get("title", str(gate_id))

    await db.upsert_user(
        user_id,
        username=username,
        first_name=first_name or None,
        joined_gate_at=_now(),
    )
    await db.log_event(user_id, "gate_join", username, gate_id, gate_title)

    target_ids = await db.get_targets_for_gate(gate_id)
    pending = await db.get_pending_for_user(user_id)
    approved_count = 0

    for req in pending:
        tid = req["target_channel_id"]
        if tid in target_ids:
            if await _approve_user(
                bot, db, user_id, tid, username, notify_member=False
            ):
                approved_count += 1

    if not pending:
        for tid in target_ids:
            if await _approve_user(
                bot, db, user_id, tid, username, notify_member=False
            ):
                approved_count += 1

    # Nhắn member
    if approved_count > 0:
        await msg_gate_joined_approved(
            bot, db, user_id, gate_id, approved_count, username, first_name
        )
    else:
        await msg_gate_joined_wait(bot, db, user_id, gate_id, username, first_name)

    name = username or first_name or str(user_id)
    await _notify_admins(
        bot,
        f"✅ Vào gate {gate_title}\n"
        f"👤 {name} ({user_id})\n"
        f"🔓 Duyệt: {approved_count} kênh",
    )


def setup_approval_handlers(dp_router: Router, db: ClenderDB) -> None:
    @router.chat_join_request()
    async def on_join_request(event: ChatJoinRequest, bot: Bot) -> None:
        target_ids = await db.get_target_channel_ids()
        if event.chat.id not in target_ids:
            return
        user = event.from_user
        if user.is_bot:
            return

        target_title = event.chat.title or str(event.chat.id)

        await db.add_pending_request(user.id, event.chat.id)
        await db.upsert_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

        gate_id = await db.get_gate_for_target(event.chat.id)
        if not gate_id:
            await _notify_member_simple(
                bot,
                user.id,
                f"⏳ Đã nhận yêu cầu join {target_title}.\n"
                f"Admin chưa cấu hình kênh gate — liên hệ admin.",
            )
            return

        if await _user_in_gate(bot, gate_id, user.id):
            await _approve_user(bot, db, user.id, event.chat.id, user.username or "")
        else:
            await msg_need_gate(
                bot, db, user.id, target_title, gate_id,
                user.username or "", user.first_name or "",
            )

    @router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
    async def on_gate_join(event: ChatMemberUpdated, bot: Bot) -> None:
        gate_ids = await db.get_gate_channel_ids()
        if not gate_ids or event.chat.id not in gate_ids:
            return
        user = event.new_chat_member.user
        if user.is_bot:
            return
        await _handle_gate_join(
            bot, db, event.chat.id, user.id, user.username or "", user.first_name or ""
        )

    dp_router.include_router(router)


async def scan_and_approve(bot: Bot, db: ClenderDB) -> str:
    rows = await db.list_all_pending()
    if not rows:
        return "🔍 Không có pending request"

    approved = 0
    for row in rows:
        uid = row["user_id"]
        tid = row["target_channel_id"]
        gate_id = await db.get_gate_for_target(tid)
        if not gate_id:
            continue
        if await _user_in_gate(bot, gate_id, uid):
            user = await db.get_user(uid)
            username = (user or {}).get("username", "")
            if await _approve_user(bot, db, uid, tid, username, notify_member=True):
                approved += 1

    return f"🔍 Bot đã duyệt {approved}/{len(rows)} yêu cầu (đã nhắn member)"
