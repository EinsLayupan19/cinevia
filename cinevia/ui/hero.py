"""The home hero: a full-width featured title with "01 / 05" paging, as in the reference."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from cinevia.data import catalog
from cinevia.data.itunes import artwork
from cinevia.data.models import Title
from cinevia.data.util import format_runtime

from .context import Session
from .images import images
from .theme import theme
from .widgets import (
    ClampLabel,
    Eyebrow,
    OutlineTitle,
    button,
    chips,
    clear_layout,
    cover_pixmap,
    icon,
    label,
    soft_blur,
)
from .workers import run_async

SLIDE_MS = 8000


def split_title(title: str) -> tuple[str, str]:
    """"Beyond Horizon" -> ("Beyond", "Horizon"); the second half is drawn in outline."""
    words = title.split()
    if len(words) < 2:
        return title, ""
    cut = (len(words) + 1) // 2
    return " ".join(words[:cut]), " ".join(words[cut:])


def wide_art(t: Title) -> tuple[str, bool]:
    """Wide image URL, and whether it is a crop of the poster (shown softly blurred)."""
    if t.backdrop:
        return t.backdrop, False
    if t.kind == "movie" and t.poster_large:
        return artwork(t.poster_large, 1600, 900, "cc"), True
    return t.poster_large, True


def meta_row(t: Title) -> QWidget:
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(14)
    if t.year:
        row.addWidget(label(str(t.year), "meta"))
    if t.rating:
        star = QLabel()
        star.setPixmap(icon("star-fill", "star").pixmap(11, 11))
        score = QHBoxLayout()
        score.setSpacing(4)
        score.addWidget(star)
        score.addWidget(label(f"{t.rating:.1f}", "score"))
        row.addLayout(score)
    runtime = format_runtime(t.runtime_min)
    if runtime:
        row.addWidget(label(f"{runtime} per episode" if t.kind == "tv" else runtime, "meta"))
    row.addWidget(label(t.certification or ("SERIES" if t.kind == "tv" else "FILM"), "quality"))
    row.addStretch()
    return w


class Backdrop(QWidget):
    """Paints wide art with the reference's left and bottom fades; crossfades between images."""

    def __init__(self, height: int, blur_all: bool = False) -> None:
        super().__init__()
        self.setFixedHeight(height)
        self.blur_all = blur_all
        self.pix = QPixmap()
        self.prev = QPixmap()
        self.soft = False
        self.fade = 1.0
        self._cache: dict[tuple, QPixmap] = {}
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=650, easingCurve=QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._tick)
        theme.changed.connect(self.update)

    def _tick(self, v) -> None:
        self.fade = float(v)
        self.update()

    def set_image(self, pix: QPixmap, soft: bool) -> None:
        self.prev = self._render(self.pix, self.soft) if not self.pix.isNull() else QPixmap()
        self.pix, self.soft = pix, soft
        self._cache.clear()
        self.anim.stop()
        self.anim.start()

    def _render(self, pix: QPixmap, soft: bool) -> QPixmap:
        key = (pix.cacheKey(), self.width(), self.height(), soft)
        if key not in self._cache:
            src = pix
            if soft:  # a poster crop: trim its outer 5% so a printed border never shows
                r = pix.rect()
                src = pix.copy(r.adjusted(r.width() // 20, r.height() // 20, -r.width() // 20, -r.height() // 20))
            img = cover_pixmap(src, self.size(), 0.28 if soft else 0.47)
            if soft or self.blur_all:
                img = soft_blur(img, 14 if self.blur_all else 9)
            self._cache[key] = img
        return self._cache[key]

    def resizeEvent(self, e) -> None:
        self._cache.clear()
        super().resizeEvent(e)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), theme.color("card"))
        if not self.prev.isNull() and self.fade < 1:
            p.drawPixmap(0, 0, self.prev)
        if not self.pix.isNull():
            p.setOpacity(self.fade * (0.85 if theme.name == "dark" else 0.95))
            p.drawPixmap(0, 0, self._render(self.pix, self.soft))
            p.setOpacity(1)
        bg = theme.color("bg")
        side = QLinearGradient(0, 0, self.width(), 0)
        for stop, alpha in ((0.02, 255), (0.24, 230), (0.66, 72), (1.0, 38)):
            c = QColor(bg)
            c.setAlpha(alpha)
            side.setColorAt(stop, c)
        p.fillRect(self.rect(), side)
        down = QLinearGradient(0, 0, 0, self.height())
        c0 = QColor(bg)
        c0.setAlpha(0)
        down.setColorAt(0.62, c0)
        down.setColorAt(1.0, bg)
        p.fillRect(self.rect(), down)


