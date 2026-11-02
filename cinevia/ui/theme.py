"""Colors and the Qt stylesheet. The dark palette and sizes follow the Movie Finder
reference design; the light palette is its counterpart. One accent: signal red.
Radius system: 4-5px chips and buttons, 6-7px cards, inputs and posters,
9-10px panels; floating icon buttons on artwork are circles."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

DARK = {
    "bg": "#0b0d12",
    "sidebar": "#0d0f14",
    "line": "#20232b",
    "line2": "#292c34",
    "surface": "#151820",
    "surface_line": "#272a33",
    "panel": "#12151c",
    "panel_line": "#242731",
    "field": "#0e1016",
    "field_line": "#2d3039",
    "card": "#1c202b",
    "hover": "#161920",
    "text": "#f6f7f9",
    "text2": "#c4c6ca",
    "text3": "#b2b5bc",
    "muted": "#848994",
    "muted2": "#777c85",
    "placeholder": "#6e737c",
    "chip_bg": "rgba(255,255,255,18)",
    "chip_line": "rgba(255,255,255,33)",
    "chip_text": "#d5d7da",
    "ghost_bg": "rgba(21,24,33,210)",
    "ghost_line": "#464952",
    "ghost_hover": "#252832",
    "red": "#e50914",
    "red_hover": "#ff1722",
    "red_text": "#ff5961",
    "red_line": "#3c252b",
    "star": "#ffd55c",
    "dots": "#60636a",
}

LIGHT = {
    "bg": "#f3f4f7",
    "sidebar": "#fbfbfc",
    "line": "#e2e4e9",
    "line2": "#d9dce3",
    "surface": "#ffffff",
    "surface_line": "#dcdfe5",
    "panel": "#fbfbfc",
    "panel_line": "#e1e3e9",
    "field": "#f3f4f7",
    "field_line": "#d6d9e0",
    "card": "#dfe2e8",
    "hover": "#eceef2",
    "text": "#12141a",
    "text2": "#3d424c",
    "text3": "#4a4f5a",
    "muted": "#5d6270",
    "muted2": "#656a75",
    "placeholder": "#7a7f89",
    "chip_bg": "rgba(16,19,28,13)",
    "chip_line": "rgba(16,19,28,33)",
    "chip_text": "#3a3f49",
    "ghost_bg": "rgba(255,255,255,210)",
    "ghost_line": "#c9ccd4",
    "ghost_hover": "#ffffff",
    "red": "#e50914",
    "red_hover": "#c80711",
    "red_text": "#c80711",
    "red_line": "#f1c9cc",
    "star": "#9a6400",
    "dots": "#b9bcc4",
}

DISPLAY = "Oswald"
SANS = "DM Sans"


class _Theme(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.name = "dark"

    @property
    def p(self) -> dict[str, str]:
        return DARK if self.name == "dark" else LIGHT

    def color(self, key: str, alpha: int | None = None) -> QColor:
        value = self.p[key]
        if value.startswith("rgba("):
            r, g, b, a = (int(x) for x in value[5:-1].split(","))
            c = QColor(r, g, b, a)
        else:
            c = QColor(value)
        if alpha is not None:
            c.setAlpha(alpha)
        return c

    def set(self, name: str) -> None:
        if name != self.name:
            self.name = name
            self.changed.emit()


theme = _Theme()


def stylesheet() -> str:
    p = theme.p
    return f"""
* {{ font-family: "{SANS}"; color: {p['text']}; outline: 0; }}
QWidget#root, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {p['bg']}; }}
QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['line2']}; padding: 4px 6px; }}

QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['line2']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; width: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

/* Sidebar */
QFrame#sidebar {{ background: {p['sidebar']}; border-right: 1px solid {p['line']}; }}
QPushButton#navItem {{
    text-align: left; padding: 11px 13px; border: 0; border-radius: 8px;
    color: {p['muted']}; font-size: 13px; background: transparent;
}}
QPushButton#navItem:hover {{ color: {p['text']}; background: {p['hover']}; }}
QPushButton#navItem[active="true"] {{
    color: {p['text']};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(229,9,20,46), stop:1 rgba(229,9,20,0));
}}
QFrame#upgrade {{
    border: 1px solid {p['line2']}; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p['surface']}, stop:1 {p['sidebar']});
}}
QLabel#upgradeTitle {{ color: {p['red']}; font-family: "{DISPLAY}"; font-size: 17px; font-weight: 700; }}
QLabel#upgradeText {{ color: {p['muted']}; font-size: 11px; }}
QPushButton#upgradeLink {{
    text-align: left; border: 0; background: transparent; padding: 0;
    color: {p['text']}; font-size: 10px; letter-spacing: 1px;
}}
QPushButton#upgradeLink:hover {{ color: {p['red_text']}; }}

