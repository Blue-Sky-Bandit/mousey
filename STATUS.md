# Status

## Progress

| Phase | State |
|---|---|
| 1. Connect and read-only | **Done** (2026-10-29) |
| 2. Backup and restore | **Done** (2026-10-29): backup verified; restore proven by changing sector 3 and reverting it byte-for-byte. Directory write and unplug persistence not yet exercised |
| 3. Parse and export | **Done** (2026-10-29): byte-exact decode/encode of all 10 user + factory profiles; `export` command |
| 4. Edit and write | **In progress**: `apply` built; physical mapping confirmed on profile 3 and restored; confirmed names and single-layer mode built (export format 2). Next: real edits, one approved write at a time |
| 5. GUI | **In progress**: Mousey (PySide6) built; first write from it (user) persisted across unplug; live profile tracking added |
| 6. Packaging | **In progress**: portable one-folder zip `dist\Mousey-0.9.0.zip` builds and passes its self-test (window + read-only mouse read); README, MIT LICENSE, CHANGELOG done; video splash waiting on the user's file; installer deferred; GitHub release not done (needs the user's account) |

## Next testing session (user away 2026-10-30; built and tested offline only)

Do these in Mousey with G Hub closed. Each write gets the normal preview; the app takes a
backup before every write.

1. **Single-layer key on sniper:** G-Shift off, sniper → a key (e.g. F). Write, then check
   it types in Notepad (or the Button tester).
2. **G-Shift with a second-layer action:** G-Shift on (sniper holds it), set one G-Shift
   action (e.g. thumb back → Ctrl+C). Write, hold sniper and check it.
3. **DPI change:** change a DPI level on the profile in use; check the feel and the DPI
   lights stepping.
4. **Button tester:** More → Button tester (or Buttons tab → Test buttons…). Check each
   button ticks its row; check **wheel tilt left/right are reported the right way round**
   (the left/right direction from Windows is a guess in the code).
5. **Copy / swap:** copy one profile to another and swap two; write and check on the mouse.
6. **Factory reset:** reset a spare profile to factory, write, and check it. Factory
   profiles store lighting brightness **0** for the colour cycle; see what the lights do
   (off? full?) and note it.
7. **Mode guard:** only if the mouse is ever found in host mode (e.g. after G Hub): the
   app shows a banner with **Switch to onboard memory**; that switch has never been run
   on this mouse. CLI equivalent: `python -m g502 set-mode onboard`.
8. **Restore from the app:** Restore backup… → pick the latest full backup → restore.
9. **Power-up profile:** unplug and replug a couple of times from different profiles;
   does it always start on profile 1?
