"""Light and dark themes (follows the Windows setting)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

DARK = {
    "bg": "#15171c", "surface": "#1e2128", "surface2": "#262a32", "hover": "#2d323b",
    "border": "#343a45", "text": "#e7e9ed", "muted": "#9aa2af", "accent": "#FDDC01",
    "accent_hover": "#FFE84D", "on_accent": "#111111", "accent_strong": "#FDDC01", "danger": "#ef5f5f",
    "warn_bg": "#3a3120", "warn_text": "#f2c46d", "ok": "#4cc38a", "selection": "#3d3714",
    "chevron": "chevron-dark.svg",
}
LIGHT = {
    "bg": "#f3f4f7", "surface": "#ffffff", "surface2": "#f1f2f5", "hover": "#e8eaef",
    "border": "#d8dbe2", "text": "#1c2027", "muted": "#5f6876", "accent": "#FDDC01",
    "accent_hover": "#F2CF00", "on_accent": "#111111", "accent_strong": "#8F7200", "danger": "#d43c3c",
    "warn_bg": "#fff4dc", "warn_text": "#7a5410", "ok": "#1f8a57", "selection": "#FFF3B0",
    "chevron": "chevron-light.svg",
}

QSS = """
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: {text}; }}
QMainWindow, QDialog {{ background: {bg}; }}
QWidget#Central {{ background: {bg}; }}
QFrame#Sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
QFrame#Header, QFrame#Footer {{ background: {surface}; }}
QFrame#Header {{ border-bottom: 1px solid {border}; }}
QFrame#Footer {{ border-top: 1px solid {border}; }}
QFrame#Rule {{ background: {border}; border: none; }}
QFrame#Card {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
QFrame#Banner {{ background: {warn_bg}; border-radius: 8px; }}
QLabel#Banner {{ color: {warn_text}; }}
QLabel#Title {{ font-size: 15pt; font-weight: 600; }}
QLabel#Section {{ font-size: 11.5pt; font-weight: 600; }}
QLabel#Muted, QLabel#Hint {{ color: {muted}; }}
QLabel#Pill {{ background: {surface2}; border: 1px solid {border}; border-radius: 11px; padding: 2px 10px; }}
QLabel#PillOk {{ background: transparent; border: 1px solid {ok}; color: {ok}; border-radius: 11px;
                 padding: 2px 10px; }}
QLabel#PillWarn {{ background: {warn_bg}; color: {warn_text}; border-radius: 11px; padding: 2px 10px; }}

QPushButton, QToolButton {{ background: {surface2}; border: 1px solid {border}; border-radius: 7px;
    padding: 6px 14px; }}
QPushButton:hover, QToolButton:hover {{ background: {hover}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {muted}; }}
QPushButton#Primary {{ background: {accent}; border-color: {accent}; color: {on_accent}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {accent_hover}; }}
QPushButton#Primary:disabled {{ background: {surface2}; border-color: {border}; color: {muted}; }}
QPushButton#Danger {{ background: {danger}; border-color: {danger}; color: #ffffff; font-weight: 600; }}
QPushButton#Danger:disabled {{ background: {surface2}; border-color: {border}; color: {muted}; }}
QToolButton::menu-indicator {{ image: none; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{ background: {surface2};
    border: 1px solid {border}; border-radius: 6px; padding: 4px 8px; selection-background-color: {accent}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {accent_strong}; }}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {border};
    selection-background-color: {selection}; selection-color: {text}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px; border: none; }}
QAbstractSpinBox {{ padding-right: 8px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
QRadioButton::indicator {{ border: 2px solid {muted}; border-radius: 8px; background: transparent;
    width: 12px; height: 12px; }}
QRadioButton::indicator:checked {{ border: 2px solid {accent_strong}; background: qradialgradient(cx:0.5,
    cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 {accent_strong}, stop:0.55 {accent_strong}, stop:0.6 transparent); }}
QRadioButton::indicator:disabled {{ border-color: {border}; }}

QListWidget#Profiles {{ background: transparent; border: none; outline: none; }}
QListWidget#Profiles::item {{ border-radius: 8px; margin: 2px 8px; }}
QListWidget#Profiles::item:selected {{ background: {selection}; }}
QListWidget#Profiles::item:hover:!selected {{ background: {hover}; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 7px 18px; margin: 6px 6px 6px 0; color: {muted}; font-weight: 600; }}
QTabBar::tab:selected {{ background: {accent}; color: {on_accent}; }}
QTabBar::tab:hover:!selected {{ background: {surface2}; border-color: {border}; color: {text}; }}

QTableWidget {{ background: {surface}; border: 1px solid {border}; border-radius: 10px;
    gridline-color: transparent; selection-background-color: {selection}; selection-color: {text}; }}
QTableWidget::item {{ padding: 6px 10px; border-bottom: 1px solid {surface2}; }}
QHeaderView::section {{ background: {surface}; color: {muted}; border: none;
    border-bottom: 1px solid {border}; padding: 8px 10px; font-weight: 600; }}
QTableCornerButton::section {{ background: {surface}; border: none; }}

QCheckBox#Switch::indicator {{ width: 34px; height: 18px; border-radius: 9px; background: {border}; }}
QCheckBox#Switch::indicator:checked {{ background: {accent}; }}
QSlider::groove:horizontal {{ height: 4px; background: {border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {accent}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QStatusBar {{ background: {surface}; color: {muted}; }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 4px; }}
QMenu {{ background: {surface}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {selection}; }}
"""


def is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False


def apply_theme(app, dark: bool | None = None) -> dict:
    tokens = DARK if (is_dark() if dark is None else dark) else LIGHT
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "surface2"), (QPalette.AlternateBase, "surface"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "surface2"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.HighlightedText, "on_accent"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted")):
        pal.setColor(role, QColor(tokens[key]))
    app.setPalette(pal)
    assets = Path(__file__).with_name("assets")
    app.setStyleSheet(QSS.format(**dict(tokens, chevron=(assets / tokens["chevron"]).as_posix())))
    return tokens
