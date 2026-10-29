"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, apply, backup, model
from .device import Device, DeviceNotFound, FeatureMissing
from .hidpp import HidppError
from .onboard import ROM_SECTOR_BASE, SECTOR_DIRECTORY, OnboardProfiles, parse_directory, sector_crc_ok


def hexdump(data: bytes, width: int = 16) -> str:
    return "\n".join(
        f"  {off:04X}: " + " ".join(f"{b:02X}" for b in data[off:off + width])
        for off in range(0, len(data), width)
    )


def cmd_info(dev: Device, args) -> None:
    proto = dev.ping()
    print(f"Tool version:   {__version__}")
    print(f"Device:         {dev.get_name()} (PID 0x{dev.info.product_id:04X})")
    print(f"HID++ protocol: {proto[0]}.{proto[1]}")
    for fw in dev.get_firmware():
        print(f"Firmware:       {fw['type']:<10} {fw['version']}")
    print("Features:")
    for f in dev.list_features():
        print(f"  [{f.index:2d}] 0x{f.feature_id:04X} v{f.version}  {f.name}")
    try:
        ob = OnboardProfiles(dev)
    except FeatureMissing as e:
        print(f"Onboard profiles: unavailable ({e})")
        return
    print("Onboard profiles:")
    for k, v in ob.info.to_dict().items():
        print(f"  {k:<18} {v}")
    print(f"  {'mode':<18} {ob.get_mode()}")
    print(f"  {'current profile':<18} {ob.get_current_profile()}")
    print(f"  {'current dpi index':<18} {ob.get_current_dpi_index()}")


def read_all_sectors(ob: OnboardProfiles) -> dict[int, bytes | str]:
    """Read the directory, every user sector and the factory ROM profiles.
    Values are bytes, or an error string if the sector couldn't be read."""
    sectors: list[int] = list(range(SECTOR_DIRECTORY, ob.info.sector_count))
    sectors += [ROM_SECTOR_BASE + i for i in range(ob.info.profile_count_oob + 1)]
    out: dict[int, bytes | str] = {}
    for s in sectors:
        try:
            out[s] = ob.read_sector(s)
        except (HidppError, TimeoutError) as e:
            out[s] = str(e)
    return out


def cmd_dump(dev: Device, args) -> None:
    ob = OnboardProfiles(dev)
    sectors = read_all_sectors(ob)

    directory = sectors.get(SECTOR_DIRECTORY)
    if isinstance(directory, bytes):
        print(f"Profile directory (sector 0x0000, CRC {'ok' if sector_crc_ok(directory) else 'BAD'}):")
        for e in parse_directory(directory):
            print(f"  sector 0x{e.sector:04X}  {'enabled' if e.enabled else 'disabled'}  raw {e.raw.hex(' ')}")
        print()

    for num, data in sectors.items():
        if isinstance(data, str):
            print(f"Sector 0x{num:04X}: unreadable ({data})\n")
            continue
        blank = all(b == 0xFF for b in data) or all(b == 0x00 for b in data)
        crc = "blank" if blank else ("CRC ok" if sector_crc_ok(data) else "CRC BAD")
        print(f"Sector 0x{num:04X} ({crc}):")
        if not args.quiet:
            print(hexdump(data))
        print()

    if args.out:
        path = Path(args.out)
        path.write_text(json.dumps({
            "tool_version": __version__,
            "created": datetime.now().isoformat(timespec="seconds"),
            "product_id": dev.info.product_id,
            "firmware": dev.get_firmware(),
            "onboard_info": ob.info.to_dict(),
            "sectors": {f"0x{n:04X}": (d.hex() if isinstance(d, bytes) else None) for n, d in sectors.items()},
        }, indent=2))
        print(f"Saved dump to {path.resolve()}")


def print_backup_summary(b: backup.Backup) -> None:
    counts: dict[str, list[str]] = {}
    for n, d in sorted(b.sectors.items()):
        counts.setdefault(backup.sector_status(n, d), []).append(f"0x{n:04X}")
    for status, nums in counts.items():
        print(f"  {status:<8} {len(nums):2d}: {' '.join(nums)}")


