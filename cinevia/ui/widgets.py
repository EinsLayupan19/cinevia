"""Shared building blocks: icons, labels, poster cards, carousels and grids."""

from __future__ import annotations

from collections.abc import Callable

import qtawesome as qta
from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cinevia.data.http import FetchError
from cinevia.data.models import Title

from .context import Session
from .images import images
from .theme import DISPLAY, SANS, theme
from .workers import run_async

# ---------- Small helpers ----------


def icon(name: str, color: str | QColor = "text", size: int = 18) -> QIcon:
    c = color if isinstance(color, QColor) else (theme.color(color) if color in theme.p else QColor(color))
    return qta.icon(f"ph.{name}", color=c)


def font(family: str = SANS, px: int = 12, weight: int = 400) -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    return f


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


def label(text: str, name: str, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def button(text: str, name: str, icon_name: str | None = None, icon_color: str = "text") -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName(name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        btn.setIcon(icon(icon_name, icon_color))
        btn.setIconSize(QSize(17, 17))
    return btn


def cover_pixmap(pix: QPixmap, size: QSize, focus_y: float = 0.5) -> QPixmap:
    """Scales ``pix`` to fill ``size`` (like CSS object-fit: cover), cropping around ``focus_y``."""
    if pix.isNull() or size.isEmpty():
        return QPixmap()
    scaled = pix.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = (scaled.width() - size.width()) // 2
    y = int((scaled.height() - size.height()) * focus_y)
    return scaled.copy(QRect(x, y, size.width(), size.height()))


def soft_blur(pix: QPixmap, factor: int = 10) -> QPixmap:
    """A cheap blur: shrink, then scale back up smoothly."""
    if pix.isNull():
        return pix
    small = pix.scaled(max(1, pix.width() // factor), max(1, pix.height() // factor), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return small.scaled(pix.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def wrap_text(text: str, metrics: QFontMetrics, width: int, max_lines: int) -> list[str]:
    """Word-wraps ``text`` into at most ``max_lines`` lines, eliding the last one."""
    words, lines, line = text.split(), [], ""
    for i, word in enumerate(words):
        trial = f"{line} {word}".strip()
        if metrics.horizontalAdvance(trial) <= width or not line:
            line = trial
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines - 1:
            line = " ".join(words[i:])
            break
    if line:
        lines.append(metrics.elidedText(line, Qt.TextElideMode.ElideRight, width))
    return lines[:max_lines]


class ClampLabel(QLabel):
    """A label that shows at most ``max_lines`` lines and ends with an ellipsis."""

    def __init__(self, text: str = "", name: str = "body", max_lines: int = 3) -> None:
        super().__init__()
        self.setObjectName(name)
        self.full = text
        self.max_lines = max_lines
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setToolTip(text if len(text) > 160 else "")

    def set_full(self, text: str) -> None:
        self.full = text
        self._relayout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        if self.width() <= 0:
            return
        lines = wrap_text(self.full, self.fontMetrics(), self.width() - 2, self.max_lines)
        text = "\n".join(lines)
        if text != self.text():
            self.setText(text)
            self.setMinimumHeight(self.fontMetrics().lineSpacing() * len(lines) + 4)


class Eyebrow(QWidget):
    """The small red-ruled uppercase label above a heading."""

    def __init__(self, text: str) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        rule = QFrame()
        rule.setFixedSize(18, 2)
        rule.setStyleSheet("background: #e50914;")
        row.addWidget(rule)
        row.addWidget(label(text.upper(), "eyebrow"))
        row.addStretch()


def chips(values: list[str]) -> QWidget:
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(7)
    for v in values:
        row.addWidget(label(v, "chip"))
    row.addStretch()
    return w


class OutlineTitle(QWidget):
    """Display type in Oswald. ``outline`` lines are drawn as a stroke, like the reference hero."""

    def __init__(self, solid: str, outline: str = "", px: int = 59, upper: bool = True) -> None:
        super().__init__()
        self.lines = [(solid.upper() if upper else solid, False)]
        if outline:
            self.lines.append((outline.upper() if upper else outline, True))
        self.px = px
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._fit()

    def _font(self) -> QFont:
        f = font(DISPLAY, self.px, 700)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98)
        return f

    def _fit(self) -> None:
        QFontMetrics(self._font())
        self.setFixedHeight(int(self.px * 0.92) * len(self.lines) + int(self.px * 0.18))

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self._font())
        return QSize(max(fm.horizontalAdvance(t) for t, _ in self.lines) + 4, self.height())

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = self._font()
        fm = QFontMetrics(f)
        y = fm.ascent() - int(self.px * 0.06)
        for text, stroked in self.lines:
            text = fm.elidedText(text, Qt.TextElideMode.ElideRight, self.width() - 2)
            path = QPainterPath()
            path.addText(QPointF(1, y), f, text)
            if stroked:
                p.setPen(QPen(theme.color("text"), 1.1))
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.color("text"))
            p.drawPath(path)
            y += int(self.px * 0.92)


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str, action: QPushButton | None = None, compact: bool = False) -> None:
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 24 if compact else 60, 0, 24 if compact else 60)
        col.setSpacing(6)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        badge = QLabel()
        badge.setObjectName("emptyIcon")
        badge.setFixedSize(62, 62)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icon(icon_name, "red").pixmap(26, 26))
        col.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(10)
        col.addWidget(label(title, "emptyTitle"), 0, Qt.AlignmentFlag.AlignHCenter)
        body = label(text, "emptyText", wrap=True)
        body.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body.setMaximumWidth(380)
        col.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)
        if action:
            col.addSpacing(12)
            col.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)


