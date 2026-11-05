"""Games: three built-in games you play right inside Cinevia (scores saved per
user in SQLite), plus a catalog of free-to-play games with gameplay videos."""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from cinevia.arcade.memory import MemoryGame
from cinevia.arcade.snake import SnakeGame
from cinevia.arcade.tictactoe import TicTacToe, winning_line
from cinevia.data import games

from .context import Session
from .pages import Page
from .theme import SANS, theme
from .widgets import ChipGroup, Row, button, card_size, icon, label

GAME_CARD = card_size("game")


# Built-in games: key, name, one-line pitch, how to play, icon, what "best" means.
ARCADE = {
    "snake": ("Snake", "Eat, grow longer, and don't hit the walls or yourself.",
              "Arrow keys or W A S D to steer. Space pauses.", "path", "max"),
    "memory": ("Memory Match", "Find all 8 pairs in as few moves as you can.",
               "Click a card to flip it, then find its twin.", "cards", "min"),
    "tictactoe": ("Tic-Tac-Toe", "You are X. Get three in a row before the computer does.",
                  "Click a square. The computer answers right away.", "hash", "sum"),
}


def best_text(key: str, best: tuple[int, int] | None) -> str:
    if not best:
        return "Not played yet"
    value, plays = best
    times = f"played {plays} {'time' if plays == 1 else 'times'}"
    if key == "memory":
        return f"Best: {value} moves · {times}"
    if key == "tictactoe":
        return f"Wins: {value} · {times}"
    return f"Best: {value} · {times}"


class ArcadeTile(QFrame):
    def __init__(self, key: str, session: Session) -> None:
        super().__init__()
        self.setObjectName("arcadeTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.key = key
        self.session = session
        name, pitch, _how, glyph, _mode = ARCADE[key]
        self.setAccessibleName(f"Play {name}")
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 20, 20, 18)
        col.setSpacing(0)
        badge = QLabel()
        badge.setObjectName("arcadeBadge")
        badge.setFixedSize(44, 44)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icon(glyph, "#ffffff").pixmap(22, 22))
        col.addWidget(badge)
        col.addSpacing(16)
        col.addWidget(label(name, "arcadeName"))
        col.addSpacing(5)
        col.addWidget(label(pitch, "arcadeText", wrap=True))
        col.addStretch()
        col.addSpacing(14)
        foot = QHBoxLayout()
        self.best = label("", "arcadeBest")
        foot.addWidget(self.best)
        foot.addStretch()
        play = button("Play", "primary", "play-fill", "#ffffff")
        play.setFixedHeight(34)
        play.clicked.connect(lambda: session.play_game(key))
        foot.addWidget(play)
        col.addLayout(foot)
        session.scores_changed.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        try:
            self.best.setText(best_text(self.key, self.session.best_scores().get(self.key)))
        except RuntimeError:
            pass

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.session.play_game(self.key)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.session.play_game(self.key)
        else:
            super().keyPressEvent(e)


