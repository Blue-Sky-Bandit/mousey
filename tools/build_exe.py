"""Build dist/Mousey.exe: one file, no console window, icon and version info built in.

    .venv\\Scripts\\python tools\\build_exe.py

Then checks the build by running its self-test and prints the result. The self-test
loads the newest backup without showing a window; add --read-mouse to also read the
mouse (read-only).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from g502 import __version__  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"

# Qt parts Mousey doesn't use; leaving them out keeps the .exe smaller.
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


def version_tuple(v: str) -> tuple[int, int, int, int]:
    parts = [int("".join(c for c in p if c.isdigit()) or 0) for p in v.split(".")][:4]
    return tuple(parts + [0] * (4 - len(parts)))


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    version_file = BUILD / "version_info.txt"
    version_file.write_text(VERSION_INFO.format(t=version_tuple(__version__), v=__version__), encoding="utf-8")
    assets = ROOT / "g502" / "gui" / "assets"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--name", "Mousey", "--icon", str(assets / "mousey.ico"), "--version-file", str(version_file),
           "--add-data", f"{assets}{';'}g502/gui/assets", "--paths", str(ROOT),
           "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD)]
    for mod in EXCLUDES:
        cmd += ["--exclude-module", mod]
    cmd.append(str(ROOT / "packaging" / "mousey.py"))
    print("Building Mousey", __version__)
    subprocess.run(cmd, check=True, cwd=ROOT)

    exe = DIST / "Mousey.exe"
    print(f"Built {exe} ({exe.stat().st_size / 1e6:.1f} MB). Running its self-test...")
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "selftest.txt"
        extra = ["--selftest-read"] if "--read-mouse" in sys.argv else []
        code = subprocess.run([str(exe), "--selftest", str(report), *extra], timeout=120).returncode
        print(report.read_text(encoding="utf-8") if report.exists() else "(no self-test report written)")
    print("Self-test", "passed" if code == 0 else f"FAILED (exit {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
