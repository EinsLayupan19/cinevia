"""Main window: sidebar, top bar and the page area (layout from the reference design)."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cinevia.data.models import Title

from . import login as login_module
from .context import Session
from .login import round_logo
from .pages import (
    DetailsPage,
    DiscoverPage,
    FavoritesPage,
    HistoryPage,
    HomePage,
    MoviesPage,
    TvPage,
)
from .player import PlayerDialog
from .theme import theme
from .widgets import button, icon, label

NAV = [
    ("home", "Home", "house"),
    ("movies", "Movies", "film-strip"),
    ("tv", "TV Shows", "television-simple"),
    ("discover", "Discover", "compass"),
    ("favorites", "Favorites", "heart"),
    ("history", "Search history", "clock-counter-clockwise"),
]


@dataclass
class Route:
    page: str
    title: Title | None = None
    query: str = ""
    focus: str | None = None
    extra: dict = field(default_factory=dict)


class Sidebar(QFrame):
    def __init__(self, window: MainWindow) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        self.window_ = window
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 28, 20, 24)
        col.setSpacing(7)

        brand = QPushButton()
        brand.setObjectName("iconButton")
        brand.setCursor(Qt.CursorShape.PointingHandCursor)
        brand.setAccessibleName("Cinevia home")
        brand.clicked.connect(lambda: window.go("home"))
        br = QHBoxLayout(brand)
        br.setContentsMargins(10, 4, 10, 4)
        br.setSpacing(11)
        mark = QLabel()
        mark.setPixmap(round_logo(QPixmap(str(login_module.LOGO)), 36))
        br.addWidget(mark)
        self.word = QLabel()
        self.word.setObjectName("logoWord")
        br.addWidget(self.word)
        br.addStretch()
        brand.setFixedHeight(46)
        col.addWidget(brand)
        col.addSpacing(40)

        self.items: dict[str, QPushButton] = {}
        for key, text, _ in NAV:
            b = QPushButton(text)
            b.setObjectName("navItem")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIconSize(QSize(19, 19))
            b.clicked.connect(lambda _=False, k=key: window.go(k))
            col.addWidget(b)
            self.items[key] = b
        self.bar = QFrame(self)
        self.bar.setFixedSize(3, 25)
        self.bar.setStyleSheet("background: #e50914; border-top-right-radius: 2px; border-bottom-right-radius: 2px;")
        col.addStretch()

        card = QFrame()
        card.setObjectName("upgrade")
        cc = QVBoxLayout(card)
        cc.setContentsMargins(16, 16, 16, 16)
        cc.setSpacing(7)
        cc.addWidget(label("Now Showing", "upgradeTitle"))
        credits = label(
            self._credits_html(),
            "upgradeText",
            wrap=True,
        )
        credits.setTextFormat(Qt.TextFormat.RichText)
        self.credits = credits
        credits.setOpenExternalLinks(True)
        cc.addWidget(credits)
        cc.addSpacing(4)
        explore = button("Explore all titles", "upgradeLink")
        explore.clicked.connect(lambda: window.go("discover"))
        cc.addWidget(explore)
        col.addWidget(card)
        col.addSpacing(8)
        self.logout = QPushButton("Logout")
        self.logout.setObjectName("navItem")
        self.logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout.setIconSize(QSize(19, 19))
        self.logout.clicked.connect(window.log_out)
        col.addWidget(self.logout)
        self.restyle()

    def _credits_html(self) -> str:
        c = theme.p["text2"]
        link = f'style="color:{c}"'
        return (
            f'Live charts from <a {link} href="https://tv.apple.com">Apple TV</a> '
            f'and <a {link} href="https://www.tvmaze.com">TVmaze</a>.'
        )

    def restyle(self) -> None:
        if hasattr(self, "credits"):
            self.credits.setText(self._credits_html())
        self.word.setText("Cinevia")
        self.logout.setIcon(icon("sign-out", "muted"))
        self.set_active(self.window_.route.page if hasattr(self.window_, "route") else "home")

    def set_active(self, page: str) -> None:
        active = {"details": None}.get(page, page)
        for key, _text, glyph in NAV:
            b = self.items[key]
            on = key == active
            b.setProperty("active", on)
            b.setIcon(icon(f"{glyph}-fill" if on else glyph, "text" if on else "muted"))
            b.style().unpolish(b)
            b.style().polish(b)
        self.bar.setVisible(active in self.items)
        if active in self.items:
            b = self.items[active]
            self.bar.move(0, b.y() + (b.height() - 25) // 2)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.set_active(self.window_.route.page if hasattr(self.window_, "route") else "home")


class Topbar(QFrame):
    def __init__(self, window: MainWindow, session: Session) -> None:
        super().__init__()
        self.setObjectName("topbar")
        self.setFixedHeight(76)
        self.window_ = window
        row = QHBoxLayout(self)
        row.setContentsMargins(34, 0, 34, 0)
        row.setSpacing(18)

        self.search = QFrame()
        self.search.setObjectName("search")
        self.search.setFixedSize(395, 40)
        sr = QHBoxLayout(self.search)
        sr.setContentsMargins(13, 0, 10, 0)
        sr.setSpacing(10)
        self.glass = QLabel()
        sr.addWidget(self.glass)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Search movies, shows, directors...")
        self.input.setAccessibleName("Search movies and TV shows")
        self.input.returnPressed.connect(self._submit)
        self.input.installEventFilter(self)
        sr.addWidget(self.input, 1)
        kbd = label("Ctrl K", "kbd")
        kbd.setFixedHeight(20)
        sr.addWidget(kbd)
        row.addWidget(self.search)

        self.filters = []
        for text, key in (("Genre", "genre"), ("Year", "year"), ("Rating", "rating")):
            b = button(text, "quickFilter")
            b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            b.setFixedHeight(40)
            b.clicked.connect(lambda _=False, k=key: window.go("discover", focus=k))
            row.addWidget(b)
            self.filters.append(b)
        row.addStretch()

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("iconButton")
        self.theme_btn.setFixedSize(36, 36)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(window.toggle_theme)
        row.addWidget(self.theme_btn)

        self.profile = QPushButton()
        self.profile.setObjectName("iconButton")
        self.profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile.setAccessibleName(f"Account menu for {session.user.username}")
        pr = QHBoxLayout(self.profile)
        pr.setContentsMargins(6, 4, 6, 4)
        pr.setSpacing(10)
        avatar = QLabel(session.user.username[:1].upper())
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet("background: #e50914; color: #ffffff; border-radius: 17px; font-weight: 700; font-size: 14px;")
        pr.addWidget(avatar)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(label(session.user.username, "profileName"))
        names.addWidget(label("Signed in", "profileSub"))
        pr.addLayout(names)
        self.profile.setFixedHeight(44)
        self.profile.setMinimumWidth(150)
        menu = QMenu(self.profile)
        menu.addAction("Favorites", lambda: window.go("favorites"))
        menu.addAction("Search history", lambda: window.go("history"))
        menu.addSeparator()
        menu.addAction("Log out", window.log_out)
        self.profile.clicked.connect(lambda: menu.exec(self.profile.mapToGlobal(self.profile.rect().bottomLeft())))
        row.addWidget(self.profile)
        self.restyle()

    def restyle(self) -> None:
        self.glass.setPixmap(icon("magnifying-glass", "muted").pixmap(17, 17))
        for b in self.filters:
            b.setIcon(icon("caret-down", "muted"))
            b.setIconSize(QSize(13, 13))
        dark = theme.name == "dark"
        self.theme_btn.setIcon(icon("sun" if dark else "moon", "muted"))
        self.theme_btn.setIconSize(QSize(19, 19))
        self.theme_btn.setToolTip("Switch to light mode" if dark else "Switch to dark mode")
        self.theme_btn.setAccessibleName(self.theme_btn.toolTip())

    def _submit(self) -> None:
        q = self.input.text().strip()
        if q:
            self.window_.session.search(q)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.input and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.search.setProperty("focus", event.type() == QEvent.Type.FocusIn)
            self.search.style().unpolish(self.search)
            self.search.style().polish(self.search)
        return False

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        # The reference hides the quick filters on narrower windows.
        for b in self.filters:
            b.setVisible(self.width() > 1030)


class MainWindow(QMainWindow):
    logged_out = Signal()

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.route = Route("home")
        self.history: list[Route] = []
        self.setWindowTitle("Cinevia")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 820)

        session.open_title = lambda t: self.go("details", title=t)
        session.play_trailer = self.play
        session.search = self.search
        session.go = lambda page: self.go(page)

        root = QWidget()
        root.setObjectName("root")
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sidebar = Sidebar(self)
        row.addWidget(self.sidebar)
        right = QVBoxLayout()
        right.setSpacing(0)
        self.topbar = Topbar(self, session)
        right.addWidget(self.topbar)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        row.addLayout(right, 1)
        self.setCentralWidget(root)

        QShortcut(QKeySequence("Ctrl+K"), self, lambda: (self.topbar.input.setFocus(), self.topbar.input.selectAll()))
        QShortcut(QKeySequence("/"), self, lambda: self.topbar.input.setFocus())
        QShortcut(QKeySequence("Alt+Left"), self, self.back)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Back), self, self.back)
        theme.changed.connect(self._on_theme)
        self._show(self.route)

    # Navigation
    def go(self, page: str, title: Title | None = None, query: str = "", focus: str | None = None) -> None:
        self.history.append(self.route)
        del self.history[:-30]
        self._show(Route(page, title, query, focus))

    def back(self) -> None:
        if self.history:
            self._show(self.history.pop())
        else:
            self._show(Route("home"))

    def _build(self, r: Route) -> QWidget:
        s = self.session
        if r.page == "details" and r.title:
            return DetailsPage(s, r.title, self.back)
        if r.page == "movies":
            return MoviesPage(s)
        if r.page == "tv":
            return TvPage(s)
        if r.page == "discover":
            return DiscoverPage(s, r.query, r.focus)
        if r.page == "favorites":
            return FavoritesPage(s)
        if r.page == "history":
            return HistoryPage(s)
        return HomePage(s)

    def _show(self, r: Route) -> None:
        self.route = r
        old = self.stack.currentWidget()
        page = self._build(r)
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        if old:
            self.stack.removeWidget(old)
            old.deleteLater()
        self.sidebar.set_active(r.page)
        names = {"details": r.title.title if r.title else "", "discover": "Discover", "favorites": "My Favorites",
                 "history": "Search History", "movies": "Movies", "tv": "TV Shows"}
        name = names.get(r.page)
        self.setWindowTitle(f"{name} | Cinevia" if name else "Cinevia")
        if r.page != "discover":
            self.topbar.input.clear()

    # Actions
    def search(self, query: str) -> None:
        self.session.add_search(query)
        self.topbar.input.setText(query)
        self.go("discover", query=query)
        self.topbar.input.setText(query)

    def play(self, title: Title) -> None:
        PlayerDialog(title, self).exec()

    def toggle_theme(self) -> None:
        name = "light" if theme.name == "dark" else "dark"
        self.session.set_theme(name)
        theme.set(name)

    def _on_theme(self) -> None:
        self.sidebar.restyle()
        self.topbar.restyle()
        # Icons are drawn in theme colors, so rebuild the current page in place.
        self._show(self.route)

    def log_out(self) -> None:
        self.logged_out.emit()

    def open_external(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
