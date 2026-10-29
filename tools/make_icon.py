"""Build the multi-size Windows .ico (PNG entries) and the 256 px PNG from
g502/gui/assets/mousey-source.png (the icon artwork, transparent corners)."""
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(source: QImage, size: int) -> bytes:
    img = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def main() -> None:
    assets = Path(__file__).resolve().parent.parent / "g502" / "gui" / "assets"
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - needed for QImage/QPainter
    source = QImage(str(assets / "mousey-source.png"))
    pngs = [render(source, s) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(SIZES))
    offset = 6 + 16 * len(SIZES)
    entries, blobs = b"", b""
    for s, png in zip(SIZES, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    (assets / "mousey.ico").write_bytes(header + entries + blobs)
    (assets / "mousey-256.png").write_bytes(pngs[-1])
    print(f"wrote {assets / 'mousey.ico'}")


if __name__ == "__main__":
    main()
