# Mousey

**by FLYHT Studios**

Mousey edits the onboard memory of a wired **Logitech G502 HERO** mouse: buttons, DPI,
lighting and profiles. The settings live on the mouse itself, so they keep working on any
PC without Mousey or any other software running.

> Mousey is unofficial and open source. It is not made, endorsed or supported by Logitech.
> "Logitech", "G502" and "HERO" are trademarks of their owners and are used here only to
> say which mouse Mousey works with.

## What it does

- **Buttons:** set any button to a mouse click, a keyboard key or shortcut, a media key,
  DPI up/down/shift, profile switching, horizontal scroll, or nothing. Left click is
  locked so a profile can never leave you without one.
- **G-Shift:** optionally give a button the G-Shift role for a second layer of actions,
  or keep a simple single-layer profile.
- **DPI:** up to five DPI steps, the default step and the sniper (DPI shift) step, and the
  polling rate.
- **Lighting:** logo and DPI lights, each off, a solid colour, breathing or a colour cycle.
- **Profiles:** five on the mouse. Rename them, deactivate the ones the profile button
  should skip, copy or swap them, or reset one to the mouse's factory settings.
- **Library:** save as many profiles as you like on the PC and load them into any slot.
- **Backups:** a timeline of restore points with what changed in each; restore any of them.
- **Live status:** shows which profile is in use and notices when the mouse is unplugged.
- **Button tester:** press buttons and see which action the PC receives.

## Safety

Every write to the mouse:

1. shows a preview listing each change in plain words, and nothing is written until you
   confirm;
2. is refused while G Hub is running (it can overwrite the mouse's profiles);
3. re-reads the mouse and stops if it changed since the preview;
4. saves a full backup of the mouse first;
5. writes one part at a time, reads each part back to check it, and stops at the first
   problem without trying again.

Mousey never writes to the mouse's empty memory areas, and the factory profiles are
read-only on the mouse.

## Requirements

- Windows 10 or 11
- A **wired** Logitech G502 HERO (USB ID 046D:C08B)
- G Hub closed while Mousey writes (it may stay installed)

## Getting started

Mousey is portable: nothing is installed.

1. Download `Mousey-<version>.zip` from the releases page.
2. Right-click it → **Extract All…** and pick a folder to keep it in. (Running it from
   inside the zip doesn't work: Windows says "This application may depend on other
   compressed files in this folder…". Choose **Extract all**.)
3. Run `Mousey.exe` in the extracted `Mousey` folder. The first time, Windows may say
   "Windows protected your PC" because the app isn't code-signed: click **More info →
   Run anyway**. Optionally right-click `Mousey.exe` → **Pin to Start**.
4. Mousey reads the mouse when it opens. Pick a profile on the left and change things in
   the Buttons, DPI, Lighting and Profile tabs.
5. Press **Write to mouse…**, check the preview, and confirm.

Keep `Mousey.exe` and its `_internal` folder together. To update, replace the folder with
the new one; to remove Mousey, delete the folder.

Your data is kept in `%APPDATA%\Mousey` (`backups` and `library`). Backups made by earlier
versions in `%APPDATA%\G502Configurator` are still shown and can still be restored.

## Troubleshooting

- **Colours change a moment after switching profiles:** Windows Dynamic Lighting is
  painting over them. Turn it off for the mouse in Settings → Personalization → Dynamic
  Lighting.
- **"The mouse is in host mode":** other software (usually G Hub) told the mouse to ignore
  its stored profiles. Quit G Hub, then press **Switch to onboard memory** in Mousey.
- **"The mouse didn't answer":** it may still be starting up after being plugged in. Wait
  a few seconds and press Read from mouse.
- **Reporting a problem:** More → Save diagnostics… creates a text file with versions,
  settings folders and the mouse's state (no profile contents or backups) to attach.

## Command line

The same engine is available as a command-line tool, useful for scripting and recovery:

```
python -m g502 info                 # device, firmware, mode, profile in use
python -m g502 backup               # save a full backup
python -m g502 verify-backup FILE…  # check backups and compare them
python -m g502 restore FILE --dry-run
python -m g502 export -o profiles.json
python -m g502 apply profiles.json --sectors 3 --dry-run
python -m g502 set-mode onboard     # leave host mode
python -m g502 diagnostics
python -m g502 gui                  # the Mousey window
```

Commands that write always show a dry run and ask for confirmation unless `--yes` is given.

## Building from source

```
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m g502 gui
```

Development tools: `pip install pytest ruff pyinstaller`, then

```
.venv\Scripts\python -m pytest          # tests (no mouse needed)
.venv\Scripts\python -m ruff check .    # lint
.venv\Scripts\python tools\build_exe.py # build dist\Mousey\ + Mousey-<version>.zip, self-tested
.venv\Scripts\python tools\make_icon.py # rebuild the icon files from mousey-source.png
```

`STATUS.md` records how the mouse's memory works, what has been confirmed on hardware and
what still needs testing.

## Licence

MIT. See [LICENSE](LICENSE).
