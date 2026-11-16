"""Translucent overlays drawn on the real screens to show where things map."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...backend.geometry import Rect
from ..theme import ACCENT

_alive: list[QWidget] = []


def _dpr() -> float:
    s = QGuiApplication.primaryScreen()
    return s.devicePixelRatio() if s else 1.0


class _Overlay(QWidget):
    def __init__(self, rect: Rect, title: str, subtitle: str, color: QColor, big: bool):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        d = _dpr()
        self.setGeometry(QRect(round(rect.x / d), round(rect.y / d), round(rect.w / d), round(rect.h / d)))
        self.title, self.subtitle, self.color, self.big = title, subtitle, color, big
        self.opacity = 1.0
        self._fade = QTimer(self, interval=30, timeout=self._step)

    def run(self, ms: int) -> None:
        self.show()
        self.raise_()
        QTimer.singleShot(ms, self._fade.start)

    def _step(self) -> None:
        self.opacity -= 0.08
        if self.opacity <= 0:
            self._fade.stop()
            self.close()
            if self in _alive:
                _alive.remove(self)
        else:
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.opacity)
        c = QColor(self.color)
        c.setAlpha(60)
        p.fillRect(self.rect(), c)
        p.setPen(QPen(self.color, 8))
        p.drawRect(self.rect().adjusted(4, 4, -4, -4))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(min(self.height() / (4 if self.big else 14), 140))
        p.setFont(f)
        p.setPen(QColor("white"))
        r = self.rect()
        if self.subtitle:
            r_title = r.adjusted(0, 0, 0, -r.height() // 8)
        else:
            r_title = r
        # dark halo for legibility on any background
        p.setPen(QColor(0, 0, 0, 180))
        p.drawText(r_title.translated(2, 2), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setPen(QColor("white"))
        p.drawText(r_title, Qt.AlignmentFlag.AlignCenter, self.title)
        if self.subtitle:
            f.setPointSizeF(max(f.pointSizeF() / 3, 12))
            f.setBold(False)
            p.setFont(f)
            p.drawText(r.adjusted(0, r.height() // 2 + int(f.pointSizeF() * 2), 0, 0),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.subtitle)


def flash(rect: Rect, title: str, subtitle: str = "", color: QColor = ACCENT,
          ms: int = 900, big: bool = False) -> None:
    if rect.w < 2 or rect.h < 2:
        return
    o = _Overlay(rect, title, subtitle, color, big)
    _alive.append(o)
    o.run(ms)
