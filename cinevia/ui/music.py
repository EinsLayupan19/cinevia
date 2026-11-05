"""Music: Apple Music's charts with 30-second previews that play in a mini player
docked at the bottom of the window, so you can keep browsing while it plays."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from cinevia.data import music
from cinevia.data.http import FetchError
from cinevia.data.models import Title

from .context import Session
from .images import images
from .pages import Page
from .theme import theme
from .widgets import (
    EmptyState,
    Row,
    clear_layout,
    cover_pixmap,
    error_state,
    icon,
    label,
)
from .workers import run_async

SONG_CARD = QSize(170, 170)


def _clock(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


class Art(QWidget):
    """Square cover art with rounded corners."""

    def __init__(self, url: str, size: int, radius: int = 5) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.radius = radius
        self.pix = QPixmap()
        if url:
            images().load(url, self._set, owner=self)

    def set_url(self, url: str) -> None:
        self.pix = QPixmap()
        self.update()
        if url:
            images().load(url, self._set, owner=self)

    def _set(self, pix: QPixmap) -> None:
        self.pix = pix
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        p.setClipPath(path)
        p.fillRect(self.rect(), theme.color("card"))
        if not self.pix.isNull():
            p.drawPixmap(0, 0, cover_pixmap(self.pix, self.size()))


class ElideLabel(QLabel):
    """One line of text that ends in "..." when it doesn't fit."""

    def __init__(self, text: str, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full(text)

    def set_full(self, text: str) -> None:
        self.full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = self.width() if self.width() > 0 else 10_000
        self.setText(self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight, width))


def _round_button(name: str, tip: str, object_name: str = "mbButton", size: int = 34, glyph: int = 18) -> QPushButton:
    b = QPushButton()
    b.setObjectName(object_name)
    b.setFixedSize(size, size)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setIcon(icon(name, "#ffffff" if object_name == "mbPlay" else "text"))
    b.setIconSize(QSize(glyph, glyph))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    return b


