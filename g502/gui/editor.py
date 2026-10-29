"""The editing tabs (Buttons, DPI, Lighting, Profile) and their change handlers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import labels, library, model
from .common import APP_NAME, profile_title
from .dialogs import banner
from .widgets import BindingDialog, DpiEditor, LedEditor, card, clear_layout, hint


class EditorMixin:
    """Part of MainWindow; uses its state (self.edited, self.source, ...)."""

    def _scroll(self, w: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(w)
        w.setObjectName("Central")
        return area

    def _buttons_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 16)
        lay.setSpacing(12)
        top = QHBoxLayout()
        self.gshift_switch = QCheckBox("G-Shift second layer", objectName="Switch")
        self.gshift_switch.toggled.connect(self._gshift_toggled)
        top.addWidget(self.gshift_switch)
        top.addStretch(1)
        lay.addLayout(top)
        self.gshift_hint = hint("")
        lay.addWidget(self.gshift_hint)
        self.button_warn = banner("")
        lay.addWidget(self.button_warn)
        self.table = QTableWidget(len(model.BUTTON_NAMES), 3)
        self.table.setHorizontalHeaderLabels(["Button", "Action", "G-Shift action (hold G-Shift)"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.setCursor(Qt.PointingHandCursor)
        self.table.cellClicked.connect(self._edit_binding)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.table)
        bottom = QHBoxLayout()
        bottom.addWidget(hint("Click an action to change it. Changed actions are highlighted; hover to see the "
                              "old one."), 1)
        tester = QPushButton("Test buttons…")
        tester.clicked.connect(self.open_tester)
        bottom.addWidget(tester)
        lay.addLayout(bottom)
        lay.addStretch(1)
        return page

    def _dpi_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 16)
        lay.setSpacing(14)
        self.dpi = DpiEditor()
        self.dpi.changed.connect(self._dpi_edited)
        lay.addWidget(self.dpi)
        frame, c = card("Polling rate")
        self.rate = QComboBox()
        for hz in sorted(model.REPORT_RATES, reverse=True):
            self.rate.addItem(f"{hz} Hz", hz)
        self.rate.currentIndexChanged.connect(self._rate_edited)
        row = QHBoxLayout()
        row.addWidget(self.rate)
        row.addStretch(1)
        c.addLayout(row)
        c.addWidget(hint("How often the mouse reports to the PC. 1000 Hz is the usual choice."))
        lay.addWidget(frame)
        lay.addStretch(1)
        return page

    def _lighting_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 16)
        lay.setSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.leds = {}
        for zone, title in labels.ZONE_LABELS.items():
            ed = LedEditor(title)
            ed.changed.connect(lambda z=zone: self._led_edited(z))
            self.leds[zone] = ed
            row.addWidget(ed, 1)
        lay.addLayout(row)
        lay.addWidget(hint("Changes show on the mouse as soon as they're written, even on the active profile."))
        lay.addWidget(banner("If Windows Dynamic Lighting is on for this mouse (Settings → Personalization → "
                             "Dynamic Lighting), Windows paints its own colours over these a moment after the "
                             "mouse loads a profile. Turn it off for the mouse to see the profile's lighting."))
        lay.addStretch(1)
        return page

    def _profile_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 16)
        lay.setSpacing(14)
        frame, c = card("Profile")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.name = QLineEdit()
        self.name.setMaxLength(24)
        self.name.setPlaceholderText("Up to 24 characters")
        self.name.textEdited.connect(self._name_edited)
        self.enabled = QCheckBox("Active", objectName="Switch")
        self.enabled.toggled.connect(self._enabled_edited)
        self.enabled.toggled.connect(lambda on: self.enabled.setText("Active" if on else "Deactivated"))
        grid.addWidget(QLabel("Name", objectName="Muted"), 0, 0)
        grid.addWidget(self.name, 0, 1)
        grid.addWidget(QLabel("Status", objectName="Muted"), 1, 0)
        grid.addWidget(self.enabled, 1, 1)
        grid.setColumnStretch(1, 1)
        c.addLayout(grid)
        self.enabled_hint = hint("Deactivated profiles are skipped by the profile button. This is stored in the "
                                 "mouse's profile list, which is written separately and shown in the preview. "
                                 "At least one profile must stay active.")
        c.addWidget(self.enabled_hint)
        lay.addWidget(frame)

        tools, t = card("Copy, swap and reset")
        t.addWidget(hint("These change the editor only. Check the result, then Write to mouse as usual. Each "
                         "profile keeps its own Active/Deactivated status."))
        row = QHBoxLayout()
        for text, slot in (("Copy to another profile…", self.copy_profile),
                           ("Swap with another profile…", self.swap_profile),
                           ("Reset to factory settings…", self.reset_to_factory)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        t.addLayout(row)
        lay.addWidget(tools)
        self.profile_warnings = QVBoxLayout()
        lay.addLayout(self.profile_warnings)
        lay.addStretch(1)
        return page

    def _show_profile(self) -> None:
        p = self.prof
        self.library_page.set_slot(profile_title(p))
        self._loading = True
        self.gshift_switch.setChecked(bool(p.get("gshift_layer")))
        self.dpi.set_dpi(p["dpi"])
        rate = p["report_rate_hz"]
        self.rate.setEnabled(isinstance(rate, int))
        if isinstance(rate, int):
            self.rate.setCurrentIndex(self.rate.findData(rate))
        for zone, ed in self.leds.items():
            ed.set_zone(p["lighting"][zone])
        name = p.get("name")
        self.name.setEnabled(not isinstance(name, dict))
        self.name.setText("" if name is None or isinstance(name, dict) else name)
        self.enabled.setChecked(bool(p.get("enabled", True)))
        clear_layout(self.profile_warnings)
        for w in self.warnings:
            if w.startswith(f"profile in sector {p['sector']}:"):
                self.profile_warnings.addWidget(banner(w.split(":", 1)[1].strip().capitalize()))
        self._loading = False
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        p = self.prof
        layer = bool(p.get("gshift_layer"))
        self.table.setColumnHidden(2, not layer)
        gshift = {"type": "special", "action": "gshift"}
        for r, name in enumerate(model.BUTTON_NAMES):
            items = [labels.BUTTON_LABELS.get(name, name), labels.describe_binding(p["buttons"][name]),
                     labels.describe_binding(p["gshift_buttons"][name]) if "gshift_buttons" in p else ""]
            for c, text in enumerate(items):
                it = QTableWidgetItem(text)
                if c == 0:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                elif c == 1 and self._left_locked(name):
                    it.setText("Left click  🔒")
                    it.setForeground(QColor(self.tokens["muted"]))
                    it.setToolTip("Locked, so a profile can never leave you without a left click. "
                                  "The G-Shift layer's left button can still be changed.")
                elif c == 2 and p["buttons"][name] == gshift:
                    it.setText("Not used: this button holds G-Shift")
                    it.setForeground(QColor(self.tokens["muted"]))
                elif self._binding_changed(c, name):
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                    it.setForeground(QColor(self.tokens["accent_strong"]))
                    it.setToolTip(f"Was: {labels.describe_binding(self._orig_binding(c, name))}")
                self.table.setItem(r, c, it)
        self.table.setFixedHeight(self.table.horizontalHeader().height()
                                  + 38 * len(model.BUTTON_NAMES) + 2 * self.table.frameWidth())
        on = model.uses_gshift(p["buttons"])
        self.gshift_hint.setText(
            "Hold the G-Shift button and every other button does its G-Shift action instead."
            if layer else "Single-layer mode: every button does one thing. Turn this on to give a button "
                          "the G-Shift role and set a second action for the others.")
        warn = ""
        if layer and not on:
            warn = "No button is set to G-Shift, so the second layer can't be reached. Set one, or turn G-Shift off."
        elif not any(b == {"type": "mouse", "buttons": [1]} for b in p["buttons"].values()):
            warn = "No button is set to Left click in this profile."
        self.button_warn.findChild(QLabel).setText(warn)
        self.button_warn.setVisible(bool(warn))

    def _orig_binding(self, col: int, name: str) -> dict:
        table = "buttons" if col == 1 else "gshift_buttons"
        return self.orig.get(table, {}).get(name, {})

    def _binding_changed(self, col: int, name: str) -> bool:
        table = "buttons" if col == 1 else "gshift_buttons"
        return self.prof.get(table, {}).get(name) != self._orig_binding(col, name)

    def _left_locked(self, name: str) -> bool:
        # Locked only while it is Left click, so a mouse set up some other way can still be fixed.
        return name == "left" and self.prof["buttons"]["left"] == library.LEFT_CLICK

    def _edit_binding(self, row: int, col: int) -> None:
        if col == 0:
            col = 1
        name = model.BUTTON_NAMES[row]
        if col == 1 and self._left_locked(name):
            self.statusBar().showMessage("Left click is locked on the main layer so you can't lose it. "
                                         "You can change its G-Shift action.", 6000)
            return
        table = "buttons" if col == 1 else "gshift_buttons"
        if table not in self.prof or (col == 2 and model.uses_gshift({name: self.prof["buttons"][name]})):
            return
        dlg = BindingDialog(name, "main" if col == 1 else "gshift", self.prof[table][name],
                            gshift_allowed=bool(self.prof.get("gshift_layer")), parent=self)
        if dlg.exec():
            self.prof[table][name] = dlg.result_binding()
            self._refresh_buttons()
            self._refresh_all()

    def _gshift_toggled(self, on: bool) -> None:
        if self._loading:
            return
        p = self.prof
        p["gshift_layer"] = on
        holders = [n for n, b in p["buttons"].items() if b == {"type": "special", "action": "gshift"}]
        if on and not holders:
            was = self.orig["buttons"]["sniper"]
            p["buttons"]["sniper"] = {"type": "special", "action": "gshift"}
            self.statusBar().showMessage(f"Sniper button now holds G-Shift (was {labels.describe_binding(was)}). "
                                         "Click it to choose a different button.", 8000)
        elif not on:
            for n in holders:
                before = self.orig["buttons"][n]
                p["buttons"][n] = (before if before != {"type": "special", "action": "gshift"} else
                                   {"type": "special", "action": "dpi_shift"} if n == "sniper" else
                                   {"type": "disabled"})
            if holders:
                self.statusBar().showMessage(
                    "G-Shift off: " + ", ".join(f"{labels.BUTTON_LABELS[n]} is now "
                                                f"{labels.describe_binding(p['buttons'][n])}" for n in holders)
                    + ". The G-Shift actions stay stored on the mouse for next time.", 10000)
        self._refresh_buttons()
        self._refresh_all()

    def _dpi_edited(self) -> None:
        if self._loading:
            return
        self.prof["dpi"] = self.dpi.dpi(self.prof["dpi"])
        self._refresh_all()

    def _rate_edited(self) -> None:
        if self._loading or not self.rate.isEnabled():
            return
        self.prof["report_rate_hz"] = self.rate.currentData()
        self._refresh_all()

    def _led_edited(self, zone: str) -> None:
        if self._loading:
            return
        self.prof["lighting"][zone] = self.leds[zone].zone()
        self._refresh_all()

    def _name_edited(self, text: str) -> None:
        if self._loading:
            return
        self.prof["name"] = text
        self._refresh_all()

    def _enabled_edited(self, on: bool) -> None:
        if self._loading:
            return
        refuse = None
        if not on and sum(bool(p.get("enabled", True)) for p in self.edited) <= 1:
            refuse = "At least one profile has to stay active."
        elif not on and self.connected and self.prof["sector"] == self.active:
            refuse = (f"Profile {self.active} is in use on the mouse, so it can't be deactivated. "
                      "Switch the mouse to another profile first.")
        if refuse:
            QMessageBox.information(self, APP_NAME, refuse)
            self._loading = True
            self.enabled.setChecked(True)
            self._loading = False
            return
        self.prof["enabled"] = on
        self._refresh_all()
