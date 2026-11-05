"""The signed-in session: who the user is, their favorites and history, and navigation hooks."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from cinevia import db
from cinevia.auth import User
from cinevia.data.models import Title


class Session(QObject):
    favorites_changed = Signal()
    history_changed = Signal()
    scores_changed = Signal()
    song_changed = Signal(str)  # id of the song now playing ("" when stopped)

    def __init__(self, conn: sqlite3.Connection, user: User) -> None:
        super().__init__()
        self.conn = conn
        self.user = user
        self._favorite_ids = {t["id"] for t in db.favorites(conn, user.id)}
        self.now_playing: str | None = None
        # Set by the main window.
        self.open_title: Callable[[Title], None] = lambda t: None
        self.play_trailer: Callable[[Title], None] = lambda t: None
        self.search: Callable[[str], None] = lambda q: None
        self.go: Callable[[str], None] = lambda page: None
        self.play_song: Callable[[Title, list[Title]], None] = lambda song, queue: None
        self.play_game: Callable[[str], None] = lambda key: None

    # Favorites
    def is_favorite(self, title_id: str) -> bool:
        return title_id in self._favorite_ids

    def favorites(self) -> list[Title]:
        return [Title.from_dict(d) for d in db.favorites(self.conn, self.user.id)]

    def toggle_favorite(self, title: Title) -> bool:
        if title.id in self._favorite_ids:
            db.remove_favorite(self.conn, self.user.id, title.id)
            self._favorite_ids.discard(title.id)
        else:
            db.add_favorite(self.conn, self.user.id, title.to_dict())
            self._favorite_ids.add(title.id)
        self.favorites_changed.emit()
        return title.id in self._favorite_ids

    # Search history
    def add_search(self, query: str) -> None:
        db.add_search(self.conn, self.user.id, query)
        self.history_changed.emit()

    def history(self) -> list[db.Search]:
        return db.history(self.conn, self.user.id)

    def remove_search(self, query: str) -> None:
        db.remove_search(self.conn, self.user.id, query)
        self.history_changed.emit()

    def clear_history(self) -> None:
        db.clear_history(self.conn, self.user.id)
        self.history_changed.emit()

    # Arcade scores
    def best_scores(self) -> dict[str, tuple[int, int]]:
        return db.best_scores(self.conn, self.user.id)

    def record_score(self, game: str, score: int, mode: str = "max") -> tuple[int, bool]:
        result = db.record_score(self.conn, self.user.id, game, score, mode)
        self.scores_changed.emit()
        return result

    # Preferences
    def theme(self) -> str:
        return db.theme(self.conn, self.user.id)

    def set_theme(self, name: str) -> None:
        db.set_theme(self.conn, self.user.id, name)
