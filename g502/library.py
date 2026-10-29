"""Profile library: any number of saved profiles kept on the PC, loadable into a slot.

A library entry holds the user-facing settings of one profile (name, polling rate, DPI,
buttons, G-Shift, lighting). Loading it into a slot is an ordinary edit: nothing reaches
the mouse until the normal preview-and-write. The slot keeps its own sector, enabled
flag and `advanced` bytes, and its hidden G-Shift table when the loaded profile has the
G-Shift layer off, so loading never touches bytes the user can't see.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import backup, model

LIBRARY_FORMAT = "mousey-library-profile"
LIBRARY_VERSION = 1
SETTINGS = ("name", "report_rate_hz", "dpi", "buttons", "gshift_layer", "lighting")
LEFT_CLICK = {"type": "mouse", "buttons": [1]}


def require_left_click(profile: dict) -> None:
    """Mousey keeps the main-layer left button as Left click, so a profile can never
    leave you unable to click. (The G-Shift layer's left button may be anything.)"""
    if profile.get("buttons", {}).get("left") != LEFT_CLICK:
        raise ValueError("its left button isn't Left click. Mousey keeps left click locked on the main layer "
                         "so you can't lose it.")


def default_library_dir() -> Path:
    return backup.data_dir() / "library"


def library_dirs(primary: Path | None = None) -> list[Path]:
    """The current library folder first, then any from earlier versions (read only)."""
    dirs = [primary or default_library_dir()] + [d / "library" for d in backup.legacy_data_dirs()]
    return [d for i, d in enumerate(dirs) if d not in dirs[:i]]


@dataclass
class Entry:
    title: str
    description: str
    profile: dict
    created: str = ""
    path: Path | None = None


def settings_of(profile: dict) -> dict:
    """The part of a profile that a library entry stores."""
    out = {k: copy.deepcopy(profile[k]) for k in SETTINGS if k in profile}
    out["gshift_layer"] = model.uses_gshift(profile["buttons"])
    if out["gshift_layer"]:
        out["gshift_buttons"] = copy.deepcopy(profile["gshift_buttons"])
    return out


def load_into_slot(settings: dict, slot: dict, button_count: int = len(model.BUTTON_NAMES)) -> dict:
    """A copy of `slot` with the entry's settings applied; validated by encoding it."""
    require_left_click(settings)
    new = copy.deepcopy(slot)
    for k in SETTINGS:
        if k in settings:
            new[k] = copy.deepcopy(settings[k])
    if settings.get("gshift_layer"):
        new["gshift_buttons"] = copy.deepcopy(settings["gshift_buttons"])
    clean = {k: v for k, v in new.items() if k not in ("sector", "enabled")}
    model.encode_profile(clean, button_count)   # raises ValueError if it can't be written
    return new


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "profile"


def save_entry(directory: Path, title: str, profile: dict, description: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = directory / f"{_slug(title)}-{now.strftime('%Y%m%d-%H%M%S')}.json"
    doc = {"format": LIBRARY_FORMAT, "format_version": LIBRARY_VERSION, "title": title,
           "description": description, "created": now.isoformat(timespec="seconds"),
           "profile": settings_of(profile)}
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def load_entry(path: Path) -> Entry:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("format") != LIBRARY_FORMAT:
        raise ValueError(f"{Path(path).name} is not a Mousey library profile")
    if doc.get("format_version") != LIBRARY_VERSION:
        raise ValueError(f"{Path(path).name}: unsupported library version {doc.get('format_version')!r}")
    return Entry(doc["title"], doc.get("description", ""), doc["profile"], doc.get("created", ""), Path(path))


def list_entries(directories: Path | list[Path]) -> tuple[list[Entry], list[str]]:
    """Entries newest first, plus a message for each file that couldn't be read."""
    if isinstance(directories, Path):
        directories = [directories]
    entries, problems = [], []
    paths = [f for d in directories if d.exists() for f in sorted(d.glob("*.json"))]
    for path in paths:
        try:
            entries.append(load_entry(path))
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as e:
            problems.append(f"{path.name}: {e}")
    entries.sort(key=lambda e: e.created, reverse=True)
    return entries, problems
