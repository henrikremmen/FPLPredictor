"""Durable session registry so imported-team sessions survive an API restart.

The API itself stays stateless: a session row is just a pointer (entry ID,
horizon, risk profile) that is enough to rebuild the full ``ImportedTeam`` by
calling ``import_team`` again. Manual squad/bank/free-transfer corrections are
already persisted separately in ``data/local/team_overrides`` and are
reapplied on rebuild.

Storage is a local SQLite file, so nothing extra needs to run. One API process
owns it: the team cache, results, chats and background jobs live in that
process's memory, so several instances could not share sessions anyway.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


@dataclass
class SessionPointer:
    session_id: str
    entry_id: int
    horizon: int
    risk_profile: str


class SessionRegistry:
    def __init__(self, root: Path, db_path: str | None = None) -> None:
        self._lock = RLock()
        if db_path is None:
            override = os.environ.get("FPL_SESSIONS_DB_PATH")
            db_path = override if override else str(Path(root) / "data" / "local" / "sessions.db")
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    entry_id INTEGER NOT NULL,
                    horizon INTEGER NOT NULL,
                    risk_profile TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                )
                """
            )

    def put(self, session_id: str, entry_id: int, horizon: int, risk_profile: str) -> None:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO sessions (session_id, entry_id, horizon, risk_profile, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (session_id) DO UPDATE SET
                    entry_id = excluded.entry_id,
                    horizon = excluded.horizon,
                    risk_profile = excluded.risk_profile,
                    updated_at = excluded.updated_at
                """,
                (session_id, entry_id, horizon, risk_profile, now, now),
            )

    def get(self, session_id: str) -> SessionPointer | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id, entry_id, horizon, risk_profile FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return SessionPointer(session_id=row[0], entry_id=int(row[1]), horizon=int(row[2]), risk_profile=row[3])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
