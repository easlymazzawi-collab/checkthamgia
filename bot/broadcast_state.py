"""Trạng thái broadcast: thu thập tin nhắn trước khi gửi."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import config


@dataclass
class BroadcastSession:
    admin_id: int
    messages: list[tuple[int, int]] = field(default_factory=list)  # (from_chat_id, message_id)
    waiting_confirm: bool = False
    _idle_task: asyncio.Task | None = field(default=None, repr=False)

    def add_message(self, chat_id: int, message_id: int) -> None:
        self.messages.append((chat_id, message_id))
        self.waiting_confirm = False

    def cancel_idle(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    def schedule_idle_check(self, callback) -> None:
        self.cancel_idle()
        self._idle_task = asyncio.create_task(self._idle_wait(callback))

    async def _idle_wait(self, callback) -> None:
        try:
            await asyncio.sleep(config.BROADCAST_IDLE_SECONDS)
            if self.messages and not self.waiting_confirm:
                self.waiting_confirm = True
                await callback()
        except asyncio.CancelledError:
            pass


# admin_id -> session
sessions: dict[int, BroadcastSession] = {}


def get_session(admin_id: int) -> BroadcastSession:
    if admin_id not in sessions:
        sessions[admin_id] = BroadcastSession(admin_id=admin_id)
    return sessions[admin_id]


def clear_session(admin_id: int) -> None:
    s = sessions.pop(admin_id, None)
    if s:
        s.cancel_idle()
