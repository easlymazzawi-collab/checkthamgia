"""Bot nhắn member — DM + đăng trong kênh gate (bot admin kênh)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from clender.database import ClenderDB

logger = logging.getLogger(__name__)

DEFAULT_NEED_GATE = (
    "👋 Bạn đã gửi yêu cầu tham gia: {target}\n\n"
    "📌 Vào kênh gate trước:\n{gate}\n\n"
    "📌 Bot admin sẽ tự duyệt sau khi bạn vào gate."
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

DEFAULT_GATE_CHANNEL = (
    "👋 Chào {mention}!\n"
    "✅ Bạn đã tham gia gate.\n"
    "{extra}"
)


def _user_name(username: str, first_name: str, user_id: int) -> str:
    return username and f"@{username.lstrip('@')}" or first_name or str(user_id)


def _user_mention(user_id: int, username: str, first_name: str) -> str:
    name = first_name or (username and f"@{username.lstrip('@')}") or "bạn"
    return f'<a href="tg://user?id={user_id}">{name}</a>'


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
    """DM — join request thì bot admin nhắn được, không cần /start."""
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=None)
        return True
    except Exception as e:
        logger.info("DM user %s: %s", user_id, e)
        return False


async def _post_in_gate(
    bot: Bot,
    db: ClenderDB,
    gate_id: int,
    user_id: int,
    username: str,
    first_name: str,
    extra: str,
) -> bool:
    """Đăng tin trong kênh gate — bot admin luôn nhắn được."""
    tpl = await db.get_setting("member_msg_gate_channel", DEFAULT_GATE_CHANNEL)
    mention = _user_mention(user_id, username, first_name)
    text = tpl.format(mention=mention, extra=extra, name=_user_name(username, first_name, user_id))
    try:
        await bot.send_message(gate_id, text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning("Không đăng tin gate %s: %s", gate_id, e)
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
    text = tpl.format(gate=gate, count=approved_count, name=name)
    await _dm_member(bot, user_id, text)
    extra = f"🔓 Đã tự duyệt {approved_count} kênh."
    await _post_in_gate(bot, db, gate_id, user_id, username, first_name, extra)


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
    await _post_in_gate(
        bot,
        db,
        gate_id,
        user_id,
        username,
        first_name,
        "⏳ Gửi join request kênh đích — bot sẽ tự duyệt.",
    )
