"""Forum topic helpers — tương thích Pyrogram / PyroFork."""

from __future__ import annotations

import inspect
import logging
from typing import Any, AsyncIterator

from pyrogram import raw, utils

log = logging.getLogger("forum_api")


def _thread_param(method) -> str | None:
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return None
    if "message_thread_id" in params:
        return "message_thread_id"
    if "reply_to_message_id" in params:
        return "reply_to_message_id"
    return None


def _with_thread_kw(client, method_name: str, topic_id: int) -> dict[str, int]:
    method = getattr(client, method_name, None)
    if not method:
        return {}
    key = _thread_param(method)
    return {key: topic_id} if key else {}


async def search_pinned_in_topic(client, chat_id: int, topic_id: int, *, limit: int = 5):
    """Tìm tin ghim trong forum topic — dùng raw API (top_msg_id)."""
    try:
        result = await client.invoke(
            raw.functions.messages.Search(
                peer=await client.resolve_peer(chat_id),
                q="",
                filter=raw.types.InputMessagesFilterPinned(),
                min_date=0,
                max_date=0,
                offset_id=0,
                add_offset=0,
                limit=limit,
                min_id=0,
                max_id=0,
                hash=0,
                top_msg_id=topic_id,
            ),
            sleep_threshold=60,
        )
        return await utils.parse_messages(client, result, replies=0)
    except Exception as e:
        log.debug("search_pinned_in_topic raw fail chat=%s topic=%s: %s", chat_id, topic_id, e)
        return []


async def iter_topic_history(
    client,
    chat_id: int,
    topic_id: int,
    *,
    limit: int = 500,
) -> AsyncIterator[Any]:
    """Duyệt tin trong forum topic — ưu tiên high-level API, fallback GetReplies."""
    thread_kw = _with_thread_kw(client, "get_chat_history")
    if thread_kw:
        async for msg in client.get_chat_history(chat_id, limit=limit, **thread_kw):
            yield msg
        return

    offset_id = 0
    fetched = 0
    while fetched < limit:
        batch_limit = min(100, limit - fetched)
        try:
            result = await client.invoke(
                raw.functions.messages.GetReplies(
                    peer=await client.resolve_peer(chat_id),
                    msg_id=topic_id,
                    offset_id=offset_id,
                    offset_date=0,
                    add_offset=0,
                    limit=batch_limit,
                    max_id=0,
                    min_id=0,
                    hash=0,
                ),
                sleep_threshold=60,
            )
        except Exception as e:
            log.warning("GetReplies fail chat=%s topic=%s: %s", chat_id, topic_id, e)
            return

        messages = await utils.parse_messages(client, result, replies=0)
        if not messages:
            return

        for msg in messages:
            yield msg
            fetched += 1
            if fetched >= limit:
                return

        offset_id = messages[-1].id
