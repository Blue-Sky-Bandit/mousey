"""Backup, verification and byte-for-byte restore of onboard memory."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import __version__
from .device import Device
from .onboard import ROM_SECTOR_BASE, SECTOR_DIRECTORY, OnboardProfiles, is_blank, parse_directory, sector_crc_ok

BACKUP_FORMAT = 1


def default_backup_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "G502Configurator" / "backups"


def ghub_running() -> list[str]:
    """Names of running G Hub processes that can overwrite onboard profiles."""
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names = {line.split(",")[0].strip('"').lower() for line in out.splitlines() if line}
    return sorted(names & {"lghub.exe", "lghub_agent.exe"})


@dataclass
class Backup:
    meta: dict
    sectors: dict[int, bytes]
    path: Path | None = None

    def user_sectors(self) -> list[int]:
        return sorted(s for s in self.sectors if s < ROM_SECTOR_BASE)

    def rom_sectors(self) -> list[int]:
        return sorted(s for s in self.sectors if s >= ROM_SECTOR_BASE)


def sector_status(num: int, data: bytes) -> str:
    """'crc-ok', 'crc-bad', 'blank' (erased/unbacked) or 'rom' (no CRC by design)."""
    if num >= ROM_SECTOR_BASE:
        return "rom"
    if is_blank(data):
        return "blank"
    return "crc-ok" if sector_crc_ok(data) else "crc-bad"


def take_backup(dev: Device, ob: OnboardProfiles) -> Backup:
    """Read every readable sector: all user sectors plus factory ROM sectors."""
    numbers = list(range(SECTOR_DIRECTORY, ob.info.sector_count)) + ob.rom_sectors()
    sectors = {n: ob.read_sector(n) for n in numbers}
    meta = {
        "backup_format": BACKUP_FORMAT,
        "tool_version": __version__,
        "created": datetime.now().isoformat(timespec="microseconds"),
        "product_id": dev.info.product_id,
        "product_name": dev.get_name(),
        "firmware": dev.get_firmware(),
        "onboard_info": ob.info.to_dict(),
        "onboard_mode": ob.get_mode(),
        "current_profile": ob.get_current_profile(),
    }
    return Backup(meta, sectors)


def save_backup(backup: Backup, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(backup.meta["created"]).strftime("%Y%m%d-%H%M%S-%f")
    path = directory / f"g502-backup-{stamp}.json"
    doc = dict(backup.meta)
    doc["sectors"] = {
        f"0x{n:04X}": {
            "status": sector_status(n, d),
            "sha256": hashlib.sha256(d).hexdigest(),
            "data": d.hex(),
        }
        for n, d in sorted(backup.sectors.items())
    }
    path.write_text(json.dumps(doc, indent=2))
    backup.path = path
    return path


def load_backup(path: Path) -> Backup:
    doc = json.loads(Path(path).read_text())
    if doc.get("backup_format") != BACKUP_FORMAT:
        raise ValueError(f"{path}: unsupported backup format {doc.get('backup_format')!r}")
    sectors = {}
    for key, entry in doc.pop("sectors").items():
        data = bytes.fromhex(entry["data"])
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"{path}: sector {key} does not match its stored SHA-256 (file damaged?)")
        sectors[int(key, 16)] = data
    return Backup(doc, sectors, Path(path))


def check_backup(backup: Backup) -> list[str]:
    """Problems that make a backup unsafe to restore (empty list = OK)."""
    problems = []
    info = backup.meta["onboard_info"]
    expected = set(range(info["sector_count"]))
    missing = expected - set(backup.user_sectors())
    if missing:
        problems.append(f"missing user sectors: {sorted(hex(s) for s in missing)}")
    for n, d in backup.sectors.items():
        if len(d) != info["sector_size"]:
            problems.append(f"sector 0x{n:04X} is {len(d)} bytes, expected {info['sector_size']}")
        elif sector_status(n, d) == "crc-bad":
            problems.append(f"sector 0x{n:04X} has a bad CRC")
    directory = backup.sectors.get(SECTOR_DIRECTORY)
    if directory is not None:
        for e in parse_directory(directory):
            target = backup.sectors.get(e.sector)
            if target is None or sector_status(e.sector, target) != "crc-ok":
                problems.append(f"directory points at sector 0x{e.sector:04X}, which has no valid profile")
    return problems


def compare_backups(a: Backup, b: Backup) -> list[str]:
    diffs = []
    for key in ("product_id", "firmware", "onboard_info"):
        if a.meta.get(key) != b.meta.get(key):
            diffs.append(f"metadata '{key}' differs")
    for n in sorted(set(a.sectors) | set(b.sectors)):
        if a.sectors.get(n) != b.sectors.get(n):
            diffs.append(f"sector 0x{n:04X} differs")
    return diffs


def compatibility_problems(backup: Backup, current: Backup) -> list[str]:
    """Reasons the backup must not be written to the connected mouse."""
    problems = []
    for key in ("product_id", "firmware", "onboard_info"):
        if backup.meta.get(key) != current.meta.get(key):
            problems.append(f"{key} differs: backup {backup.meta.get(key)} vs mouse {current.meta.get(key)}")
    return problems


@dataclass
class RestorePlan:
    write: list[int]          # in write order, directory last
    skipped: dict[int, str]   # sector -> reason it will not be written


def plan_restore(backup: Backup, current: Backup, only: list[int] | None = None,
                 allow_fill_empty: bool = False) -> RestorePlan:
    """User sectors to write, in order: profile/data sectors ascending, directory last.

    By default only sectors whose bytes differ from the mouse are written.
    `only` names sectors explicitly (written even if identical, for no-op tests).

    Blank sectors in the backup are never written: the firmware rejects them at
    WRITE_END (no valid CRC), so a restore cannot return a sector to blank.
    Sectors that are blank on the mouse are not filled with data unless
    `allow_fill_empty` is set, since profiles may reference them (e.g. macros)."""
    if only is not None:
        for s in only:
            if s not in backup.user_sectors():
                raise ValueError(f"sector 0x{s:04X} is not a user sector in the backup (ROM is never written)")
        chosen = set(only)
    else:
        chosen = {s for s in backup.user_sectors() if backup.sectors[s] != current.sectors.get(s)}
    skipped = {}
    for s in sorted(chosen):
        if is_blank(backup.sectors[s]):
            skipped[s] = "blank in backup: firmware rejects writes without a valid CRC, cannot be returned to blank"
        elif is_blank(current.sectors[s]) and not allow_fill_empty:
            skipped[s] = "blank on the mouse: not filling an empty sector without --allow-fill-empty"
    chosen -= set(skipped)
    order = sorted(chosen - {SECTOR_DIRECTORY}) + ([SECTOR_DIRECTORY] if SECTOR_DIRECTORY in chosen else [])
    return RestorePlan(order, skipped)


def diff_lines(old: bytes, new: bytes, width: int = 16, label: str = "backup") -> list[str]:
    """Hex rows (16 bytes) that differ, as 'mouse' / <label> pairs."""
    lines = []
    for off in range(0, len(new), width):
        a, b = old[off:off + width], new[off:off + width]
        if a != b:
            lines.append(f"  {off:04X} {'mouse':<{max(5, len(label))}}: " + " ".join(f"{x:02X}" for x in a))
            lines.append(f"  {off:04X} {label:<5}: " + " ".join(
                f"{y:02X}" if x != y else ".." for x, y in zip(a, b)))
    return lines


class RestoreFailed(Exception):
    def __init__(self, message: str, written: list[int]):
        super().__init__(message)
        self.written = written


def execute_restore(ob: OnboardProfiles, backup: Backup, plan: list[int], log=print) -> None:
    """Write each planned sector, read it back and compare. Stops at the first
    error or mismatch without writing anything further."""
    written: list[int] = []
    for s in plan:
        data = backup.sectors[s]
        log(f"Writing sector 0x{s:04X}...")
        try:
            ob.write_sector(s, data)
        except Exception as e:
            raise RestoreFailed(f"write of sector 0x{s:04X} failed: {e} (sector may be partially written)", written)
        try:
            readback = ob.read_sector(s)
        except Exception as e:
            raise RestoreFailed(f"read-back of sector 0x{s:04X} failed: {e}", written + [s])
        if readback != data:
            bad = sum(1 for x, y in zip(readback, data) if x != y)
            raise RestoreFailed(f"read-back of sector 0x{s:04X} does not match ({bad} bytes differ)", written + [s])
        written.append(s)
        log(f"  sector 0x{s:04X} verified ({len(data)} bytes match)")
