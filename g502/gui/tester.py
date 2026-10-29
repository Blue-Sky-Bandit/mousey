"""Button tester: shows which of the profile's buttons produced what the PC receives."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHeaderView,
    QLabel,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .. import labels, model
from .widgets import hint, key_from_event

_QT_MOUSE = {Qt.LeftButton: 1, Qt.RightButton: 2, Qt.MiddleButton: 3, Qt.BackButton: 4, Qt.ForwardButton: 5}
_QT_MEDIA = {Qt.Key_VolumeUp: "0x00E9", Qt.Key_VolumeDown: "0x00EA", Qt.Key_VolumeMute: "0x00E2",
             Qt.Key_MediaTogglePlayPause: "0x00CD", Qt.Key_MediaPlay: "0x00CD", Qt.Key_MediaNext: "0x00B5",
             Qt.Key_MediaPrevious: "0x00B6", Qt.Key_MediaStop: "0x00B7"}
# The PC can't tell left from right modifier keys reliably, so compare them as one.
_SIDELESS = {"rctrl": "lctrl", "rshift": "lshift", "ralt": "lalt", "rgui": "lgui"}
# Actions that happen inside the mouse and send nothing the PC can see.
INVISIBLE = {"dpi_up", "dpi_down", "dpi_cycle", "dpi_default", "dpi_shift", "profile_next", "profile_prev",
             "profile_cycle", "gshift", "battery_level"}


def same_action(binding: dict, seen: dict) -> bool:
    """Whether a binding would produce the input `seen` (in binding form)."""
    if binding.get("type") != seen.get("type"):
        return False
    if binding["type"] == "key":
        def mods(d):
            return {_SIDELESS.get(m, m) for m in d.get("modifiers", [])}
        return binding["key"] == seen["key"] and mods(binding) == mods(seen)
    return binding == seen


def rows_for(profile: dict) -> list[tuple[str, str, dict]]:
    """(button label, layer, binding) for every button the tester lists."""
    out = [(labels.BUTTON_LABELS.get(n, n), "", profile["buttons"][n]) for n in model.BUTTON_NAMES]
    if model.uses_gshift(profile["buttons"]):
        out += [(labels.BUTTON_LABELS.get(n, n), "G-Shift", profile["gshift_buttons"][n])
                for n in model.BUTTON_NAMES
                if profile["buttons"][n] != {"type": "special", "action": "gshift"}]
    return out


class Pad(QFrame):
    """The area to press buttons over. Reports everything it receives as bindings."""

    def __init__(self, on_input, parent=None):
        super().__init__(parent, objectName="Card")
        self.on_input = on_input
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(150)
        self.setCursor(Qt.CrossCursor)
        lay = QVBoxLayout(self)
        text = QLabel("Point here and press the mouse's buttons", objectName="Section")
        text.setAlignment(Qt.AlignCenter)
        lay.addWidget(text)

    def event(self, e) -> bool:
        if e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(e)       # keep Tab for the tester instead of moving focus
            return True
        return super().event(e)

    def mousePressEvent(self, e) -> None:
        self.setFocus()
        n = _QT_MOUSE.get(e.button())
        if n:
            self.on_input({"type": "mouse", "buttons": [n]})

    def wheelEvent(self, e) -> None:
        x, y = e.angleDelta().x(), e.angleDelta().y()
        if x:
            self.on_input({"type": "special", "action": "wheel_left" if x > 0 else "wheel_right"})
        elif y:
            self.on_input({"type": "wheel", "label": "Scroll up" if y > 0 else "Scroll down"})

    def keyPressEvent(self, e) -> None:
        if e.isAutoRepeat():
            return
        if e.key() in _QT_MEDIA:
            self.on_input({"type": "consumer", "usage": _QT_MEDIA[e.key()]})
            return
        name = key_from_event(e)
        if name is None:
            return
        mods = [m for m, flag in (("lctrl", Qt.ControlModifier), ("lshift", Qt.ShiftModifier),
                                  ("lalt", Qt.AltModifier), ("lgui", Qt.MetaModifier)) if e.modifiers() & flag]
        seen = {"type": "key", "key": name}
        if mods:
            seen["modifiers"] = mods
        self.on_input(seen)


class ButtonTesterDialog(QDialog):
    def __init__(self, profile: dict, title: str, tokens: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Button tester")
        self.resize(720, 760)
        self.tokens = tokens
        self.rows = rows_for(profile)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Button tester", objectName="Title"))
        lay.addWidget(hint(f"Testing {title}. Each button's action is ticked when the PC receives it. DPI, "
                           "profile and G-Shift buttons work inside the mouse and send nothing to the PC: watch "
                           "the mouse's lights (or the In use label) for those. Media keys may be taken by "
                           "Windows before they reach this window."))
        self.pad = Pad(self._received)
        lay.addWidget(self.pad)

        self.table = QTableWidget(len(self.rows), 3)
        self.table.setHorizontalHeaderLabels(["Button", "Action", "Seen"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        for r, (button, layer, binding) in enumerate(self.rows):
            name = f"{button} (G-Shift)" if layer else button
            action = labels.describe_binding(binding)
            invisible = binding.get("type") == "special" and binding.get("action") in INVISIBLE
            for c, text in enumerate((name, action, "inside the mouse" if invisible else "")):
                item = QTableWidgetItem(text)
                if invisible:
                    item.setForeground(QColor(tokens["muted"]))
                self.table.setItem(r, c, item)
        self.table.resizeRowsToContents()
        lay.addWidget(self.table, 1)

        lay.addWidget(QLabel("Received", objectName="Muted"))
        self.log = QListWidget()
        self.log.setMaximumHeight(110)
        self.log.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.log)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Close).setFocusPolicy(Qt.NoFocus)
        lay.addWidget(buttons)
        QTimer.singleShot(0, self.pad.setFocus)

    def matches(self, seen: dict) -> list[int]:
        return [r for r, (_, _, b) in enumerate(self.rows) if same_action(b, seen)]

    def _received(self, seen: dict) -> None:
        text = seen.get("label") or labels.describe_binding(seen)
        hits = self.matches(seen)
        who = ", ".join(self.table.item(r, 0).text() for r in hits)
        self.log.insertItem(0, f"{text}  →  {who}" if who else f"{text}  (not one of this profile's actions)")
        while self.log.count() > 30:
            self.log.takeItem(self.log.count() - 1)
        for r in hits:
            item = self.table.item(r, 2)
            item.setText("✓")
            item.setForeground(QColor(self.tokens["ok"]))
            for c in range(3):
                self.table.item(r, c).setBackground(QColor(self.tokens["selection"]))
            QTimer.singleShot(700, lambda r=r: [self.table.item(r, c).setBackground(QColor(0, 0, 0, 0))
                                                for c in range(3)])
