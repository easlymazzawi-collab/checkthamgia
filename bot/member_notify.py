"""Bot nhắn member trực tiếp (DM) — bot admin + join request."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from clender.database import ClenderDB

logger = logging.getLogger(__name__)

DEFAULT_NEED_GATE = (
    "👋 Bạn đã gửi yêu cầu tham gia: {target}\n\n"
    "📌 Vào kênh gate trước:\n{gate}\n\n"
    "📌 Bot sẽ tự duyệt sau khi bạn vào gate."
)

DEFAULT_APPROVED = (
    "✅ Đã duyệt bạn vào kênh: {target}\n"
    "Mời bạn vào kênh xem nội dung!"
)

DEFAULT_GATE_OK = (
    "✅ Chào {name}! Bạn đã vào gate.\n"
    "🔓 Bot đã tự duyệt {count} kênh — kiểm tra Telegram nhé!"
)

DEFAULT_GATE_WAIT = (
    "✅ Chào {name}! Bạn đã vào gate.\n\n"
    "⏳ Hãy bấm Join các kênh đích — bot sẽ tự duyệt ngay."
)


def _user_name(username: str, first_name: str, user_id: int) -> str:
    return username and f"@{username.lstrip('@')}" or first_name or str(user_id)


async def _gate_keyboard(bot: Bot, gate_id: int) -> InlineKeyboardMarkup | None:
    try:
        chat = await bot.get_chat(gate_id)
        if chat.username:
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Kênh gate", url=f"https://t.me/{chat.username}")]
                ]
            )
        if chat.invite_link:
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Kênh gate", url=chat.invite_link)]
                ]
            )
    except Exception as e:
        logger.debug("gate keyboard %s: %s", gate_id, e)
    return None


async def _gate_label(bot: Bot, db: ClenderDB, gate_id: int) -> str:
    ch = await db.get_channel(gate_id)
    title = (ch or {}).get("title") or ""
    if not title:
        try:
            title = (await bot.get_chat(gate_id)).title or str(gate_id)
        except Exception:
            title = str(gate_id)
    try:
        chat = await bot.get_chat(gate_id)
        if chat.username:
            return f"{title} (@{chat.username})"
    except Exception:
        pass
    return title


async def _dm_member(
    bot: Bot, user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> bool:
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=None)
        return True
    except Exception as e:
        logger.warning("Không nhắn user %s: %s", user_id, e)
        return False


async def msg_need_gate(
    bot: Bot,
    db: ClenderDB,
    user_id: int,
    target_title: str,
    gate_id: int,
    username: str = "",
    first_name: str = "",
) -> None:
    tpl = await db.get_setting("member_msg_need_gate", DEFAULT_NEED_GATE)
    gate = await _gate_label(bot, db, gate_id)
    text = tpl.format(
        target=target_title,
        gate=gate,
        name=_user_name(username, first_name, user_id),
    )
    kb = await _gate_keyboard(bot, gate_id)
    await _dm_member(bot, user_id, text, kb)


async def msg_approved(
    bot: Bot, db: ClenderDB, user_id: int, target_title: str
) -> None:
    tpl = await db.get_setting("member_msg_approved", DEFAULT_APPROVED)
    await _dm_member(bot, user_id, tpl.format(target=target_title))


async def msg_gate_joined_approved(
    bot: Bot,
    db: ClenderDB,
    user_id: int,
    gate_id: int,
    approved_count: int,
    username: str = "",
    first_name: str = "",
) -> None:
    tpl = await db.get_setting("member_msg_gate_ok", DEFAULT_GATE_OK)
    gate = await _gate_label(bot, db, gate_id)
    name = _user_name(username, first_name, user_id)
    await _dm_member(bot, user_id, tpl.format(gate=gate, count=approved_count, name=name))


async def msg_gate_joined_wait(
    bot: Bot,
    db: ClenderDB,
    user_id: int,
    gate_id: int,
    username: str = "",
    first_name: str = "",
) -> None:
    tpl = await db.get_setting("member_msg_gate_wait", DEFAULT_GATE_WAIT)
    gate = await _gate_label(bot, db, gate_id)
    name = _user_name(username, first_name, user_id)
    await _dm_member(bot, user_id, tpl.format(gate=gate, name=name))