def cmd_backup(dev: Device, args) -> None:
    ob = OnboardProfiles(dev)
    b = backup.take_backup(dev, ob)
    path = backup.save_backup(b, Path(args.dir) if args.dir else backup.default_backup_dir())
    print(f"Backed up {len(b.sectors)} sectors ({len(b.user_sectors())} user, {len(b.rom_sectors())} ROM):")
    print_backup_summary(b)
    problems = backup.check_backup(b)
    for p in problems:
        print(f"  WARNING: {p}")
    print(f"Saved to {path}")


def cmd_verify_backup(args) -> int:
    loaded = [backup.load_backup(Path(p)) for p in args.files]
    ok = True
    for b in loaded:
        print(f"{b.path}  (created {b.meta['created']}, fw {b.meta['firmware'][0]['version']})")
        print_backup_summary(b)
        for p in backup.check_backup(b):
            print(f"  PROBLEM: {p}")
            ok = False
    for other in loaded[1:]:
        diffs = backup.compare_backups(loaded[0], other)
        if diffs:
            ok = False
            print(f"{loaded[0].path.name} vs {other.path.name}: DIFFERENT")
            for d in diffs:
                print(f"  {d}")
        else:
            print(f"{loaded[0].path.name} vs {other.path.name}: byte-identical ({len(other.sectors)} sectors)")
    print("RESULT: OK" if ok else "RESULT: FAILED")
    return 0 if ok else 1


def parse_sectors(text: str) -> list[int]:
    return [int(s, 0) for s in text.replace(" ", "").split(",") if s]


def cmd_restore(dev: Device, args) -> int:
    source = backup.load_backup(Path(args.file))
    problems = backup.check_backup(source)
    if problems:
        print("Refusing: backup failed validation:")
        for p in problems:
            print(f"  {p}")
        return 1

    running = backup.ghub_running()
    if running and not args.dry_run:
        print(f"Refusing: G Hub is running ({', '.join(running)}) and can overwrite onboard profiles. Quit it first.")
        return 1

    ob = OnboardProfiles(dev)
    print("Reading current mouse contents...")
    current = backup.take_backup(dev, ob)
    problems = backup.compatibility_problems(source, current)
    if problems:
        print("Refusing: backup does not match this mouse:")
        for p in problems:
            print(f"  {p}")
        return 1

    result = backup.plan_restore(source, current, parse_sectors(args.sectors) if args.sectors else None,
                                 allow_fill_empty=args.allow_fill_empty)
    plan = result.write
    print(f"{'DRY RUN - ' if args.dry_run else ''}Restore from {source.path}")
    for s, reason in result.skipped.items():
        print(f"Skipping sector 0x{s:04X}: {reason}")
    if not plan:
        print("Nothing to write: the mouse already matches the backup.")
        return 0
    print(f"Sectors to write, in order: {', '.join(f'0x{s:04X}' for s in plan)}")
    for s in plan:
        old, new = current.sectors[s], source.sectors[s]
        status = backup.sector_status(s, new)
        if old == new:
            print(f"\nSector 0x{s:04X} ({status}): identical to mouse - no-op rewrite of {len(new)} bytes")
        else:
            print(f"\nSector 0x{s:04X} ({status}): differs from mouse")
            print("\n".join(backup.diff_lines(old, new)))

    if args.dry_run:
        print("\nDry run: nothing was written.")
        return 0

    if not args.yes:
        answer = input(f"\nType WRITE to write {len(plan)} sector(s) to the mouse: ")
        if answer.strip() != "WRITE":
            print("Aborted: nothing was written.")
            return 1

    safety = backup.save_backup(current, Path(args.dir) if args.dir else backup.default_backup_dir())
    print(f"\nPre-write backup of the mouse saved to {safety}")
    try:
        backup.execute_restore(ob, source, plan)
    except backup.RestoreFailed as e:
        print(f"\nRESTORE STOPPED: {e}")
        print(f"Sectors fully written and verified before the failure: "
              f"{', '.join(f'0x{s:04X}' for s in e.written) or 'none'}")
        print(f"No further writes were attempted. Pre-write backup: {safety}")
        return 1
    print(f"\nRestore complete: {len(plan)} sector(s) written and verified.")
    return 0


