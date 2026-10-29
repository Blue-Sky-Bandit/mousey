"""Shared constants and helpers for the Mousey window modules."""

from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QIcon

from .. import backup

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
    """Newest backup in `directory` or, failing that, in an older version's folder."""
    files = backup.list_backups(backup.backup_dirs(directory))
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
