"""Library tab: the user's saved profiles."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import labels, library
from .common import led_css
from .widgets import card, clear_layout, hint


def _dot(zone: dict) -> QLabel:
    d = QLabel()
    d.setFixedSize(14, 14)
    d.setStyleSheet(f"{led_css(zone)} border-radius: 7px; border: 1px solid rgba(127,127,127,0.6);")
    return d


def summary(settings: dict) -> str:
    dpi = settings["dpi"]
    levels = dpi["levels"]
    bits = []
    if isinstance(levels, list):
        bits.append(f"{levels[dpi['default_index']]} DPI")
    rate = settings.get("report_rate_hz")
    if isinstance(rate, int):
        bits.append(f"{rate} Hz")
    bits.append("G-Shift on" if settings.get("gshift_layer") else "single layer")
    bits.append(labels.describe_led(settings["lighting"]["logo_led"]))
    return " · ".join(bits)


class LibraryPage(QWidget):
    load_requested = Signal(object, str)     # settings dict, title
    save_requested = Signal()
    delete_requested = Signal(object)        # Path
    open_folder_requested = Signal()

    def __init__(self, directories: list[Path], parent=None):
        super().__init__(parent)
        self.directories = directories     # first one is where new entries are saved
        self.slot = "this profile"
        self.saved_buttons: list[QPushButton] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 16)
        lay.setSpacing(14)

        top = QHBoxLayout()
        self.intro = hint("")
        top.addWidget(self.intro, 1)
        self.save_btn = QPushButton("Save to library…")
        self.save_btn.clicked.connect(self.save_requested)
        top.addWidget(self.save_btn)
        lay.addLayout(top)

        head = QHBoxLayout()
        head.addWidget(QLabel("My saved profiles", objectName="Section"))
        head.addStretch(1)
        folder = QPushButton("Open library folder")
        folder.clicked.connect(self.open_folder_requested)
        head.addWidget(folder)
        lay.addLayout(head)
        self.saved = QVBoxLayout()
        self.saved.setSpacing(10)
        lay.addLayout(self.saved)
        lay.addStretch(1)
        self.reload()

    def _card(self, entry: library.Entry) -> QWidget:
        frame, c = card()
        c.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(6)
        for zone in ("logo_led", "dpi_leds"):
            row.addWidget(_dot(entry.profile["lighting"][zone]))
        title = QLabel(entry.title, objectName="Section")
        row.addSpacing(4)
        row.addWidget(title)
        row.addStretch(1)
        c.addLayout(row)
        if entry.description:
            c.addWidget(hint(entry.description))
        meta = hint(summary(entry.profile) + (f" · saved {entry.created[:16].replace('T', ' ')}"
                                                if entry.created else ""))
        c.addWidget(meta)
        c.addStretch(1)
        buttons = QHBoxLayout()
        load = QPushButton()
        load.clicked.connect(lambda: self.load_requested.emit(entry.profile, entry.title))
        self.saved_buttons.append(load)
        buttons.addWidget(load)
        buttons.addStretch(1)
        if entry.path and entry.path.parent == self.directories[0]:
            delete = QPushButton("Delete")
            delete.clicked.connect(lambda: self.delete_requested.emit(entry.path))
            buttons.addWidget(delete)
        else:
            buttons.addWidget(hint("from an older version's folder"))
        c.addLayout(buttons)
        return frame

    def reload(self) -> None:
        clear_layout(self.saved)
        self.saved_buttons = []
        entries, problems = library.list_entries(self.directories)
        if not entries:
            self.saved.addWidget(hint("Nothing saved yet. Set up a profile the way you like it, then press "
                                      "Save to library. Saved profiles can be loaded into any slot."))
        for e in entries:
            self.saved.addWidget(self._card(e))
        for p in problems:
            self.saved.addWidget(hint(f"Couldn't read {p}"))
        self.set_slot(self.slot)

    def set_slot(self, slot: str) -> None:
        self.slot = slot
        self.intro.setText(f"Load a saved profile into {slot}. It replaces that profile's buttons, "
                           "DPI, lighting and name in the editor; nothing is written until you press Write "
                           "to mouse.")
        self.save_btn.setText(f"Save {slot} to library…")
        for b in self.saved_buttons:
            b.setText(f"Load into {slot}")
