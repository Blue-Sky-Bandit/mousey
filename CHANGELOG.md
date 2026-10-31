# Changelog

## Unreleased

- Button tester reads keys by their position, so it names the right button on any keyboard
  layout (it got punctuation keys wrong on a UK layout). Key capture in the binding editor
  too.
- Key names show what the key types in the PC's layout (e.g. `#` instead of `\` on UK).
- The button tester follows the mouse when its profile button switches profile.
- Brightness 0 (stored by the factory profiles) shows as full brightness, which is how the
  mouse shows it; editing a factory profile's lighting no longer dims it to 1%.
- Fixed an occasional silent crash when Mousey closed.
- With no mouse and no backups, the window shows a "Plug in your G502 HERO" page instead of
  an empty editor and an error.

## 0.9.0 (beta), 2026-10-30

First packaged build of Mousey: a portable zip (`Mousey-0.9.0.zip`) containing the
`Mousey` folder. Extract it and run `Mousey.exe`; nothing is installed.

- Read, back up and restore the G502 HERO's onboard memory, byte for byte, with checks.
- Edit buttons (with left click locked), G-Shift or single-layer mode, DPI steps, polling
  rate, logo and DPI lighting, profile names and which profiles are active.
- Write with a plain-language preview, an automatic backup first, read-back checks, and a
  stop on the first problem. Refused while G Hub runs.
- Live status: profile in use, unplug/replug, and a banner to leave host mode.
- Profile library, copy/swap between slots, reset to factory settings.
- Backups window with a timeline of restore points and what changed in each.
- Button tester and a diagnostics report.
- Start-up splash: the FLYHT Studios animation with version and loading progress.
- Data folder is now `%APPDATA%\Mousey`; backups in the old `%APPDATA%\G502Configurator`
  folder are still listed and restorable.
- Command-line tool (`python -m g502`) for scripting and recovery.

Still to be confirmed on hardware before 1.0: see "Next testing session" in STATUS.md.
