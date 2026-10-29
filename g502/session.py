"""Read / plan / write steps shared by the GUI, with the same safety rules as the CLI.

Every write goes: G Hub check -> fresh read of the mouse -> check the mouse has not
changed since the preview the user approved -> pre-write backup -> one sector at a
time with read-back -> stop at the first failure, no retries.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import apply, backup
from .backup import Backup
from .device import Device
from .onboard import SECTOR_DIRECTORY, OnboardProfiles


# One conversation with the mouse at a time: the live profile check, reads and writes
# all go through this lock so their HID++ replies can never get mixed up.
DEVICE_LOCK = threading.Lock()


class MouseChanged(Exception):
    """The mouse no longer matches what the user previewed."""


@dataclass
class WritePlan:
    """Sectors to write (in order) and the mouse contents they were planned against."""
    sectors: dict[int, bytes]
    order: list[int]
    planned_against: Backup
    skipped: dict[int, str]
    notes: list[str]

    @property
    def empty(self) -> bool:
        return not self.order


def _read() -> Backup:
    with Device.open_first() as dev:
        return backup.take_backup(dev, OnboardProfiles(dev))


def read_mouse(retry_delay: float = 1.5) -> Backup:
    """Read everything. A timeout (e.g. the mouse still starting up after being
    plugged in) is retried once after a short wait; reads never change the mouse."""
    with DEVICE_LOCK:
        try:
            return _read()
        except TimeoutError:
            time.sleep(retry_delay)
            return _read()


@dataclass
class Status:
    profile: int
    mode: str


def poll() -> Status | None:
    """The profile in use and the mode, or None if another operation is using the
    mouse. Raises DeviceNotFound when the mouse is unplugged."""
    if not DEVICE_LOCK.acquire(blocking=False):
        return None
    try:
        with Device.open_first() as dev:
            ob = OnboardProfiles(dev)
            return Status(ob.get_current_profile(), ob.get_mode())
    finally:
        DEVICE_LOCK.release()


def switch_to_onboard() -> str:
    """Put the mouse back in onboard memory mode and return the mode it reports after.
    Refused while G Hub runs, since G Hub would just switch it back."""
    running = backup.ghub_running()
    if running:
        raise WriteFailed(f"G Hub is running ({', '.join(running)}). Quit it first.", [], None)
    with DEVICE_LOCK, Device.open_first() as dev:
        ob = OnboardProfiles(dev)
        ob.set_mode("onboard")
        return ob.get_mode()


def changed_profiles(original: list[dict], edited: list[dict]) -> list[dict]:
    before = {p["sector"]: p for p in original}
    return [p for p in edited if before.get(p["sector"]) != p]


def plan_profiles(edited: list[dict], original: list[dict], current: Backup, device: dict) -> WritePlan:
    """Plan writing every edited profile (and enable/disable changes) to `current`."""
    changed = changed_profiles(original, edited)
    profiles = [dict(p, _device=device) for p in changed]
    sectors = [p["sector"] for p in changed]
    before = {p["sector"]: p for p in original}
    directory = any(p.get("enabled") != before[p["sector"]].get("enabled") for p in changed)
    plan = apply.plan_apply(profiles, current, sectors, directory=directory)
    return WritePlan(plan.sectors, plan.order, current, {}, plan.notes)


def plan_backup_restore(source: Backup, current: Backup, only: list[int] | None = None) -> WritePlan:
    problems = backup.check_backup(source) + backup.compatibility_problems(source, current)
    if problems:
        raise ValueError("this backup can't be restored to this mouse:\n" + "\n".join(problems))
    rp = backup.plan_restore(source, current, only)
    return WritePlan({s: source.sectors[s] for s in rp.write}, rp.write, current, rp.skipped, [])


@dataclass
class WriteResult:
    safety_backup: Path
    written: list[int]
    after: Backup


class WriteFailed(Exception):
    def __init__(self, message: str, written: list[int], safety_backup: Path | None):
        super().__init__(message)
        self.written = written
        self.safety_backup = safety_backup


def execute(plan: WritePlan, backup_dir: Path | None = None, log=lambda line: None) -> WriteResult:
    running = backup.ghub_running()
    if running:
        raise WriteFailed(f"G Hub is running ({', '.join(running)}) and can overwrite onboard profiles. "
                          "Quit it first.", [], None)
    with DEVICE_LOCK, Device.open_first() as dev:
        ob = OnboardProfiles(dev)
        log("Reading the mouse...")
        fresh = backup.take_backup(dev, ob)
        moved = [s for s in plan.order if fresh.sectors.get(s) != plan.planned_against.sectors.get(s)]
        if moved:
            raise MouseChanged("the mouse changed since the preview (sectors "
                               + ", ".join(str(s) for s in moved) + "); nothing was written. Preview again.")
        safety = backup.save_backup(fresh, backup_dir or backup.default_backup_dir())
        log(f"Pre-write backup saved to {safety}")
        try:
            backup.execute_restore(ob, Backup(fresh.meta, plan.sectors), plan.order, log=log)
        except backup.RestoreFailed as e:
            raise WriteFailed(str(e), e.written, safety) from e
        log("Reading the mouse back...")
        after = backup.take_backup(dev, ob)
    return WriteResult(safety, list(plan.order), after)


def sector_label(sector: int) -> str:
    return "Profile list" if sector == SECTOR_DIRECTORY else f"Profile {sector}"


def describe_plan(plan: WritePlan, button_count: int) -> list[tuple[str, str, str, str, str]]:
    """(where, area, setting, before, after) rows describing what `plan` writes,
    decoded from the actual sector bytes, so the list matches what is written."""
    from . import labels, model
    from .onboard import parse_directory

    rows = []
    for s in plan.order:
        old, new = plan.planned_against.sectors[s], plan.sectors[s]
        if s == SECTOR_DIRECTORY:
            before = {e.sector: e.enabled for e in parse_directory(old)}
            after = {e.sector: e.enabled for e in parse_directory(new)}
            for n in sorted(set(before) | set(after)):
                if before.get(n) != after.get(n):
                    yes = {True: "Active", False: "Deactivated", None: "Not listed"}
                    rows.append((sector_label(SECTOR_DIRECTORY), "Profiles", f"Profile {n}",
                                 yes[before.get(n)], yes[after.get(n)]))
            continue
        changes = labels.describe_changes(model.decode_profile(old, button_count),
                                          model.decode_profile(new, button_count))
        if old == new:
            rows.append((sector_label(s), "", "No change (identical data rewritten)", "", ""))
        elif not changes:
            rows.append((sector_label(s), "", "Byte-level change only (see details)", "", ""))
        rows += [(sector_label(s), *c) for c in changes]
    return rows
