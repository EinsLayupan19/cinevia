"""SQLite storage: user accounts, plus each user's favorites, search history, game scores and theme."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "cinevia.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    salt          BLOB    NOT NULL,
    password_hash BLOB    NOT NULL,
    iterations    INTEGER NOT NULL,
    theme         TEXT    NOT NULL DEFAULT 'dark',
    created_at    REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title_id TEXT    NOT NULL,
    data     TEXT    NOT NULL,
    added_at REAL    NOT NULL,
    PRIMARY KEY (user_id, title_id)
);

CREATE TABLE IF NOT EXISTS history (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query       TEXT    NOT NULL COLLATE NOCASE,
    searched_at REAL    NOT NULL,
    PRIMARY KEY (user_id, query)
);

CREATE TABLE IF NOT EXISTS scores (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    game       TEXT    NOT NULL,
    best       INTEGER NOT NULL,
    plays      INTEGER NOT NULL DEFAULT 0,
    updated_at REAL    NOT NULL,
    PRIMARY KEY (user_id, game)
);
"""

HISTORY_LIMIT = 30


def connect(path: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Opens the database (``CINEVIA_DB`` overrides the default location)."""
    target = path or os.environ.get("CINEVIA_DB") or DEFAULT_PATH
    if str(target) != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)


# ---------- Favorites ----------


def favorites(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT data FROM favorites WHERE user_id = ? ORDER BY added_at DESC", (user_id,)
    ).fetchall()
    return [json.loads(r["data"]) for r in rows]


def is_favorite(conn: sqlite3.Connection, user_id: int, title_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM favorites WHERE user_id = ? AND title_id = ?", (user_id, title_id)
    ).fetchone()
    return row is not None


def add_favorite(conn: sqlite3.Connection, user_id: int, title: dict) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO favorites (user_id, title_id, data, added_at) VALUES (?, ?, ?, ?)",
            (user_id, title["id"], json.dumps(title), time.time()),
        )


def remove_favorite(conn: sqlite3.Connection, user_id: int, title_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM favorites WHERE user_id = ? AND title_id = ?", (user_id, title_id))


# ---------- Search history ----------


@dataclass(frozen=True)
class Search:
    query: str
    at: float


def add_search(conn: sqlite3.Connection, user_id: int, query: str, at: float | None = None) -> None:
    q = query.strip()
    if len(q) < 2:
        return
    with conn:
        # Same query in any letter case counts once; the newest spelling wins.
        conn.execute("DELETE FROM history WHERE user_id = ? AND query = ?", (user_id, q))
        conn.execute(
            "INSERT INTO history (user_id, query, searched_at) VALUES (?, ?, ?)",
            (user_id, q, time.time() if at is None else at),
        )
        conn.execute(
            """DELETE FROM history WHERE user_id = ? AND query NOT IN (
                   SELECT query FROM history WHERE user_id = ? ORDER BY searched_at DESC LIMIT ?)""",
            (user_id, user_id, HISTORY_LIMIT),
        )


def history(conn: sqlite3.Connection, user_id: int) -> list[Search]:
    rows = conn.execute(
        "SELECT query, searched_at FROM history WHERE user_id = ? ORDER BY searched_at DESC", (user_id,)
    ).fetchall()
    return [Search(r["query"], r["searched_at"]) for r in rows]


def remove_search(conn: sqlite3.Connection, user_id: int, query: str) -> None:
    with conn:
        conn.execute("DELETE FROM history WHERE user_id = ? AND query = ?", (user_id, query))


def clear_history(conn: sqlite3.Connection, user_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))


# ---------- Arcade scores ----------


def record_score(conn: sqlite3.Connection, user_id: int, game: str, score: int, mode: str = "max") -> tuple[int, bool]:
    """Saves one finished game. ``mode`` says what "best" means: the highest score
    ("max"), the fewest moves ("min") or a running total such as wins ("sum").
    Returns the best after this game and whether this game improved it."""
    row = conn.execute("SELECT best FROM scores WHERE user_id = ? AND game = ?", (user_id, game)).fetchone()
    old = row["best"] if row else None
    if mode == "sum":
        best = (old or 0) + score
    elif mode == "min":
        best = score if old is None else min(old, score)
    else:
        best = score if old is None else max(old, score)
    improved = old is None or best != old
    with conn:
        conn.execute(
            """INSERT INTO scores (user_id, game, best, plays, updated_at) VALUES (?, ?, ?, 1, ?)
               ON CONFLICT (user_id, game) DO UPDATE SET best = excluded.best, plays = plays + 1,
               updated_at = excluded.updated_at""",
            (user_id, game, best, time.time()),
        )
    return best, improved


def best_scores(conn: sqlite3.Connection, user_id: int) -> dict[str, tuple[int, int]]:
    """{game: (best, times played)} for one user."""
    rows = conn.execute("SELECT game, best, plays FROM scores WHERE user_id = ?", (user_id,)).fetchall()
    return {r["game"]: (r["best"], r["plays"]) for r in rows}


# ---------- Preferences ----------


def theme(conn: sqlite3.Connection, user_id: int) -> str:
    row = conn.execute("SELECT theme FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["theme"] if row else "dark"


def set_theme(conn: sqlite3.Connection, user_id: int, value: str) -> None:
    if value not in ("dark", "light"):
        raise ValueError(f"unknown theme {value!r}")
    with conn:
        conn.execute("UPDATE users SET theme = ? WHERE id = ?", (value, user_id))