class Hero(Backdrop):
    def __init__(self, session: Session) -> None:
        super().__init__(515)
        self.session = session
        self.slides: list[Title] = []
        self.index = 0
        self.content = QWidget(self)
        self.content.setGeometry(44, 58, 520, 420)
        self.col = QVBoxLayout(self.content)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(0)
        self.col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.index_label = label("", "heroIndex")
        self.total_label = label("", "heroIndexTotal")
        self.index_box = QWidget(self)
        ib = QHBoxLayout(self.index_box)
        ib.setContentsMargins(0, 0, 0, 0)
        ib.setSpacing(5)
        ib.addWidget(self.index_label, 0, Qt.AlignmentFlag.AlignBaseline)
        ib.addWidget(self.total_label, 0, Qt.AlignmentFlag.AlignBaseline)
        self.dots = QWidget(self)
        self.dot_row = QHBoxLayout(self.dots)
        self.dot_row.setContentsMargins(0, 0, 0, 0)
        self.dot_row.setSpacing(5)
        self.timer = QTimer(self, interval=SLIDE_MS)
        self.timer.timeout.connect(lambda: self.show_slide((self.index + 1) % max(1, len(self.slides))))
        theme.changed.connect(self._restyle_dots)

    def load(self, loader) -> None:
        run_async(loader, self.set_slides, lambda e: self.hide(), owner=self)

    def set_slides(self, slides: list[Title]) -> None:
        self.slides = slides
        if not slides:
            self.hide()
            return
        clear_layout(self.dot_row)
        for i, t in enumerate(slides):
            dot = QPushButton()
            dot.setFixedSize(31, 16)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setAccessibleName(f"Show {t.title}")
            dot.setToolTip(t.title)
            dot.clicked.connect(lambda _=False, i=i: self.show_slide(i))
            self.dot_row.addWidget(dot)
        self.show_slide(0)
        self.timer.start()

    def _restyle_dots(self) -> None:
        for i in range(self.dot_row.count()):
            dot = self.dot_row.itemAt(i).widget()
            active = i == self.index
            color = theme.p["red"] if active else theme.p["dots"]
            width = 31 if active else 16
            dot.setFixedWidth(width)
            dot.setStyleSheet(f"QPushButton {{ border: 0; background: transparent; border-bottom: 2px solid {color}; margin-bottom: 7px; }}")
        n = len(self.slides)
        self.index_label.setText(f"{self.index + 1:02d}")
        self.total_label.setText(f"/ {n:02d}")
        self._place_overlays()

    def show_slide(self, i: int) -> None:
        if not self.slides:
            return
        self.index = i
        t = self.slides[i]
        self._fill(t)
        self._restyle_dots()
        url, soft = wide_art(t)
        images().load(url, lambda pix, soft=soft, i=i: self.index == i and self.set_image(pix, soft), owner=self)
        # Shows get wide background art from TVmaze; films get runtime and rating from Apple.
        run_async(lambda: catalog.details(t), lambda extra, i=i: self._enrich(i, extra), lambda e: None, owner=self)
        self.timer.start()

    def _enrich(self, i: int, extra: dict) -> None:
        if i >= len(self.slides):
            return
        t = self.slides[i]
        merged = t.with_details({**extra, "summary": t.summary or extra.get("summary")})
        self.slides[i] = merged
        if i == self.index:
            self._fill(merged)
            if merged.backdrop and not t.backdrop:
                images().load(merged.backdrop, lambda pix: self.index == i and self.set_image(pix, False), owner=self)

    def _fill(self, t: Title) -> None:
        clear_layout(self.col)
        self.col.addWidget(Eyebrow("Cinevia Premiere"))
        self.col.addSpacing(17)
        solid, outline = split_title(t.title)
        self.col.addWidget(OutlineTitle(solid, outline, 46 if len(t.title) > 18 else 59))
        self.col.addSpacing(14)
        self.col.addWidget(meta_row(t))
        self.col.addSpacing(15)
        summary = ClampLabel(t.summary, "body", 3)
        summary.setMaximumWidth(500)
        self.col.addWidget(summary)
        self.col.addSpacing(15)
        if t.genres:
            self.col.addWidget(chips(t.genres[:3]))
        self.col.addSpacing(22)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        play = button("Watch teaser" if t.kind == "tv" else "Watch trailer", "primary", "play", "#ffffff")
        play.clicked.connect(lambda: self.session.play_trailer(t))
        info = button("View details", "ghost", "info")
        info.clicked.connect(lambda: self.session.open_title(t))
        actions.addWidget(play)
        actions.addWidget(info)
        actions.addStretch()
        self.col.addLayout(actions)

    def _place_overlays(self) -> None:
        self.index_box.adjustSize()
        n = self.dot_row.count()
        self.dots.resize(max(0, 31 + (16 + 5) * (n - 1)), 16)  # sized by hand: new buttons aren't shown yet
        self.index_box.move(self.width() - 38 - self.index_box.width(), self.height() - 80 - self.index_box.height())
        self.dots.move(self.width() - 38 - self.dots.width(), self.height() - 53 - 8)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.content.setGeometry(44, 58, min(520, self.width() - 88), self.height() - 100)
        self._place_overlays()

    def enterEvent(self, e) -> None:
        self.timer.stop()  # hold the slide while the viewer is reading it

    def leaveEvent(self, e) -> None:
        if self.slides:
            self.timer.start()
