"""Editors for one binding, one LED zone and the DPI table."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import labels, model

# -- small pieces ----------------------------------------------------------------


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(objectName="Card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 18)
    lay.setSpacing(12)
    if title:
        lay.addWidget(QLabel(title, objectName="Section"))
    return frame, lay


def clear_layout(layout) -> None:
    """Remove and delete every widget in `layout` (hidden at once, deleted later)."""
    while layout.count():
        w = layout.takeAt(0).widget()
        if w is not None:
            w.hide()
            w.deleteLater()


def hint(text: str) -> QLabel:
    lab = QLabel(text, objectName="Hint")
    lab.setWordWrap(True)
    return lab


class ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self._color = color.upper()
        text = "#000000" if QColor(self._color).lightness() > 150 else "#FFFFFF"
        self.setText(self._color)
        self.setStyleSheet(f"QPushButton {{ background: {self._color}; color: {text}; border-radius: 7px;"
                           f" border: 1px solid rgba(127,127,127,0.5); padding: 6px 14px; font-weight: 600; }}")

    def color(self) -> str:
        return self._color

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self._color), self, "Choose a colour")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit(self._color)


# Windows virtual-key codes -> HID key names (model.KEYS values).
_VK = {0x0D: "enter", 0x1B: "escape", 0x08: "backspace", 0x09: "tab", 0x20: "space", 0x14: "caps_lock",
       0x2C: "print_screen", 0x91: "scroll_lock", 0x13: "pause", 0x2D: "insert", 0x24: "home",
       0x21: "page_up", 0x2E: "delete", 0x23: "end", 0x22: "page_down", 0x27: "right", 0x25: "left",
       0x28: "down", 0x26: "up", 0x90: "num_lock", 0x5D: "menu", 0xBA: "semicolon", 0xBB: "equal",
       0xBC: "comma", 0xBD: "minus", 0xBE: "period", 0xBF: "slash", 0xC0: "grave", 0xDB: "left_bracket",
       0xDC: "backslash", 0xDD: "right_bracket", 0xDE: "apostrophe", 0xE2: "non_us_backslash",
       0x6A: "kp_multiply", 0x6B: "kp_plus", 0x6D: "kp_minus", 0x6E: "kp_period", 0x6F: "kp_divide"}
_VK.update({0x41 + i: chr(ord("a") + i) for i in range(26)})
_VK.update({0x30 + i: str(i) for i in range(10)})
_VK.update({0x60 + i: f"kp_{i}" for i in range(10)})
_VK.update({0x70 + i: f"f{i + 1}" for i in range(24)})
_MODIFIER_VKS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}


def key_from_event(event) -> str | None:
    vk = event.nativeVirtualKey()
    if vk in _MODIFIER_VKS:
        return None
    name = _VK.get(vk)
    if name is None:
        k = event.key()
        if Qt.Key_A <= k <= Qt.Key_Z:
            name = chr(ord("a") + k - Qt.Key_A)
        elif Qt.Key_0 <= k <= Qt.Key_9:
            name = chr(ord("0") + k - Qt.Key_0)
        elif Qt.Key_F1 <= k <= Qt.Key_F24:
            name = f"f{k - Qt.Key_F1 + 1}"
    return name if name in model.KEY_CODES else None


# -- binding editor ----------------------------------------------------------------

CATEGORIES = [
    ("mouse", "Mouse click"),
    ("key", "Keyboard key"),
    ("consumer", "Media key"),
    ("special", "DPI, profile or scroll"),
    ("gshift", "G-Shift (hold for the second layer)"),
    ("disabled", "Do nothing"),
    ("keep", "Keep as it is"),
]


class BindingDialog(QDialog):
    """Pick what one button does."""

    def __init__(self, button: str, layer: str, binding: dict, gshift_allowed: bool, parent=None):
        super().__init__(parent)
        self.button, self.layer, self.original = button, layer, copy.deepcopy(binding)
        where = "G-Shift layer" if layer == "gshift" else "main layer"
        self.setWindowTitle(f"{labels.BUTTON_LABELS.get(button, button)} ({where})")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(QLabel(labels.BUTTON_LABELS.get(button, button), objectName="Title"))
        lay.addWidget(hint(f"Currently: {labels.describe_binding(binding)}  ·  {where}"))

        self.category = QComboBox()
        t = binding.get("type")
        current = ("keep" if t in ("macro", "raw") or (t == "mouse" and len(binding["buttons"]) != 1) else
                   "gshift" if t == "special" and binding["action"] == "gshift" else t)
        for key, text in CATEGORIES:
            if key == "keep" and current != "keep":
                continue
            if key == "gshift" and not (gshift_allowed and layer == "main") and current != "gshift":
                continue
            self.category.addItem(text, key)
        lay.addWidget(self.category)

        self.pages = QStackedWidget()
        self._page_index = {}
        self._build_pages(binding)
        lay.addWidget(self.pages)

        self.preview = QLabel(objectName="Section")
        self.warning = QLabel(objectName="Banner")
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("padding: 8px 10px;")
        lay.addWidget(self.preview)
        lay.addWidget(self.warning)
        lay.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.button(QDialogButtonBox.Ok).setText("Set")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        self.category.currentIndexChanged.connect(self._update)
        self.category.setCurrentIndex(max(0, self.category.findData(current)))
        self._update()

    def _build_pages(self, b: dict) -> None:
        def add(key, widget):
            self._page_index[key] = self.pages.addWidget(widget)

        # mouse
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.mouse = QComboBox()
        for n in range(1, 17):
            self.mouse.addItem(labels.MOUSE_BUTTONS.get(n, f"Mouse button {n}"), n)
        if b.get("type") == "mouse" and len(b["buttons"]) == 1:
            self.mouse.setCurrentIndex(b["buttons"][0] - 1)
        self.mouse.currentIndexChanged.connect(self._update)
        lay.addWidget(self.mouse)
        add("mouse", w)

        # key
        w = QWidget()
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 0, 0, 0)
        self.mods = {}
        mods = b.get("modifiers", []) if b.get("type") == "key" else []
        for i, m in enumerate(model.MODIFIERS):
            cb = QCheckBox(labels.MODIFIER_LABELS[m])
            cb.setChecked(m in mods)
            cb.toggled.connect(self._update)
            self.mods[m] = cb
            grid.addWidget(cb, i // 4, i % 4)
        self.key = QComboBox()
        self.key.setEditable(True)
        self.key.setInsertPolicy(QComboBox.NoInsert)
        for name in labels.key_names_sorted():
            self.key.addItem(labels.key_label(name), name)
        comp = self.key.completer()
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        if b.get("type") == "key" and b["key"] in model.KEY_CODES:
            self.key.setCurrentIndex(self.key.findData(b["key"]))
        self.key.currentIndexChanged.connect(self._update)
        self.record = QPushButton("Record a key…")
        self.record.setCheckable(True)
        self.record.toggled.connect(self._recording)
        grid.addWidget(self.key, 2, 0, 1, 3)
        grid.addWidget(self.record, 2, 3)
        add("key", w)

        # consumer
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.consumer = QComboBox()
        for usage, text in labels.CONSUMER_LABELS.items():
            self.consumer.addItem(text, usage)
        if b.get("type") == "consumer":
            if self.consumer.findData(b["usage"]) < 0:
                self.consumer.addItem(labels.describe_binding(b), b["usage"])
            self.consumer.setCurrentIndex(self.consumer.findData(b["usage"]))
        self.consumer.currentIndexChanged.connect(self._update)
        lay.addWidget(self.consumer)
        add("consumer", w)

        # special
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.special = QComboBox()
        for action, text in labels.SPECIAL_LABELS.items():
            if action in ("gshift", "battery_level"):
                continue
            self.special.addItem(text, action)
        if b.get("type") == "special" and b["action"] not in ("gshift",):
            if self.special.findData(b["action"]) < 0:
                self.special.addItem(labels.describe_binding(b), b["action"])
            self.special.setCurrentIndex(self.special.findData(b["action"]))
        self.special.currentIndexChanged.connect(self._update)
        lay.addWidget(self.special)
        add("special", w)

        for key, text in (("gshift", "While held, every other button uses its G-Shift layer action."),
                          ("disabled", "The button does nothing."),
                          ("keep", "This button has an action the editor can't change "
                                   "(for example a macro). It is kept exactly as it is.")):
            add(key, hint(text))

    def _recording(self, on: bool) -> None:
        self.record.setText("Press a key… (Esc cancels)" if on else "Record a key…")
        if on:
            self.grabKeyboard()
        else:
            self.releaseKeyboard()

    def keyPressEvent(self, event) -> None:
        if not self.record.isChecked():
            return super().keyPressEvent(event)
        if event.key() == Qt.Key_Escape and not event.modifiers():
            self.record.setChecked(False)
            return
        name = key_from_event(event)
        if name is None:
            return  # a modifier on its own: wait for the real key
        mods = event.modifiers()
        for m, flag in (("lctrl", Qt.ControlModifier), ("lshift", Qt.ShiftModifier),
                        ("lalt", Qt.AltModifier), ("lgui", Qt.MetaModifier)):
            self.mods[m].setChecked(bool(mods & flag))
        for m in ("rctrl", "rshift", "ralt", "rgui"):
            self.mods[m].setChecked(False)
        self.key.setCurrentIndex(self.key.findData(name))
        self.record.setChecked(False)

    def result_binding(self) -> dict:
        cat = self.category.currentData()
        if cat == "mouse":
            return {"type": "mouse", "buttons": [self.mouse.currentData()]}
        if cat == "key":
            out = {"type": "key", "key": self.key.currentData()}
            mods = [m for m in model.MODIFIERS if self.mods[m].isChecked()]
            if mods:
                out["modifiers"] = mods
            return out
        if cat == "consumer":
            return {"type": "consumer", "usage": self.consumer.currentData()}
        if cat == "special":
            out = {"type": "special", "action": self.special.currentData()}
            if self.original.get("type") == "special" and self.original.get("action") == out["action"] \
                    and "arg" in self.original:
                out["arg"] = self.original["arg"]
            return out
        if cat == "gshift":
            return {"type": "special", "action": "gshift"}
        if cat == "disabled":
            return {"type": "disabled"}
        return copy.deepcopy(self.original)

    def _update(self) -> None:
        cat = self.category.currentData()
        self.pages.setCurrentIndex(self._page_index[cat])
        result = self.result_binding()
        self.preview.setText(f"→  {labels.describe_binding(result)}")
        warn = ""
        if self.button == "left" and self.layer == "main" and result != {"type": "mouse", "buttons": [1]}:
            warn = ("This is your left-click button. Unless another button is set to Left click, "
                    "you won't be able to click with this profile.")
        elif cat == "gshift":
            warn = "Hold this button for the G-Shift layer. Its own normal action is replaced."
        self.warning.setText(warn)
        self.warning.setVisible(bool(warn))


# -- lighting ------------------------------------------------------------------------

EFFECTS = [("off", "Off"), ("fixed", "Solid colour"), ("breathing", "Breathing"), ("cycle", "Colour cycle")]


class LedEditor(QFrame):
    changed = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent, objectName="Card")
        self._zone: dict = {"effect": "off"}
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(QLabel(title, objectName="Section"))
        top.addStretch(1)
        self.swatch = QLabel()
        self.swatch.setFixedSize(22, 22)
        top.addWidget(self.swatch)
        lay.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.effect = QComboBox()
        for key, text in EFFECTS:
            self.effect.addItem(text, key)
        self.color = ColorButton()
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.1, 65.0)
        self.speed.setSingleStep(0.5)
        self.speed.setDecimals(1)
        self.speed.setSuffix(" s")
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(1, 100)
        self.bright_label = QLabel()
        self.bright_label.setMinimumWidth(40)
        self.rows = {}
        for r, (name, text, widget) in enumerate((("effect", "Effect", self.effect),
                                                    ("color", "Colour", self.color),
                                                    ("speed", "Cycle time", self.speed),
                                                    ("bright", "Brightness", self.bright))):
            label = QLabel(text, objectName="Muted")
            grid.addWidget(label, r, 0)
            if name == "bright":
                h = QHBoxLayout()
                h.addWidget(self.bright, 1)
                h.addWidget(self.bright_label)
                holder = QWidget()
                holder.setLayout(h)
                h.setContentsMargins(0, 0, 0, 0)
                grid.addWidget(holder, r, 1)
                self.rows[name] = (label, holder)
            else:
                grid.addWidget(widget, r, 1)
                self.rows[name] = (label, widget)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.note = hint("")
        lay.addWidget(self.note)

        self.effect.currentIndexChanged.connect(self._edited)
        self.color.changed.connect(self._edited)
        self.speed.valueChanged.connect(self._edited)
        self.bright.valueChanged.connect(self._edited)

    def set_zone(self, zone: dict) -> None:
        self._loading = True
        self._zone = copy.deepcopy(zone)
        e = zone.get("effect")
        if e == "raw":
            if self.effect.findData("raw") < 0:
                self.effect.addItem("Keep as it is (unrecognised)", "raw")
        elif self.effect.findData("raw") >= 0:
            self.effect.removeItem(self.effect.findData("raw"))
        self.effect.setCurrentIndex(self.effect.findData(e))
        self.color.set_color(zone.get("color", "#FFFFFF"))
        self.speed.setValue(zone.get("period_ms", 8000) / 1000)
        self.bright.setValue(max(1, zone.get("brightness", 100)))
        self._loading = False
        self._refresh()

    def zone(self) -> dict:
        e = self.effect.currentData()
        if e == "raw":
            return copy.deepcopy(self._zone)
        if e == "off":
            return {"effect": "off"}
        if e == "fixed":
            return {"effect": "fixed", "color": self.color.color()}
        period = int(round(self.speed.value() * 1000))
        if e == "cycle":
            return {"effect": "cycle", "period_ms": period, "brightness": self.bright.value()}
        return {"effect": "breathing", "color": self.color.color(), "period_ms": period,
                "waveform": self._zone.get("waveform", 0) if self._zone.get("effect") == "breathing" else 0,
                "brightness": self.bright.value()}

    def _edited(self) -> None:
        if self._loading:
            return
        self._refresh()
        self.changed.emit()

    def _refresh(self) -> None:
        e = self.effect.currentData()
        show = {"color": e in ("fixed", "breathing"), "speed": e in ("cycle", "breathing"),
                "bright": e in ("cycle", "breathing")}
        for name, visible in show.items():
            for w in self.rows[name]:
                w.setVisible(visible)
        self.bright_label.setText(f"{self.bright.value()}%")
        if e in ("fixed", "breathing"):
            css = f"background: {self.color.color()};"
        elif e == "cycle":
            css = ("background: qconicalgradient(cx:0.5, cy:0.5, angle:0, stop:0 #ff4d4d, stop:0.33 #4dff88,"
                   " stop:0.66 #4d7bff, stop:1 #ff4d4d);")
        else:
            css = "background: transparent;"
        self.swatch.setStyleSheet(f"{css} border-radius: 11px; border: 1px solid rgba(127,127,127,0.6);")
        self.note.setText("Breathing hasn't been tried on this mouse yet." if e == "breathing" else
                          "This zone's data isn't recognised; it's kept exactly as it is." if e == "raw" else "")
        self.note.setVisible(bool(self.note.text()))


# -- DPI ------------------------------------------------------------------------------

DPI_MIN, DPI_MAX, DPI_STEP = 100, 25600, 50


class DpiEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, objectName="Card")
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(10)
        lay.addWidget(QLabel("DPI levels", objectName="Section"))
        lay.addWidget(hint("The DPI buttons step through the ticked levels in order. The default level is "
                           "used when the profile is selected; the sniper level while the DPI-shift button "
                           "is held."))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        for c, text in enumerate(("", "DPI", "Default", "Sniper")):
            grid.addWidget(QLabel(text, objectName="Muted"), 0, c)
        self.default_group, self.shift_group = QButtonGroup(self), QButtonGroup(self)
        self.rows = []
        for i in range(5):
            on = QCheckBox(f"Level {i + 1}")
            spin = QSpinBox()
            spin.setRange(DPI_MIN, DPI_MAX)
            spin.setSingleStep(DPI_STEP)
            spin.setSuffix(" DPI")
            spin.setToolTip("Type a value, or use the mouse wheel / arrow keys (steps of 50)")
            spin.setMinimumWidth(130)
            d, s = QRadioButton(), QRadioButton()
            self.default_group.addButton(d, i)
            self.shift_group.addButton(s, i)
            for col, w in enumerate((on, spin, d, s)):
                grid.addWidget(w, i + 1, col, alignment=Qt.AlignLeft if col < 2 else Qt.AlignCenter)
            on.toggled.connect(self._edited)
            spin.valueChanged.connect(self._edited)
            d.toggled.connect(self._edited)
            s.toggled.connect(self._edited)
            self.rows.append((on, spin, d, s))
        grid.setColumnStretch(4, 1)
        lay.addLayout(grid)
        self.raw_note = hint("")
        lay.addWidget(self.raw_note)

    def set_dpi(self, dpi: dict) -> None:
        self._loading = True
        levels = dpi["levels"]
        raw = not isinstance(levels, list)
        self.raw_note.setText("This profile's DPI data isn't recognised, so it can't be edited here."
                              if raw else "")
        self.raw_note.setVisible(raw)
        for i, (on, spin, d, s) in enumerate(self.rows):
            for w in (on, spin, d, s):
                w.setEnabled(not raw)
            has = not raw and i < len(levels)
            on.setChecked(has)
            if has:
                spin.setRange(min(DPI_MIN, levels[i]), max(DPI_MAX, levels[i]))
                spin.setValue(levels[i])
            elif not raw:
                spin.setValue(levels[-1] if levels else 800)   # a sensible start if it gets ticked
        if not raw:
            self.rows[min(dpi["default_index"], 4)][2].setChecked(True)
            self.rows[min(dpi["shift_index"], 4)][3].setChecked(True)
        self._loading = False
        self._refresh()

    def dpi(self, old: dict) -> dict:
        if not isinstance(old["levels"], list):
            return copy.deepcopy(old)
        active = [i for i, r in enumerate(self.rows) if r[0].isChecked()]
        levels = [self.rows[i][1].value() for i in active]

        def index(group, fallback):
            i = group.checkedId()
            return active.index(i) if i in active else fallback
        return {"levels": levels, "default_index": index(self.default_group, 0),
                "shift_index": index(self.shift_group, 0)}

    def _edited(self) -> None:
        if self._loading:
            return
        # keep at least one level, and keep the default/sniper picks on ticked levels
        if not any(r[0].isChecked() for r in self.rows):
            self._loading = True
            self.rows[0][0].setChecked(True)
            self._loading = False
        self._refresh()
        self.changed.emit()

    def _refresh(self) -> None:
        self._loading = True
        first = next(i for i, r in enumerate(self.rows) if r[0].isChecked()) if any(
            r[0].isChecked() for r in self.rows) else 0
        for group, col in ((self.default_group, 2), (self.shift_group, 3)):
            if not self.rows[max(group.checkedId(), 0)][0].isChecked():
                self.rows[first][col].setChecked(True)
        for on, spin, d, s in self.rows:
            if on.isEnabled() or spin.isEnabled():
                for w in (spin, d, s):
                    w.setEnabled(on.isChecked())
        self._loading = False
