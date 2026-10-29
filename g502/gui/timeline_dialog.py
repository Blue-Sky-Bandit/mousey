"""Backups window: every backup on a timeline, what changed in each, and restore."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import timeline
from .dialogs import change_table
from .widgets import clear_layout, hint

ROW_HEIGHT = 58


class TimelineRow(QWidget):
    """One restore point: a dot on a vertical line, with time, kind and summary."""

    def __init__(self, point: timeline.Point, tokens: dict, top: bool, bottom: bool, parent=None):
        super().__init__(parent)
        self.point, self.tokens, self.top, self.bottom = point, tokens, top, bottom
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 6, 10, 6)
        lay.setSpacing(0)
        when = point.created.strftime("%H:%M:%S") if point.created else "?"
        title = QLabel(f"{when}  ·  {point.reason}" + ("  ·  matches the mouse" if point.matches_mouse else ""))
        title.setStyleSheet("font-weight: 600;" + (f"color: {tokens['accent_strong']};"
                                                   if point.matches_mouse else ""))
        sub = QLabel(point.summary + ("  (older folder)" if point.legacy else ""), objectName="Muted")
        sub.setWordWrap(False)
        sub.setToolTip(point.summary)
        lay.addWidget(title)
        lay.addWidget(sub)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x, y = 20.0, self.height() / 2
        p.setPen(QPen(QColor(self.tokens["border"]), 2))
        p.drawLine(QPointF(x, 0 if self.top else y), QPointF(x, self.height() if self.bottom else y))
        has_changes = bool(self.point.changes) or self.point.first
        fill = QColor(self.tokens["accent"]) if self.point.matches_mouse else (
            QColor(self.tokens["text"]) if has_changes else QColor(self.tokens["surface2"]))
        p.setPen(QPen(QColor(self.tokens["border"] if not self.point.matches_mouse else "#111111"), 2))
        p.setBrush(fill)
        r = 7 if has_changes or self.point.matches_mouse else 5
        p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
        p.end()


class TimelineDialog(QDialog):
    """Pick a restore point. `restore_path` is set when the user chooses Restore."""

    def __init__(self, points: list[timeline.Point], tokens: dict, can_restore: bool, start_dir: Path,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Backups")
        self.resize(1080, 700)
        self.points, self.tokens, self.start_dir = points, tokens, start_dir
        self.restore_path: Path | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Backups", objectName="Title"))
        lay.addWidget(hint("Every backup is a restore point. Mousey makes one automatically before every write; "
                           "the dot is filled where something changed since the backup before it, and yellow "
                           "where the backup matches what's on the mouse now."))

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget(objectName="Profiles")
        self.list.setMinimumWidth(420)
        self.list.currentRowChanged.connect(self._select)
        split.addWidget(self.list)
        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(16, 0, 0, 0)
        self.heading = QLabel(objectName="Section")
        self.where = hint("")
        self.where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.table_holder = QVBoxLayout()
        r.addWidget(self.heading)
        r.addWidget(self.where)
        r.addLayout(self.table_holder, 1)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        buttons = QHBoxLayout()
        other = QPushButton("Open another file…")
        other.clicked.connect(self._other)
        self.folder = QPushButton("Show in folder")
        self.folder.clicked.connect(self._show_in_folder)
        self.restore = QPushButton("Restore this backup…", objectName="Primary")
        self.restore.clicked.connect(self._restore)
        self.restore.setEnabled(False)
        self.can_restore = can_restore
        if not can_restore:
            self.restore.setToolTip("Restoring needs the mouse connected.")
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for w in (other, self.folder):
            buttons.addWidget(w)
        buttons.addStretch(1)
        buttons.addWidget(self.restore)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self._fill()

    def _fill(self) -> None:
        day = None
        for i, pt in enumerate(self.points):
            d = pt.created.date() if pt.created else None
            if d != day:
                day = d
                header = QListWidgetItem(pt.created.strftime("%A %d %B %Y") if pt.created else "Unknown date")
                header.setFlags(Qt.NoItemFlags)
                f = header.font()
                f.setBold(True)
                header.setFont(f)
                self.list.addItem(header)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, i)
            item.setSizeHint(QSize(400, ROW_HEIGHT))
            self.list.addItem(item)
            self.list.setItemWidget(item, TimelineRow(pt, self.tokens, i > 0, i < len(self.points) - 1))
        if self.points:
            self.list.setCurrentRow(1)

    def _point(self) -> timeline.Point | None:
        item = self.list.currentItem()
        i = item.data(Qt.UserRole) if item else None
        return self.points[i] if i is not None else None

    def _select(self, _row: int) -> None:
        pt = self._point()
        clear_layout(self.table_holder)
        if pt is None:
            return
        when = pt.created.strftime("%d %b %Y, %H:%M:%S") if pt.created else "unknown time"
        self.heading.setText(f"{pt.reason}, {when}")
        self.where.setText(f"{pt.path}" + ("\nIn the folder used by an earlier version." if pt.legacy else ""))
        if pt.problem:
            self.table_holder.addWidget(hint(f"This file can't be read: {pt.problem}"))
        elif pt.first:
            self.table_holder.addWidget(hint("The oldest backup, so there's nothing earlier to compare with."))
        elif not pt.changes:
            self.table_holder.addWidget(hint("Nothing changed on the mouse since the backup before this one."))
        else:
            self.table_holder.addWidget(hint("Changes since the backup before this one:"))
            self.table_holder.addWidget(change_table(pt.changes), 1)
        if pt.problem or pt.first or not pt.changes:
            self.table_holder.addStretch(1)
        self.restore.setEnabled(self.can_restore and pt.backup is not None and not pt.matches_mouse)
        if pt.matches_mouse:
            self.restore.setToolTip("The mouse already matches this backup.")

    def _restore(self) -> None:
        pt = self._point()
        if pt:
            self.restore_path = pt.path
            self.accept()

    def _other(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore from a backup file", str(self.start_dir),
                                              "Backups (*.json)")
        if path:
            self.restore_path = Path(path)
            self.accept()

    def _show_in_folder(self) -> None:
        pt = self._point()
        if pt:
            subprocess.Popen(["explorer", "/select,", str(pt.path)])  # noqa: S603,S607 - opens Explorer
