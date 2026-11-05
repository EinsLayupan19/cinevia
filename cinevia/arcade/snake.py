"""Snake: the rules only (no drawing), so they can be unit tested."""

from __future__ import annotations

import random

Cell = tuple[int, int]


class SnakeGame:
    def __init__(self, width: int = 24, height: int = 16, rng: random.Random | None = None) -> None:
        self.width = width
        self.height = height
        self.rng = rng or random.Random()
        x, y = width // 2, height // 2
        self.body: list[Cell] = [(x, y), (x - 1, y), (x - 2, y)]  # head first
        self.direction: Cell = (1, 0)
        self._next: Cell = self.direction
        self.score = 0
        self.alive = True
        self.food = self._place_food()

    def _place_food(self) -> Cell:
        free = [(x, y) for x in range(self.width) for y in range(self.height) if (x, y) not in self.body]
        return self.rng.choice(free) if free else self.body[0]

    def turn(self, direction: Cell) -> None:
        # A U-turn would run straight into the neck, so it is ignored.
        if (direction[0] + self.direction[0], direction[1] + self.direction[1]) != (0, 0):
            self._next = direction

    def step(self) -> None:
        if not self.alive:
            return
        self.direction = self._next
        hx, hy = self.body[0]
        head = (hx + self.direction[0], hy + self.direction[1])
        eating = head == self.food
        body = self.body if eating else self.body[:-1]
        if not (0 <= head[0] < self.width and 0 <= head[1] < self.height) or head in body:
            self.alive = False
            return
        self.body = [head, *body]
        if eating:
            self.score += 1
            self.food = self._place_food()
