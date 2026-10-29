"""Import an edited profile file, validate it and plan the write."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import model
from .backup import Backup
from .onboard import SECTOR_DIRECTORY, crc_ccitt, is_blank, parse_directory, sector_crc_ok


@dataclass
class ApplyPlan:
    sectors: dict[int, bytes] = field(default_factory=dict)   # sector -> new bytes, only changed ones
    field_diffs: dict[int, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def order(self) -> list[int]:
        """Profile sectors ascending, directory last."""
        return sorted(s for s in self.sectors if s != SECTOR_DIRECTORY) + \
            ([SECTOR_DIRECTORY] if SECTOR_DIRECTORY in self.sectors else [])


def load_profiles(path: Path) -> list[dict]:
    """Profiles from an export file, or a file holding one profile object."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(doc, dict) and doc.get("format") == model.EXPORT_FORMAT:
        if doc.get("format_version") != model.EXPORT_FORMAT_VERSION:
            raise ValueError(f"unsupported export format version {doc.get('format_version')!r} "
                             f"(expected {model.EXPORT_FORMAT_VERSION}; re-export from the mouse)")
        device = doc.get("device", {})
        return [dict(p, _device=device) for p in doc["profiles"]]
    if isinstance(doc, dict) and "dpi" in doc and "sector" in doc:
        return [doc]
    raise ValueError(f"{path}: not a profile export or a single profile with a 'sector'")


def _describe(d: dict) -> str:
    """One binding or LED zone as a short string, e.g. 'key lctrl+v'."""
    kind = d.get("type") or d.get("effect")
    rest = [f"{k}={v}" for k, v in d.items() if k not in ("type", "effect")]
    if d.get("type") == "key":
        return "key " + "+".join(d.get("modifiers", []) + [d["key"]])
    return " ".join([kind] + rest)


def _flatten(d, prefix=""):
    if isinstance(d, dict) and ("type" in d or "effect" in d):
        return {prefix: _describe(d)}
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: d}


def field_diff(old: dict, new: dict) -> list[str]:
    a, b = _flatten(old), _flatten(new)
    return [f"{k}: {a.get(k, '<absent>')!r} -> {b.get(k, '<absent>')!r}"
            for k in sorted(set(a) | set(b)) if a.get(k, "<absent>") != b.get(k, "<absent>")]


def plan_apply(profiles: list[dict], current: Backup, sectors: list[int], directory: bool = False) -> ApplyPlan:
    """Validate the chosen profiles against the mouse and work out what to write.

    Only sectors named in `sectors` are considered. A profile may only replace a
    sector that already holds a valid profile listed in the directory, so this
    never writes into an empty sector. Enable/disable changes are written to the
    directory only with `directory=True`."""
    info = current.meta["onboard_info"]
    buttons = info["button_count"]
    dir_bytes = current.sectors[SECTOR_DIRECTORY]
    dir_entries = {e.sector: e for e in parse_directory(dir_bytes)}
    by_sector = {}
    for p in profiles:
        s = p.get("sector")
        if s in by_sector:
            raise ValueError(f"profile file lists sector {s} twice")
        by_sector[s] = p

    plan = ApplyPlan()
    new_enabled = {}
    for s in sectors:
        if s == SECTOR_DIRECTORY:
            raise ValueError("the directory is not a profile; use --directory to apply enable/disable changes")
        if s not in by_sector:
            raise ValueError(f"sector {s} is not in the profile file")
        if s not in dir_entries:
            raise ValueError(f"sector {s} is not a profile in the mouse's directory (refusing to fill a new sector)")
        cur = current.sectors[s]
        if is_blank(cur) or not sector_crc_ok(cur):
            raise ValueError(f"sector {s} on the mouse is not a valid profile")
        p = by_sector[s]
        dev = p.get("_device")
        if dev:
            mine = {"product_id": f"0x{current.meta['product_id']:04X}",
                    "profile_format_id": info["profile_format_id"], "button_count": buttons}
            for k, v in mine.items():
                if dev.get(k) != v:
                    raise ValueError(f"profile file is for {k}={dev.get(k)}, this mouse has {v}")
        clean = {k: v for k, v in p.items() if k not in ("sector", "enabled", "_device")}
        try:
            new = model.encode_profile(clean, buttons, base=cur)
        except (KeyError, TypeError) as e:
            raise ValueError(f"sector {s}: missing or malformed field {e}") from e
        except ValueError as e:
            raise ValueError(f"sector {s}: {e}") from e
        if new != cur:
            plan.sectors[s] = new
            plan.field_diffs[s] = field_diff(model.decode_profile(cur, buttons), model.decode_profile(new, buttons))
        if "enabled" in p and bool(p["enabled"]) != dir_entries[s].enabled:
            new_enabled[s] = bool(p["enabled"])

    if new_enabled:
        if not directory:
            plan.notes.append(f"enabled flag differs for sectors {sorted(new_enabled)}; "
                              "ignored (pass --directory to write it)")
        else:
            d = bytearray(dir_bytes)
            for i in range(0, len(d) - 2, 4):
                num = int.from_bytes(d[i:i + 2], "big")
                if num == 0xFFFF:
                    break
                if num in new_enabled:
                    d[i + 2] = 1 if new_enabled[num] else 0
            if not any(new_enabled.get(e.sector, e.enabled) for e in dir_entries.values()):
                raise ValueError("refusing to disable every profile")
            d[-2:] = crc_ccitt(bytes(d[:-2])).to_bytes(2, "big")
            plan.sectors[SECTOR_DIRECTORY] = bytes(d)
            plan.field_diffs[SECTOR_DIRECTORY] = [f"sector {s} enabled -> {v}" for s, v in sorted(new_enabled.items())]
    return plan
