"""Build the portable release: dist/Mousey/ (Mousey.exe + _internal) and dist/Mousey-<version>.zip.

    .venv\\Scripts\\python tools\\build_exe.py [--read-mouse]

One-folder build: it starts quickly because nothing is unpacked at launch, and the same
folder can go into an installer later. After building, it runs the app's self-test, which
builds the window from the newest backup without showing it; --read-mouse also reads the
mouse (read-only). The zip is only made if the self-test passes.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from g502 import __version__  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"
APP_DIR = DIST / "Mousey"

# Parts Mousey doesn't use; leaving them out keeps the download smaller.
EXCLUDES = ["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql",
            "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtDBus", "PySide6.QtOpenGL", "PySide6.QtPrintSupport",
            "PySide6.QtConcurrent", "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtDesigner"]

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'FLYHT Studios'),
      StringStruct('FileDescription', 'Mousey: onboard profile editor for the G502 HERO (unofficial)'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'Mousey'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 FLYHT Studios. MIT licence.'),
      StringStruct('OriginalFilename', 'Mousey.exe'),
      StringStruct('ProductName', 'Mousey'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

START_HERE = """Mousey {v} by FLYHT Studios
================================

Mousey runs from this folder; nothing is installed.

1. If you're looking at this inside the zip, extract it first:
   right-click the zip > Extract All..., and choose a folder to keep it in.
   (Running Mousey.exe from inside the zip doesn't work.)
2. Run Mousey.exe from the extracted Mousey folder.
   The first time, Windows may say "Windows protected your PC" because the app isn't
   code-signed: click "More info", then "Run anyway".
3. Optional: right-click Mousey.exe > Pin to Start (or Pin to taskbar).

Keep Mousey.exe and the _internal folder together. To update, replace this folder with the
new one. Your backups and library are kept in %APPDATA%\\Mousey and aren't affected.
To remove Mousey, delete this folder.

Mousey is unofficial and isn't affiliated with or endorsed by Logitech. MIT licence.
"""


def version_tuple(v: str) -> tuple[int, int, int, int]:
    parts = [int("".join(c for c in p if c.isdigit()) or 0) for p in v.split(".")][:4]
    return tuple(parts + [0] * (4 - len(parts)))


def build() -> None:
    BUILD.mkdir(exist_ok=True)
    (DIST / "Mousey.exe").unlink(missing_ok=True)      # left over from the old one-file build
    version_file = BUILD / "version_info.txt"
    version_file.write_text(VERSION_INFO.format(t=version_tuple(__version__), v=__version__), encoding="utf-8")
    assets = ROOT / "g502" / "gui" / "assets"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
           "--name", "Mousey", "--icon", str(assets / "mousey.ico"), "--version-file", str(version_file),
           "--add-data", f"{assets};g502/gui/assets", "--paths", str(ROOT),
           "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD)]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    cmd.append(str(ROOT / "packaging" / "mousey.py"))
    print("Building Mousey", __version__)
    subprocess.run(cmd, check=True, cwd=ROOT)
    (APP_DIR / "START HERE.txt").write_text(START_HERE.format(v=__version__), encoding="utf-8")
    shutil.copy(ROOT / "LICENSE", APP_DIR / "LICENSE.txt")


def selftest() -> int:
    exe = APP_DIR / "Mousey.exe"
    size = sum(f.stat().st_size for f in APP_DIR.rglob("*") if f.is_file())
    print(f"Built {APP_DIR} ({size / 1e6:.0f} MB). Running its self-test...")
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "selftest.txt"
        extra = ["--selftest-read"] if "--read-mouse" in sys.argv else []
        code = subprocess.run([str(exe), "--selftest", str(report), *extra], timeout=120).returncode
        print(report.read_text(encoding="utf-8") if report.exists() else "(no self-test report written)")
    print("Self-test", "passed" if code == 0 else f"FAILED (exit {code})")
    return code


def make_zip() -> Path:
    """Zip with the Mousey folder at the top, so Extract All gives one tidy folder."""
    path = DIST / f"Mousey-{__version__}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(APP_DIR.rglob("*")):
            if f.is_file():
                z.write(f, Path("Mousey") / f.relative_to(APP_DIR))
    print(f"Zipped {path} ({path.stat().st_size / 1e6:.0f} MB)")
    return path


def main() -> int:
    build()
    code = selftest()
    if code == 0:
        make_zip()
    return code


if __name__ == "__main__":
    sys.exit(main())
