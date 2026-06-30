import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClenderDB:
    """Kho dữ liệu clender: người dùng, kênh, tham gia, cấu hình."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE NOT NULL,
                    title TEXT,
                    channel_type TEXT NOT NULL DEFAULT 'target',
                    gate_channel_id INTEGER,
                    folder_name TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    joined_gate_at TEXT,
                    approved_at TEXT,
                    target_channel_id INTEGER,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS join_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    event_type TEXT NOT NULL,
                    channel_id INTEGER,
                    channel_title TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pending_requests (
                    user_id INTEGER NOT NULL,
                    target_channel_id INTEGER NOT NULL,
                    requested_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, target_channel_id)
                );

                CREATE TABLE IF NOT EXISTS folders (
                    folder_name TEXT PRIMARY KEY,
                    gate_channel_id INTEGER NOT NULL,
                    gate_title TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.commit()
            await self._migrate(db)

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        try:
            await db.execute(
                "ALTER TABLE channels ADD COLUMN gate_channel_id INTEGER"
            )
            await db.commit()
        except Exception:
            pass
        try:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS folders (
                    folder_name TEXT PRIMARY KEY,
                    gate_channel_id INTEGER NOT NULL,
                    gate_title TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.commit()
        except Exception:
            pass

    async def set_folder_gate(
        self, folder_name: str, gate_channel_id: int, gate_title: str = ""
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO folders (folder_name, gate_channel_id, gate_title, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(folder_name) DO UPDATE SET
                    gate_channel_id = excluded.gate_channel_id,
                    gate_title = excluded.gate_title
                """,
                (folder_name, gate_channel_id, gate_title, _now()),
            )
            await db.commit()
        await self.add_channel(
            gate_channel_id, gate_title or folder_name, "gate", folder_name, gate_channel_id
        )
        await self.apply_folder_gate_to_targets(folder_name)

    async def get_folder_gate(self, folder_name: str) -> int | None:
        if not folder_name:
            return None
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT gate_channel_id FROM folders WHERE folder_name = ?", (folder_name,)
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else None

    async def get_folder(self, folder_name: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM folders WHERE folder_name = ?", (folder_name,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_folders(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM folders ORDER BY folder_name") as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def apply_folder_gate_to_targets(self, folder_name: str) -> int:
        gate_id = await self.get_folder_gate(folder_name)
        if not gate_id:
            return 0
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE channels SET gate_channel_id = ?
                WHERE channel_type = 'target' AND folder_name = ?
                """,
                (gate_id, folder_name),
            )
            await db.commit()
            return cur.rowcount

    async def list_targets_by_folder(self, folder_name: str) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM channels WHERE channel_type='target' AND folder_name=? ORDER BY id",
                (folder_name,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_gate_channel_ids(self) -> list[int]:
        gates = await self.list_channels("gate")
        ids = [g["chat_id"] for g in gates]
        for f in await self.list_folders():
            gid = f["gate_channel_id"]
            if gid not in ids:
                ids.append(gid)
        legacy = await self.get_setting("gate_channel_id")
        if legacy:
            lid = int(legacy)
            if lid not in ids:
                ids.append(lid)
        return ids

    async def get_gate_for_target(self, target_channel_id: int) -> int | None:
        ch = await self.get_channel(target_channel_id)
        if ch:
            if ch.get("gate_channel_id"):
                return int(ch["gate_channel_id"])
            folder = ch.get("folder_name") or ""
            if folder:
                fg = await self.get_folder_gate(folder)
                if fg:
                    return fg
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT gate_channel_id FROM channels WHERE chat_id = ? AND channel_type = 'target'",
                (target_channel_id,),
            ) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    return int(row[0])
        gates = await self.get_gate_channel_ids()
        return gates[0] if gates else None

    async def get_targets_for_gate(self, gate_id: int) -> list[int]:
        targets = await self.list_channels("target")
        folders = await self.list_folders()
        folder_names = {f["folder_name"] for f in folders if f["gate_channel_id"] == gate_id}
        result: list[int] = []
        for t in targets:
            g = t.get("gate_channel_id")
            if g and int(g) == gate_id:
                result.append(t["chat_id"])
            elif not g and t.get("folder_name") in folder_names:
                result.append(t["chat_id"])
        return result

    async def set_channel_folder(self, chat_id: int, folder_name: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE channels SET folder_name = ? WHERE chat_id = ?",
                (folder_name, chat_id),
            )
            await db.commit()

    async def set_target_gate(self, target_channel_id: int, gate_channel_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE channels SET gate_channel_id = ? WHERE chat_id = ? AND channel_type = 'target'",
                (gate_channel_id, target_channel_id),
            )
            await db.commit()

    async def get_channel(self, chat_id: int) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM channels WHERE chat_id = ?", (chat_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_setting(self, key: str, default: str = "") -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            await db.commit()

    async def get_gate_channel_id(self) -> int | None:
        val = await self.get_setting("gate_channel_id")
        return int(val) if val else None

    async def set_gate_channel_id(self, chat_id: int) -> None:
        await self.set_setting("gate_channel_id", str(chat_id))

    async def get_target_channel_ids(self) -> list[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT chat_id FROM channels WHERE channel_type = 'target'"
            ) as cur:
                rows = await cur.fetchall()
                return [r[0] for r in rows]

    async def add_channel(
        self,
        chat_id: int,
        title: str,
        channel_type: str = "target",
        folder_name: str = "",
        gate_channel_id: int | None = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO channels (chat_id, title, channel_type, gate_channel_id, folder_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title = excluded.title,
                    channel_type = excluded.channel_type,
                    gate_channel_id = COALESCE(excluded.gate_channel_id, channels.gate_channel_id),
                    folder_name = excluded.folder_name
                """,
                (chat_id, title, channel_type, gate_channel_id, folder_name, _now()),
            )
            await db.commit()

    async def remove_channel(self, chat_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
            await db.commit()

    async def list_channels(self, channel_type: str | None = None) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if channel_type:
                async with db.execute(
                    "SELECT * FROM channels WHERE channel_type = ? ORDER BY id",
                    (channel_type,),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute(
                    "SELECT * FROM channels ORDER BY id"
                ) as cur:
                    rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def upsert_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        phone: str | None = None,
        **extra: Any,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cur:
                existing = await cur.fetchone()

            fields = {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
            }
            if existing:
                merged = dict(existing)
                for k, v in fields.items():
                    if v is not None:
                        merged[k] = v
                for k, v in extra.items():
                    if v is not None:
                        merged[k] = v
                await db.execute(
                    """
                    UPDATE users SET username=?, first_name=?, last_name=?, phone=?,
                        joined_gate_at=?, approved_at=?, target_channel_id=?, updated_at=?
                    WHERE user_id=?
                    """,
                    (
                        merged.get("username"),
                        merged.get("first_name"),
                        merged.get("last_name"),
                        merged.get("phone"),
                        merged.get("joined_gate_at"),
                        merged.get("approved_at"),
                        merged.get("target_channel_id"),
                        _now(),
                        user_id,
                    ),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, last_name, phone,
                        joined_gate_at, approved_at, target_channel_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        username,
                        first_name,
                        last_name,
                        phone,
                        extra.get("joined_gate_at"),
                        extra.get("approved_at"),
                        extra.get("target_channel_id"),
                        _now(),
                    ),
                )
            await db.commit()

    async def get_user(self, user_id: int) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_all_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users") as cur:
                rows = await cur.fetchall()
                return [r[0] for r in rows]

    async def log_event(
        self,
        user_id: int,
        event_type: str,
        username: str = "",
        channel_id: int | None = None,
        channel_title: str = "",
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO join_events (user_id, username, event_type, channel_id, channel_title, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, event_type, channel_id, channel_title, _now()),
            )
            await db.commit()

    async def add_pending_request(self, user_id: int, target_channel_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO pending_requests (user_id, target_channel_id, requested_at)
                VALUES (?, ?, ?)
                """,
                (user_id, target_channel_id, _now()),
            )
            await db.commit()

    async def remove_pending_request(self, user_id: int, target_channel_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM pending_requests WHERE user_id=? AND target_channel_id=?",
                (user_id, target_channel_id),
            )
            await db.commit()

    async def get_pending_for_user(self, user_id: int) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM pending_requests WHERE user_id = ?", (user_id,)
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def list_all_pending(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT user_id, target_channel_id FROM pending_requests"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def stats_summary(self) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                total_users = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE joined_gate_at IS NOT NULL"
            ) as cur:
                gate_joined = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE approved_at IS NOT NULL"
            ) as cur:
                approved = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM join_events WHERE event_type='gate_join'"
            ) as cur:
                gate_events = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM join_events WHERE event_type='approved'"
            ) as cur:
                approve_events = (await cur.fetchone())[0]
            return {
                "total_users": total_users,
                "gate_joined": gate_joined,
                "approved": approved,
                "gate_events": gate_events,
                "approve_events": approve_events,
            }

    async def stats_by_channel(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT channel_id, channel_title, event_type, COUNT(*) as cnt
                FROM join_events
                WHERE channel_id IS NOT NULL
                GROUP BY channel_id, event_type
                ORDER BY channel_id, event_type
                """
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def recent_events(self, limit: int = 20) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM join_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def export_json(self) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            data: dict[str, Any] = {"exported_at": _now()}
            for table in ("settings", "channels", "users", "join_events", "pending_requests", "folders"):
                async with db.execute(f"SELECT * FROM {table}") as cur:
                    rows = await cur.fetchall()
                    data[table] = [dict(r) for r in rows]
            return json.dumps(data, ensure_ascii=False, indent=2)