/* Top bar */
QFrame#topbar {{ background: {p['bg']}; border-bottom: 1px solid {p['line']}; }}
QFrame#search {{ background: {p['surface']}; border: 1px solid {p['surface_line']}; border-radius: 7px; }}
QFrame#search[focus="true"] {{ border-color: {p['red']}; }}
QFrame#search QLineEdit {{ background: transparent; border: 0; font-size: 12px; padding: 0; }}
QLabel#kbd {{ color: {p['muted']}; border: 1px solid {p['field_line']}; border-radius: 4px; padding: 2px 6px; font-size: 9px; }}
QPushButton#quickFilter {{
    border: 1px solid {p['line2']}; border-radius: 7px; padding: 0 11px; height: 38px;
    color: {p['muted']}; font-size: 11px; background: transparent;
}}
QPushButton#quickFilter:hover {{ color: {p['text']}; border-color: {p['ghost_line']}; }}
QPushButton#iconButton {{ border: 0; border-radius: 7px; background: transparent; }}
QPushButton#iconButton:hover {{ background: {p['hover']}; }}
QLabel#profileName {{ font-size: 11px; font-weight: 700; }}
QLabel#profileSub {{ color: {p['muted2']}; font-size: 9px; }}

/* Buttons */
QPushButton#primary {{
    background: {p['red']}; color: #ffffff; border: 0; border-radius: 5px;
    padding: 0 17px; min-height: 40px; font-size: 11px; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {p['red_hover']}; }}
QPushButton#primary:disabled {{ background: rgba(229,9,20,150); color: rgba(255,255,255,190); }}
QPushButton#ghost {{
    background: {p['ghost_bg']}; color: {p['text']}; border: 1px solid {p['ghost_line']}; border-radius: 5px;
    padding: 0 17px; min-height: 38px; font-size: 11px; font-weight: 600;
}}
QPushButton#ghost:hover {{ background: {p['ghost_hover']}; }}
QPushButton#ghost[favorited="true"] {{ color: {p['red_text']}; }}
QPushButton#textButton {{ border: 0; background: transparent; color: {p['muted']}; font-size: 10px; padding: 4px; }}
QPushButton#textButton:hover {{ color: {p['text']}; }}
QPushButton#linkButton {{ border: 0; background: transparent; color: {p['red']}; font-size: 10px; font-weight: 600; padding: 0; }}
QPushButton#clearButton {{
    border: 1px solid {p['red_line']}; border-radius: 5px; padding: 9px 12px;
    color: {p['red_text']}; font-size: 10px; background: transparent;
}}
QPushButton#clearButton:hover {{ background: rgba(229,9,20,20); }}

/* Text */
QLabel#eyebrow {{ color: {p['text3']}; font-size: 10px; font-weight: 600; letter-spacing: 1.6px; }}
QLabel#pageTitle {{ font-family: "{DISPLAY}"; font-size: 38px; font-weight: 600; }}
QLabel#pageSub, QLabel#muted {{ color: {p['muted']}; font-size: 12px; }}
QLabel#sectionTitle {{ font-family: "{DISPLAY}"; font-size: 18px; font-weight: 600; }}
QLabel#sectionMeta {{ color: {p['muted2']}; font-size: 9px; }}
QLabel#body {{ color: {p['text3']}; font-size: 12px; }}
QLabel#meta {{ color: {p['text2']}; font-size: 11px; }}
QLabel#score {{ color: {p['star']}; font-size: 11px; }}
QLabel#quality {{ color: {p['text2']}; border: 1px solid {p['muted2']}; border-radius: 3px; padding: 1px 5px; font-size: 8px; }}
QLabel#chip {{
    color: {p['chip_text']}; background: {p['chip_bg']}; border: 1px solid {p['chip_line']};
    border-radius: 4px; padding: 4px 9px; font-size: 9px;
}}
QLabel#fieldLabel {{ color: {p['muted']}; font-size: 9px; letter-spacing: 0.8px; }}
QLabel#error {{ color: {p['red_text']}; font-size: 11px; }}
QLabel#emptyTitle {{ font-family: "{DISPLAY}"; font-size: 20px; font-weight: 500; }}
QLabel#emptyText {{ color: {p['muted2']}; font-size: 11px; }}
QLabel#emptyIcon {{ background: {p['surface']}; border: 1px solid {p['line2']}; border-radius: 31px; }}
QLabel#facts {{ color: {p['muted']}; font-size: 10px; }}

