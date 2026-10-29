"""Main window: pick a profile, edit it, then one "Write to mouse" button."""

from __future__ import annotations

import copy
import json
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QGraphicsOpacityEffect,
                               QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QStatusBar, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

from .. import __version__, apply, backup, labels, library, model, session
from ..device import DeviceNotFound
from . import style
from .dialogs import ConfirmWriteDialog, RestorePickDialog, banner
from .library_page import LibraryPage
from .tester import ButtonTesterDialog
from .widgets import BindingDialog, DpiEditor, LedEditor, card, hint

APP_NAME = "Mousey"
STUDIO = "FLYHT Studios"
APP_ID = "FLYHTStudios.Mousey"
DEFAULT_NAME = "PROFILE_NAME_DEFAULT"
ASSETS = Path(__file__).with_name("assets")
POLL_MS = 1000


def app_icon() -> QIcon:
    return QIcon(str(ASSETS / "mousey.ico"))


# -- background work ---------------------------------------------------------------

class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)
    log = Signal(str)


class Task(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # reported to the UI, never retried
            e.trace = traceback.format_exc()
            self.signals.failed.emit(e)
        else:
            self.signals.done.emit(result)


# -- helpers --------------------------------------------------------------------------

def latest_backup(directory: Path) -> Path | None:
    files = sorted(directory.glob("g502-backup-*.json"))
    return files[-1] if files else None


def profile_title(p: dict) -> str:
    return f"Profile {p['sector']}"


def profile_subtitle(p: dict) -> str:
    name = p.get("name")
    return "" if name in (None, DEFAULT_NAME) or isinstance(name, dict) else name


def led_css(zone: dict) -> str:
    e = zone.get("effect")
    if e in ("fixed", "breathing"):
        return f"background: {zone['color']};"
    if e == "cycle":
        return ("background: qconicalgradient(cx:0.5, cy:0.5, angle:0, stop:0 #ff4d4d, stop:0.33 #4dff88,"
                " stop:0.66 #4d7bff, stop:1 #ff4d4d);")
    return "background: transparent;"


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


# -- the window --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, backup_dir: Path | None = None, tokens: dict | None = None, library_dir: Path | None = None):
        super().__init__()
        self.backup_dir = backup_dir or backup.default_backup_dir()
        self.library_dir = library_dir or library.default_library_dir()
        self.tokens = tokens or style.LIGHT
        self.pool = QThreadPool.globalInstance()
        self.tasks: set[Task] = set()
        self.source: backup.Backup | None = None
        self.connected = False
        self.unplugged_from_session = False
        self.original: list[dict] = []
        self.edited: list[dict] = []
        self.device: dict = {}
        self.warnings: list[str] = []
        self.sel = -1
        self._loading = False
        self.active = None
        self.mode = None
        self.plugged = False          # mouse answered the last check
        self.follow_mouse = True      # re-read automatically when it is plugged back in
        self._polling = False
        self.settings = QSettings(STUDIO, APP_NAME)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(1200, 820)
        self._build()
        self._set_loaded(False)
        self.poll_timer = QTimer(self, interval=POLL_MS, timeout=self._poll)

    # ---- layout --------------------------------------------------------------------
    def _build(self) -> None:
        central = QWidget(objectName="Central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(objectName="Header")
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 12, 16, 12)
        h.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSETS / "mousey-256.png")).scaled(
            34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        h.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(QLabel(APP_NAME, objectName="Title"))
        by = QLabel(f"by {STUDIO}", objectName="Muted")
        by.setStyleSheet("font-size: 8.5pt;")
        names.addWidget(by)
        h.addLayout(names)
        h.addSpacing(8)
        self.status_pill = QLabel(objectName="Pill")
        h.addWidget(self.status_pill)
        h.addStretch(1)
        self.read_btn = QPushButton("Read from mouse")
        self.read_btn.clicked.connect(self.read_from_mouse)
        self.backup_btn = QPushButton("Back up now")
        self.backup_btn.clicked.connect(self.backup_now)
        self.restore_btn = QPushButton("Restore backup…")
        self.restore_btn.clicked.connect(self.restore_backup)
        more = QToolButton(text="More ▾")
        more.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(more)
        menu.addAction("Button tester…", self.open_tester)
        menu.addAction("Name your mouse…", self.rename_mouse)
        menu.addSeparator()
        menu.addAction("Open a backup (view only)…", self.open_backup)
        menu.addSeparator()
        self.export_act = menu.addAction("Export profiles to JSON…", self.export_json)
        self.import_act = menu.addAction("Import profiles from JSON…", self.import_json)
        menu.addSeparator()
        menu.addAction("Open backups folder", self.open_backups_folder)
        menu.addAction("About", self.about)
        more.setMenu(menu)
        for w in (self.read_btn, self.backup_btn, self.restore_btn, more):
            h.addWidget(w)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(0)
        side = QFrame(objectName="Sidebar")
        side.setFixedWidth(250)
        s = QVBoxLayout(side)
        s.setContentsMargins(0, 16, 0, 12)
        lab = QLabel("PROFILES", objectName="Muted")
        lab.setStyleSheet("font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; padding-left: 20px;")
        s.addWidget(lab)
        self.list = QListWidget(objectName="Profiles")
        self.list.currentRowChanged.connect(self._select)
        s.addWidget(self.list, 1)
        self.side_hint = hint("")
        self.side_hint.setContentsMargins(20, 0, 16, 0)
        s.addWidget(self.side_hint)
        body.addWidget(side)

        main = QVBoxLayout()
        main.setContentsMargins(24, 14, 24, 0)
        self.mode_holder = QVBoxLayout()
        main.addLayout(self.mode_holder)
        self.banner_holder = QVBoxLayout()
        main.addLayout(self.banner_holder)
        rule = QFrame(objectName="Rule")
        rule.setFixedHeight(1)
        main.addWidget(rule)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.addTab(self._scroll(self._buttons_page()), "Buttons")
        self.tabs.addTab(self._scroll(self._dpi_page()), "DPI")
        self.tabs.addTab(self._scroll(self._lighting_page()), "Lighting")
        self.tabs.addTab(self._scroll(self._profile_page()), "Profile")
        self.library_page = LibraryPage(self.library_dir)
        self.library_page.load_requested.connect(self.load_from_library)
        self.library_page.save_requested.connect(self.save_to_library)
        self.library_page.delete_requested.connect(self.delete_from_library)
        self.library_page.open_folder_requested.connect(self.open_library_folder)
        self.tabs.addTab(self._scroll(self.library_page), "Library")
        main.addWidget(self.tabs, 1)
        holder = QWidget()
        holder.setLayout(main)
        body.addWidget(holder, 1)
        root.addLayout(body, 1)

        footer = QFrame(objectName="Footer")
        f = QHBoxLayout(footer)
        f.setContentsMargins(20, 10, 20, 10)
        self.changes_label = QLabel(objectName="Muted")
        f.addWidget(self.changes_label)
        f.addStretch(1)
        self.revert_btn = QPushButton("Undo changes to this profile")
        self.revert_btn.clicked.connect(self.revert_profile)
        self.revert_all_btn = QPushButton("Undo all")
        self.revert_all_btn.clicked.connect(self.revert_all)
        self.write_btn = QPushButton("Write to mouse…", objectName="Primary")
        self.write_btn.clicked.connect(self.write_to_mouse)
        for w in (self.revert_btn, self.revert_all_btn, self.write_btn):
            f.addWidget(w)
        root.addWidget(footer)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(160)
        self.progress.hide()
        sb.addPermanentWidget(self.progress)

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

    # ---- state ----------------------------------------------------------------------
    def _set_loaded(self, loaded: bool) -> None:
        for w in (self.tabs, self.revert_btn, self.revert_all_btn, self.write_btn):
            w.setEnabled(loaded)
        self.export_act.setEnabled(loaded)
        self.import_act.setEnabled(loaded)
        if not loaded:
            self.status_pill.setText("Nothing loaded")

    def _busy(self, text: str | None) -> None:
        busy = text is not None
        self.centralWidget().setEnabled(not busy)
        self.progress.setVisible(busy)
        self.statusBar().showMessage(text or "")

    def run(self, text: str, fn, *args, done, failed=None, log=None, **kwargs) -> None:
        task = Task(fn, *args, **kwargs)
        self.tasks.add(task)

        def finish(handler):
            def inner(value):
                self.tasks.discard(task)
                self._busy(None)
                (handler or self._show_error)(value)
            return inner
        task.signals.done.connect(finish(done))
        task.signals.failed.connect(finish(failed))
        if log:
            task.signals.log.connect(log)
        self._busy(text)
        self.pool.start(task)

    def _show_error(self, e: Exception) -> None:
        if isinstance(e, DeviceNotFound):
            QMessageBox.warning(self, APP_NAME, "No G502 HERO found. Check it's plugged in by cable.")
            return
        if isinstance(e, TimeoutError):
            QMessageBox.warning(self, APP_NAME, "The mouse didn't answer. If you've just plugged it in it may "
                                                "still be starting up; try again in a few seconds.\n\n"
                                                f"({e})")
            return
        box = QMessageBox(QMessageBox.Critical, APP_NAME, str(e) or type(e).__name__, parent=self)
        box.setDetailedText(getattr(e, "trace", ""))
        box.exec()

    def load(self, source: backup.Backup, connected: bool) -> None:
        keep = self.sel
        self.source, self.connected = source, connected
        self.unplugged_from_session = False
        if connected:
            self.plugged = True
            self.follow_mouse = True
            self.poll_timer.start()
        doc = model.build_export(source)
        self.device = doc["device"]
        self.original = doc["profiles"]
        self.edited = copy.deepcopy(self.original)
        self.warnings = doc.get("warnings", [])
        self.active = source.meta.get("current_profile")
        self._show_mode(source.meta.get("onboard_mode") if connected else None)
        self._update_pill()
        self._set_banner(None if connected else
                         "You're looking at a backup file. You can edit and preview, but writing needs the "
                         "mouse: plug it in and press Read from mouse.")
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.edited:
            item = QListWidgetItem()
            row = ProfileRow()
            item.setSizeHint(QSize(200, 58))
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        self.list.blockSignals(False)
        self.list.doItemsLayout()
        self.side_hint.setText("\"In use\" is the profile the mouse is using right now." if connected else "")
        self._set_loaded(True)
        self.sel = -1
        self.list.setCurrentRow(keep if 0 <= keep < len(self.edited) else
                                next((i for i, p in enumerate(self.edited) if p["sector"] == self.active), 0))
        self._refresh_all()

    def mouse_name(self) -> str:
        return self.settings.value("mouse_name", "", str) or "G502 HERO"

    def _update_pill(self) -> None:
        if self.connected:
            self.status_pill.setObjectName("PillOk")
            self.status_pill.setText(f"{self.mouse_name()} connected")
            self.status_pill.setToolTip(f"Firmware {self.device.get('firmware')}")
        elif self.source is not None and self.unplugged_from_session:
            self.status_pill.setObjectName("PillWarn")
            self.status_pill.setText(f"{self.mouse_name()} unplugged")
            self.status_pill.setToolTip("Plug it back in and it will be read again automatically.")
        elif self.source is not None:
            self.status_pill.setObjectName("PillWarn")
            self.status_pill.setText("Viewing a backup, not the mouse")
            self.status_pill.setToolTip(str(self.source.path or ""))
        else:
            self.status_pill.setObjectName("Pill")
            self.status_pill.setText("Nothing loaded")
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

    def _set_banner(self, text: str | None) -> None:
        while self.banner_holder.count():
            self.banner_holder.takeAt(0).widget().deleteLater()
        if text:
            self.banner_holder.addWidget(banner(text))

    def rename_mouse(self) -> None:
        name, ok = QInputDialog.getText(
            self, APP_NAME, "A name for your mouse, shown in this app.\n(The mouse itself can't store a name.)",
            text=self.settings.value("mouse_name", "", str))
        if ok:
            self.settings.setValue("mouse_name", name.strip()[:40])
            self._update_pill()

    # ---- live profile / plug tracking ---------------------------------------------
    def _poll(self) -> None:
        if self.tasks or self._polling:
            return
        self._polling = True
        task = Task(session.poll)
        task.signals.done.connect(self._poll_done)
        task.signals.failed.connect(self._poll_failed)
        self._poll_task = task
        self.pool.start(task)

    def _show_mode(self, mode: str | None) -> None:
        """Banner with a fix-it button whenever the mouse isn't in onboard memory mode."""
        self.mode = mode
        while self.mode_holder.count():
            self.mode_holder.takeAt(0).widget().deleteLater()
        if mode and mode != "onboard":
            self.mode_holder.addWidget(banner(
                f"The mouse is in {mode} mode, so it's ignoring its stored profiles (other software, such as "
                "G Hub, may have switched it). Switch it back to onboard memory to use them.",
                ("Switch to onboard memory", self.switch_to_onboard)))

    def switch_to_onboard(self) -> None:
        question = ("Switch the mouse back to onboard memory mode?\n\nThe mouse will use its stored profiles "
                    "again. This changes the mode only; no profile is written.")
        if QMessageBox.question(self, APP_NAME, question) != QMessageBox.Yes:
            return

        def done(mode: str) -> None:
            self._show_mode(mode)
            if mode == "onboard":
                self.statusBar().showMessage("The mouse is back in onboard memory mode.", 6000)
            else:
                QMessageBox.warning(self, APP_NAME, f"The mouse still reports {mode} mode.")
        self.run("Switching to onboard memory…", session.switch_to_onboard, done=done,
                 failed=self._write_failed)

    def _poll_done(self, status) -> None:
        self._polling = False
        if status is None:
            return
        profile = status.profile
        if self.connected and status.mode != self.mode:
            self._show_mode(status.mode)
        if not self.plugged:
            self.plugged = True
            if self.follow_mouse and self.edited == self.original:
                self.statusBar().showMessage("Mouse plugged in, reading it…")
                QTimer.singleShot(1500, self._auto_read)
            else:
                self._set_banner("The mouse is plugged in. Press Read from mouse to load it "
                                 "(unsaved changes would be discarded).")
            return
        if profile != self.active:
            self.active = profile
            self._refresh_all()
            self.statusBar().showMessage(f"Profile {profile} is now in use on the mouse", 4000)

    def _poll_failed(self, e: Exception) -> None:
        self._polling = False
        if isinstance(e, DeviceNotFound) and self.plugged:
            self.plugged = False
            if self.connected:
                self.connected = False
                self.unplugged_from_session = True
                self._set_banner("The mouse was unplugged. You can keep editing; writing needs it plugged in. "
                                 "It will be read again when you plug it back in.")
            self._update_pill()
            self._refresh_all()
        # timeouts / HID++ errors here are ignored: this is only a status check

    def _auto_read(self) -> None:
        if not self.tasks and self.edited == self.original:
            self.run("Reading the mouse…", session.read_mouse, done=lambda b: self.load(b, True),
                     failed=self._show_error)

    def _select(self, row: int) -> None:
        if row < 0:
            return
        self.sel = row
        self._show_profile()

    @property
    def prof(self) -> dict:
        return self.edited[self.sel]

    @property
    def orig(self) -> dict:
        return self.original[self.sel]

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
        while self.profile_warnings.count():
            self.profile_warnings.takeAt(0).widget().deleteLater()
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

    def _refresh_all(self) -> None:
        total_settings = 0
        changed_profiles = 0
        for i, (o, e) in enumerate(zip(self.original, self.edited)):
            n = len(labels.describe_changes(o, e))
            total_settings += n
            changed_profiles += bool(n) or o != e
            row = self.list.itemWidget(self.list.item(i))
            if row:
                row.show_profile(e, e["sector"] == self.active and self.connected, o != e)
        if changed_profiles:
            self.changes_label.setText(f"{total_settings} unsaved change(s) in {changed_profiles} profile(s)")
        else:
            self.changes_label.setText("No unsaved changes")
        dirty = self.sel >= 0 and self.prof != self.orig
        self.revert_btn.setEnabled(dirty)
        self.revert_all_btn.setEnabled(bool(changed_profiles))
        self.write_btn.setEnabled(bool(changed_profiles))

    # ---- edits ------------------------------------------------------------------------
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

    # ---- tester, copy / swap / factory reset -------------------------------------------
    def open_tester(self) -> None:
        if self.connected and self.active is not None:
            profile = next((p for p in self.original if p["sector"] == self.active), None)
            title = f"Profile {self.active}, as stored on the mouse"
        else:
            profile, title = None, ""
        if profile is None:
            profile = self.prof
            title = f"{profile_title(profile)} as shown in the editor (it may not be what's on the mouse)"
        ButtonTesterDialog(profile, title, self.tokens, self).exec()

    def _pick_profile(self, prompt: str) -> int | None:
        """Index into self.edited of another profile the user picks, or None."""
        others = [i for i in range(len(self.edited)) if i != self.sel]
        names = [profile_title(self.edited[i]) + (f" ({profile_subtitle(self.edited[i])})"
                                                  if profile_subtitle(self.edited[i]) else "") for i in others]
        choice, ok = QInputDialog.getItem(self, APP_NAME, prompt, names, 0, False)
        return others[names.index(choice)] if ok else None

    def _replace(self, index: int, new: dict) -> None:
        self.edited[index] = new

    def copy_profile(self) -> None:
        i = self._pick_profile(f"Copy {profile_title(self.prof)}'s settings to:")
        if i is None:
            return
        try:
            self._replace(i, library.load_into_slot(library.settings_of(self.prof), self.edited[i],
                                                    self.device["button_count"]))
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, f"Can't copy: {e}")
            return
        self._refresh_all()
        self.statusBar().showMessage(f"Copied {profile_title(self.prof)} to {profile_title(self.edited[i])}. "
                                     "Nothing is written until you press Write to mouse.", 8000)

    def swap_profile(self) -> None:
        i = self._pick_profile(f"Swap {profile_title(self.prof)} with:")
        if i is None:
            return
        mine, theirs = library.settings_of(self.prof), library.settings_of(self.edited[i])
        try:
            new_mine = library.load_into_slot(theirs, self.prof, self.device["button_count"])
            new_theirs = library.load_into_slot(mine, self.edited[i], self.device["button_count"])
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, f"Can't swap: {e}")
            return
        self._replace(self.sel, new_mine)
        self._replace(i, new_theirs)
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"Swapped {profile_title(self.prof)} and {profile_title(self.edited[i])}. "
                                     "Nothing is written until you press Write to mouse.", 8000)

    def factory_profiles(self) -> dict[int, dict]:
        """The mouse's factory default profiles (read-only memory), by number."""
        out = {}
        for n in range(1, 6):
            data = self.source.sectors.get(0x100 + n) if self.source else None
            if data:
                out[n] = model.decode_profile(data, self.device["button_count"])
        return out

    def reset_to_factory(self) -> None:
        factory = self.factory_profiles()
        if not factory:
            QMessageBox.information(self, APP_NAME, "The factory profiles weren't found in this data. "
                                                    "Read from the mouse first.")
            return
        names = [f"Factory profile {n}" for n in factory]
        default = min(max(self.prof["sector"] - 1, 0), len(names) - 1)
        choice, ok = QInputDialog.getItem(
            self, APP_NAME, f"Reset {profile_title(self.prof)} to which factory default?", names, default, False)
        if not ok:
            return
        n = list(factory)[names.index(choice)]
        new = dict(factory[n], sector=self.prof["sector"], enabled=self.prof.get("enabled", True))
        try:
            model.encode_profile({k: v for k, v in new.items() if k not in ("sector", "enabled")},
                                 self.device["button_count"])
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, f"Can't reset: {e}")
            return
        self._replace(self.sel, new)
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"{profile_title(new)} set to factory profile {n}, including its G-Shift "
                                     "layer and name. Nothing is written until you press Write to mouse.", 10000)

    # ---- library ----------------------------------------------------------------------
    def load_from_library(self, settings: dict, title: str) -> None:
        try:
            new = library.load_into_slot(settings, self.prof, self.device["button_count"])
        except (ValueError, KeyError, TypeError) as e:
            QMessageBox.warning(self, APP_NAME, f"\"{title}\" can't be loaded into this profile:\n\n{e}")
            return
        self.edited[self.sel] = new
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"Loaded \"{title}\" into {profile_title(new)}. Check it over, then "
                                     "press Write to mouse. Undo changes to this profile puts it back.", 10000)

    def save_to_library(self) -> None:
        p = self.prof
        default = profile_subtitle(p) or profile_title(p)
        title, ok = QInputDialog.getText(self, APP_NAME, "Name for this saved profile:", text=default)
        if not ok or not title.strip():
            return
        try:
            path = library.save_entry(self.library_dir, title.strip(), p)
        except (OSError, KeyError) as e:
            self._show_error(e)
            return
        self.library_page.reload()
        self.statusBar().showMessage(f"Saved \"{title.strip()}\" to the library ({path.name})", 6000)

    def delete_from_library(self, path: Path) -> None:
        if QMessageBox.question(self, APP_NAME, f"Delete the saved profile {path.name} from the library?\n"
                                                "This doesn't change the mouse.") != QMessageBox.Yes:
            return
        path.unlink(missing_ok=True)
        self.library_page.reload()

    def open_library_folder(self) -> None:
        self.library_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.library_dir)  # noqa: S606 - Windows only, opens Explorer

    def revert_profile(self) -> None:
        self.edited[self.sel] = copy.deepcopy(self.orig)
        self._show_profile()
        self._refresh_all()

    def revert_all(self) -> None:
        if QMessageBox.question(self, APP_NAME, "Undo every unsaved change?") != QMessageBox.Yes:
            return
        self.edited = copy.deepcopy(self.original)
        self._show_profile()
        self._refresh_all()

    def _discard_ok(self) -> bool:
        if self.edited == self.original:
            return True
        return QMessageBox.question(self, APP_NAME, "You have unsaved changes. Discard them?") == QMessageBox.Yes

    # ---- reading ----------------------------------------------------------------------
    def read_from_mouse(self) -> None:
        if not self._discard_ok():
            return
        self.run("Reading the mouse…", session.read_mouse, done=lambda b: self.load(b, True),
                 failed=self._read_failed)

    def _read_failed(self, e: Exception) -> None:
        self.poll_timer.start()       # notice when the mouse turns up
        if self.source is None:
            path = latest_backup(self.backup_dir)
            if path:
                self.load(backup.load_backup(path), False)
        self._show_error(e)

    def open_backup(self) -> None:
        if not self._discard_ok():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open a backup", str(self.backup_dir), "Backups (*.json)")
        if path:
            try:
                self.load(backup.load_backup(Path(path)), False)
                self.follow_mouse = False
            except (ValueError, KeyError, OSError) as e:
                self._show_error(e)

    def backup_now(self) -> None:
        def work():
            b = session.read_mouse()
            return b, backup.save_backup(b, self.backup_dir)
        self.run("Backing up the mouse…", work,
                 done=lambda r: QMessageBox.information(self, APP_NAME, f"Backup saved:\n{r[1]}"))

    def open_backups_folder(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.backup_dir)  # noqa: S606 - Windows only, opens Explorer

    # ---- writing ----------------------------------------------------------------------
    def write_to_mouse(self) -> None:
        if not self.connected:
            self._preview_and_write(self.source, preview_only=(
                "Preview only: the mouse isn't connected, so this compares with the data last loaded. "
                "Plug it in and read it to write."))
            return
        self.run("Reading the mouse for the preview…", session.read_mouse,
                 done=lambda current: self._preview_and_write(current, preview_only=None))

    def _preview_and_write(self, current: backup.Backup, preview_only: str | None) -> None:
        in_use = current.meta.get("current_profile")
        if not preview_only and any(p["sector"] == in_use and not p.get("enabled", True) for p in self.edited):
            QMessageBox.warning(self, APP_NAME, f"Profile {in_use} is in use on the mouse and is set to "
                                                "Deactivated. Switch the mouse to another profile, or set it "
                                                "back to Active, then write again.")
            return
        try:
            plan = session.plan_profiles(self.edited, self.original, current, self.device)
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, f"These settings can't be written yet:\n\n{e}")
            return
        notes = []
        if not preview_only and any(current.sectors.get(s) != self.source.sectors.get(s)
                                    for s in current.user_sectors()):
            notes.append("The mouse changed since it was read (for example by other software). The list below "
                         "compares with what's on it now.")
        running = backup.ghub_running()
        blocked = (f"G Hub is running ({', '.join(running)}). It can overwrite the mouse's profiles, so "
                   "writing is blocked. Quit G Hub first.") if running and not preview_only else None
        if plan.empty:
            QMessageBox.information(self, APP_NAME, "Nothing to write: the mouse already has these settings.")
            return
        dlg = ConfirmWriteDialog("Write to mouse", plan, self.device["button_count"], preview_only=preview_only,
                                 blocked=blocked, notes=notes, parent=self)
        if dlg.exec():
            self._execute(plan)

    def _execute(self, plan: session.WritePlan) -> None:
        log_lines: list[str] = []

        def work():
            return session.execute(plan, self.backup_dir, log=lambda s: (log_lines.append(s),))
        self.run("Writing to the mouse… don't unplug it", work, done=self._written, failed=self._write_failed)

    def _written(self, result: session.WriteResult) -> None:
        self.load(result.after, True)
        parts = ", ".join(session.sector_label(s) for s in result.written)
        QMessageBox.information(self, APP_NAME, f"Written and checked: {parts}.\n\n"
                                                f"Backup taken just before writing:\n{result.safety_backup}")

    def _write_failed(self, e: Exception) -> None:
        if isinstance(e, session.WriteFailed):
            done = ", ".join(session.sector_label(s) for s in e.written) or "none"
            msg = (f"Writing stopped: {e}\n\nParts written and checked before it stopped: {done}.\n"
                   "Nothing further was written.")
            if e.safety_backup:
                msg += f"\n\nBackup taken just before writing:\n{e.safety_backup}\nUse Restore backup to put it back."
            QMessageBox.critical(self, APP_NAME, msg)
        elif isinstance(e, session.MouseChanged):
            QMessageBox.warning(self, APP_NAME, str(e).capitalize())
        else:
            self._show_error(e)

    def restore_backup(self) -> None:
        if not self._discard_ok():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Restore from backup", str(self.backup_dir), "Backups (*.json)")
        if not path:
            return
        try:
            source = backup.load_backup(Path(path))
        except (ValueError, KeyError, OSError) as e:
            self._show_error(e)
            return
        self.run("Reading the mouse…", session.read_mouse, done=lambda cur: self._restore_pick(source, cur))

    def _restore_pick(self, source: backup.Backup, current: backup.Backup) -> None:
        try:
            session.plan_backup_restore(source, current)
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        pick = RestorePickDialog(source, current, self)
        if not pick.exec() or not pick.selected():
            return
        plan = session.plan_backup_restore(source, current, pick.selected())
        running = backup.ghub_running()
        blocked = (f"G Hub is running ({', '.join(running)}). Quit it first.") if running else None
        dlg = ConfirmWriteDialog("Restore from backup", plan, self.device.get("button_count", 11),
                                 preview_only=None, blocked=blocked, parent=self)
        if dlg.exec():
            self._execute(plan)

    # ---- JSON -------------------------------------------------------------------------
    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export profiles", "g502-profiles.json", "JSON (*.json)")
        if not path:
            return
        doc = model.build_export(self.source)
        doc["profiles"] = self.edited
        Path(path).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"Exported to {path}", 6000)

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import profiles", "", "JSON (*.json)")
        if not path:
            return
        try:
            profiles = apply.load_profiles(Path(path))
            by_sector = {p["sector"]: p for p in self.edited}
            n = 0
            for p in profiles:
                dev = p.pop("_device", None)
                if dev and (dev.get("product_id"), dev.get("button_count")) != \
                        (self.device["product_id"], self.device["button_count"]):
                    raise ValueError("this file is for a different mouse")
                if p.get("sector") not in by_sector:
                    raise ValueError(f"profile {p.get('sector')} isn't on this mouse")
                try:
                    library.require_left_click(p)
                except ValueError as e:
                    raise ValueError(f"profile {p['sector']}: {e}") from None
                model.encode_profile({k: v for k, v in p.items() if k not in ("sector", "enabled")},
                                     self.device["button_count"],
                                     base=self.source.sectors[p["sector"]])
                p.setdefault("enabled", by_sector[p["sector"]].get("enabled", True))
                self.edited[self.edited.index(by_sector[p["sector"]])] = p
                n += 1
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, APP_NAME, f"Couldn't import that file:\n\n{e}")
            return
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"Imported {n} profile(s). Nothing is written until you press Write.", 8000)

    def about(self) -> None:
        QMessageBox.about(self, APP_NAME, f"<b>{APP_NAME}</b> {__version__}<br>by {STUDIO}<br><br>"
                                          "Edit the onboard profiles of a wired Logitech G502 HERO: "
                                          "buttons, DPI and lighting.<br>"
                                          "Unofficial and open source. Not affiliated with or endorsed by "
                                          "Logitech.<br><br>"
                                          f"Backups: {self.backup_dir}")

    def closeEvent(self, event) -> None:
        if self.tasks:
            QMessageBox.information(self, APP_NAME, "Please wait until the current operation finishes.")
            event.ignore()
            return
        if not self._discard_ok():
            event.ignore()
            return
        event.accept()


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="g502 gui")
    p.add_argument("--backup", help="open this backup file (view only) instead of reading the mouse")
    p.add_argument("--dir", help="backup folder")
    p.add_argument("--theme", choices=["auto", "light", "dark"], default="auto")
    args = p.parse_args(argv)
    if sys.platform == "win32":
        # Own taskbar entry and icon instead of being grouped under python.exe.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(STUDIO)
    app.setWindowIcon(app_icon())
    tokens = style.apply_theme(app, None if args.theme == "auto" else args.theme == "dark")
    win = MainWindow(Path(args.dir) if args.dir else None, tokens)
    win.show()
    if args.backup:
        win.load(backup.load_backup(Path(args.backup)), False)
    else:
        win.read_from_mouse()
    return app.exec()
