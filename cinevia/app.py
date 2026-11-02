"""Starts Cinevia: sign-in first, then the main window for that user."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from cinevia import db
from cinevia.auth import Accounts, User
from cinevia.data import catalog

from .ui import login as login_module
from .ui.context import Session
from .ui.login import LoginScreen
from .ui.theme import stylesheet, theme

ASSETS = Path(__file__).resolve().parent.parent / "assets"


class CineviaApp:
    def __init__(self, argv: list[str]) -> None:
        self.qt = QApplication(argv)
        self.qt.setApplicationName("Cinevia")
        self.qt.setWindowIcon(QIcon(str(ASSETS / "cinevia-logo.png")))
        for font_file in ("Oswald.ttf", "DMSans.ttf"):
            QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / font_file))
        login_module.LOGO = ASSETS / "cinevia-logo.png"

        self.conn = db.connect()
        db.migrate(self.conn)
        self.accounts = Accounts(self.conn)
        self.main = None

        theme.changed.connect(self._restyle)
        self._restyle()
        self.login = LoginScreen(self.accounts)
        self.login.authenticated.connect(self.open_main)
        # Fetch the catalog while the user is signing in, so Home opens quickly.
        threading.Thread(target=catalog.warm_up, daemon=True).start()

    def _restyle(self) -> None:
        self.qt.setStyleSheet(stylesheet())

    def open_main(self, user: User) -> None:
        from .ui.main_window import MainWindow

        session = Session(self.conn, user)
        theme.set(session.theme())
        self.main = MainWindow(session)
        self.main.logged_out.connect(self.log_out)
        self.main.show()
        self.login.hide()

    def log_out(self) -> None:
        if self.main:
            self.main.close()
            self.main.deleteLater()
            self.main = None
        theme.set("dark")
        self.login.reset()
        self.login.show()

    def run(self) -> int:
        self.login.show()
        return self.qt.exec()


def main() -> int:
    return CineviaApp(sys.argv).run()
