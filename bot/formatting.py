"""Gửi tin Telegram an toàn — tránh lỗi parse Markdown."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


def md_escape(text: object) -> str:
    """Escape nội dung động cho Telegram Markdown (legacy)."""
    s = str(text) if text is not None else ""
    for old, new in (("\\", "\\\\"), ("_", "\\_"), ("*", "\\*"), ("`", "\\`"), ("[", "\\[")):
        s = s.replace(old, new)
    return s


async def answer_text(message: Message, text: str) -> None:
    await message.answer(text[:4000], parse_mode=None)


async def answer_md(message: Message, text: str) -> None:
    chunk = text[:4000]
    try:
        await message.answer(chunk, parse_mode="Markdown")
    except TelegramBadRequest:
        await message.answer(chunk, parse_mode=None)
