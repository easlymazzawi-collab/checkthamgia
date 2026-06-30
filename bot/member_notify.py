"""Bot nhắn tin cho member tham gia — tham khảo clender force_join flow."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from clender.database import ClenderDB

logger = logging.getLogger(__name__)

DEFAULT_NEED_GATE = (
    "👋 Bạn đã gửi yêu cầu tham gia kênh: {target}\n\n"
    "📌 Bước 1: Vào kênh gate trước:\n{gate}\n\n"
    "📌 Bước 2: Sau khi vào gate, bot tự duyệt — không cần chờ admin.\n\n"
    "⚠️ Nếu không nhận tin, hãy /start bot trước."
)

DEFAULT_APPROVED = (
    "✅ Đã duyệt bạn vào kênh: {target}\n"
    "Mời bạn vào kênh xem nội dung!"
)

DEFAULT_GATE_OK = (
    "✅ Bạn đã vào kênh gate: {gate}\n"
    "🔓 Đã tự duyệt {count} kênh.\n"
    "Mời bạn kiểm tra Telegram!"
)

DEFAULT_GATE_WAIT = (
    "✅ Bạn đã vào kênh gate: {gate}\n\n"
    "⏳ Hãy gửi yêu cầu tham gia kênh đích (bấm Join kênh).\n"
    "Bot sẽ tự duyệt ngay khi nhận request."
)


async def _gate_keyboard(bot: Bot, gate_id: int) -> InlineKeyboardMarkup | None:
    try:
        chat = await bot.get_chat(gate_id)
        if chat.username:
            url = f"https://t.me/{chat.username}"
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Vào kênh gate", url=url)]
                ]
            )
        if chat.invite_link:
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Vào kênh gate", url=chat.invite_link)]
                ]
            )
    except Exception as e:
        logger.debug("gate keyboard %s: %s", gate_id, e)
    return None


async def _gate_label(bot: Bot, db: ClenderDB, gate_id: int) -> str:
    ch = await db.get_channel(gate_id)
    if ch and ch.get("title"):
        title = ch["title"]
    else:
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


async def _notify_member(
    bot: Bot, user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> bool:
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup, parse_mode=None)
        return True
    except Exception as e:
        logger.warning("Không nhắn được user %s (cần /start bot?): %s", user_id, e)
        return False


async def msg_need_gate(
    bot: Bot,
    db: ClenderDB,
    user_id: int,
    target_title: str,
    gate_id: int,
) -> bool:
    tpl = await db.get_setting("member_msg_need_gate", DEFAULT_NEED_GATE)
    gate = await _gate_label(bot, db, gate_id)
    text = tpl.format(target=target_title, gate=gate)
    kb = await _gate_keyboard(bot, gate_id)
    return await _notify_member(bot, user_id, text, kb)


async def msg_approved(
    bot: Bot, db: ClenderDB, user_id: int, target_title: str
) -> bool:
    tpl = await db.get_setting("member_msg_approved", DEFAULT_APPROVED)
    return await _notify_member(bot, user_id, tpl.format(target=target_title))


async def msg_gate_joined_approved(
    bot: Bot, db: ClenderDB, user_id: int, gate_id: int, approved_count: int
) -> bool:
    tpl = await db.get_setting("member_msg_gate_ok", DEFAULT_GATE_OK)
    gate = await _gate_label(bot, db, gate_id)
    return await _notify_member(
        bot, user_id, tpl.format(gate=gate, count=approved_count)
    )


async def msg_gate_joined_wait(
    bot: Bot, db: ClenderDB, user_id: int, gate_id: int
) -> bool:
    tpl = await db.get_setting("member_msg_gate_wait", DEFAULT_GATE_WAIT)
    gate = await _gate_label(bot, db, gate_id)
    return await _notify_member(bot, user_id, tpl.format(gate=gate))