def error_state(what: str, retry: Callable[[], None], compact: bool = True, message: str | None = None) -> EmptyState:
    again = button("Try again", "ghost", "arrow-clockwise")
    again.clicked.connect(retry)
    return EmptyState("warning-circle", f"Couldn't load {what}", message or "Check your connection and try again.", again, compact)


# ---------- Poster card ----------


class PosterCard(QWidget):
    """A 2:3 poster with the title, year and rating over a shade, and a favorite heart.
    Hovering reveals the info and genres, as in the reference design."""

    HEART = 30

    def __init__(self, title: Title, session: Session, size: QSize = QSize(155, 227), removable: bool = False) -> None:
        super().__init__()
        self.title = title
        self.session = session
        self.removable = removable
        self.pix = QPixmap()
        self._scaled = QPixmap()
        self.hover = 0.0
        self.setFixedSize(size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{title.title}, {'series' if title.kind == 'tv' else 'film'}")
        self.setToolTip(title.title)
        self.anim = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._on_hover)
        session.favorites_changed.connect(self.update)
        theme.changed.connect(self.update)
        images().load(title.poster, self._set_pixmap, owner=self)

    def set_size(self, size: QSize) -> None:
        if size != self.size():
            self.setFixedSize(size)
            self._scaled = QPixmap()

    def _set_pixmap(self, pix: QPixmap) -> None:
        self.pix = pix
        self._scaled = QPixmap()
        self.update()

    def _on_hover(self, v) -> None:
        self.hover = float(v)
        self.update()

    def _animate(self, to: float) -> None:
        self.anim.stop()
        self.anim.setStartValue(self.hover)
        self.anim.setEndValue(to)
        self.anim.start()

    def enterEvent(self, e) -> None:
        self._animate(1.0)

    def leaveEvent(self, e) -> None:
        if not self.hasFocus():
            self._animate(0.0)

    def focusInEvent(self, e) -> None:
        self._animate(1.0)
        super().focusInEvent(e)

    def focusOutEvent(self, e) -> None:
        if not self.underMouse():
            self._animate(0.0)
        super().focusOutEvent(e)

    def _heart_rect(self) -> QRect:
        return QRect(self.width() - self.HEART - 9, 9, self.HEART, self.HEART)

    def _remove_rect(self) -> QRect:
        return QRect(11, self.height() - 24, 60, 16)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() != Qt.MouseButton.LeftButton or not self.rect().contains(e.position().toPoint()):
            return
        pos = e.position().toPoint()
        if self._heart_rect().adjusted(-4, -4, 4, 4).contains(pos) or (self.removable and self._remove_rect().contains(pos)):
            self.session.toggle_favorite(self.title)
        else:
            self.session.open_title(self.title)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.session.open_title(self.title)
        elif e.key() == Qt.Key.Key_F:
            self.session.toggle_favorite(self.title)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 6, 6)
        p.setClipPath(clip)
        p.fillRect(r, theme.color("card"))
        h = self.hover

        if not self.pix.isNull():
            zoom = 1 + 0.04 * h
            target = QSize(int(self.width() * zoom), int(self.height() * zoom))
            if self._scaled.size() != target:
                self._scaled = cover_pixmap(self.pix, target, 0.5)
            p.drawPixmap((self.width() - target.width()) // 2, (self.height() - target.height()) // 2, self._scaled)
        else:
            p.setPen(theme.color("muted"))
            p.setFont(font(DISPLAY, 14, 500))
            p.drawText(r.adjusted(12, 12, -12, -12), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.title.title.upper())

        shade = QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0.42, QColor(5, 6, 9, 0))
        shade.setColorAt(1.0, QColor(5, 6, 9, int(250 * (0.7 + 0.3 * h))))
        p.fillRect(r, QBrush(shade))

        # Info block slides up 25px on hover (always up when "Remove" is shown).
        lift = 0 if self.removable else int(25 * (1 - h))
        w = self.width() - 22
        title_font = font(SANS, 12, 600)
        fm = QFontMetrics(title_font)
        lines = wrap_text(self.title.title, fm, w, 2)
        bottom = self.height() - 10 + lift - (24 if self.removable else 0)
        genres_h = 15
        meta_h = 13
        y = bottom - genres_h - meta_h - 5 - len(lines) * fm.lineSpacing()
        p.setFont(title_font)
        p.setPen(QColor("#ffffff"))
        for line in lines:
            p.drawText(QPoint(11, y + fm.ascent()), line)
            y += fm.lineSpacing()
        y += 5
        p.setFont(font(SANS, 9))
        p.setPen(QColor("#b5b8bd"))
        left = str(self.title.year or "")
        if self.title.kind == "tv":
            left = f"{left} · Series" if left else "Series"
        p.drawText(QRect(11, y, w, meta_h), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, left)
        if self.title.rating:
            text = f"{self.title.rating:.1f}"
            tw = QFontMetrics(p.font()).horizontalAdvance(text)
            p.setPen(QColor("#ffd55c"))
            p.drawText(QRect(11, y, w, meta_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
            star = qta.icon("ph.star-fill", color=QColor("#ffd55c")).pixmap(20, 20)
            p.drawPixmap(QRect(11 + w - tw - 12, y + 2, 9, 9), star)
        else:
            p.drawText(QRect(11, y, w, meta_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Film")
        y += meta_h + 4
        if self.title.genres:
            c = QColor("#81858d")
            c.setAlphaF(h)
            p.setPen(c)
            p.setFont(font(SANS, 8))
            text = QFontMetrics(p.font()).elidedText(" • ".join(self.title.genres[:2]), Qt.TextElideMode.ElideRight, w)
            p.drawText(QRect(11, y, w, 11), Qt.AlignmentFlag.AlignLeft, text)
        if self.removable:
            rr = self._remove_rect()
            f = font(SANS, 9)
            f.setUnderline(True)
            p.setFont(f)
            p.setPen(QColor("#ff626a"))
            p.drawText(rr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Remove")

        # Heart: faint until hover, solid red when saved.
        saved = self.session.is_favorite(self.title.id)
        hr = QRectF(self._heart_rect())
        p.setOpacity(1.0 if (saved or h > 0.01) else 0.3)
        if not saved and h > 0.01:
            p.setOpacity(0.3 + 0.7 * h)
        p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        p.setBrush(QColor(8, 9, 12, 180))
        p.drawEllipse(hr.adjusted(0.5, 0.5, -0.5, -0.5))
        heart = qta.icon("ph.heart-fill" if saved else "ph.heart", color=QColor("#e50914") if saved else QColor("#ffffff"))
        p.drawPixmap(hr.adjusted(7, 7, -7, -7).toRect(), heart.pixmap(32, 32))
        p.setOpacity(1)

        if self.hasFocus():
            p.setClipping(False)
            p.setPen(QPen(theme.color("red"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 6, 6)


class SkeletonCard(QWidget):
    def __init__(self, size: QSize = QSize(155, 227)) -> None:
        super().__init__()
        self.setFixedSize(size)
        theme.changed.connect(self.update)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color("card"))
        p.drawRoundedRect(QRectF(self.rect()), 6, 6)


# ---------- Carousel row ----------


class _EdgeButton(QPushButton):
    """The fading arrow strip at each end of a row."""

    def __init__(self, direction: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.direction = direction
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(27)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Scroll forward" if direction > 0 else "Scroll back")

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), 0)
        dark = QColor(11, 13, 18, 225)
        clear = QColor(11, 13, 18, 0)
        g.setColorAt(0, dark if self.direction < 0 else clear)
        g.setColorAt(1, clear if self.direction < 0 else dark)
        p.fillRect(self.rect(), g)
        arrow = qta.icon("ph.caret-right" if self.direction > 0 else "ph.caret-left", color=QColor(255, 255, 255, 230 if self.underMouse() else 200))
        p.drawPixmap(QRect((self.width() - 20) // 2, (self.height() - 20) // 2, 20, 20), arrow.pixmap(40, 40))


class Row(QWidget):
    """A titled horizontal carousel of poster cards: drag it, scroll it, or use the edge arrows."""

    CARD = QSize(155, 227)
    GAP = 11

    def __init__(
        self,
        heading: str,
        session: Session,
        meta: str = "",
        see_all: Callable[[], None] | None = None,
        removable: bool = False,
        limit: int = 20,
    ) -> None:
        super().__init__()
        self.session = session
        self.heading = heading
        self.removable = removable
        self.limit = limit
        self.loader: Callable[[], list[Title]] | None = None

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 36)
        col.setSpacing(12)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 35, 0)
        head.setSpacing(9)
        head.addWidget(label(heading, "sectionTitle"))
        self.meta = label(meta, "sectionMeta")
        head.addWidget(self.meta, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch()
        if see_all:
            more = button("See all", "textButton")
            more.clicked.connect(see_all)
            head.addWidget(more)
        col.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        col.addLayout(self.body)

        self.frame = QWidget()
        self.frame.setFixedHeight(self.CARD.height() + 14)
        self.scroll = QScrollArea(self.frame)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().setAutoFillBackground(False)
        self.strip = QWidget()
        self.strip.setAutoFillBackground(False)
        self.cards = QHBoxLayout(self.strip)
        self.cards.setContentsMargins(0, 0, 40, 0)
        self.cards.setSpacing(self.GAP)
        self.cards.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.strip)
        self.left = _EdgeButton(-1, self.frame)
        self.right = _EdgeButton(1, self.frame)
        self.left.clicked.connect(lambda: self.page(-1))
        self.right.clicked.connect(lambda: self.page(1))
        self.track = QFrame(self.frame)
        self.thumb = QFrame(self.track)
        self.scroll.horizontalScrollBar().valueChanged.connect(self._update_edges)
        self.scroll.horizontalScrollBar().rangeChanged.connect(self._update_edges)
        self.frame.installEventFilter(self)
        self.anim = QPropertyAnimation(self.scroll.horizontalScrollBar(), b"value", self)
        self.anim.setDuration(420)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._drag: tuple[int, int] | None = None
        self._dragged = False
        theme.changed.connect(self._style_track)
        self._style_track()
        self.body.addWidget(self.frame)

    # Loading
    def load(self, loader: Callable[[], list[Title]]) -> Row:
        self.loader = loader
        self._show_skeleton()
        run_async(loader, self.set_items, self._failed, owner=self)
        return self

    def set_items(self, items: list[Title]) -> None:
        items = items[: self.limit]
        if not items:
            self.hide()
            return
        self.show()
        self._ensure_frame()
        clear_layout(self.cards)
        for t in items:
            card = PosterCard(t, self.session, self.CARD, self.removable)
            card.installEventFilter(self)
            self.cards.addWidget(card)
        self.scroll.horizontalScrollBar().setValue(0)
        self._update_edges()

    def _show_skeleton(self) -> None:
        self._ensure_frame()
        clear_layout(self.cards)
        for _ in range(9):
            self.cards.addWidget(SkeletonCard(self.CARD))

    def _failed(self, error: Exception) -> None:
        clear_layout(self.cards)
        self.frame.hide()
        msg = str(error) if isinstance(error, FetchError) else None
        self.body.addWidget(error_state(self.heading.lower(), self._retry, message=msg))

    def _retry(self) -> None:
        for i in reversed(range(self.body.count())):
            w = self.body.itemAt(i).widget()
            if w is not self.frame:
                w.deleteLater()
        if self.loader:
            self.load(self.loader)

    def _ensure_frame(self) -> None:
        self.frame.show()

    # Scrolling
    def page(self, direction: int) -> None:
        bar = self.scroll.horizontalScrollBar()
        self.anim.stop()
        self.anim.setStartValue(bar.value())
        self.anim.setEndValue(max(0, min(bar.maximum(), bar.value() + direction * int(self.scroll.width() * 0.8))))
        self.anim.start()

    def _style_track(self) -> None:
        self.track.setStyleSheet(f"background: {'rgba(255,255,255,14)' if theme.name == 'dark' else 'rgba(16,19,28,18)'}; border-radius: 1px;")
        self.thumb.setStyleSheet(f"background: {'#555a64' if theme.name == 'dark' else '#a9adb6'}; border-radius: 1px;")

    def _update_edges(self, *_args) -> None:
        bar = self.scroll.horizontalScrollBar()
        hover = self.frame.underMouse()
        self.left.setVisible(hover and bar.value() > 4)
        self.right.setVisible(hover and bar.value() < bar.maximum() - 4)
        total = bar.maximum() + self.scroll.width()
        self.track.setVisible(bar.maximum() > 0)
        if total > 0 and self.track.width() > 0:
            tw = max(18, int(self.track.width() * self.scroll.width() / total))
            x = int((self.track.width() - tw) * (bar.value() / bar.maximum())) if bar.maximum() else 0
            self.thumb.setGeometry(x, 0, tw, 2)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.frame:
            if event.type() == QEvent.Type.Resize:
                w, h = self.frame.width(), self.frame.height()
                self.scroll.setGeometry(0, 0, w, h - 7)
                self.left.setGeometry(0, 0, 27, self.CARD.height())
                self.right.setGeometry(w - 27, 0, 27, self.CARD.height())
                self.track.setGeometry(0, h - 4, max(0, w - 36), 2)
                self._update_edges()
            elif event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
                self._update_edges()
            return False
        # Mouse drag on the cards scrolls the row; a drag is not a click.
        if isinstance(obj, PosterCard):
            t = event.type()
            if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag = (int(event.globalPosition().x()), self.scroll.horizontalScrollBar().value())
                self._dragged = False
            elif t == QEvent.Type.MouseMove and self._drag and event.buttons() & Qt.MouseButton.LeftButton:
                dx = int(event.globalPosition().x()) - self._drag[0]
                if abs(dx) > 6:
                    self._dragged = True
                    obj.setCursor(Qt.CursorShape.ClosedHandCursor)
                if self._dragged:
                    self.scroll.horizontalScrollBar().setValue(self._drag[1] - dx)
                    return True
            elif t == QEvent.Type.MouseButtonRelease and self._drag:
                self._drag = None
                obj.setCursor(Qt.CursorShape.PointingHandCursor)
                if self._dragged:
                    self._dragged = False
                    return True
        return False


# ---------- Responsive grid ----------


class Grid(QWidget):
    """Poster grid that fits as many columns as the width allows (max 6), cards stay 2:3."""

    GAP = 15

    def __init__(self, session: Session, min_card: int = 130, max_cols: int = 6) -> None:
        super().__init__()
        self.session = session
        self.min_card = min_card
        self.max_cols = max_cols
        self.items: list[Title] = []
        self.cards: list[QWidget] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_items(self, items: list[Title], skeleton: int = 0) -> None:
        for c in self.cards:
            c.deleteLater()
        self.items = items
        if skeleton:
            self.cards = [SkeletonCard() for _ in range(skeleton)]
        else:
            self.cards = [PosterCard(t, self.session) for t in items]
        for c in self.cards:
            c.setParent(self)
            c.show()
        self._layout()

    def _columns(self) -> int:
        return max(2, min(self.max_cols, (self.width() + self.GAP) // (self.min_card + self.GAP)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout()

    def _layout(self) -> None:
        if not self.cards or self.width() <= 0:
            self.setFixedHeight(0)
            return
        cols = self._columns()
        w = (self.width() - self.GAP * (cols - 1)) // cols
        h = int(w * 1.5)
        for i, c in enumerate(self.cards):
            r, k = divmod(i, cols)
            if isinstance(c, PosterCard):
                c.set_size(QSize(w, h))
            else:
                c.setFixedSize(w, h)
            c.move(k * (w + self.GAP), r * (h + self.GAP))
        rows = (len(self.cards) + cols - 1) // cols
        self.setFixedHeight(rows * h + (rows - 1) * self.GAP)