class GamesPage(Page):
    def __init__(self, session: Session) -> None:
        super().__init__((40, 48, 0, 70))
        self.body.addWidget(self.header("Games", "Play a quick game right here, or browse free-to-play games and watch their gameplay."))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 12)
        head.setSpacing(9)
        head.addWidget(label("Play Now in Cinevia", "sectionTitle"))
        head.addWidget(label("Your best scores are saved to your account", "sectionMeta"), 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch()
        self.body.addLayout(head)
        tiles = QHBoxLayout()
        tiles.setContentsMargins(0, 0, 40, 0)
        tiles.setSpacing(14)
        for key in ARCADE:
            t = ArcadeTile(key, session)
            t.setMinimumHeight(206)
            tiles.addWidget(t, 1)
        self.body.addLayout(tiles)
        self.body.addSpacing(44)
        self.body.addWidget(Row("Most Played Free Games", session, card=GAME_CARD).load(games.all_games))
        for group in games.GAME_GROUPS:
            self.body.addWidget(Row(group, session, card=GAME_CARD).load(lambda g=group: games.games_in(g)))


# ---------- The boards ----------


def _font(px: int, weight: int = 600) -> QFont:
    f = QFont(SANS)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    return f


class SnakeBoard(QWidget):
    score_changed = Signal(int)
    finished = Signal(int)

    COLS, ROWS, CELL, TICK_MS = 24, 16, 26, 115
    KEYS: ClassVar[dict] = {
        Qt.Key.Key_Up: (0, -1), Qt.Key.Key_W: (0, -1),
        Qt.Key.Key_Down: (0, 1), Qt.Key.Key_S: (0, 1),
        Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_A: (-1, 0),
        Qt.Key.Key_Right: (1, 0), Qt.Key.Key_D: (1, 0),
    }

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(self.COLS * self.CELL, self.ROWS * self.CELL)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Snake board. Use the arrow keys to steer.")
        self.timer = QTimer(self, interval=self.TICK_MS)
        self.timer.timeout.connect(self._tick)
        self.restart()

    def restart(self) -> None:
        self.timer.stop()
        self.game = SnakeGame(self.COLS, self.ROWS)
        self.state = "ready"  # ready, playing, paused, over
        self.score_changed.emit(0)
        self.update()
        self.setFocus()

    def _tick(self) -> None:
        before = self.game.score
        self.game.step()
        if self.game.score != before:
            self.score_changed.emit(self.game.score)
        if not self.game.alive:
            self.timer.stop()
            self.state = "over"
            self.finished.emit(self.game.score)
        self.update()

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key in self.KEYS:
            self.game.turn(self.KEYS[key])
            if self.state in ("ready", "paused"):
                self.state = "playing"
                self.timer.start()
            self.update()
        elif key == Qt.Key.Key_Space and self.state in ("playing", "paused"):
            self.state = "paused" if self.state == "playing" else "playing"
            self.timer.stop() if self.state == "paused" else self.timer.start()
            self.update()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.state == "over":
            self.restart()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        self.setFocus()

    def focusOutEvent(self, e) -> None:
        if self.state == "playing":  # don't let the snake run while you look away
            self.state = "paused"
            self.timer.stop()
            self.update()
        super().focusOutEvent(e)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self.CELL
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color("panel"))
        p.drawRoundedRect(QRectF(self.rect()), 9, 9)
        # Faint dots mark the grid.
        p.setBrush(theme.color("line2"))
        for x in range(self.COLS):
            for y in range(self.ROWS):
                p.drawEllipse(QPointF(x * c + c / 2, y * c + c / 2), 1.2, 1.2)
        fx, fy = self.game.food
        p.setBrush(theme.color("star"))
        p.drawEllipse(QRectF(fx * c + 6, fy * c + 6, c - 12, c - 12))
        red = theme.color("red")
        for i, (x, y) in enumerate(self.game.body):
            col = QColor(red)
            col.setAlphaF(1.0 if i == 0 else max(0.45, 0.9 - i * 0.02))
            p.setBrush(col)
            p.drawRoundedRect(QRectF(x * c + 2, y * c + 2, c - 4, c - 4), 6, 6)
        message = {
            "ready": ("Press an arrow key to start", "Eat the yellow dots to grow"),
            "paused": ("Paused", "Press Space or an arrow key to keep going"),
            "over": (f"Game over · {self.game.score} {'point' if self.game.score == 1 else 'points'}",
                     "Press Enter or New game to play again"),
        }.get(self.state)
        if message:
            p.setBrush(QColor(0, 0, 0, 150 if theme.name == "dark" else 120))
            p.drawRoundedRect(QRectF(self.rect()), 9, 9)
            p.setPen(QColor("#ffffff"))
            p.setFont(_font(22))
            p.drawText(QRectF(0, self.height() / 2 - 34, self.width(), 32), Qt.AlignmentFlag.AlignCenter, message[0])
            p.setPen(QColor("#d0d2d6"))
            p.setFont(_font(13, 400))
            p.drawText(QRectF(0, self.height() / 2 + 4, self.width(), 24), Qt.AlignmentFlag.AlignCenter, message[1])
        if self.hasFocus():
            p.setPen(QPen(theme.color("line2"), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)


class MemoryBoard(QWidget):
    score_changed = Signal(int)
    finished = Signal(int)

    SYMBOLS = ("film-strip", "music-notes", "game-controller", "television-simple", "ticket", "star", "headphones", "trophy")
    SIDE, GAP, HIDE_MS = 108, 12, 750

    def __init__(self) -> None:
        super().__init__()
        n = 4 * self.SIDE + 3 * self.GAP
        self.setFixedSize(n, n)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Memory board: 16 face-down cards")
        self.setMouseTracking(True)
        self.hover = -1
        self.cursor_index = 0
        self.hide_timer = QTimer(self, singleShot=True, interval=self.HIDE_MS)
        self.hide_timer.timeout.connect(self._hide)
        self.restart()

    def restart(self) -> None:
        self.hide_timer.stop()
        self.game = MemoryGame(list(self.SYMBOLS))
        self.score_changed.emit(0)
        self.update()
        self.setFocus()

    def _hide(self) -> None:
        self.game.hide_misses()
        self.update()

    def _rect(self, i: int) -> QRectF:
        r, k = divmod(i, 4)
        return QRectF(k * (self.SIDE + self.GAP), r * (self.SIDE + self.GAP), self.SIDE, self.SIDE)

    def _at(self, pos) -> int:
        return next((i for i in range(16) if self._rect(i).contains(QPointF(pos))), -1)

    def _flip(self, i: int) -> None:
        if i < 0 or self.game.done:
            return
        self.hide_timer.stop()
        result = self.game.flip(i)
        if result in ("match", "miss"):
            self.score_changed.emit(self.game.moves)
        if result == "miss":
            self.hide_timer.start()
        if self.game.done:
            self.finished.emit(self.game.moves)
        self.update()

    def mouseMoveEvent(self, e) -> None:
        i = self._at(e.position())
        if i != self.hover:
            self.hover = i
            self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e) -> None:
        self.hover = -1
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._flip(self._at(e.position()))

    def keyPressEvent(self, e) -> None:
        moves = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -4, Qt.Key.Key_Down: 4}
        if e.key() in moves:
            self.cursor_index = (self.cursor_index + moves[e.key()]) % 16
            self.update()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._flip(self.cursor_index)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        for i in range(16):
            r = self._rect(i)
            up = i in self.game.open or i in self.game.matched
            matched = i in self.game.matched
            if up:
                p.setPen(QPen(theme.color("red") if matched else theme.color("line2"), 1.5))
                p.setBrush(theme.color("surface"))
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 7, 7)
                glyph = icon(self.game.faces[i], "red" if matched else "text").pixmap(96, 96)
                p.drawPixmap(r.adjusted(32, 32, -32, -32).toRect(), glyph)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                base = theme.color("card")
                if i == self.hover:
                    base = base.lighter(118) if theme.name == "dark" else base.darker(106)
                p.setBrush(base)
                p.drawRoundedRect(r, 7, 7)
                p.drawPixmap(r.adjusted(40, 40, -40, -40).toRect(), icon("question", "muted2").pixmap(64, 64))
            if self.hasFocus() and i == self.cursor_index:
                p.setPen(QPen(theme.color("text2"), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 9, 9)
        if self.game.done:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(QRectF(self.rect()), 9, 9)
            p.setPen(QColor("#ffffff"))
            p.setFont(_font(22))
            p.drawText(QRectF(0, self.height() / 2 - 34, self.width(), 32), Qt.AlignmentFlag.AlignCenter,
                       f"All pairs found in {self.game.moves} moves")
            p.setPen(QColor("#d0d2d6"))
            p.setFont(_font(13, 400))
            p.drawText(QRectF(0, self.height() / 2 + 4, self.width(), 24), Qt.AlignmentFlag.AlignCenter, "Press New game to shuffle again")


class TicTacToeBoard(QWidget):
    result = Signal(str)  # "X" (you won), "O" (computer won) or "draw"

    SIDE, CPU_DELAY_MS = 128, 380

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(3 * self.SIDE, 3 * self.SIDE)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Tic-tac-toe board. You are X.")
        self.setMouseTracking(True)
        self.hard = False
        self.hover = -1
        self.cursor_index = 4
        self.cpu_timer = QTimer(self, singleShot=True, interval=self.CPU_DELAY_MS)
        self.cpu_timer.timeout.connect(self._cpu)
        self.restart()

    def restart(self) -> None:
        self.cpu_timer.stop()
        self.game = TicTacToe(hard=self.hard)
        self.update()
        self.setFocus()

    def _cell(self, pos) -> int:
        x, y = int(pos.x()) // self.SIDE, int(pos.y()) // self.SIDE
        return y * 3 + x if 0 <= x < 3 and 0 <= y < 3 else -1

    def _play(self, i: int) -> None:
        if i < 0 or self.game.turn != "X" or self.cpu_timer.isActive():
            return
        if self.game.play(i):
            self._after_move()
            if not self.game.result:
                self.cpu_timer.start()

    def _cpu(self) -> None:
        if not self.game.result:
            self.game.play(self.game.cpu_move())
            self._after_move()

    def _after_move(self) -> None:
        self.update()
        if self.game.result:
            self.result.emit(self.game.result)

    def mouseMoveEvent(self, e) -> None:
        i = self._cell(e.position())
        if i != self.hover:
            self.hover = i
            self.update()

    def leaveEvent(self, e) -> None:
        self.hover = -1
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._play(self._cell(e.position()))

    def keyPressEvent(self, e) -> None:
        moves = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -3, Qt.Key.Key_Down: 3}
        if e.key() in moves:
            self.cursor_index = (self.cursor_index + moves[e.key()]) % 9
            self.update()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._play(self.cursor_index)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.SIDE
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color("panel"))
        p.drawRoundedRect(QRectF(self.rect()), 9, 9)
        line = winning_line(self.game.board) or ()
        for i in range(9):
            r = QRectF((i % 3) * s, (i // 3) * s, s, s)
            mark = self.game.board[i]
            if i in line:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.color("red", 40))
                p.drawRoundedRect(r.adjusted(6, 6, -6, -6), 7, 7)
            elif mark == " " and i == self.hover and not self.game.result:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.color("hover"))
                p.drawRoundedRect(r.adjusted(6, 6, -6, -6), 7, 7)
            inner = r.adjusted(36, 36, -36, -36)
            if mark == "X":
                p.setPen(QPen(theme.color("red"), 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(inner.topLeft(), inner.bottomRight())
                p.drawLine(inner.topRight(), inner.bottomLeft())
            elif mark == "O":
                p.setPen(QPen(theme.color("text"), 9))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(inner)
            if self.hasFocus() and i == self.cursor_index and not self.game.result:
                p.setPen(QPen(theme.color("text2"), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(4, 4, -4, -4), 8, 8)
        p.setPen(QPen(theme.color("line2"), 2))
        for k in (1, 2):
            p.drawLine(QPointF(k * s, 14), QPointF(k * s, 3 * s - 14))
            p.drawLine(QPointF(14, k * s), QPointF(3 * s - 14, k * s))


# ---------- The page around a board ----------


class ArcadePage(QWidget):
    """One built-in game: name, how to play, score and best, and the board."""

    def __init__(self, session: Session, key: str, go_back) -> None:
        super().__init__()
        self.setObjectName("page")
        self.session = session
        self.key = key if key in ARCADE else "snake"
        name, pitch, how, _glyph, self.mode = ARCADE[self.key]
        self.tally = {"X": 0, "O": 0, "draw": 0}

        col = QVBoxLayout(self)
        col.setContentsMargins(40, 26, 40, 30)
        col.setSpacing(0)
        back = button("Back to games", "textButton", "arrow-left", "text2")
        back.setStyleSheet("font-size: 10px;")
        back.clicked.connect(go_back)
        col.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        col.addSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(30)
        names = QVBoxLayout()
        names.setSpacing(6)
        names.addWidget(label(name, "pageTitle"))
        names.addWidget(label(f"{pitch} {how}", "pageSub", wrap=True))
        top.addLayout(names, 1)
        self.score = self._stat("Moves" if self.key == "memory" else ("This session" if self.key == "tictactoe" else "Score"))
        self.best = self._stat("Wins saved" if self.key == "tictactoe" else "Best")
        top.addWidget(self.score[0], 0, Qt.AlignmentFlag.AlignBottom)
        top.addWidget(self.best[0], 0, Qt.AlignmentFlag.AlignBottom)
        again = button("New game", "primary", "arrow-clockwise", "#ffffff")
        again.clicked.connect(self.restart)
        top.addWidget(again, 0, Qt.AlignmentFlag.AlignBottom)
        col.addLayout(top)
        col.addSpacing(22)

        if self.key == "snake":
            self.board = SnakeBoard()
            self.board.score_changed.connect(lambda n: self.score[1].setText(str(n)))
            self.board.finished.connect(self._finished)
        elif self.key == "memory":
            self.board = MemoryBoard()
            self.board.score_changed.connect(lambda n: self.score[1].setText(str(n)))
            self.board.finished.connect(self._finished)
        else:
            self.board = TicTacToeBoard()
            self.board.result.connect(self._ttt_result)
            self.level = ChipGroup("Computer", ["Easy", "Hard"])
            self.level.setFixedWidth(150)  # room for both chips on one line
            self.level.changed.connect(self._set_level)
            col.addWidget(self.level, 0, Qt.AlignmentFlag.AlignHCenter)
            col.addSpacing(14)
            self.status = label("Your move", "arcadeStatus")
            self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(self.status)
            col.addSpacing(12)
        col.addWidget(self.board, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addStretch()
        self._show_best()
        self._show_tally()
        self.board.setFocus()

    def _stat(self, caption: str) -> tuple[QWidget, QLabel]:
        box = QFrame()
        box.setObjectName("statBox")
        box.setMinimumWidth(112)
        c = QVBoxLayout(box)
        c.setContentsMargins(14, 9, 14, 9)
        c.setSpacing(2)
        c.addWidget(label(caption, "statCaption"))
        value = label("0", "statValue")
        c.addWidget(value)
        return box, value

    def _show_best(self) -> None:
        best = self.session.best_scores().get(self.key)
        self.best[1].setText(str(best[0]) if best else "-")

    def _show_tally(self) -> None:
        if self.key == "tictactoe":
            t = self.tally
            self.score[1].setText(f"{t['X']}-{t['O']}-{t['draw']}")
            self.score[1].setToolTip("Wins, losses and draws since you opened this game")

    def restart(self) -> None:
        self.board.restart()
        if self.key == "tictactoe":
            self.status.setText("Your move")

    def _finished(self, value: int) -> None:
        best, improved = self.session.record_score(self.key, value, self.mode)
        self.best[1].setText(str(best))
        if improved and self.key != "tictactoe":
            self.best[1].setStyleSheet(f"color: {theme.p['red_text']};")  # a new personal best

    def _set_level(self, value: str) -> None:
        self.board.hard = value == "Hard"
        self.restart()

    def _ttt_result(self, result: str) -> None:
        self.tally[result] += 1
        self._show_tally()
        self.status.setText({"X": "You win!", "O": "The computer wins this one.", "draw": "It's a draw."}[result] + " Press New game.")
        best, _ = self.session.record_score(self.key, 1 if result == "X" else 0, "sum")
        self.best[1].setText(str(best))
