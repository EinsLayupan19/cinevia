"""Sign in / create account: artwork on the left, the form on the right (as in the reference)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cinevia.auth import Accounts, AuthError, User, password_problem, username_problem
from cinevia.data import itunes

from .images import images
from .theme import theme
from .widgets import button, cover_pixmap, icon, label
from .workers import run_async

LOGO = None  # set by the app: path to the logo image


class _Art(QWidget):
    """Key art from this week's top film, with the logo and a line of copy."""

    def __init__(self) -> None:
        super().__init__()
        self.pix = QPixmap()
        self.setMinimumWidth(420)
        col = QVBoxLayout(self)
        col.setContentsMargins(54, 0, 54, 60)
        col.addStretch()
        brand = QHBoxLayout()
        brand.setSpacing(12)
        mark = QLabel()
        mark.setFixedSize(44, 44)
        if LOGO:
            mark.setPixmap(round_logo(QPixmap(str(LOGO)), 44))
        brand.addWidget(mark)
        word = QLabel("Cinevia")
        word.setObjectName("authWordmark")
        brand.addWidget(word)
        brand.addStretch()
        col.addLayout(brand)
        col.addSpacing(30)
        quote = QLabel("Find something good to watch tonight.")
        quote.setWordWrap(True)
        quote.setMaximumWidth(440)
        quote.setObjectName("authQuote")
        col.addWidget(quote)
        sub = QLabel("Trending movies and TV shows, with their trailers.")
        sub.setObjectName("authQuoteSub")
        col.addSpacing(8)
        col.addWidget(sub)
        run_async(lambda: itunes.top_movies()[0].poster_large, self._got_url, lambda e: None, owner=self)

    def _got_url(self, url: str) -> None:
        images().load(url, self._set, owner=self)

    def _set(self, pix: QPixmap) -> None:
        self.pix = pix
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#11131a"))
        if not self.pix.isNull():
            p.setOpacity(0.85)
            # Trim the outer 5% so a poster's own printed border doesn't show.
            r = self.pix.rect()
            inner = self.pix.copy(r.adjusted(r.width() // 20, r.height() // 20, -r.width() // 20, -r.height() // 20))
            p.drawPixmap(0, 0, cover_pixmap(inner, self.size(), 0.3))
            p.setOpacity(1)
        down = QLinearGradient(0, 0, 0, self.height())
        down.setColorAt(0.35, QColor(8, 9, 13, 0))
        down.setColorAt(1.0, QColor(8, 9, 13, 240))
        p.fillRect(self.rect(), down)
        side = QLinearGradient(0, 0, self.width(), 0)
        side.setColorAt(0.0, QColor(11, 13, 18, 0))
        side.setColorAt(1.0, theme.color("bg"))
        p.fillRect(self.rect(), side)


def round_logo(pix: QPixmap, size: int) -> QPixmap:
    """The logo artwork is a ring on a dark square; crop it to the ring."""
    out = QPixmap(size * 2, size * 2)
    out.fill(Qt.GlobalColor.transparent)
    if pix.isNull():
        return out
    p = QPainter(out)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addEllipse(QRectF(0, 0, size * 2, size * 2))
    p.setClipPath(path)
    zoom = 1.46
    side = int(size * 2 * zoom)
    off = (side - size * 2) // 2
    p.drawPixmap(-off, -off, side, side, pix)
    p.end()
    out.setDevicePixelRatio(2)
    return out


class _Field(QFrame):
    """Label above an input with a leading icon, like the reference's auth inputs."""

    def __init__(self, caption: str, icon_name: str, placeholder: str, secret: bool = False) -> None:
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(7)
        cap = label(caption, "fieldLabel")
        col.addWidget(cap)
        self.box = QFrame()
        self.box.setObjectName("authInput")
        self.box.setFixedHeight(44)
        row = QHBoxLayout(self.box)
        row.setContentsMargins(13, 0, 8, 0)
        row.setSpacing(10)
        self.icon = QLabel()
        self.icon_name = icon_name
        row.addWidget(self.icon)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setAccessibleName(caption)
        cap.setBuddy(self.edit)
        if secret:
            self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(self.edit, 1)
        self.toggle: QPushButton | None = None
        if secret:
            self.toggle = QPushButton()
            self.toggle.setObjectName("iconButton")
            self.toggle.setFixedSize(30, 30)
            self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            self.toggle.setToolTip("Show password")
            self.toggle.setAccessibleName("Show password")
            self.toggle.clicked.connect(self._toggle)
            row.addWidget(self.toggle)
        col.addWidget(self.box)
        self.edit.installEventFilter(self)
        self.restyle()

    def restyle(self) -> None:
        self.icon.setPixmap(icon(self.icon_name, "muted2").pixmap(17, 17))
        if self.toggle:
            hidden = self.edit.echoMode() == QLineEdit.EchoMode.Password
            self.toggle.setIcon(icon("eye" if hidden else "eye-slash", "muted"))

    def _toggle(self) -> None:
        hidden = self.edit.echoMode() == QLineEdit.EchoMode.Password
        self.edit.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.toggle.setToolTip("Hide password" if hidden else "Show password")
        self.toggle.setAccessibleName(self.toggle.toolTip())
        self.restyle()

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.box.setProperty("focus", event.type() == QEvent.Type.FocusIn)
            self.box.style().unpolish(self.box)
            self.box.style().polish(self.box)
        return False

    def text(self) -> str:
        return self.edit.text()


class LoginScreen(QWidget):
    authenticated = Signal(object)  # User

    def __init__(self, accounts: Accounts) -> None:
        super().__init__()
        self.accounts = accounts
        self.mode = "login"
        self.setObjectName("root")
        self.setWindowTitle("Cinevia | Sign in")
        self.resize(1180, 760)
        self.setMinimumSize(QSize(960, 640))

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(_Art(), 52)

        wrap = QWidget()
        wrap_col = QVBoxLayout(wrap)
        wrap_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form = QWidget()
        form.setObjectName("authForm")
        form.setFixedWidth(360)
        col = QVBoxLayout(form)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.heading = label("", "authTitle")
        col.addWidget(self.heading)
        col.addSpacing(7)
        self.sub = label("", "muted")
        self.sub.setStyleSheet("font-size: 11px;")
        col.addWidget(self.sub)
        col.addSpacing(31)

        self.username = _Field("Username", "user", "Enter your username")
        self.password = _Field("Password", "lock", "Enter your password", secret=True)
        self.confirm = _Field("Confirm password", "lock", "Type your password again", secret=True)
        self.rules = label("At least 8 characters, with a letter and a number.", "facts")
        for w in (self.username, self.password):
            col.addWidget(w)
            col.addSpacing(17)
        col.addWidget(self.confirm)
        col.addSpacing(8)
        col.addWidget(self.rules)
        col.addSpacing(9)

        self.error = label("", "error", wrap=True)
        self.error.setAccessibleName("Error")
        self.error.hide()  # only takes space when there is something to say
        col.addWidget(self.error)
        col.addSpacing(8)
        self.submit = button("", "primary")
        self.submit.setFixedHeight(44)
        self.submit.clicked.connect(self._submit)
        col.addWidget(self.submit)
        col.addSpacing(23)

        switch = QHBoxLayout()
        switch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        switch.setSpacing(4)
        self.switch_text = label("", "authSwitch")
        self.switch_btn = button("", "linkButton")
        self.switch_btn.clicked.connect(self._toggle_mode)
        switch.addWidget(self.switch_text)
        switch.addWidget(self.switch_btn)
        col.addLayout(switch)
        wrap_col.addWidget(form)
        row.addWidget(wrap, 48)

        for f in (self.username, self.password, self.confirm):
            f.edit.returnPressed.connect(self._submit)
        theme.changed.connect(lambda: [f.restyle() for f in (self.username, self.password, self.confirm)])
        self._apply_mode()

    def _apply_mode(self) -> None:
        login = self.mode == "login"
        self.heading.setText("Welcome back" if login else "Create your account")
        self.sub.setText("Sign in to see your favorites and recent searches." if login else "Save favorites and keep your search history in one place.")
        self.confirm.setVisible(not login)
        self.rules.setVisible(not login)
        self.submit.setText("Sign in" if login else "Create account")
        self.switch_text.setText("New to Cinevia?" if login else "Already have an account?")
        self.switch_btn.setText("Create an account" if login else "Sign in")
        self.password.edit.setPlaceholderText("Enter your password" if login else "Create a password")
        self.error.hide()
        self.username.edit.setFocus()

    def _toggle_mode(self) -> None:
        self.mode = "signup" if self.mode == "login" else "login"
        self.password.edit.clear()
        self.confirm.edit.clear()
        self._apply_mode()

    def _submit(self) -> None:
        if not self.submit.isEnabled():
            return
        name, pw = self.username.text().strip(), self.password.text()
        if not name or not pw:
            self._fail("Enter your username and password.")
            return
        if self.mode == "signup":
            problem = username_problem(name) or password_problem(pw)
            if not problem and pw != self.confirm.text():
                problem = "Passwords don't match."
            if problem:
                self._fail(problem)
                return
        self.error.hide()
        self.submit.setEnabled(False)
        self.submit.setText("Signing in..." if self.mode == "login" else "Creating account...")
        # Hashing takes a moment on purpose (600,000 PBKDF2 rounds), so it runs off the UI thread.
        action = self.accounts.login if self.mode == "login" else self.accounts.register
        run_async(lambda: action(name, pw), self._done, self._error, owner=self)

    def _done(self, user: User) -> None:
        self.password.edit.clear()
        self.confirm.edit.clear()
        self.submit.setEnabled(True)
        self._apply_mode()
        self.authenticated.emit(user)

    def _error(self, e: Exception) -> None:
        self.submit.setEnabled(True)
        self.submit.setText("Sign in" if self.mode == "login" else "Create account")
        self._fail(str(e) if isinstance(e, AuthError) else "Something went wrong. Please try again.")

    def _fail(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.password.edit.setFocus()
        self.password.edit.selectAll()

    def reset(self) -> None:
        self.username.edit.clear()
        self.password.edit.clear()
        self.confirm.edit.clear()
        self.mode = "login"
        self._apply_mode()
