"""Trailer and teaser player: Apple's preview videos play right inside the app."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cinevia.data import catalog
from cinevia.data.models import Title
from cinevia.data.util import youtube_search_url

from .widgets import button, icon, label
from .workers import run_async


def _clock(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


class PlayerDialog(QDialog):
    def __init__(self, title: Title, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.kind = "teaser" if title.kind == "tv" else "trailer"
        self.setWindowTitle(f"{title.title} | Official {self.kind}")
        self.setModal(True)
        self.setStyleSheet("QDialog { background: #08090c; }")
        self.resize(QSize(1000, 640))

        col = QVBoxLayout(self)
        col.setContentsMargins(24, 20, 24, 20)
        col.setSpacing(12)
        head = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(f"OFFICIAL {self.kind.upper()}", "playerKicker"))
        text.addWidget(label(title.title.upper(), "playerTitle"))
        head.addLayout(text)
        head.addStretch()
        close = QPushButton()
        close.setObjectName("iconButton")
        close.setFixedSize(34, 34)
        close.setIcon(icon("x", "#ffffff"))
        close.setAccessibleName("Close player")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.close)
        head.addWidget(close)
        col.addLayout(head)

        self.stack = QStackedWidget()
        self.note = QWidget()
        nc = QVBoxLayout(self.note)
        nc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note_text = label(f"Finding the {self.kind}...", "playerNote")
        self.note_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nc.addWidget(self.note_text)
        self.youtube = button("Find it on YouTube", "ghost", "youtube-logo", "#ffffff")
        self.youtube.setStyleSheet("QPushButton { color: #ffffff; background: rgba(21,24,33,210); border-color: #464952; }")
        self.youtube.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(youtube_search_url(title.title, title.kind))))
        self.youtube.hide()
        nc.addSpacing(12)
        nc.addWidget(self.youtube, 0, Qt.AlignmentFlag.AlignCenter)
        self.video = QVideoWidget()
        self.video.setStyleSheet("background: #000000;")
        self.stack.addWidget(self.note)
        self.stack.addWidget(self.video)
        col.addWidget(self.stack, 1)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("iconButton")
        self.play_btn.setFixedSize(34, 34)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self.toggle)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName("Seek")
        self.slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 3px; background: #2d3039; border-radius: 1px; }"
            "QSlider::sub-page:horizontal { background: #e50914; border-radius: 1px; }"
            "QSlider::handle:horizontal { width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; background: #ffffff; }"
        )
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v))
        self.time = label("0:00 / 0:00", "time")
        controls.addWidget(self.play_btn)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.time)
        self.controls = QWidget()
        self.controls.setLayout(controls)
        self.controls.setEnabled(False)
        col.addWidget(self.controls)

        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        self.player.playbackStateChanged.connect(lambda _s: self._sync_play_icon())
        self.player.errorOccurred.connect(lambda *_: self._missing())
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle)
        self._sync_play_icon()

        run_async(lambda: catalog.resolve_trailer(title), self._got_url, lambda e: self._missing(), owner=self)

    def _got_url(self, url: str | None) -> None:
        if not url:
            self._missing()
            return
        self.stack.setCurrentWidget(self.video)
        self.controls.setEnabled(True)
        self.player.setSource(QUrl(url))
        self.player.play()

    def _missing(self) -> None:
        self.player.stop()
        self.stack.setCurrentWidget(self.note)
        self.controls.setEnabled(False)
        self.note_text.setText(f"Apple TV has no {self.kind} for this title.")
        self.youtube.show()

    def _position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time.setText(f"{_clock(ms)} / {_clock(self.player.duration())}")

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _sync_play_icon(self) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setIcon(icon("pause" if playing else "play", "#ffffff"))
        self.play_btn.setAccessibleName("Pause" if playing else "Play")

    def closeEvent(self, e) -> None:
        self.player.stop()
        super().closeEvent(e)