class MusicBar(QFrame):
    """The mini player. Hidden until a song is picked; plays the rest of that list next."""

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.setObjectName("musicBar")
        self.setFixedHeight(78)
        self.session = session
        self.queue: list[Title] = []
        self.index = -1
        self.hide()

        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self._position)
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.playbackStateChanged.connect(lambda _s: self._sync())
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(lambda *_: self.artist.set_full("This preview couldn't play. Try another song."))

        row = QHBoxLayout(self)
        row.setContentsMargins(22, 10, 22, 10)
        row.setSpacing(14)

        # Left: what is playing.
        self.art = Art("", 52)
        row.addWidget(self.art)
        names = QVBoxLayout()
        names.setSpacing(3)
        names.addStretch()
        self.name = ElideLabel("", "mbTitle")
        self.artist = ElideLabel("", "mbArtist")
        for w in (self.name, self.artist):
            names.addWidget(w)
        names.addStretch()
        left = QWidget()
        left.setFixedWidth(200)
        left.setLayout(names)
        row.addWidget(left)
        self.fav = _round_button("heart", "Add to favorites", size=32, glyph=17)
        self.fav.clicked.connect(self._toggle_fav)
        row.addWidget(self.fav)
        row.addSpacing(10)

        # Center: transport and timeline.
        center = QVBoxLayout()
        center.setSpacing(4)
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()
        self.prev = _round_button("skip-back-fill", "Previous song")
        self.prev.clicked.connect(lambda: self.step(-1))
        self.play_btn = _round_button("play-fill", "Play", "mbPlay", 38, 17)
        self.play_btn.clicked.connect(self.toggle)
        self.next = _round_button("skip-forward-fill", "Next song")
        self.next.clicked.connect(lambda: self.step(1))
        for b in (self.prev, self.play_btn, self.next):
            buttons.addWidget(b)
        buttons.addStretch()
        center.addLayout(buttons)
        line = QHBoxLayout()
        line.setSpacing(10)
        self.pos_label = label("0:00", "mbTime")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setObjectName("mbSeek")
        self.seek.setAccessibleName("Seek")
        self.seek.setMinimumWidth(120)
        self.seek.setMaximumWidth(380)
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.len_label = label("0:30", "mbTime")
        for t in (self.pos_label, self.len_label):
            t.setFixedWidth(30)
        self.pos_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(self.pos_label)
        line.addWidget(self.seek, 1)
        line.addWidget(self.len_label)
        center.addLayout(line)
        row.addLayout(center, 1)
        row.addSpacing(10)

        # Right: volume and close.
        self.vol_icon = QLabel()
        row.addWidget(self.vol_icon)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("mbSeek")
        self.volume.setAccessibleName("Volume")
        self.volume.setFixedWidth(90)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.valueChanged.connect(lambda v: (self.audio.setVolume(v / 100), self._sync()))
        row.addWidget(self.volume)
        close = _round_button("x", "Stop and close the player", size=32, glyph=16)
        close.clicked.connect(self.stop)
        self.close_btn = close
        row.addWidget(close)

        session.favorites_changed.connect(self._sync)
        theme.changed.connect(self._sync)
        self._sync()

    # ----- Playing -----

    def play(self, song: Title, queue: list[Title]) -> None:
        songs = [s for s in queue if s.kind == "song"] or [song]
        self.queue = songs
        self.index = next((i for i, s in enumerate(songs) if s.id == song.id), 0)
        if songs[self.index].id != song.id:
            self.queue, self.index = [song], 0
        self._load()

    def _load(self) -> None:
        song = self.queue[self.index]
        self.name.set_full(song.title)
        self.artist.set_full(song.credit or "")
        self.art.set_url(song.poster)
        self.seek.setRange(0, 0)
        self.pos_label.setText("0:00")
        self.show()
        self.player.setSource(QUrl(song.trailer or ""))
        self.player.play()
        self.session.now_playing = song.id
        self.session.song_changed.emit(song.id)
        self._sync()

    def current(self) -> Title | None:
        return self.queue[self.index] if 0 <= self.index < len(self.queue) else None

    def toggle(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self.current():
            self.player.play()

    def pause(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()

    def step(self, delta: int) -> None:
        if not self.queue:
            return
        # "Previous" a few seconds into a song restarts it, like most players.
        if delta < 0 and self.player.position() > 3000:
            self.player.setPosition(0)
            return
        self.index = (self.index + delta) % len(self.queue)
        self._load()

    def stop(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())
        self.session.now_playing = None
        self.session.song_changed.emit("")
        self.hide()

    def _status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.index < len(self.queue) - 1:
                self.step(1)
            else:
                self._sync()

    def _toggle_fav(self) -> None:
        song = self.current()
        if song:
            self.session.toggle_favorite(song)

    def _position(self, ms: int) -> None:
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        self.pos_label.setText(_clock(ms))
        if self.player.duration():
            self.len_label.setText(_clock(self.player.duration()))

    def _sync(self) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setIcon(icon("pause-fill" if playing else "play-fill", "#ffffff"))
        self.play_btn.setToolTip("Pause" if playing else "Play")
        self.play_btn.setAccessibleName(self.play_btn.toolTip())
        for b, glyph in ((self.prev, "skip-back-fill"), (self.next, "skip-forward-fill"), (self.close_btn, "x")):
            b.setIcon(icon(glyph, "text2"))
        multi = len(self.queue) > 1
        self.prev.setEnabled(bool(self.queue))
        self.next.setEnabled(multi)
        muted = self.volume.value() == 0
        self.vol_icon.setPixmap(icon("speaker-x" if muted else "speaker-high", "muted").pixmap(17, 17))
        song = self.current()
        saved = bool(song and self.session.is_favorite(song.id))
        self.fav.setIcon(icon("heart-fill" if saved else "heart", "red_text" if saved else "text2"))
        self.fav.setToolTip("Remove from favorites" if saved else "Add to favorites")
        self.fav.setAccessibleName(self.fav.toolTip())


# ---------- Track list ----------


class TrackRow(QFrame):
    """One song in a chart: rank, cover, title and artist, album, heart. Click to play."""

    def __init__(self, rank: int | None, song: Title, queue: list[Title], session: Session) -> None:
        super().__init__()
        self.setObjectName("trackRow")
        self.song = song
        self.queue = queue
        self.session = session
        self.setFixedHeight(62)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"Play {song.title} by {song.credit}")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 8, 0)
        row.setSpacing(13)
        if rank is not None:
            self.rank = label(str(rank), "trackRank")
            self.rank.setFixedWidth(22)
            self.rank.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(self.rank)
        row.addWidget(Art(song.poster, 44))
        names = QVBoxLayout()
        names.setSpacing(3)
        names.addStretch()
        self.name = ElideLabel(song.title, "trackTitle")
        names.addWidget(self.name)
        names.addWidget(ElideLabel(song.credit or "", "trackArtist"))
        names.addStretch()
        row.addLayout(names, 3)
        row.addWidget(ElideLabel(song.album or "", "trackAlbum"), 2)
        self.fav = QPushButton()
        self.fav.setObjectName("trackIcon")
        self.fav.setFixedSize(32, 32)
        self.fav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav.clicked.connect(lambda: session.toggle_favorite(song))
        row.addWidget(self.fav)
        self.play_icon = QLabel()
        self.play_icon.setFixedSize(22, 22)
        row.addWidget(self.play_icon)
        session.favorites_changed.connect(self._sync)
        session.song_changed.connect(lambda _id: self._sync())
        self._sync()

    def _sync(self) -> None:
        try:
            saved = self.session.is_favorite(self.song.id)
            self.fav.setIcon(icon("heart-fill" if saved else "heart", "red_text" if saved else "muted"))
            self.fav.setToolTip("Remove from favorites" if saved else "Add to favorites")
            self.fav.setAccessibleName(f"{self.fav.toolTip()}: {self.song.title}")
            playing = self.session.now_playing == self.song.id
            self.play_icon.setPixmap(icon("speaker-high" if playing else "play", "red_text" if playing else "muted").pixmap(18, 18))
            self.setProperty("playing", playing)
            self.style().unpolish(self)
            self.style().polish(self)
            self.name.setStyleSheet(f"color: {theme.p['red_text']};" if playing else "")
        except RuntimeError:
            pass  # row already deleted

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.session.play_song(self.song, self.queue)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.session.play_song(self.song, self.queue)
        else:
            super().keyPressEvent(e)


