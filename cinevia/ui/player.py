"""Trailer and teaser player. Like Netflix, it takes over the app window itself
(no separate pop-up): back arrow and title on top, controls along the bottom,
both fading away while the video plays."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSizeF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from cinevia.data import catalog
from cinevia.data.models import Title

from .widgets import icon, label
from .workers import run_async

HIDE_AFTER_MS = 2600
SKIP_MS = 10_000

SLIDER_STYLE = (
    "QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,60); border-radius: 2px; }"
    "QSlider::sub-page:horizontal { background: #e50914; border-radius: 2px; }"
    "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: #e50914; }"
)


def _clock(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


class _Shade(QFrame):
    """A dark fade behind the top or bottom controls so they read over any frame."""

    def __init__(self, at_top: bool, parent: QWidget) -> None:
        super().__init__(parent)
        self.at_top = at_top
        self.setMouseTracking(True)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        dark, clear = QColor(0, 0, 0, 200), QColor(0, 0, 0, 0)
        g.setColorAt(0, dark if self.at_top else clear)
        g.setColorAt(1, clear if self.at_top else dark)
        p.fillRect(self.rect(), QBrush(g))


def _icon_button(name: str, tip: str, size: int = 26) -> QPushButton:
    b = QPushButton()
    b.setObjectName("pvButton")
    b.setFixedSize(size + 18, size + 18)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setIcon(icon(name, "#ffffff"))
    b.setIconSize(QSizeF(size, size).toSize())
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    return b


class PlayerView(QWidget):
    """Full-window video player that sits on top of the app's pages."""

    closed = Signal()

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.host = host
        self.title: Title | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        # The video is drawn in a graphics scene (not a native video surface),
        # so the controls can float on top of it.
        self.scene = QGraphicsScene(self)
        self.video = QGraphicsVideoItem()
        self.scene.addItem(self.video)
        self.view = QGraphicsView(self.scene, self)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setBackgroundBrush(QColor("#000000"))
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().installEventFilter(self)

        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.playbackStateChanged.connect(lambda _s: self._sync())
        self.player.errorOccurred.connect(lambda *_: self._no_video())

        # Message for loading / no video, centered over the black frame.
        self.message = label("", "pvMessage", wrap=True)
        self.message.setParent(self)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Top: just the back arrow, as on Netflix; the title sits at the bottom.
        self.top = _Shade(True, self)
        tr = QHBoxLayout(self.top)
        tr.setContentsMargins(24, 18, 24, 18)
        self.back = _icon_button("arrow-left", "Back (Esc)", 28)
        self.back.clicked.connect(self.close_player)
        tr.addWidget(self.back, 0, Qt.AlignmentFlag.AlignTop)
        tr.addStretch()

        # Bottom: timeline, then the transport controls.
        self.bottom = _Shade(False, self)
        bc = QVBoxLayout(self.bottom)
        bc.setContentsMargins(28, 40, 28, 20)
        bc.setSpacing(10)
        line = QHBoxLayout()
        line.setSpacing(14)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setAccessibleName("Seek")
        self.seek.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek.setStyleSheet(SLIDER_STYLE)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.time = label("0:00", "pvTime")
        line.addWidget(self.seek, 1)
        line.addWidget(self.time)
        bc.addLayout(line)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.play_btn = _icon_button("play-fill", "Play (Space)", 30)
        self.play_btn.clicked.connect(self.toggle)
        rewind = _icon_button("arrow-counter-clockwise", "Back 10 seconds (Left)")
        rewind.clicked.connect(lambda: self.skip(-SKIP_MS))
        forward = _icon_button("arrow-clockwise", "Forward 10 seconds (Right)")
        forward.clicked.connect(lambda: self.skip(SKIP_MS))
        self.mute_btn = _icon_button("speaker-high", "Mute (M)")
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setAccessibleName("Volume")
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume.setFixedWidth(90)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setStyleSheet(SLIDER_STYLE)
        self.volume.valueChanged.connect(lambda v: (self.audio.setVolume(v / 100), self._sync()))
        self.audio.setVolume(0.8)
        self.small_name = label("", "pvSmallTitle")
        self.full_btn = _icon_button("corners-out", "Full screen (F)")
        self.full_btn.clicked.connect(self.toggle_fullscreen)
        for w in (self.play_btn, rewind, forward, self.mute_btn, self.volume):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.small_name)
        row.addStretch()
        row.addWidget(self.full_btn)
        bc.addLayout(row)
        self.controls = [self.seek, self.play_btn, rewind, forward]

        self.hide_timer = QTimer(self, singleShot=True, interval=HIDE_AFTER_MS)
        self.hide_timer.timeout.connect(self._hide_chrome)
        host.installEventFilter(self)
        for w in (self, self.top, self.bottom):
            w.installEventFilter(self)

    # ----- Opening and closing -----

    def open(self, title: Title) -> None:
        self.title = title
        kind = {"tv": "teaser", "game": "gameplay video"}.get(title.kind, "trailer")
        self.small_name.setText(f"{title.title}  ·  Gameplay" if title.kind == "game" else f"{title.title}  ·  Official {kind}")
        # Start from a clean timeline, not the previous video's.
        self.seek.setRange(0, 0)
        self.seek.setValue(0)
        self.time.setText("")
        self._set_enabled(False)
        self._message(f"Loading {kind}...")
        self.setGeometry(self.host.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._show_chrome()
        run_async(lambda: catalog.resolve_trailer(title), self._got_url, lambda e: self._no_video(), owner=self)

    def close_player(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        if self.window().isFullScreen():
            self.window().showNormal()
        self.unsetCursor()
        self.hide()
        self.closed.emit()

    def _got_url(self, url: str | None) -> None:
        if not self.isVisible():
            return  # closed while we were looking it up
        if not url:
            self._no_video()
            return
        self.message.hide()
        self._set_enabled(True)
        self.player.setSource(QUrl(url))
        self.player.play()
        self._show_chrome()

    def _no_video(self) -> None:
        self.player.stop()
        self._set_enabled(False)
        if self.title and self.title.kind == "game":
            text = "FreeToGame has no gameplay video for this game yet."
        else:
            kind = "teaser" if self.title and self.title.kind == "tv" else "trailer"
            text = f"Apple TV has no {kind} for this title yet."
        self._message(f"{text}\nPress Esc or the back arrow to return.")
        self._show_chrome()

    def _message(self, text: str) -> None:
        self.message.setText(text)
        self.message.show()
        self._layout()

    def _set_enabled(self, on: bool) -> None:
        for w in self.controls:
            w.setEnabled(on)

    # ----- Playback -----

    def toggle(self) -> None:
        if self.player.source().isEmpty():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self._show_chrome()

    def skip(self, ms: int) -> None:
        if not self.player.source().isEmpty():
            self.player.setPosition(max(0, min(self.player.duration(), self.player.position() + ms)))
            self._show_chrome()

    def toggle_mute(self) -> None:
        self.audio.setMuted(not self.audio.isMuted())
        self._sync()
        self._show_chrome()

    def toggle_fullscreen(self) -> None:
        win = self.window()
        win.showNormal() if win.isFullScreen() else win.showFullScreen()
        QTimer.singleShot(0, self, self._sync)

    def _position(self, ms: int) -> None:
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        left = self.player.duration() - ms
        self.time.setText(_clock(left) if self.player.duration() else _clock(ms))

    def _sync(self) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setIcon(icon("pause-fill" if playing else "play-fill", "#ffffff"))
        self.play_btn.setToolTip("Pause (Space)" if playing else "Play (Space)")
        self.play_btn.setAccessibleName(self.play_btn.toolTip())
        muted = self.audio.isMuted() or self.volume.value() == 0
        self.mute_btn.setIcon(icon("speaker-x" if muted else "speaker-high", "#ffffff"))
        full = self.window().isFullScreen()
        self.full_btn.setIcon(icon("corners-in" if full else "corners-out", "#ffffff"))
        self.full_btn.setToolTip("Exit full screen (F)" if full else "Full screen (F)")
        if playing:
            self.hide_timer.start()
        else:
            self._show_chrome(keep=True)

    # ----- Controls that fade away while playing -----

    def _show_chrome(self, keep: bool = False) -> None:
        self.top.show()
        self.bottom.show()
        self.unsetCursor()
        self.view.viewport().unsetCursor()
        if keep or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.hide_timer.stop()
        else:
            self.hide_timer.start()

    def _hide_chrome(self) -> None:
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return
        self.top.hide()
        self.bottom.hide()
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.view.viewport().setCursor(Qt.CursorShape.BlankCursor)

    # ----- Layout and input -----

    def _layout(self) -> None:
        w, h = self.width(), self.height()
        self.view.setGeometry(0, 0, w, h)
        self.scene.setSceneRect(0, 0, w, h)
        self.video.setPos(0, 0)
        self.video.setSize(QSizeF(w, h))
        self.top.setGeometry(0, 0, w, 100)
        bh = self.bottom.sizeHint().height()
        self.bottom.setGeometry(0, h - bh, w, bh)
        self.message.setGeometry(QRectF(40, h / 2 - 50, w - 80, 100).toRect())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout()

    def eventFilter(self, obj, event) -> bool:
        t = event.type()
        if obj is self.host and t == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.host.rect())
        elif t == QEvent.Type.MouseMove and self.isVisible():
            self._show_chrome()
        elif obj is self.view.viewport() and t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.toggle()  # click the picture to pause or resume
        elif obj is self.view.viewport() and t == QEvent.Type.MouseButtonDblClick:
            self.toggle_fullscreen()
        return False

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key == Qt.Key.Key_Escape:
            if self.window().isFullScreen():
                self.toggle_fullscreen()
            else:
                self.close_player()
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_K):
            self.toggle()
        elif key == Qt.Key.Key_Left:
            self.skip(-SKIP_MS)
        elif key == Qt.Key.Key_Right:
            self.skip(SKIP_MS)
        elif key == Qt.Key.Key_M:
            self.toggle_mute()
        elif key == Qt.Key.Key_F:
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, event) -> None:
        QPainter(self).fillRect(self.rect(), QColor("#000000"))
