# Changelog

## 0.9.0 (beta), 2026-10-30

First packaged build of Mousey (`Mousey.exe`).

- Read, back up and restore the G502 HERO's onboard memory, byte for byte, with checks.
- Edit buttons (with left click locked), G-Shift or single-layer mode, DPI steps, polling
  rate, logo and DPI lighting, profile names and which profiles are active.
- Write with a plain-language preview, an automatic backup first, read-back checks, and a
  stop on the first problem. Refused while G Hub runs.
- Live status: profile in use, unplug/replug, and a banner to leave host mode.
- Profile library, copy/swap between slots, reset to factory settings.
- Backups window with a timeline of restore points and what changed in each.
- Button tester and a diagnostics report.
- Data folder is now `%APPDATA%\Mousey`; backups in the old `%APPDATA%\G502Configurator`
  folder are still listed and restorable.
- Command-line tool (`python -m g502`) for scripting and recovery.

Still to be confirmed on hardware before 1.0: see "Next testing session" in STATUS.md.