class TrackList(QWidget):
    """Songs in two side-by-side columns (ranked 1-10 and 11-20 for a chart)."""

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.cols = QHBoxLayout(self)
        self.cols.setContentsMargins(0, 0, 0, 0)
        self.cols.setSpacing(28)

    def set_songs(self, songs: list[Title], ranked: bool = True) -> None:
        clear_layout(self.cols)
        half = (len(songs) + 1) // 2
        for start in (0, half):
            col = QVBoxLayout()
            col.setSpacing(2)
            for i, s in enumerate(songs[start : start + half], start=start):
                col.addWidget(TrackRow(i + 1 if ranked else None, s, songs, self.session))
            col.addStretch()
            self.cols.addLayout(col, 1)


# ---------- The Music page ----------


class MusicPage(Page):
    TYPE_DELAY_MS = 400

    def __init__(self, session: Session) -> None:
        super().__init__((40, 48, 0, 70))
        self.session = session
        self.body.addWidget(self.header("Music", "This week's top songs on Apple Music. Pick any song to hear a 30-second preview."))

        self.field = QFrame()
        self.field.setObjectName("field")
        self.field.setFixedHeight(40)
        self.field.setMaximumWidth(520)
        fr = QHBoxLayout(self.field)
        fr.setContentsMargins(11, 0, 11, 0)
        fr.setSpacing(9)
        glass = QLabel()
        glass.setPixmap(icon("magnifying-glass", "muted2").pixmap(16, 16))
        fr.addWidget(glass)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search songs or artists...")
        self.query.setAccessibleName("Search songs or artists")
        self.query.setClearButtonEnabled(True)
        self.query.installEventFilter(self)
        fr.addWidget(self.query)
        self.body.addWidget(self.field)
        self.body.addSpacing(34)

        self.timer = QTimer(self, singleShot=True, interval=self.TYPE_DELAY_MS)
        self.timer.timeout.connect(self._search)
        self.query.textChanged.connect(lambda _t: self.timer.start())
        self.query.returnPressed.connect(lambda: (self.timer.stop(), self._search()))

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 35, 12)
        head.setSpacing(9)
        self.list_title = label("Top 20 Songs", "sectionTitle")
        self.list_meta = label("Apple Music, this week", "sectionMeta")
        head.addWidget(self.list_title)
        head.addWidget(self.list_meta, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch()
        self.body.addLayout(head)
        self.tracks = TrackList(session)
        tracks_box = QWidget()
        tb = QVBoxLayout(tracks_box)
        tb.setContentsMargins(0, 0, 40, 0)
        tb.addWidget(self.tracks)
        self.body.addWidget(tracks_box)
        self.status = QVBoxLayout()
        self.body.addLayout(self.status)
        self.body.addSpacing(40)

        self.rows = QWidget()
        rc = QVBoxLayout(self.rows)
        rc.setContentsMargins(0, 0, 0, 0)
        rc.setSpacing(0)
        for genre_id, name in music.MUSIC_GENRES:
            rc.addWidget(Row(name, session, card=SONG_CARD).load(lambda g=genre_id: music.top_songs(g)))
        self.body.addWidget(self.rows)
        self._load_chart()

    def eventFilter(self, obj, event) -> bool:
        if obj is getattr(self, "query", None) and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.field.setProperty("focus", event.type() == QEvent.Type.FocusIn)
            self.field.style().unpolish(self.field)
            self.field.style().polish(self.field)
        return super().eventFilter(obj, event)

    def _load_chart(self) -> None:
        self.list_title.setText("Top 20 Songs")
        self.list_meta.setText("Apple Music, this week")
        self.rows.show()
        self._loading()
        run_async(lambda: music.top_songs()[:20], lambda songs: self._show(songs, True, ""), self._failed, owner=self)

    def _search(self) -> None:
        q = self.query.text().strip()
        if len(q) < 2:
            self._load_chart()
            return
        self.list_title.setText(f'Songs for "{q}"')
        self.list_meta.setText("")
        self.rows.hide()
        self._loading()
        run_async(lambda: music.search_songs(q), lambda songs, q=q: self._show(songs, False, q), self._failed, owner=self)

    def _loading(self) -> None:
        clear_layout(self.status)
        self.tracks.set_songs([])
        self.status.addWidget(label("Loading songs...", "pageSub"))

    def _show(self, songs: list[Title], ranked: bool, q: str) -> None:
        if q and q != self.query.text().strip():
            return  # a newer search is on its way
        clear_layout(self.status)
        if q:
            self.list_meta.setText(f"{len(songs)} {'song' if len(songs) == 1 else 'songs'}")
        if not songs:
            self.tracks.set_songs([])
            self.status.addWidget(EmptyState("music-notes", "No songs found", "Try a different song title or artist name."))
            return
        self.tracks.set_songs(songs[:20], ranked)

    def _failed(self, e: Exception) -> None:
        clear_layout(self.status)
        self.tracks.set_songs([])
        msg = str(e) if isinstance(e, FetchError) else None
        self.status.addWidget(error_state("songs", self._search if self.query.text().strip() else self._load_chart, compact=False, message=msg))