10. **Packaged app:** extract `dist\Mousey-0.9.0.zip` somewhere (e.g. Documents) and run
    `Mousey\Mousey.exe` without the venv: check the icon in the title bar and taskbar, the
    start-up speed, that it reads the mouse, and do one small write and a restore. Also try
    double-clicking `Mousey.exe` inside the zip without extracting, to see what Windows
    shows (expected: an error from the launcher, since `_internal` isn't next to it).
11. **Backups window:** open Backups…, check the timeline makes sense, restore an older
    point to a spare profile, and check the new backup appears at the top.
12. **Diagnostics:** More → Save diagnostics…, check the file reads sensibly.

## How to run

```
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m g502 info
.venv\Scripts\python -m g502 dump [-q] [-o dump.json]
.venv\Scripts\python -m g502 export [-o profiles\mouse-export.json]
.venv\Scripts\python -m g502 gui [--backup FILE] [--theme light|dark]
.venv\Scripts\python -m pytest -q
```

`info`, `dump`, `backup` and `export` are read-only. CLI uses `argparse` (no extra deps, simpler for PyInstaller).
HID library is the `hidapi` PyPI package (Cython, hidapi statically linked into the
`.pyd` on Windows — no separate DLL to bundle).

## Phase 2: backup and restore

Commands (`g502/backup.py`, wired into the CLI):

```
python -m g502 backup [--dir D]                 # read-only
python -m g502 verify-backup A.json B.json ...  # offline
python -m g502 restore FILE --dry-run [--sectors 6]
python -m g502 restore FILE [--sectors 6] [--yes]   # WRITES
```

- **Backup** reads every sector that answers: user 0x0000–0x000F (16, including blank ones)
  and ROM 0x0100–0x0105 (probed upwards until the first error). Metadata: product ID/name,
  firmware, full onboard info (incl. profile format, sector size), onboard mode, current
  profile, timestamp, tool version, backup format. Each sector stores status + SHA-256.
  Default folder `%APPDATA%\G502Configurator\backups`.
- Probing showed nothing else is readable (0x0010+, 0x0106+, 0x0200, 0x0300, 0x0400,
  0x0800, 0x1000, 0x8000 all return InvalidArgument).
- **Verify**: SHA-256 per sector, size, CRC on every non-blank user sector, directory only
  points at valid profiles, and pairwise byte comparison. Blank (all FF / all 00) and ROM
  sectors carry no CRC by design and are reported as such, not as failures.
- **Restore** safety: refuses if the backup fails validation, if product/firmware/onboard
  info differ from the mouse, or if `lghub.exe`/`lghub_agent.exe` is running. Never writes
  ROM sectors (≥0x0100) or anything outside 0..sector_count-1. Takes and saves a fresh
  backup immediately before writing. Default plan = only sectors that differ; `--sectors`
  forces specific ones (for no-op tests). Order: data sectors ascending, **directory last**.
  Each sector: write → read back → compare; first error or mismatch stops everything, with
  no retries, and reports which sectors were already written.
- Write sequence (per libratbag): fn 6 MEMORY_ADDR_WRITE `[sector BE, offset 0, length BE]`,
  fn 7 MEMORY_WRITE ×16 (16-byte chunks), fn 8 MEMORY_WRITE_END. **Not yet exercised on
  hardware.**

Verified backups (2026-10-29), byte-identical, 22 sectors each:
- `g502-backup-20261029-082724-624652.json`
- `g502-backup-20261029-082725-514325.json`

Dry runs: `--sectors 6` and `--sectors 3` each plan a single identical-bytes rewrite; a full
restore plans nothing (mouse already matches).

### Write test 1 — sector 6 no-op (2026-10-29 08:30): **rejected by the mouse, no damage**

- MEMORY_ADDR_WRITE and all 16 MEMORY_WRITE chunks were accepted; **MEMORY_WRITE_END
  (fn 8) returned HardwareError (0x04)**. Restore stopped, nothing further attempted.
- Post-failure backup `g502-backup-20261029-083048-756313.json` is byte-identical (22
  sectors) to the pre-write backup `...083041-226756.json` and the verified backups.
  Mode still onboard, current profile 4, DPI index 1.
- Most likely explanation: the firmware buffers the sector and **validates the CRC at
  WRITE_END**, committing nothing if it fails. Sector 6 is all FF, so its "CRC" is FF FF
  ≠ CRC of the data. Consistent with libratbag always appending a CRC. Not yet proven —
  a write with a valid CRC (sector 3 no-op) would confirm it.
- Consequence: **blank sectors can't be restored by writing them.**

### Write test 2 — sector 3 no-op (2026-10-29 09:01): **success**

- Full sequence (ADDR_WRITE, 16 × WRITE, WRITE_END) accepted; read-back byte-identical.
- Pre-write backup `...090104-092084.json`; fresh post-write backup `...090112-753203.json`.
  Both are byte-identical (22 sectors) to the verified original `...082725-514325.json`.
- Mouse still onboard mode, profile 4, DPI index 1.
- Supports the test-1 explanation: WRITE_END commits only sectors with a valid CRC.
  (A no-op still can't prove the bytes were committed; that needs test 3.)

### Write test 3 — real change and revert: **success** (2026-10-29 09:06–09:08)

- **Step B succeeded.** Pre-write backup `...090801-906728.json`. Read-back matched; fresh
  backup `...090808-709467.json` is byte-identical (22 sectors) to the original verified
  backup `...082725-514325.json`. Name back to `PROFILE_NAME_DEFAULT`. Mode onboard,
  profile 4, DPI index 1. **Restore is proven: change a sector, restore it, get the
  original bytes back.**
- Still open: persistence across unplug/replug (not tested; the change was reverted).


- **Step A succeeded.** Pre-write backup `...090603-294710.json`. Read-back matched; an
  independent fresh backup `...090611-332164.json` differs from the original only in sector
  3, which equals the test file. The profile name on the mouse is now `PROFILE_NAME_DEFAULX`.
  Mode onboard, profile 4, DPI index 1. **The write path really commits data.**
- Not yet checked: that the change survives unplugging the mouse (flash vs RAM cache).
- Step B live dry run: writes sector 3 only, reverting 0xC6 `X`→`T` and CRC C739→FE7E. A
  full restore without `--sectors` plans the same single sector.

- Test file `experiments/sector3-name-change.json` (outside the backups folder, gitignored):
  copy of `...090112-753203.json` with sector 3 byte 0xC6 changed `T`→`X` (profile name
  "PROFILE_NAME_DEFAULT" → "PROFILE_NAME_DEFAULX"), CRC recomputed FE7E → C739. Only
  bytes 0xC6, 0xFE, 0xFF differ.
- Step A: `restore experiments/sector3-name-change.json --sectors 3`, read back, confirm the
  change stuck. Step B: `restore <...090112-753203.json> --sectors 3`, confirm byte-identical
  to the original. Each step needs approval; step B gets a live dry run after step A.

### Blank-sector rule (implemented after test 1)

- The restore planner **skips blank sectors** (all FF or all 00) in the backup and says so
  in the dry-run output. Therefore **a restore can never return a sector to blank** — if
  data ever lands in an empty sector, restoring an old backup will not remove it.
- So **nothing should ever write data into an empty sector unless we've explicitly decided
  to.** The planner also skips sectors that are blank on the mouse unless
  `--allow-fill-empty` is passed.
- **Never use sector 6 or any empty sector for tests**: profile 1's G-Shift bindings point
  at sector 6.

Caveat: a no-op rewrite proves the write commands are accepted and nothing is damaged, but
cannot prove bytes were actually committed (an ignored write reads back the same).
A real-change test is needed later (e.g. change one byte in an unused sector, then restore).

## Device findings (confirmed on hardware)

- **USB**: VID 0x046D, **PID 0xC08B** (confirmed). Product string "G502 HERO Gaming Mouse".
- **Windows HID layout**: HID++ is on usage page 0xFF00 of interface 1, split into two
  collections — usage 0x01 (short, 7 B) and usage 0x02 (long, 20 B). Each needs its own
  handle. We send long reports only; replies arrive on the long handle.
- **Device index** 0xFF works (wired).
- **HID++ protocol** 4.2.
- **Firmware**: main `U1 27.03.B0010`, bootloader `BOT81.00.B0002`.
- **Lighting feature is 0x8070 (Color LED Effects) v3.** 0x8071 is not present.
- Feature table (index → ID):

  | idx | ID | name |
  |---|---|---|
  | 0 | 0x0000 | Root |
  | 1 | 0x0001 | Feature Set |
  | 2 | 0x8070 | Color LED Effects (v3) |
  | 3 | 0x0003 | Device FW Version |
  | 4 | 0x0005 | Device Name |
  | 5 | 0x1300 | LED Control |
  | 6–9 | 0x18A1, 0x1E00, 0x1E22, 0x1EB0 | hidden/internal |
  | 10 | 0x2201 | Adjustable DPI (v1) |
  | 11 | 0x8060 | Report Rate |
  | 12 | 0x8100 | Onboard Profiles (v0) |
  | 13 | 0x8110 | Mouse Button Spy |
  | 14–18 | 0x00C2, 0x1801, 0x1802, 0x1806, 0x18B1 | DFU / internal |

- **Onboard profile info** (0x8100 fn 0): memory model 1, **profile format 2**, macro
  format 1, 5 profiles (5 OOB), **11 buttons**, 16 sectors, **sector size 256**,
  mechanical layout 0x0A, various info 0x01.
- Current state: **onboard mode**, current profile 4, DPI index 1.

## Memory layout (from dump `tests/fixtures/g502_dump_initial.json`)

- Sector 0x0000: profile directory. 4-byte entries `[sector_hi, sector_lo, enabled, 0]`,
  terminated by `FF FF`. Currently sectors 1–5, all enabled.
- Sectors 0x0001–0x0005: user profiles.
- Sector 0x0006: erased (all FF). **Note:** profile 1's G-shift table (0x60–0x8B) has
  entries `00 06 00 xx` that look like macro pointers into sector 6 — which is blank.
  Needs checking during Phase 3; backups must include sector 6 regardless.
- Sectors 0x0007–0x000F: read back all 0x00 (probably unused/unbacked).
- Sectors 0x0100–0x0105: factory ROM. 0x0100 is a ROM directory/info block containing the
  firmware string `U127.03_B0010`; 0x0101–0x0105 are factory default profiles. **ROM sectors
  carry no CRC** (trailing bytes FF FF).
- Reads past the sector end are rejected; the last 16-byte chunk is read end-aligned.
- Reading an invalid sector (0x7F00) returns HID++ error InvalidArgument — error path works.

## CRC

**Confirmed:** CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), over the first
`sector_size - 2` bytes, stored big-endian in the last 2 bytes. Matches all 6 written user
sectors (directory + 5 profiles).

## Phase 3: profile format 2 decode (implemented in `g502/model.py`)

Layout matches libratbag's `union hidpp20_internal_profile`. Confirmed by: every user
profile (sectors 1–5) and every factory profile (0x0101–0x0105) decodes with no raw
fallback and re-encodes **byte-identical** (factory ones without a CRC, which ROM lacks).

| offset | field | notes |
|---|---|---|
| 0x00 | report rate | byte = 1000 / Hz (1 = 1000 Hz; 2 = 500 Hz seen in ROM) |
| 0x01 / 0x02 | default / shift DPI index | index into the DPI list |
| 0x03–0x0C | 5 × DPI, little-endian | 0 = unused slot |
| 0x0D–0x1F | profile colour, power mode, angle snapping, reserved, timeouts | unused on this wired mouse; kept under `advanced` |
| 0x20–0x5F | 16 bindings (11 used) | slots 11–15 all FF |
| 0x60–0x9F | 16 G-Shift bindings | |
| 0xA0–0xCF | name, UTF-16LE, 24 chars, 00-padded | factory profiles: all FF (no name) |
| 0xD0–0xE5 | LED zones: `logo_led`, `dpi_leds` (11 B each) | |
| 0xE6–0xFB | alternate LEDs | all FF; exported only if not |
| 0xFC–0xFD | free | `00 FF` on most, `FF FF` on profile 1; preserved |
| 0xFE–0xFF | CRC | |

**Bindings** (4 bytes): `FF FF FF FF` disabled · `80 01 <mask BE>` mouse buttons ·
`80 02 <mods> <HID key>` keyboard · `80 03 <usage BE>` consumer · `90 <code> <arg>` special ·
`00 <sector> 00 <offset>` macro. Specials: 01 wheel left, 02 wheel right, 03 DPI up, 04 DPI
down, 05 DPI cycle, 06 DPI default, 07 DPI shift, 08/09 profile next/prev, 0A profile cycle,
0B G-Shift, 0C battery. User profiles use arg `00 00`, ROM uses `FF FF`; both preserved.

**Button names** (confirmed on the mouse 2026-10-29, both layers), in slot order: `left`,
`right`, `middle` (wheel click), `thumb_back` (rear thumb), `thumb_forward` (front thumb),
`sniper`, `dpi_down`, `dpi_up`, `profile_switch` (button behind the wheel),
`wheel_tilt_right`, `wheel_tilt_left`. The G-Shift table uses the same order. LED zone
names: `logo_led` (zone 0), `dpi_leds` (zone 1). Export format_version 2 uses these
names; version-1 files (old names `back`/`forward`/`zone0`/`zone1`) are refused with a
hint to re-export.

**LEDs** (11 bytes): `00` off · `01 RGB` fixed · `03 …5×00 period(BE) brightness` cycle ·
`0A RGB period(BE) waveform brightness` breathing. **Confirmed 2026-10-29:** zone 0 is
the logo, zone 1 is the DPI indicator lights. Factory profiles have brightness 0, user
profiles 100; what 0 means is not confirmed.

**Safety of the model**: any field whose decoding would not re-encode exactly (unknown
binding type, unknown LED effect, odd padding) is kept as raw hex, so export → encode never
loses bytes. Encoding validates report rate (125/250/500/1000), DPI count and range, that
DPI indexes are in range, colours, key names, name length, and that all 11 buttons exist.

### Export

```
python -m g502 export [-o FILE] [--from-backup BACKUP.json] [--include-rom]
```

Read-only. Without `--from-backup` it reads the mouse. `profiles/mouse-export.json` holds
the current profiles; re-encoding every profile in it gives the original backup bytes.

Current profiles on the mouse:

| sector | name | DPI (default bold) | shift | lighting | notable buttons |
|---|---|---|---|---|---|
| 1 | PROFILE_NAME_DEFAULT | 1200, 2400, 3200, **3750**, 6400 | 1200 | fixed #FBC900 | back Ctrl+V, forward Ctrl+C, sniper Enter, dpi_down mouse 4, dpi_up Win+Tab |
| 2 | PROFILE_NAME_DEFAULT | 1200, **2400**, 3200, 6400 | 1200 | cycle 8 s | game keys 1 r f 2 g 3 c |
| 3 | PROFILE_NAME_DEFAULT | 1200, **2400**, 3200, 6400 | 1200 | cycle 8 s | factory layout |
| 4 | Finals (active) | 1200, **2400**, 3200, 6400 | 1200 | fixed #F82F25 | punctuation keys |
| 5 | PROFILE_NAME_DEFAULT | 1200, **2400**, 3200, 6400 | 1200 | fixed #00FFFF | punctuation keys |

All profiles: 1000 Hz, profile_switch = profile cycle, wheel tilt = horizontal scroll.

**Finding:** profile 1's G-Shift table binds all 11 buttons to macros in sector 6
(offsets 0, 2, … 20), but sector 6 is empty. Export flags this as a warning. Profile 1 has
no button bound to G-Shift, so those bindings are probably unreachable anyway. The macro
format (offset units, macro encoding) is not decoded; macros are a non-goal in the spec.

## Phase 4: apply

```
python -m g502 apply FILE --sectors 3 [--directory] --dry-run
python -m g502 apply FILE --sectors 3 [--directory] [--yes]   # WRITES
```

- FILE is an export file or a single profile object with a `sector` key.
- `--sectors` is required: only the named profiles are considered.
- Refuses: the directory as a profile; any sector not already a valid profile in the
  mouse's directory (never fills an empty sector); a file for a different product /
  profile format / button count; invalid values (via `model.encode_profile`).
- Enable/disable changes only reach the directory with `--directory`, written last, and
  disabling every profile is refused.
- Dry run prints field-level changes plus the byte diff. Writes use the same path as
  restore: G Hub check, fresh pre-write backup, one sector at a time with read-back,
  stop on first failure.

Mapping test files (in `experiments/`, built from the live export of 2026-10-29):
- `p3-led1-zone0-red.json`: profile 3 zone0 fixed #FF0000 (zone1 unchanged, cycle).
- `p3-led2-zone0-red-zone1-blue.json`: zone0 red, zone1 fixed #0000FF.
- `p3-btn1-main-letters.json`: main layer right→b, middle→c, back→d, forward→e,
  sniper→f, dpi_down→g, dpi_up→h, profile_switch→i, wheel_tilt_right→j,
  wheel_tilt_left→k; left unchanged; G-Shift layer unchanged. Lighting back to base.
- `p3-btn2-gshift-letters.json`: as btn1 but main sniper→G-Shift; G-Shift layer right→m,
  middle→n, back→o, forward→p, sniper→q (unreachable while sniper is held), dpi_down→r,
  dpi_up→s, profile_switch→t, wheel_tilt_right→u, wheel_tilt_left→v; left unchanged.
  Rebuild if btn1 shows sniper is not slot 5.

Sequence: LED1 → LED2 → BTN1 → BTN2 → restore sector 3 from
`g502-backup-20261029-090808-709467.json`, each write approved separately. LED2 is
written while profile 3 is active, which shows whether the mouse picks up a write to the
active profile without switching (matters once the profile button is remapped).

Results:
- LED1 (2026-10-29, pre-write backup `g502-backup-20261029-093353-219963.json`): the logo
  turned red on profile 3. Zone 0 = logo.
- LED2 (pre-write backup `g502-backup-20261029-133332-790528.json`), written while
  profile 3 was active: the DPI lights turned blue immediately, logo stayed red. Zone 1 =
  DPI indicator. **A write to the active profile takes effect at once, no profile switch
  needed.**
- Note: HID++ get-current-profile does reflect switches made with the profile button.
- BTN1 (pre-write backup `g502-backup-20261029-133644-435346.json`): every slot typed its
  own letter and matched the factory-derived names. Main-layer map, slot → physical:
  0 left = left click (by elimination) · 1 right = right click (b) · 2 middle = wheel
  click (c) · 3 back = rear thumb button (d) · 4 forward = front thumb button (e) ·
  5 sniper = sniper button (f) · 6 dpi_down = DPI button (g) · 7 dpi_up = DPI button (h)
  · 8 profile_switch = button behind the wheel (i) · 9 wheel_tilt_right (j) ·
  10 wheel_tilt_left (k). The user confirmed the DPI-up button typed h (slot 7 = dpi_up).
- BTN2 (pre-write backup `g502-backup-20261029-134236-098155.json`): main sniper set to
  G-Shift. Holding sniper, every G-Shift slot typed its own letter, in the same slot order
  as the main layer: right m, middle n, back (rear thumb) o, forward (front thumb) p,
  dpi_down r, dpi_up s, wheel_tilt_right u, wheel_tilt_left v. G-Shift table at 0x60 uses
  the same slot indexes as the main table at 0x20. Not letter-tested: G-Shift left
  (unchanged by design), sniper (held), profile_switch (kept as profile cycle at user's
  request).
- User request: the button behind the wheel stays as profile switching, so BTN2 was
  rebuilt with profile_switch = profile_cycle on both layers (its G-Shift slot is then
  not letter-tested; slot layout is the same table at 0x60).

- Restore (pre-write backup `g502-backup-20261029-200957-589155.json`): sector 3 written
  back from `g502-backup-20261029-090808-709467.json` and verified. Fresh backup
  `g502-backup-20261029-201003-462531.json` is byte-identical to the original-state
  backup in all 22 sectors. Mouse: onboard mode, profile 3, DPI index 1.
  **Mapping complete.**

Mapping is confirmed, so profiles 1, 4 and the directory are no longer off-limits for
mapping reasons (every write still needs a dry run and approval).

### Requirement: single-layer mode (user request, 2026-10-29)

The user wants to be able to turn the G-Shift layer off per profile and use single-layer
mode, with an ordinary key/action assigned to the button that would otherwise be G-Shift.
The firmware has no G-Shift on/off flag: the layer is reachable only while some main-layer
button is bound to the `gshift` special. **Built** (model + apply, tested offline):
- Profile JSON gets `gshift_layer: true|false`, derived on export (true if any main
  binding is `gshift`).
- `false` + a main binding of `gshift` is a validation error, and so is `true` with no
  `gshift` binding (layer unreachable). Leaving `gshift_layer` out skips the check. The
  GUI (Phase 5) should hide the G-Shift tab when it is off.
- When off, the G-Shift table bytes are left as they are on the mouse (unreachable, so
  harmless), so turning the layer back on brings the old bindings back. Profile 1's
  table points at macros in empty sector 6; preserving it avoids touching that.
- With `false`, `gshift_buttons` may be left out of the file; `apply` then copies the
  G-Shift table from the sector on the mouse unchanged. If it is present it is written
  as given (still unreachable).
- Export warns about G-Shift macros pointing at empty sectors as "unreachable anyway"
  when the layer is off.


## Phase 5: GUI (`g502/gui/`, PySide6)

**Name: Mousey, by FLYHT Studios** (working name chosen by the user). Icon: the user's
artwork (grey top-down gaming mouse on a yellow tile, black outlines) with the Logitech G
replaced by a yellow "A" (no Logitech branding), stored as
`g502/gui/assets/mousey-source.png`; `tools/make_icon.py` builds `mousey.ico` (16–256 px)
and `mousey-256.png` from it. App accent colour is the icon's yellow (#FDDC01, black text).
The window sets its own Windows AppUserModelID (`FLYHTStudios.Mousey`) so the taskbar
shows the Mousey icon instead of grouping it under python.exe.

Live tracking: every 1.5 s the app asks the mouse which profile is active (read-only) and
moves the Active label; if the mouse is unplugged it says so and blocks writing, and when
it is plugged back in it re-reads automatically (unless there are unsaved edits). All
device access (check, read, write) goes through one lock (`session.DEVICE_LOCK`). Reads
that time out are retried once after 1.5 s. Mouse nickname is stored in app settings
(QSettings, FLYHT Studios/Mousey) because the mouse can't store one.

Toolkit: PySide6, chosen by the user for a polished look (over Tkinter). Installed as
`PySide6-Essentials` only (no WebEngine/PDF add-ons) to keep the Phase 6 .exe smaller.

- Window: profile list (lighting dots, active badge, `•` for unsaved changes), tabs for
  Buttons, DPI, Lighting, Profile; footer with change count, undo, **Write to mouse…**.
  Follows the Windows light/dark setting (`--theme` overrides).
- Buttons tab: table of main + G-Shift actions, click to edit (mouse click, keyboard key
  with modifiers or "Record a key", media key, DPI/profile/scroll functions, G-Shift, do
  nothing; macros/unknown kept as is). G-Shift switch implements single-layer mode: on
  assigns G-Shift to sniper if no button has it; off puts the holder's previous action
  back and hides the column. Warns if no button is Left click.
- Write: plans with `apply.plan_apply` against a **fresh read**, then a confirmation
  dialog lists every change in words (decoded from the bytes that will be written) with
  byte-level details on request. Writing is blocked while G Hub runs. `session.execute`
  re-reads the mouse and refuses if it changed since the preview, saves the pre-write
  backup, writes with read-back, stops at the first failure.
- Restore backup: pick a file, tick which differing parts to restore, same confirmation.
- Viewing a backup file (no mouse): editing and preview work, writing is disabled.
- Import/export JSON (format 2), Back up now, open backups folder.
- **First GUI write (user, 2026-10-29 20:45):** profile 3 logo → solid #FF00FF, pre-write
  backup `g502-backup-20261029-204523-538060.json`. After unplug/replug the user saw no
  change, but a read-only backup (`g502-backup-20261029-205010-260180.json`) shows sector 3
  still holds the new colour, the only difference from the pre-write backup. **Writes
  survive power loss.** The mouse came back up on **profile 1** (DPI index 3 = profile 1's
  default), not profile 3, so the change wasn't visible. Whether it always powers up on
  profile 1 is not confirmed.
- The first read right after replugging failed with "No reply to feature index 0x0C
  function 5" (memory read timeout); the next reads worked. Likely the mouse still
  starting up.
- **Windows Dynamic Lighting overrides the onboard lighting.** With Settings →
  Personalization → Dynamic Lighting on for the mouse (via `logi_lamparray_service`),
  the profile's colours show briefly after a profile switch, then Windows repaints them
  (yellow on this PC). The stored profile is unaffected. The user turned it off
  (2026-10-29). The Lighting tab now says so.
- **Breathing lighting works** (user confirmed 2026-10-30): profile 3 DPI lights set to
  breathing #FF00FF, 4 s, from Mousey.
- **Profile deactivation works** (user, 2026-10-29, from Mousey): the profile list
  (sector 0, first write to it) was written with a profile's enabled byte set to 0 and the
  profile button skipped that profile; re-activating restored it. Mousey refuses to
  deactivate the profile in use (checked again against a fresh read before writing).
- Device name: only 0x0005 Device Name (read-only) is present; there is no 0x0007 Friendly
  Name, so the mouse itself can't be renamed. Profile names (24 chars) are writable.
- Not yet: a write made from the GUI (first one should be a small change with approval),
  app icon, the clickable mouse picture.

**Left click lock** (user decision, 2026-10-29): in Mousey the main-layer left button can't
be changed while it is Left click (shown as "Left click 🔒"); its G-Shift-layer action can.
Library loads and JSON imports whose main-layer left button isn't Left click are refused.
If a profile on the mouse ever has left click remapped (e.g. by the CLI), the lock doesn't
apply, so it can be fixed in Mousey. The CLI stays unrestricted.

### Mode guard, button tester, copy/swap, factory reset (2026-10-30, offline only)

- **Mode guard:** `OnboardProfiles.set_mode()` (fn 1; 1 = onboard, 2 = host). The app checks
  the mode on every read and in the 1-second status check; if it isn't onboard it shows a
  banner with **Switch to onboard memory** (confirmation, refused while G Hub runs). CLI:
  `g502 set-mode onboard`. Never run on the mouse yet.
- **Button tester** (`g502/gui/tester.py`): a pad that receives mouse buttons, keys, wheel
  tilt and media keys, and ticks the profile's buttons whose action matches. DPI, profile
  and G-Shift actions are marked "inside the mouse" since the PC sees nothing. Tilt
  direction mapping (Qt horizontal wheel sign) is unverified.
- **Copy / swap** (Profile tab): copy this profile's settings to another slot, or swap two;
  same rules as library loads (left click lock, hidden G-Shift table kept when single-layer,
  Active status stays with the slot).
- **Factory reset** (Profile tab): replaces the slot with a decoded factory profile from ROM
  (0x101–0x105), including its G-Shift table, advanced bytes and blank name; sector and
  Active status kept. Factory profile 3 differs from the others (G-Shift layer, rate).

### Profile library (`g502/library.py`, Library tab)

- Saved profiles live in `%APPDATA%\G502Configurator\library\*.json`
  (format `mousey-library-profile` v1): title, description, created, and the profile's
  name, polling rate, DPI, buttons, G-Shift layer (+ G-Shift table only when on) and
  lighting. Any number can be kept; the mouse still has 5 slots.
- Loading an entry or preset into a slot is an ordinary edit (preview + write as usual).
  The slot keeps its sector, active flag, `advanced` bytes, and its hidden G-Shift table
  when the loaded profile is single-layer, so no unseen bytes change.
- No built-in presets: the user builds the library themselves (built-in game presets were
  tried and removed at the user's request, 2026-10-29).
- Mouse's profile list re-read 2026-10-29 after the deactivation tests: all 5 active.

## Phase 6: packaging and tidy-up (2026-10-30)

- **Data folder:** `%APPDATA%\Mousey\backups` and `\library` for everything new. The old
  `%APPDATA%\G502Configurator` folders are still read (backups list, timeline, latest
  backup, library) but never written, moved or cleaned up. Backups now record why they
  were made (`reason`: manual / before-write / before-restore).
- **Backups window** (`g502/timeline.py`, `g502/gui/timeline_dialog.py`; header button
  "Backups…"): every backup on a vertical timeline grouped by day, with what changed since
  the one before (same wording as the write preview, via `session.describe_sector_change`),
  which one matches the mouse now, and Restore / Show in folder / Open another file.
- **Diagnostics** (`g502/diagnostics.py`; More → Save diagnostics…, `g502 diagnostics`):
  versions, folders, Logitech processes, mouse state with sector status and SHA-256
  prefixes, recent errors. No profile contents or backups.
- **Code tidy-up:** `gui/app.py` (1,180 lines) split into `app.py` (window and state),
  `common.py`, `sidebar.py`, `editor.py` (editing tabs), `device_ops.py` (status checks,
  read, write, restore), `profile_tools.py` (tester, copy/swap/reset, library, JSON).
  `pyproject.toml` with ruff config; `ruff check .` is clean. The CLI write flow was left as
  it is (hardware-proven) rather than moved onto `session.execute`.
- **Packaging (decided 2026-10-30): portable one-folder zip.** `tools/build_exe.py`
  builds `dist\Mousey\` (`Mousey.exe` + `_internal\`, plus `START HERE.txt` and
  `LICENSE.txt`) with PyInstaller (windowed, icon, FLYHT Studios version info, unused Qt
  modules excluded), runs `Mousey.exe --selftest` (`--read-mouse` adds a read-only mouse
  read), and only then zips it as `dist\Mousey-<version>.zip` with a single `Mousey` folder
  at the top. 0.9.0: folder ≈ 94 MB, zip ≈ 37 MB; extracted from the zip it builds its
  window in 0.8 s. Chosen over the one-file .exe because nothing is unpacked at each
  launch (faster start, a video splash can show first, fewer antivirus false positives).
- **Installer: not now, kept as an option.** The one-folder build is exactly what an
  installer (e.g. Inno Setup: Program Files, Start menu, uninstaller) would package, so
  it can be added later without changing the app.
- **Splash (planned, waiting on the user's video):** the user is making a video splash
  with space left for the version and a loading bar/status. Plan: the user exports it as
  an animated WebP (Qt plays it with what's already bundled; MP4 would need Qt
  Multimedia + FFmpeg, roughly +50–100 MB); Mousey shows it in a borderless window as soon
  as Qt starts and draws the version and progress into the reserved area. Still needed
  from the user: the file, its size, where the reserved area is, and whether it plays once
  or loops until Mousey is ready. Nothing built for it yet.
- **Running from inside the zip** can't be caught by Mousey: the launcher fails to find
  `_internal` before any of Mousey's code runs. Covered by `START HERE.txt` and the README.
- **Docs:** README.md (features, safety, troubleshooting incl. Dynamic Lighting and host
  mode, CLI, building), LICENSE (MIT, FLYHT Studios), CHANGELOG.md.
- **Branding check:** no Logitech logos; Logitech is named only to say which mouse it is
  for, in the "not affiliated" notice, and in technical identifiers (USB vendor ID,
  G Hub process names). The user's icon had a Logitech G, replaced by an "A".
- **Not done:** GitHub repository and release (needs the user's account; nothing pushed).

## Environment notes

- G Hub: only `lghub_updater.exe` was running (not `lghub.exe` / `lghub_agent.exe`).
  `logi_lamparray_service` is also running — may matter for lighting later.
- Python 3.11.9 in `.venv` (chosen over 3.14 for PyInstaller compatibility).
