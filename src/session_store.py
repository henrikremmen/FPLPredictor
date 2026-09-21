"""Durable session registry so imported-team sessions survive an API restart.

The API itself stays stateless: a session row is just a pointer (entry ID,
horizon, risk profile) that is enough to rebuild the full ``ImportedTeam`` by
calling ``import_team`` again. Manual squad/bank/free-transfer corrections are
already persisted separately in ``data/local/team_overrides`` and are
reapplied on rebuild.

Storage defaults to a local SQLite file so nothing extra needs to run for
local development. Set ``DATABASE_URL`` to a ``postgresql://`` URL to point
at a shared Postgres instance instead (requires ``psycopg2`` to be
installed); the schema and queries are written to work unchanged against
either backend.
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
    def __init__(self, root: Path, database_url: str | None = None, db_path: str | None = None) -> None:
        self._lock = RLock()
        database_url = database_url if database_url is not None else os.environ.get("DATABASE_URL")
        if database_url and database_url.startswith(("postgres://", "postgresql://")):
            import psycopg2  # optional dependency, only needed for Postgres deployments

            self._conn = psycopg2.connect(database_url)
            self._conn.autocommit = True
        else:
            if db_path is None:
                override = os.environ.get("FPL_SESSIONS_DB_PATH")
                db_path = override if override else str(Path(root) / "data" / "local" / "sessions.db")
            if db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self) -> None:
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
        placeholder = "%s" if self._is_postgres() else "?"
        query = f"""
            INSERT INTO sessions (session_id, entry_id, horizon, risk_profile, created_at, updated_at)
            VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            ON CONFLICT (session_id) DO UPDATE SET
                entry_id = excluded.entry_id,
                horizon = excluded.horizon,
                risk_profile = excluded.risk_profile,
                updated_at = excluded.updated_at
        """
        with self._lock, self._conn:
            self._conn.execute(query, (session_id, entry_id, horizon, risk_profile, now, now))

    def get(self, session_id: str) -> SessionPointer | None:
        placeholder = "%s" if self._is_postgres() else "?"
        with self._lock:
            cursor = self._conn.execute(
                f"SELECT session_id, entry_id, horizon, risk_profile FROM sessions WHERE session_id = {placeholder}",
                (session_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return SessionPointer(session_id=row[0], entry_id=int(row[1]), horizon=int(row[2]), risk_profile=row[3])

    def _is_postgres(self) -> bool:
        return type(self._conn).__module__.startswith("psycopg2")
