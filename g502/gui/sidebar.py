"""A profile row in the sidebar."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .common import led_css, profile_subtitle, profile_title


class ProfileRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        self.dots = [QLabel(), QLabel()]
        dots = QVBoxLayout()
        dots.setSpacing(4)
        for d in self.dots:
            d.setFixedSize(12, 12)
            dots.addWidget(d)
        lay.addLayout(dots)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600;")
        self.sub = QLabel(objectName="Muted")
        text.addWidget(self.title)
        text.addWidget(self.sub)
        lay.addLayout(text, 1)
        self.badges = QLabel(objectName="Muted")
        self.badges.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.badges)
        self.fade = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fade)

    def show_profile(self, p: dict, active: bool, edited: bool) -> None:
        for d, zone in zip(self.dots, ("logo_led", "dpi_leds")):
            d.setStyleSheet(f"{led_css(p['lighting'][zone])} border-radius: 6px;"
                            " border: 1px solid rgba(127,127,127,0.6);")
        self.title.setText(profile_title(p) + ("  •" if edited else ""))
        on = p.get("enabled", True)
        bits = [profile_subtitle(p)] if profile_subtitle(p) else []
        if not on:
            bits.append("Deactivated")
        self.sub.setText(" · ".join(bits) or " ")
        self.badges.setText("In use" if active else "")
        self.fade.setOpacity(1.0 if on else 0.4)
        self.setToolTip("" if on else "Deactivated: the profile button skips this profile")
        self.title.setToolTip("Unsaved changes" if edited else "")

