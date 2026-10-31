"""Talking to the mouse from the window: live status checks, reading, writing, restoring."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox

from .. import backup, session, timeline
from ..device import DeviceNotFound
from .common import APP_NAME, Task, latest_backup
from .dialogs import ConfirmWriteDialog, RestorePickDialog, banner
from .timeline_dialog import TimelineDialog
from .widgets import clear_layout


class DeviceMixin:
    """Part of MainWindow; uses its state (self.edited, self.source, ...)."""

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
        clear_layout(self.mode_holder)
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
            if self.tester is not None:
                self.tester.set_profile(*self._tester_profile())

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

    def _auto_read(self) -> None:
        if not self.tasks and self.edited == self.original:
            self.run("Reading the mouse…", session.read_mouse, done=lambda b: self.load(b, True),
                     failed=self._show_error)

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
            elif isinstance(e, DeviceNotFound):
                self.note_error(e)        # the "Plug in your G502 HERO" page says it all
                self.statusBar().showMessage("No G502 HERO found. Waiting for it to be plugged in…")
                return
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
            return b, backup.save_backup(b, self.backup_dir, "manual")
        self.run("Backing up the mouse…", work,
                 done=lambda r: QMessageBox.information(self, APP_NAME, f"Backup saved:\n{r[1]}"))

    def open_backups_folder(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.backup_dir)  # noqa: S606 - Windows only, opens Explorer

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

    def _execute(self, plan: session.WritePlan, reason: str = "before-write") -> None:
        log_lines: list[str] = []

        def work():
            return session.execute(plan, self.backup_dir, log=lambda s: (log_lines.append(s),), reason=reason)
        self.run("Writing to the mouse… don't unplug it", work, done=self._written, failed=self._write_failed)

    def _written(self, result: session.WriteResult) -> None:
        self.load(result.after, True)
        parts = ", ".join(session.sector_label(s) for s in result.written)
        QMessageBox.information(self, APP_NAME, f"Written and checked: {parts}.\n\n"
                                                f"Backup taken just before writing:\n{result.safety_backup}")

    def _write_failed(self, e: Exception) -> None:
        self.note_error(e)
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
        """The Backups window: a timeline of restore points; restore the one picked."""
        dirs = backup.backup_dirs(self.backup_dir)
        points = timeline.build(backup.list_backups(dirs), dirs[1:], self.source if self.connected else None,
                                self.device.get("button_count", 11))
        dlg = TimelineDialog(points, self.tokens, self.connected, self.backup_dir, self)
        if not dlg.exec() or dlg.restore_path is None:
            return
        if not self.connected:
            QMessageBox.information(self, APP_NAME, "Restoring needs the mouse. Plug it in and read it first.")
            return
        if not self._discard_ok():
            return
        path = dlg.restore_path
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
            self._execute(plan, "before-restore")
