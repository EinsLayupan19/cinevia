"""Memory match: flip two cards; a pair stays open, a miss closes again."""

from __future__ import annotations

import random


class MemoryGame:
    def __init__(self, symbols: list[str], rng: random.Random | None = None) -> None:
        self.faces = [*symbols, *symbols]
        (rng or random.Random()).shuffle(self.faces)
        self.open: set[int] = set()  # face up, not yet matched
        self.matched: set[int] = set()
        self.moves = 0  # one move = turning over a second card

    @property
    def done(self) -> bool:
        return len(self.matched) == len(self.faces)

    def hide_misses(self) -> None:
        self.open.clear()

    def flip(self, i: int) -> str | None:
        """Returns "first", "match" or "miss"; None when the click does nothing."""
        if len(self.open) == 2:
            self.hide_misses()  # the player clicked on before the miss closed by itself
        if i in self.open or i in self.matched or not 0 <= i < len(self.faces):
            return None
        self.open.add(i)
        if len(self.open) == 1:
            return "first"
        self.moves += 1
        a, b = self.open
        if self.faces[a] == self.faces[b]:
            self.matched |= self.open
            self.open.clear()
            return "match"
        return "miss"
