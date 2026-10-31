"""A plain-text diagnostics report for bug reports.

It describes the setup and the mouse's state (firmware, mode, which sectors hold valid
profiles, checksums) but not the profiles' contents, and it never includes backups.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, backup, library
from .backup import Backup
from .onboard import SECTOR_DIRECTORY, parse_directory


def logitech_processes() -> list[str]:
    """Running processes from Logitech software (G Hub and its services)."""
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ["(couldn't list processes)"]
    names = {line.split(",")[0].strip('"') for line in out.splitlines() if line}
    return sorted(n for n in names if "lghub" in n.lower() or n.lower().startswith("logi"))


def _versions() -> list[str]:
    lines = [f"Mousey {__version__}", f"Python {platform.python_version()} ({platform.architecture()[0]})",
             f"Windows: {platform.platform()}", f"Packaged app: {'yes' if getattr(sys, 'frozen', False) else 'no'}"]
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        lines.append(f"PySide6 {PySide6.__version__}, Qt {qVersion()}")
    except ImportError:
        lines.append("PySide6 not installed")
    try:
        import hid
        lines.append(f"hidapi {getattr(hid, '__version__', '?')}")
    except ImportError:
        lines.append("hidapi not installed")
    return lines


def folders(backup_dir: Path | None, library_dir: Path | None) -> list[str]:
    lines = []
    for d in backup.backup_dirs(backup_dir):
        lines.append(f"Backups: {d} ({len(backup.list_backups([d]))} files)")
    for d in library.library_dirs(library_dir):
        n = len(list(d.glob('*.json'))) if d.is_dir() else 0
        lines.append(f"Library: {d} ({n} files)")
    return lines


def _mouse(source: Backup | None, connected: bool) -> list[str]:
    if source is None:
        return ["Nothing has been read yet."]
    m = source.meta
    lines = [f"Data from: {'the mouse' if connected else 'a backup file: ' + str(source.path)}",
             f"Read at: {m.get('created')}",
             f"Product: {m.get('product_name')} (PID 0x{m.get('product_id', 0):04X})"]
    for fw in m.get("firmware", []):
        lines.append(f"Firmware: {fw.get('type')} {fw.get('version')}")
    lines.append(f"Onboard info: {m.get('onboard_info')}")
    lines.append(f"Mode: {m.get('onboard_mode')}   Profile in use: {m.get('current_profile')}")
    directory = source.sectors.get(SECTOR_DIRECTORY)
    if directory:
        lines.append("Profile list: " + ", ".join(f"{e.sector}={'active' if e.enabled else 'deactivated'}"
                                                  for e in parse_directory(directory)))
    for n, data in sorted(source.sectors.items()):
        lines.append(f"  sector 0x{n:04X}: {backup.sector_status(n, data):<8} sha256 "
                     f"{hashlib.sha256(data).hexdigest()[:16]}")
    return lines


def report(source: Backup | None, connected: bool, errors: list[str] = (), backup_dir: Path | None = None,
           library_dir: Path | None = None) -> str:
    sections = [
        ("Versions", _versions()),
        ("Folders", folders(backup_dir, library_dir)),
        ("Logitech software running", logitech_processes() or ["none"]),
        ("Mouse", _mouse(source, connected)),
        ("Recent errors", list(errors) or ["none"]),
    ]
    out = [f"Mousey diagnostics, {datetime.now().isoformat(timespec='seconds')}",
           "(No profile contents or backups are included.)", ""]
    for title, lines in sections:
        out += [f"== {title} ==", *lines, ""]
    return "\n".join(out)
