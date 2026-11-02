"""The app's screens. Each one is a scrollable page built on demand."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cinevia.data import catalog, itunes, tvmaze
from cinevia.data.catalog import Filters
from cinevia.data.http import FetchError
from cinevia.data.models import Title
from cinevia.data.util import format_when

from .context import Session
from .hero import Backdrop, Hero, meta_row, wide_art
from .images import images
from .theme import theme
from .widgets import (
    ClampLabel,
    EmptyState,
    Eyebrow,
    Grid,
    Row,
    button,
    chips,
    clear_layout,
    cover_pixmap,
    error_state,
    icon,
    label,
)
from .workers import run_async


class Page(QScrollArea):
    def __init__(self, margins: tuple[int, int, int, int] = (40, 48, 40, 70)) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("page")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(0)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(inner)

    def header(self, eyebrow: str, title: str, sub: str) -> QWidget:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 36)
        col.setSpacing(0)
        col.addWidget(Eyebrow(eyebrow))
        col.addSpacing(9)
        col.addWidget(label(title, "pageTitle"))
        col.addSpacing(6)
        self.subtitle = label(sub, "pageSub", wrap=True)
        col.addWidget(self.subtitle)
        return box


def row(heading: str, session: Session, loader, **kw) -> Row:
    return Row(heading, session, **kw).load(loader)


# ---------- Home, Movies, TV ----------


def featured() -> list[Title]:
    """Chart-topping films with trailers, interleaved with two trending shows."""
    movies = [t for t in itunes.top_movies() if t.trailer and t.summary]
    try:
        shows = [t for t in tvmaze.trending_shows() if t.summary][:2]
    except FetchError:
        shows = []
    if not movies and not shows:
        raise FetchError("Couldn't load featured titles.")
    mix = [*movies[:1], *shows[:1], *movies[1:2], *shows[1:2], *movies[2:5]]
    return mix[:5]


def shows_in(bucket: str):
    return lambda: [t for t in tvmaze.show_library() if bucket in catalog.buckets_of(t)]


class HomePage(Page):
    def __init__(self, session: Session) -> None:
        super().__init__((0, 0, 0, 0))
        hero = Hero(session)
        hero.load(featured)
        self.body.addWidget(hero)
        rows = QWidget()
        col = QVBoxLayout(rows)
        col.setContentsMargins(38, 6, 0, 55)
        col.setSpacing(0)
        col.addWidget(row("Top 10 Movies This Week", session, itunes.top_movies, limit=10, see_all=lambda: session.go("movies")))
        col.addWidget(row("Trending TV Shows", session, tvmaze.trending_shows, see_all=lambda: session.go("tv")))
        col.addWidget(row("New Episodes Today", session, tvmaze.airing_today))
        col.addWidget(row("Action & Adventure", session, lambda: itunes.top_movies(4401)))
        col.addWidget(row("Science Fiction Series", session, shows_in("Science Fiction")))
        col.addWidget(row("Comedy", session, lambda: itunes.top_movies(4404)))
        col.addWidget(row("Horror & Thriller", session, lambda: itunes.top_movies(4408)))
        col.addWidget(row("Popular Series", session, tvmaze.show_library))
        self.body.addWidget(rows)


class MoviesPage(Page):
    def __init__(self, session: Session) -> None:
        super().__init__((40, 48, 0, 70))
        self.body.addWidget(self.header("Now on Apple TV", "Movies", "This week's charts by genre. Every title comes with its official trailer."))

        def newest() -> list[Title]:
            return sorted(catalog.movie_library(), key=lambda t: (t.year or 0, t.popularity), reverse=True)

        self.body.addWidget(row("Top 10 Movies This Week", session, itunes.top_movies, limit=10))
        self.body.addWidget(row("Recently Released", session, newest))
        for genre_id, name in itunes.MOVIE_GENRES:
            self.body.addWidget(row(name, session, lambda g=genre_id: itunes.top_movies(g)))


class TvPage(Page):
    def __init__(self, session: Session) -> None:
        super().__init__((40, 48, 0, 70))
        self.body.addWidget(self.header("Tonight on TV", "TV Shows", "Trending seasons, today's new episodes and the series viewers rate highest."))
        self.body.addWidget(row("Trending This Week", session, tvmaze.trending_shows))
        self.body.addWidget(row("New Episodes Today", session, tvmaze.airing_today))
        self.body.addWidget(row("Highest Rated", session, lambda: sorted(tvmaze.show_library(), key=lambda t: -(t.rating or 0))))
        for bucket, heading in [
            ("Drama", "Drama"),
            ("Crime", "Crime"),
            ("Thriller", "Mystery & Thriller"),
            ("Comedy", "Comedy"),
            ("Science Fiction", "Science Fiction"),
            ("Fantasy", "Fantasy"),
            ("Action", "Action"),
            ("Horror", "Horror"),
            ("Animation", "Anime & Family"),
        ]:
            self.body.addWidget(row(heading, session, shows_in(bucket)))


# ---------- Details ----------


class _Poster(QWidget):
    def __init__(self, url: str, size: QSize) -> None:
        super().__init__()
        self.setFixedSize(size)
        self.pix = QPixmap()
        images().load(url, self._set, owner=self)

    def _set(self, pix: QPixmap) -> None:
        self.pix = pix
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 7, 7)
        p.setClipPath(path)
        p.fillRect(self.rect(), theme.color("card"))
        if not self.pix.isNull():
            p.drawPixmap(0, 0, cover_pixmap(self.pix, self.size()))


class DetailsPage(Page):
    def __init__(self, session: Session, title: Title, go_back) -> None:
        super().__init__((0, 0, 0, 0))
        self.session = session
        self.title = title
        self.hero = Backdrop(595, blur_all=True)
        self.body.addWidget(self.hero)
        back = button("Back to browse", "textButton", "arrow-left", "text2")
        back.setStyleSheet("font-size: 10px;")
        back.setParent(self.hero)
        back.move(32, 24)
        back.clicked.connect(go_back)
        self.content = QWidget(self.hero)
        self.content_row = QHBoxLayout(self.content)
        self.content_row.setContentsMargins(0, 0, 0, 0)
        self.content_row.setSpacing(30)
        self.content_row.setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.hero.installEventFilter(self)
        self._fill(title)
        url, soft = wide_art(title)
        images().load(url, lambda pix: self.hero.set_image(pix, soft), owner=self)
        run_async(lambda: catalog.details(title), self._enrich, lambda e: None, owner=self)

        more = QWidget()
        mc = QVBoxLayout(more)
        mc.setContentsMargins(39, 5, 0, 60)
        mc.addWidget(row("More Like This", session, lambda: catalog.more_like_this(title)))
        self.body.addWidget(more)

    def eventFilter(self, obj, event) -> bool:
        if obj is getattr(self, "hero", None) and event.type() == QEvent.Type.Resize:
            self._place()
        return super().eventFilter(obj, event)

    def _place(self) -> None:
        self.content_row.activate()
        h = self.content.sizeHint().height()
        self.content.setGeometry(40, self.hero.height() - 40 - h, self.hero.width() - 80, h)

    def _enrich(self, extra: dict) -> None:
        self.title = self.title.with_details(extra)
        self._fill(self.title)
        if extra.get("backdrop"):
            images().load(extra["backdrop"], lambda pix: self.hero.set_image(pix, False), owner=self)

    def _fill(self, t: Title) -> None:
        clear_layout(self.content_row)
        self.content_row.addWidget(_Poster(t.poster_large or t.poster, QSize(210, 315)), 0, Qt.AlignmentFlag.AlignBottom)
        copy = QWidget()
        copy.setMaximumWidth(570)
        col = QVBoxLayout(copy)
        col.setContentsMargins(0, 0, 0, 7)
        col.setSpacing(0)
        col.addWidget(Eyebrow("Cinevia Series" if t.kind == "tv" else "Cinevia Select"))
        col.addSpacing(12)
        name = label(t.title.upper(), "detailsTitle", wrap=True)
        if len(t.title) > 20:
            name.setStyleSheet("font-size: 40px;")
        col.addWidget(name)
        col.addSpacing(11)
        col.addWidget(meta_row(t))
        if t.genres:
            col.addSpacing(15)
            col.addWidget(chips(t.genres[:5]))
        col.addSpacing(15)
        col.addWidget(ClampLabel(t.summary or "No synopsis yet.", "body", 4))
        facts = []
        if t.credit:
            facts.append(f"{'Network' if t.kind == 'tv' else 'Director'}  <b>{t.credit}</b>")
        if t.cast:
            facts.append(f"Cast  <b>{', '.join(t.cast[:4])}</b>")
        if facts:
            f = label("&nbsp;&nbsp;&nbsp;&nbsp;".join(facts), "facts", wrap=True)
            f.setTextFormat(Qt.TextFormat.RichText)
            col.addSpacing(10)
            col.addWidget(f)
        col.addSpacing(22)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        play = button("Watch teaser" if t.kind == "tv" else "Watch trailer", "primary", "play", "#ffffff")
        play.clicked.connect(lambda: self.session.play_trailer(t))
        actions.addWidget(play)
        self.fav = button("", "ghost")
        self.fav.clicked.connect(lambda: self.session.toggle_favorite(self.title))
        self.session.favorites_changed.connect(self._sync_fav)
        actions.addWidget(self.fav)
        actions.addStretch()
        col.addLayout(actions)
        self.content_row.addWidget(copy, 1, Qt.AlignmentFlag.AlignBottom)
        self._sync_fav()
        self._place()
        QTimer.singleShot(0, self, self._place)  # once the new widgets have been laid out

    def _sync_fav(self) -> None:
        if not hasattr(self, "fav"):
            return
        try:
            saved = self.session.is_favorite(self.title.id)
            self.fav.setText("In favorites" if saved else "Add to favorites")
            self.fav.setIcon(icon("heart-fill" if saved else "heart", "red_text" if saved else "text"))
            self.fav.setProperty("favorited", saved)
            self.fav.style().unpolish(self.fav)
            self.fav.style().polish(self.fav)
        except RuntimeError:
            pass  # the button was replaced while details were refreshing


# ---------- Discover ----------


class _Select(QWidget):
    def __init__(self, caption: str, options: list[str]) -> None:
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(7)
        cap = label(caption.upper(), "fieldLabel")
        col.addWidget(cap)
        self.combo = QComboBox()
        self.combo.addItems(options)
        self.combo.setAccessibleName(caption)
        self.combo.setCursor(Qt.CursorShape.PointingHandCursor)
        cap.setBuddy(self.combo)
        col.addWidget(self.combo)

    def value(self) -> str:
        return self.combo.currentText()

    def set(self, value: str) -> None:
        self.combo.setCurrentText(value)


class DiscoverPage(Page):
    PAGE = 36

    def __init__(self, session: Session, query: str = "", focus: str | None = None) -> None:
        super().__init__()
        self.session = session
        self.pool: list[Title] = []
        self.results: list[Title] = []
        self.shown = self.PAGE
        self.pool_query: str | None = None
        self.body.addWidget(self.header("Find your next favorite", "Discover", "Explore movies and series across every world, mood and moment."))

        panel = QFrame()
        panel.setObjectName("filterPanel")
        grid = QGridLayout(panel)
        grid.setContentsMargins(17, 17, 17, 17)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(14)
        search = QWidget()
        sc = QVBoxLayout(search)
        sc.setContentsMargins(0, 0, 0, 0)
        sc.setSpacing(7)
        cap = label("SEARCH BY TITLE", "fieldLabel")
        sc.addWidget(cap)
        self.field = QFrame()
        self.field.setObjectName("field")
        self.field.setFixedHeight(39)
        fr = QHBoxLayout(self.field)
        fr.setContentsMargins(11, 0, 11, 0)
        fr.setSpacing(9)
        glass = QLabel()
        glass.setPixmap(icon("magnifying-glass", "muted2").pixmap(16, 16))
        fr.addWidget(glass)
        self.query = QLineEdit(query)
        self.query.setPlaceholderText("Search movies and shows...")
        self.query.setAccessibleName("Search by title")
        cap.setBuddy(self.query)
        self.query.returnPressed.connect(self.apply)
        self.query.installEventFilter(self)
        fr.addWidget(self.query)
        sc.addWidget(self.field)
        self.type = _Select("Type", catalog.TYPE_OPTIONS)
        self.genre = _Select("Genre", catalog.GENRE_OPTIONS)
        self.year = _Select("Release year", catalog.year_options())
        self.rating = _Select("Rating", catalog.RATING_OPTIONS)
        self.sort = _Select("Sort by", catalog.SORT_OPTIONS)
        grid.addWidget(search, 0, 0)
        for i, w in enumerate((self.type, self.genre, self.year, self.rating, self.sort), start=1):
            grid.addWidget(w, 0, i)
        grid.setColumnStretch(0, 17)
        for i in range(1, 6):
            grid.setColumnStretch(i, 10)
        actions = QHBoxLayout()
        actions.addStretch()
        reset = button("Reset", "textButton")
        reset.clicked.connect(self.reset)
        apply_btn = button("Apply filters", "primary")
        apply_btn.setFixedHeight(35)
        apply_btn.clicked.connect(self.apply)
        actions.addWidget(reset)
        actions.addSpacing(10)
        actions.addWidget(apply_btn)
        grid.addLayout(actions, 1, 0, 1, 6)
        self.body.addWidget(panel)

        head = QHBoxLayout()
        head.setContentsMargins(0, 34, 0, 14)
        self.results_title = label("All Titles", "sectionTitle")
        self.count = label("", "sectionMeta")
        self.count.setStyleSheet("font-size: 11px;")
        head.addWidget(self.results_title)
        head.addSpacing(7)
        head.addWidget(self.count, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch()
        self.note = label("Live from Apple TV charts and TVmaze", "sectionMeta")
        self.note.setStyleSheet("font-size: 10px;")
        head.addWidget(self.note)
        self.body.addLayout(head)
        self.grid = Grid(session)
        self.body.addWidget(self.grid)
        self.status = QVBoxLayout()
        self.body.addLayout(self.status)
        self.more = button("", "ghost")
        self.more.clicked.connect(self._show_more)
        self.body.addSpacing(30)
        self.body.addWidget(self.more, 0, Qt.AlignmentFlag.AlignHCenter)
        self.more.hide()

        if focus in ("genre", "year", "rating"):
            getattr(self, focus).combo.setFocus()
            getattr(self, focus).combo.showPopup()
        self.apply()

    def eventFilter(self, obj, event) -> bool:
        if obj is getattr(self, "query", None) and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.field.setProperty("focus", event.type() == QEvent.Type.FocusIn)
            self.field.style().unpolish(self.field)
            self.field.style().polish(self.field)
        return super().eventFilter(obj, event)

    def filters(self) -> Filters:
        return Filters(
            query=self.query.text(),
            type=self.type.value(),
            genre=self.genre.value(),
            year=self.year.value(),
            rating=self.rating.value(),
            sort=self.sort.value(),
        )

    def apply(self) -> None:
        f = self.filters()
        q = f.query.strip()
        if q and q.lower() != (self.pool_query or "").lower():
            self.session.add_search(q)
        self.shown = self.PAGE
        self.results_title.setText(f'Results for "{q}"' if q else "All Titles")
        self.note.setText(
            "Ratings come from TVmaze, so rated results are TV shows." if f.rating != "Any Rating" else "Live from Apple TV charts and TVmaze"
        )
        if self.pool_query is not None and q.lower() == self.pool_query.lower():
            self._render()
            return
        self.pool_query = q
        clear_layout(self.status)
        self.count.setText("")
        self.more.hide()
        self.grid.set_items([], skeleton=12)
        run_async(lambda: catalog.discover_pool(q), lambda pool, q=q: self._got_pool(q, pool), self._failed, owner=self)

    def _got_pool(self, q: str, pool: list[Title]) -> None:
        if q != self.pool_query:
            return  # a newer search is on its way
        self.pool = pool
        self._render()

    def _failed(self, e: Exception) -> None:
        self.grid.set_items([])
        self.pool_query = None
        clear_layout(self.status)
        self.status.addWidget(error_state("titles", self.apply, compact=False, message=str(e) if isinstance(e, FetchError) else None))

    def _render(self) -> None:
        clear_layout(self.status)
        self.results = catalog.apply_filters(self.pool, self.filters())
        self.count.setText(str(len(self.results)))
        if not self.results:
            self.grid.set_items([])
            reset = button("Reset filters", "ghost")
            reset.clicked.connect(self.reset)
            self.status.addWidget(EmptyState("magnifying-glass", "No titles found", "Try broadening your filters or searching a different title.", reset))
            self.more.hide()
            return
        self.grid.set_items(self.results[: self.shown])
        left = len(self.results) - self.shown
        self.more.setVisible(left > 0)
        self.more.setText(f"Show more ({left} left)")

    def _show_more(self) -> None:
        self.shown += self.PAGE
        self._render()

    def reset(self) -> None:
        self.query.clear()
        for s in (self.type, self.genre, self.year, self.rating, self.sort):
            s.combo.setCurrentIndex(0)
        self.apply()


# ---------- Favorites ----------


class FavoritesPage(Page):
    def __init__(self, session: Session) -> None:
        super().__init__((40, 48, 0, 70))
        self.session = session
        self.body.addWidget(self.header("Your personal cinema", "My Favorites", ""))
        self.rows = QVBoxLayout()
        self.body.addLayout(self.rows)
        self.body.addStretch(1)
        session.favorites_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        favorites = self.session.favorites()
        n = len(favorites)
        self.subtitle.setText(f"{n} {'story' if n == 1 else 'stories'} saved for later.")
        clear_layout(self.rows)
        if not favorites:
            browse = button("Discover titles", "primary")
            browse.clicked.connect(lambda: self.session.go("discover"))
            self.rows.addWidget(EmptyState("heart", "No favorites yet", "Tap the heart on any poster to save it here.", browse))
            return
        groups: dict[str, list[Title]] = {}
        for t in favorites:
            groups.setdefault((catalog.buckets_of(t) or ["More Picks"])[0], []).append(t)
        for genre, items in groups.items():
            r = Row(genre, self.session, meta=f"{len(items)} {'title' if len(items) == 1 else 'titles'}", removable=True, limit=100)
            r.set_items(items)
            self.rows.addWidget(r)


# ---------- History ----------


class HistoryPage(Page):
    def __init__(self, session: Session) -> None:
        super().__init__((40, 48, 100, 70))
        self.session = session
        top = QHBoxLayout()
        top.addWidget(self.header("Pick up where you left off", "Search History", "Your recent searches across Cinevia."))
        top.addStretch()
        self.clear = button("  Clear history", "clearButton", "x", "red_text")
        self.clear.clicked.connect(session.clear_history)
        top.addWidget(self.clear, 0, Qt.AlignmentFlag.AlignBottom)
        self.body.addLayout(top)
        self.list = QVBoxLayout()
        self.list.setSpacing(0)
        self.body.addLayout(self.list)
        self.body.addStretch(1)
        session.history_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        clear_layout(self.list)
        items = self.session.history()
        self.clear.setVisible(bool(items))
        if not items:
            self.list.addWidget(EmptyState("clock-counter-clockwise", "No recent searches", "Your searches will appear here so you can revisit them in a click."))
            return
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {theme.p['line']};")
        self.list.addWidget(line)
        for h in items:
            item = QFrame()
            item.setObjectName("historyItem")
            item.setFixedHeight(76)
            r = QHBoxLayout(item)
            r.setContentsMargins(0, 0, 0, 0)
            r.setSpacing(13)
            ic = QLabel()
            ic.setObjectName("historyIcon")
            ic.setFixedSize(38, 38)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setPixmap(icon("clock-counter-clockwise", "muted2").pixmap(18, 18))
            r.addWidget(ic)
            text = QVBoxLayout()
            text.setSpacing(4)
            text.addStretch()
            text.addWidget(label(h.query, "historyQuery"))
            text.addWidget(label(format_when(h.at), "historyTime"))
            text.addStretch()
            r.addLayout(text, 1)
            again = button("Search again", "historyAction")
            again.setIcon(icon("caret-right", "muted"))
            again.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            again.clicked.connect(lambda _=False, q=h.query: self.session.search(q))
            r.addWidget(again)
            remove = QPushButton()
            remove.setObjectName("historyAction")
            remove.setIcon(icon("x", "muted"))
            remove.setAccessibleName(f'Remove "{h.query}" from history')
            remove.setToolTip("Remove")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda _=False, q=h.query: self.session.remove_search(q))
            r.addWidget(remove)
            self.list.addWidget(item)
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background: {theme.p['line']};")
            self.list.addWidget(sep)