def print_profile_summary(doc: dict) -> None:
    for p in doc["profiles"]:
        dpi = p["dpi"]
        lv = dpi["levels"]
        levels = ", ".join(f"[{v}]" if i == dpi["default_index"] else str(v) for i, v in enumerate(lv))             if isinstance(lv, list) else "raw"
        shift = lv[dpi["shift_index"]] if isinstance(lv, list) and dpi["shift_index"] < len(lv) else "?"
        leds = " / ".join(z.get("color", z["effect"]) if z["effect"] == "fixed" else z["effect"]
                          for z in p["lighting"].values())
        print(f"Sector {p['sector']} ({'enabled' if p['enabled'] else 'disabled'}): {p['name']!r}")
        print(f"  {p['report_rate_hz']} Hz | DPI {levels} | shift {shift} | lighting {leds}")
    for w in doc.get("warnings", []):
        print(f"WARNING: {w}")


def export_doc(dev: Device | None, args) -> dict:
    if args.from_backup:
        src = backup.load_backup(Path(args.from_backup))
    else:
        src = backup.take_backup(dev, OnboardProfiles(dev))
    return model.build_export(src, include_rom=args.include_rom)


def cmd_export(dev: Device | None, args) -> int:
    doc = export_doc(dev, args)
    text = json.dumps(doc, indent=2)
    if args.out:
        Path(args.out).write_text(text)
        print_profile_summary(doc)
        print(f"Saved to {Path(args.out).resolve()}")
    else:
        print(text)
    return 0


def cmd_apply(dev: Device, args) -> int:
    profiles = apply.load_profiles(Path(args.file))
    running = backup.ghub_running()
    if running and not args.dry_run:
        print(f"Refusing: G Hub is running ({', '.join(running)}) and can overwrite onboard profiles. Quit it first.")
        return 1
    ob = OnboardProfiles(dev)
    print("Reading current mouse contents...")
    current = backup.take_backup(dev, ob)
    try:
        plan = apply.plan_apply(profiles, current, parse_sectors(args.sectors), directory=args.directory)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1

    print(f"{'DRY RUN - ' if args.dry_run else ''}Apply {args.file} to sector(s) {args.sectors}")
    for n in plan.notes:
        print(f"Note: {n}")
    if not plan.sectors:
        print("Nothing to write: the mouse already matches.")
        return 0
    print(f"Sectors to write, in order: {', '.join(f'0x{s:04X}' for s in plan.order)}")
    for s in plan.order:
        print(f"\nSector 0x{s:04X} changes:")
        for line in plan.field_diffs[s]:
            print(f"  {line}")
        print("  bytes:")
        print("\n".join(backup.diff_lines(current.sectors[s], plan.sectors[s], label="new")))

    if args.dry_run:
        print("\nDry run: nothing was written.")
        return 0
    if not args.yes:
        answer = input(f"\nType WRITE to write {len(plan.order)} sector(s) to the mouse: ")
        if answer.strip() != "WRITE":
            print("Aborted: nothing was written.")
            return 1

    safety = backup.save_backup(current, Path(args.dir) if args.dir else backup.default_backup_dir())
    print(f"\nPre-write backup of the mouse saved to {safety}")
    target = backup.Backup(current.meta, plan.sectors)
    try:
        backup.execute_restore(ob, target, plan.order)
    except backup.RestoreFailed as e:
        print(f"\nAPPLY STOPPED: {e}")
        print(f"Sectors written and verified before the failure: "
              f"{', '.join(f'0x{s:04X}' for s in e.written) or 'none'}")
        print(f"No further writes were attempted. Pre-write backup: {safety}")
        return 1
    print(f"\nApply complete: {len(plan.order)} sector(s) written and verified.")
    return 0


