import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    ended_at TEXT,
    attacks_done INTEGER DEFAULT 0,
    gold_collected INTEGER DEFAULT 0,
    elixir_collected INTEGER DEFAULT 0,
    dark_collected INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    timestamp TEXT,
    strategy TEXT,
    enemy_gold INTEGER,
    enemy_elixir INTEGER,
    enemy_dark INTEGER,
    loot_gold INTEGER,
    loot_elixir INTEGER,
    loot_dark INTEGER,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS upgrades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    timestamp TEXT,
    target TEXT,
    cost_gold INTEGER,
    cost_elixir INTEGER,
    cost_dark INTEGER,
    success INTEGER
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    timestamp TEXT,
    level TEXT,
    message TEXT
);
"""


class Database:
    def __init__(self, path: str = "data/autoloot.db") -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()
        logger.info("Database schema initialized at %s", self.path)

    def start_session(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        cur = conn.execute("INSERT INTO sessions (started_at) VALUES (?)", (now,))
        conn.commit()
        session_id = cur.lastrowid
        logger.info("Session started: id=%d", session_id)
        return session_id

    def end_session(self, session_id: int, stats: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """UPDATE sessions SET ended_at=?, attacks_done=?, gold_collected=?, elixir_collected=?, dark_collected=?
               WHERE id=?""",
            (
                now,
                stats.get("attacks_done", 0),
                stats.get("gold_collected", 0),
                stats.get("elixir_collected", 0),
                stats.get("dark_collected", 0),
                session_id,
            ),
        )
        conn.commit()
        logger.info("Session ended: id=%d", session_id)

    def log_attack(self, session_id: int, result) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO attacks
               (session_id, timestamp, strategy, enemy_gold, enemy_elixir, enemy_dark,
                loot_gold, loot_elixir, loot_dark)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                session_id, now,
                result.strategy,
                result.enemy_gold, result.enemy_elixir, result.enemy_dark,
                result.loot_gold, result.loot_elixir, result.loot_dark,
            ),
        )
        conn.commit()

    def log_upgrade(
        self,
        session_id: int,
        target: str,
        cost_gold: int = 0,
        cost_elixir: int = 0,
        cost_dark: int = 0,
        success: bool = True,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO upgrades (session_id, timestamp, target, cost_gold, cost_elixir, cost_dark, success)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, now, target, cost_gold, cost_elixir, cost_dark, int(success)),
        )
        conn.commit()

    def log(self, session_id: int, level: str, message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO logs (session_id, timestamp, level, message) VALUES (?,?,?,?)",
            (session_id, now, level, message),
        )
        conn.commit()

    def get_session_stats(self, session_id: int) -> dict:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row:
            return dict(row)
        return {}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
