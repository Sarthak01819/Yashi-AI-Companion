"""
Database initialization and connection management for Yashi.
Uses SQLite with WAL mode for better concurrent read performance.
"""

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Return a thread-safe SQLite connection."""
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")   # 32 MB page cache
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_cursor():
    """Context manager yielding a cursor, auto-committing on success."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database() -> None:
    """Create all tables if they don't exist."""
    logger.info("Initializing database at %s", DATABASE_PATH)
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

    with db_cursor() as cur:
        # ── conversations ─────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
                content     TEXT NOT NULL,
                emotion     TEXT DEFAULT 'neutral',
                timestamp   REAL NOT NULL DEFAULT (unixepoch('now','subsec'))
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_ts ON conversations(timestamp)")

        # ── reflections ───────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reflections (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT,
                summary     TEXT NOT NULL,
                insight     TEXT,
                mood_trend  TEXT,
                timestamp   REAL NOT NULL DEFAULT (unixepoch('now','subsec'))
            )
        """)

        # ── memory_vectors ────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_vectors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                content     TEXT NOT NULL,
                source      TEXT DEFAULT 'conversation',
                vector_blob BLOB NOT NULL,
                timestamp   REAL NOT NULL DEFAULT (unixepoch('now','subsec'))
            )
        """)

        # ── personal_facts ────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS personal_facts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT NOT NULL,
                fact        TEXT NOT NULL UNIQUE,
                confidence  REAL DEFAULT 1.0,
                timestamp   REAL NOT NULL DEFAULT (unixepoch('now','subsec'))
            )
        """)

        # ── behavior_state ────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS behavior_state (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  REAL NOT NULL DEFAULT (unixepoch('now','subsec'))
            )
        """)

        # ── session_stats ─────────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS session_stats (
                session_id      TEXT PRIMARY KEY,
                start_time      REAL NOT NULL,
                total_messages  INTEGER DEFAULT 0,
                total_seconds   REAL DEFAULT 0.0,
                date            TEXT NOT NULL
            )
        """)

    logger.info("Database ready.")


def add_narrative_entry(session_id: str, content: str) -> int:
    """Append to the rolling narrative memory (story of the user over time)."""
    import time
    with db_cursor() as cur:
        # Store narrative as a reflection entry only — no dummy vector blobs
        cur.execute(
            "INSERT OR IGNORE INTO reflections"
            " (session_id, summary, insight, mood_trend, timestamp)"
            " VALUES (?,?,?,?,?)",
            (session_id, f"[NARRATIVE] {content}", "", "narrative", time.time()),
        )
        return cur.lastrowid


def get_narrative(session_id: str, limit: int = 10) -> list:
    """Return the narrative thread for a session."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT summary, timestamp FROM reflections WHERE session_id=? AND mood_trend='narrative' "
            "ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]
