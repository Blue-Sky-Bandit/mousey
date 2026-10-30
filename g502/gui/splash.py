"""Start-up splash: the FLYHT Studios animation with Mousey's version and loading progress.

The animation always plays to the end (about 4 s) and then holds its last frame; the
splash closes only once the animation has finished and loading is done.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QMovie, QPainter
from PySide6.QtWidgets import QWidget

from .. import __version__
from .common import APP_NAME, ASSETS

SPLASH_FILE = ASSETS / "splash.webp"
SIZE = (640, 360)
CYAN = QColor("#7FE8FF")
# The bottom of the animation is dark; the overlay sits there.
STATUS_RECT = QRectF(140, 294, 360, 20)
BAR_RECT = QRectF(140, 320, 360, 4)
VERSION_RECT = QRectF(12, 336, 300, 18)


class Splash(QWidget):
    finished = Signal()        # animation done and loading done: time to show the window

    def __init__(self, path=SPLASH_FILE):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(*SIZE)
        self.setWindowTitle(APP_NAME)
        self.status = "Starting…"
        self.loaded = False
        self.played = False
        self._started = time.monotonic()
        self.movie = QMovie(str(path))
        self.movie.setCacheMode(QMovie.CacheAll)
        self.frames = max(self.movie.frameCount(), 1)
        self.duration = self.frames * 1000 / 30          # ms; the file is 30 fps
        # Frames are picked by the clock rather than QMovie's own timer, which drifts
        # (~15% slow here), so the animation lasts its real 4 seconds.
        self._tick = QTimer(self, interval=15, timeout=self._advance)

    def start(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.show()
        self._started = time.monotonic()
        if self.movie.isValid():
            self.movie.jumpToFrame(0)
        else:                                            # missing or broken file: don't block start-up
            QTimer.singleShot(0, self._played)
        self._tick.start()

    def set_status(self, text: str) -> None:
        self.status = text
        self.update()

    def set_loaded(self, text: str = "Ready") -> None:
        self.loaded = True
        self.set_status(text)
        self._maybe_finish()

    def progress(self) -> float:
        """Loading bar position: follows the animation's time, and only reaches the end
        once loading is done too."""
        elapsed = (time.monotonic() - self._started) * 1000
        fraction = min(elapsed / self.duration, 1.0)
        return fraction if self.loaded else min(fraction, 0.92)

    def _advance(self) -> None:
        if self.movie.isValid() and not self.played:
            target = min(int((time.monotonic() - self._started) * 1000 / self.duration * self.frames),
                         self.frames - 1)
            while self.movie.currentFrameNumber() < target and self.movie.jumpToNextFrame():
                pass
            self._frame(self.movie.currentFrameNumber())
        self.update()

    def _frame(self, n: int) -> None:
        self.update()
        if n >= self.frames - 1 and not self.played:
            self._played()                               # hold the lit sign; don't loop

    def _played(self) -> None:
        self.played = True
        self._maybe_finish()

    def _maybe_finish(self) -> None:
        if self.played and self.loaded:
            self._tick.stop()
            self.update()
            QTimer.singleShot(150, self.finished.emit)   # let the full bar be seen

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        frame = self.movie.currentPixmap()
        if frame.isNull():
            p.fillRect(self.rect(), Qt.black)
        else:
            p.drawPixmap(0, 0, frame)
        f = QFont(self.font())
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor(230, 240, 255, 210))
        p.drawText(STATUS_RECT, Qt.AlignCenter, self.status)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(BAR_RECT, 2, 2)
        p.setBrush(CYAN)
        p.drawRoundedRect(QRectF(BAR_RECT.x(), BAR_RECT.y(), BAR_RECT.width() * self.progress(),
                                 BAR_RECT.height()), 2, 2)
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 150))
        p.drawText(VERSION_RECT, Qt.AlignLeft | Qt.AlignVCenter, f"{APP_NAME} {__version__}")
        p.end()
