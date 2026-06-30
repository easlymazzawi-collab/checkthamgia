"""Parse link addlist Telegram (t.me/addlist/...)."""

from __future__ import annotations

import re

_ADDLIST_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/addlist/([A-Za-z0-9_-]+)"
    r"|tg://addlist\?slug=([A-Za-z0-9_-]+)"
    r"|^([A-Za-z0-9_-]{8,})$"
)


def parse_addlist_slug(text: str) -> str | None:
    text = text.strip()
    m = _ADDLIST_RE.search(text)
    if not m:
        return None
    return next(g for g in m.groups() if g)
