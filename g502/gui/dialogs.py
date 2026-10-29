"""The write confirmation (dry run) dialog and the restore picker."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from .. import backup, session
from ..onboard import SECTOR_DIRECTORY
from .widgets import hint


def banner(text: str, action: tuple[str, object] | None = None) -> QFrame:
    """A highlighted note, optionally with one button: action = (label, callback)."""
    frame = QFrame(objectName="Banner")
    lay = QHBoxLayout(frame)
    lay.setContentsMargins(12, 8, 12, 8)
    lab = QLabel(text, objectName="Banner")
    lab.setWordWrap(True)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lay.addWidget(lab, 1)
    if action:
        button = QPushButton(action[0], objectName="Primary")
        button.clicked.connect(action[1])
        lay.addWidget(button)
    return frame


def change_table(rows: list[tuple]) -> QTableWidget:
    table = QTableWidget(len(rows), 5)
    table.setHorizontalHeaderLabels(["Where", "Area", "Setting", "Before", "After"])
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setFocusPolicy(Qt.NoFocus)
    table.setWordWrap(True)
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            item = QTableWidgetItem(text)
            if c == 4:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            table.setItem(r, c, item)
    h = table.horizontalHeader()
    for c in range(3):
        h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
    h.setSectionResizeMode(3, QHeaderView.Stretch)
    h.setSectionResizeMode(4, QHeaderView.Stretch)
    table.resizeRowsToContents()
    return table


class ConfirmWriteDialog(QDialog):
    """Dry run: shows exactly what will change before anything is written."""

    def __init__(self, title: str, plan: session.WritePlan, button_count: int, *, preview_only: str | None,
                 blocked: str | None = None, notes: list[str] = (), parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(12)
        lay.addWidget(QLabel(title, objectName="Title"))

        where = ", ".join(session.sector_label(s) for s in plan.order)
        lay.addWidget(hint(f"This will write {len(plan.order)} part(s) of the mouse's memory: {where}. "
                           "A backup of the mouse is saved automatically just before writing, and every part "
                           "is read back and checked afterwards. If anything fails, it stops without writing "
                           "anything further."))
        for text in ([preview_only] if preview_only else []) + ([blocked] if blocked else []) + list(notes) \
                + list(plan.notes):
            lay.addWidget(banner(text))
        for s, reason in plan.skipped.items():
            lay.addWidget(hint(f"Skipped {session.sector_label(s)}: {reason}"))

        rows = session.describe_plan(plan, button_count)
        lay.addWidget(change_table(rows), 1)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)
        f = self.details.font()
        f.setFamily("Cascadia Mono, Consolas")
        self.details.setFont(f)
        lines = []
        for s in plan.order:
            old, new = plan.planned_against.sectors[s], plan.sectors[s]
            lines.append(f"Sector 0x{s:04X} ({session.sector_label(s)}):")
            lines += backup.diff_lines(old, new, label="new") or ["  identical bytes"]
        self.details.setPlainText("\n".join(lines))
        self.details.hide()
        toggle = QPushButton("Show technical details")
        toggle.setCheckable(True)
        toggle.toggled.connect(lambda on: (self.details.setVisible(on),
                                           toggle.setText("Hide technical details" if on else
                                                          "Show technical details")))

        buttons = QDialogButtonBox()
        self.write = buttons.addButton("Write to mouse", QDialogButtonBox.AcceptRole)
        self.write.setObjectName("Primary")
        self.write.setEnabled(not preview_only and not blocked and not plan.empty)
        buttons.addButton("Cancel" if not preview_only else "Close", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(toggle)
        bottom.addStretch(1)
        bottom.addWidget(buttons)
        lay.addWidget(self.details, 1)
        lay.addLayout(bottom)


class RestorePickDialog(QDialog):
    """Choose which parts of a backup to put back on the mouse."""

    def __init__(self, source: backup.Backup, current: backup.Backup, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore from backup")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Restore from backup", objectName="Title"))
        lay.addWidget(hint(f"{source.path.name}\ncreated {source.meta['created'][:19].replace('T', ' ')}"))
        rp = backup.plan_restore(source, current)
        self.boxes: dict[int, QCheckBox] = {}
        if not rp.write:
            lay.addWidget(hint("The mouse already matches this backup. Nothing needs restoring."))
        else:
            lay.addWidget(hint("These parts differ from the mouse. Untick any you want to leave as they are:"))
            for s in rp.write:
                cb = QCheckBox(session.sector_label(s) + (" (which profiles are on)"
                                                          if s == SECTOR_DIRECTORY else ""))
                cb.setChecked(True)
                self.boxes[s] = cb
                lay.addWidget(cb)
        for s, reason in rp.skipped.items():
            lay.addWidget(hint(f"Not restored: {session.sector_label(s)}: {reason}"))
        buttons = QDialogButtonBox()
        ok = buttons.addButton("Preview restore…", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        ok.setEnabled(bool(self.boxes))
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addSpacing(6)
        lay.addWidget(buttons)

    def selected(self) -> list[int]:
        return [s for s, cb in self.boxes.items() if cb.isChecked()]
