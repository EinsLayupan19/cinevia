"""Tic-tac-toe against the computer. You are X and go first; the computer is O.
Hard uses minimax (it never loses); Easy wins or blocks when it can, otherwise guesses."""

from __future__ import annotations

import random

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def winner(board: list[str]) -> str | None:
    """"X" or "O" for three in a row, "draw" for a full board, otherwise None."""
    for a, b, c in LINES:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return "draw" if " " not in board else None


def winning_line(board: list[str]) -> tuple[int, int, int] | None:
    for line in LINES:
        a, b, c = line
        if board[a] != " " and board[a] == board[b] == board[c]:
            return line
    return None


def _minimax(board: list[str], turn: str) -> int:
    w = winner(board)
    if w == "O":
        return 1
    if w == "X":
        return -1
    if w == "draw":
        return 0
    scores = []
    for i in range(9):
        if board[i] == " ":
            board[i] = turn
            scores.append(_minimax(board, "X" if turn == "O" else "O"))
            board[i] = " "
    return max(scores) if turn == "O" else min(scores)


class TicTacToe:
    def __init__(self, hard: bool = True, rng: random.Random | None = None) -> None:
        self.hard = hard
        self.rng = rng or random.Random()
        self.board = [" "] * 9
        self.turn = "X"
        self.result: str | None = None

    def play(self, i: int) -> bool:
        if self.result or self.board[i] != " ":
            return False
        self.board[i] = self.turn
        self.turn = "O" if self.turn == "X" else "X"
        self.result = winner(self.board)
        return True

    def _finishing(self, mark: str) -> int | None:
        """A square that completes three in a row for ``mark``."""
        for a, b, c in LINES:
            cells = [self.board[a], self.board[b], self.board[c]]
            if cells.count(mark) == 2 and cells.count(" ") == 1:
                return (a, b, c)[cells.index(" ")]
        return None

    def cpu_move(self) -> int:
        free = [i for i in range(9) if self.board[i] == " "]
        win = self._finishing("O")
        if win is not None:
            return win
        block = self._finishing("X")
        if block is not None:
            return block
        if not self.hard:
            return self.rng.choice(free)
        best, best_score = free[0], -2
        for i in free:
            self.board[i] = "O"
            score = _minimax(self.board, "X")
            self.board[i] = " "
            if score > best_score:
                best, best_score = i, score
        return best
