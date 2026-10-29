"""Backup timeline: every backup as a restore point, with what changed since the one before."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import backup, session
from .backup import Backup


@dataclass
class Point:
    path: Path
    created: datetime | None
    reason: str
    legacy: bool                       # in an older version's folder
    changes: list[tuple] = field(default_factory=list)   # since the previous backup
    first: bool = False                # the oldest backup: nothing to compare with
    matches_mouse: bool = False
    problem: str = ""
    backup: Backup | None = None

    @property
    def summary(self) -> str:
        if self.problem:
            return f"Can't be read: {self.problem}"
        if self.first:
            return "Oldest backup"
        if not self.changes:
            return "No changes since the previous backup"
        by_where: dict[str, list[str]] = {}
        for where, area, setting, _before, after in self.changes:
            by_where.setdefault(where, []).append(f"{setting} {after.lower()}" if area == "Profiles" else setting)
        parts = []
        for where, settings in by_where.items():
            shown = ", ".join(dict.fromkeys(settings[:3]))
            more = f" +{len(settings) - 3} more" if len(settings) > 3 else ""
            parts.append(f"{where}: {shown}{more}")
        return "; ".join(parts)


def user_sectors_equal(a: Backup, b: Backup) -> bool:
    return all(a.sectors.get(s) == b.sectors.get(s) for s in set(a.user_sectors()) | set(b.user_sectors()))


def diff(old: Backup, new: Backup, button_count: int) -> list[tuple]:
    rows = []
    for s in sorted(set(old.user_sectors()) | set(new.user_sectors())):
        a, b = old.sectors.get(s), new.sectors.get(s)
        if a is not None and b is not None:
            rows += session.describe_sector_change(s, a, b, button_count)
    return rows


def build(paths: list[Path], legacy_dirs: list[Path], current: Backup | None = None,
          button_count: int = 11) -> list[Point]:
    """Restore points newest first. `paths` may be in any order; they are sorted by time."""
    points: list[Point] = []
    previous: Backup | None = None
    for path in sorted(paths, key=lambda f: f.name):
        try:
            b = backup.load_backup(path)
        except (ValueError, KeyError, OSError) as e:
            points.append(Point(path, None, "Backup", path.parent in legacy_dirs, problem=str(e)))
            continue
        created = datetime.fromisoformat(b.meta["created"]) if b.meta.get("created") else None
        point = Point(path, created, backup.REASONS.get(b.meta.get("reason"), "Backup"),
                      path.parent in legacy_dirs, backup=b)
        if previous is None:
            point.first = True
        else:
            point.changes = diff(previous, b, button_count)
        point.matches_mouse = current is not None and user_sectors_equal(b, current)
        points.append(point)
        previous = b
    return list(reversed(points))