def cmd_set_mode(dev: Device, args) -> int:
    running = backup.ghub_running()
    if running:
        print(f"Refusing: G Hub is running ({', '.join(running)}) and would switch it back. Quit it first.")
        return 1
    ob = OnboardProfiles(dev)
    print(f"Current mode: {ob.get_mode()}")
    if not args.yes:
        if input(f"Type YES to switch the mouse to {args.mode} mode: ").strip() != "YES":
            print("Aborted: nothing was changed.")
            return 1
    ob.set_mode(args.mode)
    print(f"Mode is now: {ob.get_mode()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="g502", description="Unofficial G502 HERO onboard profile tool")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="show device, firmware, features and onboard profile info")

    d = sub.add_parser("dump", help="dump all onboard profile sectors as hex (read-only)")
    d.add_argument("-o", "--out", help="also save the dump as JSON to this file")
    d.add_argument("-q", "--quiet", action="store_true", help="only print sector status, not hex")

    b = sub.add_parser("backup", help="save every readable sector plus metadata to a timestamped file")
    b.add_argument("--dir", help=f"backup folder (default {backup.default_backup_dir()})")

    v = sub.add_parser("verify-backup", help="validate backup files and check they are byte-identical")
    v.add_argument("files", nargs="+")

    r = sub.add_parser("restore", help="write a backup back to the mouse, byte for byte")
    r.add_argument("file")
    r.add_argument("--dry-run", action="store_true", help="show what would be written and the diff; write nothing")
    r.add_argument("--sectors", help="only these user sectors, e.g. '6' or '3,4' (written even if identical)")
    r.add_argument("--allow-fill-empty", action="store_true",
                   help="allow writing data into a sector that is currently blank on the mouse")
    r.add_argument("--yes", action="store_true", help="skip the interactive WRITE confirmation")
    r.add_argument("--dir", help="where to save the automatic pre-write backup")

    e = sub.add_parser("export", help="decode the onboard profiles to readable JSON (read-only)")
    e.add_argument("-o", "--out", help="write JSON here (default: print to the console)")
    e.add_argument("--from-backup", help="decode a backup file instead of reading the mouse")
    e.add_argument("--include-rom", action="store_true", help="also decode the factory default profiles")

    a = sub.add_parser("apply", help="write an edited profile file to the mouse (validated, dry-run first)")
    a.add_argument("file", help="an export file, or a single profile object with a 'sector'")
    a.add_argument("--sectors", required=True, help="profile sectors to apply from the file, e.g. '3'")
    a.add_argument("--directory", action="store_true", help="also write enable/disable changes to the directory")
    a.add_argument("--dry-run", action="store_true", help="validate and show the diff; write nothing")
    a.add_argument("--yes", action="store_true", help="skip the interactive WRITE confirmation")
    a.add_argument("--dir", help="where to save the automatic pre-write backup")

    m = sub.add_parser("set-mode", help="switch the mouse back to onboard memory mode (no profile is written)")
    m.add_argument("mode", choices=["onboard"])
    m.add_argument("--yes", action="store_true", help="skip the confirmation")

    sub.add_parser("gui", help="open the desktop app (any further options go to it, e.g. --backup FILE)",
                   add_help=False)

    args, rest = p.parse_known_args(argv)
    if args.command == "gui":
        from .gui.app import main as gui_main
        return gui_main(rest)
    if rest:
        p.error(f"unrecognized arguments: {' '.join(rest)}")
    try:
        if args.command == "verify-backup":
            return cmd_verify_backup(args)
        if args.command == "export" and args.from_backup:
            return cmd_export(None, args)
        handlers = {"info": cmd_info, "dump": cmd_dump, "backup": cmd_backup, "restore": cmd_restore,
                    "export": cmd_export, "apply": cmd_apply, "set-mode": cmd_set_mode}
        with Device.open_first() as dev:
            return handlers[args.command](dev, args) or 0
    except (DeviceNotFound, FeatureMissing, HidppError, TimeoutError, OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