/* Discover */
QFrame#filterPanel {{ background: {p['panel']}; border: 1px solid {p['panel_line']}; border-radius: 9px; }}
QFrame#field {{ background: {p['field']}; border: 1px solid {p['field_line']}; border-radius: 5px; }}
QFrame#field[focus="true"] {{ border-color: {p['red']}; }}
QFrame#field QLineEdit {{ background: transparent; border: 0; font-size: 11px; padding: 0; }}
QComboBox {{
    background: {p['field']}; border: 1px solid {p['field_line']}; border-radius: 5px;
    padding: 0 10px; min-height: 37px; font-size: 10px; color: {p['text2']};
}}
QComboBox:focus {{ border-color: {p['red']}; }}
QComboBox::drop-down {{ border: 0; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {p['surface']}; border: 1px solid {p['line2']}; selection-background-color: {p['red']};
    selection-color: #ffffff; padding: 4px; outline: 0;
}}

/* History */
QFrame#historyItem {{ border-bottom: 1px solid {p['line']}; }}
QLabel#historyIcon {{ background: {p['surface']}; border: 1px solid {p['line2']}; border-radius: 7px; }}
QLabel#historyQuery {{ font-size: 12px; font-weight: 500; }}
QLabel#historyTime {{ color: {p['muted2']}; font-size: 9px; }}
QPushButton#historyAction {{ border: 0; background: transparent; color: {p['muted']}; font-size: 10px; padding: 4px 6px; }}
QPushButton#historyAction:hover {{ color: {p['red_text']}; }}

/* Login */
QWidget#authForm QLabel#authTitle {{ font-family: "{DISPLAY}"; font-size: 39px; font-weight: 600; }}
QFrame#authInput {{ background: {p['surface']}; border: 1px solid {p['field_line']}; border-radius: 6px; }}
QFrame#authInput[focus="true"] {{ border-color: {p['red']}; }}
QFrame#authInput QLineEdit {{ background: transparent; border: 0; font-size: 12px; padding: 0; }}
QLabel#authSwitch {{ color: {p['muted']}; font-size: 10px; }}
QLabel#authQuote {{ font-family: "{DISPLAY}"; font-size: 27px; font-weight: 500; color: #ffffff; }}
QLabel#authQuoteSub {{ color: #969aa3; font-size: 11px; }}
QLabel#authWordmark {{ font-family: "{DISPLAY}"; font-size: 22px; font-weight: 700; color: #ffffff; letter-spacing: 3px; }}
QLabel#logoWord {{ font-family: "{DISPLAY}"; font-size: 14px; font-weight: 600; letter-spacing: 1.7px; }}
QLabel#heroIndex {{ font-family: "{DISPLAY}"; font-size: 25px; font-weight: 500; }}
QLabel#heroIndexTotal {{ color: {p['muted2']}; font-size: 10px; }}
QLabel#detailsTitle {{ font-family: "{DISPLAY}"; font-size: 50px; font-weight: 600; }}
QLabel#playerTitle {{ font-family: "{DISPLAY}"; font-size: 20px; font-weight: 600; color: #ffffff; }}
QLabel#playerKicker {{ color: #9a9ea6; font-size: 10px; letter-spacing: 1.4px; }}
QLabel#playerNote {{ color: #b2b5bc; font-size: 12px; }}
QLabel#time {{ color: #b2b5bc; font-size: 10px; }}

QLineEdit {{ selection-background-color: {p['red']}; selection-color: #ffffff; }}
QMenu {{ background: {p['surface']}; border: 1px solid {p['line2']}; padding: 4px; }}
QMenu::item {{ padding: 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p['hover']}; }}
"""
