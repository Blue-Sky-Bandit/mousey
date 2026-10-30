"""Main window: pick a profile, edit it, then one "Write to mouse" button."""

from __future__ import annotations

import copy
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, backup, diagnostics, labels, library, model, session
from ..device import DeviceNotFound
from . import style
from .common import APP_ID, APP_NAME, ASSETS, POLL_MS, STUDIO, Task, app_icon, latest_backup
from .device_ops import DeviceMixin
from .dialogs import banner
from .editor import EditorMixin
from .library_page import LibraryPage
from .profile_tools import ToolsMixin
from .sidebar import ProfileRow
from .splash import Splash
from .widgets import clear_layout, hint


class MainWindow(EditorMixin, DeviceMixin, ToolsMixin, QMainWindow):
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
        self.errors: list[str] = []   # recent errors, for the diagnostics report
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
        self.restore_btn = QPushButton("Backups…")
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
        menu.addAction("Save diagnostics…", self.save_diagnostics)
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
        self.library_page = LibraryPage(library.library_dirs(self.library_dir))
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

    def note_error(self, e: Exception) -> None:
        when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.errors.append(f"{when} {type(e).__name__}: {e}" + (f"\n{e.trace}" if getattr(e, "trace", "") else ""))
        del self.errors[:-20]

    def save_diagnostics(self) -> None:
        name = f"mousey-diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(self, "Save diagnostics", str(Path.home() / "Desktop" / name),
                                              "Text (*.txt)")
        if not path:
            return
        text = diagnostics.report(self.source, self.connected, self.errors, self.backup_dir, self.library_dir)
        Path(path).write_text(text, encoding="utf-8")
        self.statusBar().showMessage(f"Diagnostics saved to {path}", 8000)

    def _show_error(self, e: Exception) -> None:
        self.note_error(e)
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
        clear_layout(self.banner_holder)
        if text:
            self.banner_holder.addWidget(banner(text))

    def rename_mouse(self) -> None:
        name, ok = QInputDialog.getText(
            self, APP_NAME, "A name for your mouse, shown in this app.\n(The mouse itself can't store a name.)",
            text=self.settings.value("mouse_name", "", str))
        if ok:
            self.settings.setValue("mouse_name", name.strip()[:40])
            self._update_pill()





        # timeouts / HID++ errors here are ignored: this is only a status check


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
    p.add_argument("--no-splash", action="store_true", help="skip the start-up animation")
    p.add_argument("--selftest", metavar="REPORT", help=argparse.SUPPRESS)
    p.add_argument("--selftest-read", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if args.selftest:
        return selftest(Path(args.selftest), read_mouse=args.selftest_read)
    if sys.platform == "win32":
        # Own taskbar entry and icon instead of being grouped under python.exe.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(STUDIO)
    app.setWindowIcon(app_icon())
    tokens = style.apply_theme(app, None if args.theme == "auto" else args.theme == "dark")
    if args.no_splash:
        win = MainWindow(Path(args.dir) if args.dir else None, tokens)
        win.show()
        if args.backup:
            win.load(backup.load_backup(Path(args.backup)), False)
        else:
            win.read_from_mouse()
        return app.exec()
    return run_with_splash(app, args, tokens)


def run_with_splash(app: QApplication, args, tokens: dict) -> int:
    """Show the splash (always the full animation), load during it, then open the window."""
    splash = Splash()
    splash.start()
    app.processEvents()
    win = MainWindow(Path(args.dir) if args.dir else None, tokens)
    result: dict = {}

    def open_window() -> None:
        splash.close()
        win.show()
        if "backup" in result:
            win.load(result["backup"], result["connected"])
        elif "error" in result:
            win._read_failed(result["error"])      # falls back to the newest backup and explains

    splash.finished.connect(open_window)
    if args.backup:
        splash.set_status("Opening the backup…")
        try:
            result.update(backup=backup.load_backup(Path(args.backup)), connected=False)
        except (ValueError, KeyError, OSError) as e:
            result["error"] = e
        splash.set_loaded("Ready")
    else:
        splash.set_status("Reading the mouse…")

        def done(b) -> None:
            result.update(backup=b, connected=True)
            splash.set_loaded("Ready")

        def failed(e) -> None:
            result["error"] = e
            splash.set_loaded("Mouse not found" if isinstance(e, DeviceNotFound) else "Couldn't read the mouse")

        task = Task(session.read_mouse)
        task.signals.done.connect(done)
        task.signals.failed.connect(failed)
        result["task"] = task                      # keep it alive until it reports
        win.pool.start(task)
    return app.exec()


def selftest(report: Path, read_mouse: bool = False) -> int:
    """Build the window from the newest backup without showing it, and write what
    happened to `report`. With `read_mouse`, also read the mouse (read-only). Used to
    check a packaged build."""
    lines = []
    try:
        app = QApplication.instance() or QApplication(sys.argv[:1])
        tokens = style.apply_theme(app, True)
        win = MainWindow(None, tokens)
        lines.append(f"assets: {ASSETS} exists={ASSETS.is_dir()} icon={not app_icon().isNull()}")
        splash = Splash()
        lines.append(f"splash: valid={splash.movie.isValid()} frames={splash.frames}")
        path = latest_backup(backup.default_backup_dir())
        if path:
            win.load(backup.load_backup(path), False)
            lines.append(f"loaded {path.name}: {win.list.count()} profiles")
        for i in range(win.tabs.count()):
            win.tabs.setCurrentIndex(i)
            app.processEvents()
        if read_mouse:
            b = session.read_mouse()
            lines.append(f"read the mouse: {len(b.sectors)} sectors, mode {b.meta['onboard_mode']}, "
                         f"profile in use {b.meta['current_profile']}")
        lines.append("OK")
        code = 0
    except Exception as e:  # report anything, this is a smoke test
        import traceback
        lines.append(f"FAILED: {e}\n{traceback.format_exc()}")
        code = 1
    report.write_text("\n".join(lines), encoding="utf-8")
    return code
