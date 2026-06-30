"""Unpin old + pin next content marker in forum topic."""

import logging

from pyrogram import enums
from pyrogram.errors import FloodWait, RPCError

from core.forum_api import search_pinned_in_topic

log = logging.getLogger("pin_manager")


async def get_pinned_message_id(client, chat_id: int, topic_id: int) -> int | None:
    try:
        messages = await search_pinned_in_topic(client, chat_id, topic_id, limit=5)
        for msg in messages:
            if msg and not msg.empty:
                return msg.id
    except Exception as e:
        log.debug("search_pinned_in_topic: %s", e)

    try:
        async for msg in client.search_messages(
            chat_id,
            query="",
            filter=enums.MessagesFilter.PINNED,
            limit=20,
        ):
            if not msg or msg.empty:
                continue
            header = getattr(msg, "reply_to_message", None) or getattr(msg, "reply_to", None)
            if header is None:
                continue
            top_id = getattr(header, "message_thread_id", None) or getattr(
                header, "reply_to_top_id", None
            )
            if top_id == topic_id:
                return msg.id
    except Exception as e:
        log.debug("search_messages pinned: %s", e)

    try:
        pinned = await client.get_chat_pinned_message(chat_id)
        if pinned and not pinned.empty:
            header = getattr(pinned, "reply_to_message", None) or getattr(pinned, "reply_to", None)
            top_id = None
            if header is not None:
                top_id = getattr(header, "message_thread_id", None) or getattr(
                    header, "reply_to_top_id", None
                )
            if top_id in (None, topic_id):
                return pinned.id
    except Exception as e:
        log.warning("get_pinned_message_id: %s", e)

    return None


async def unpin_message(client, chat_id: int, msg_id: int | None) -> None:
    if not msg_id:
        return
    try:
        await client.unpin_chat_message(chat_id, msg_id)
        log.info("Unpinned chat=%s msg=%s", chat_id, msg_id)
    except FloodWait as e:
        import asyncio
        await asyncio.sleep(e.value + 1)
        await client.unpin_chat_message(chat_id, msg_id)
    except RPCError as e:
        log.warning("unpin fail chat=%s msg=%s: %s", chat_id, msg_id, e)


async def pin_message(client, chat_id: int, msg_id: int) -> None:
    try:
        await client.pin_chat_message(chat_id, msg_id, disable_notification=True)
        log.info("Pinned chat=%s msg=%s", chat_id, msg_id)
    except FloodWait as e:
        import asyncio
        await asyncio.sleep(e.value + 1)
        await client.pin_chat_message(chat_id, msg_id, disable_notification=True)
    except RPCError as e:
        log.warning("pin fail chat=%s msg=%s: %s", chat_id, msg_id, e)
        raise


async def advance_topic_pin(
    client,
    chat_id: int,
    topic_id: int,
    old_pin_msg_id: int | None,
    new_pin_msg_id: int,
) -> None:
    """Unpin marker cũ, ghim bài tiếp theo chưa up."""
    await unpin_message(client, chat_id, old_pin_msg_id)
    await pin_message(client, chat_id, new_pin_msg_id)
