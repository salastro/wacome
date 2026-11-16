"""Shared colors and painting helpers."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QWidget

ACCENT = QColor("#4c8dff")     # applied / active state
PENDING = QColor("#ffa62b")    # edited but not applied yet
CURSOR = QColor("#ff4d6d")     # live pen / pointer
OK = QColor("#2fbf71")
WARN = QColor("#e5534b")


def fg(w: QWidget, alpha: int = 255) -> QColor:
    c = QColor(w.palette().color(QPalette.ColorRole.WindowText))
    c.setAlpha(alpha)
    return c


def base(w: QWidget) -> QColor:
    return QColor(w.palette().color(QPalette.ColorRole.Base))


def mid(w: QWidget) -> QColor:
    return QColor(w.palette().color(QPalette.ColorRole.Mid))


def alpha(c: QColor, a: int) -> QColor:
    c = QColor(c)
    c.setAlpha(a)
    return c


def dashed(c: QColor, width: float = 2.0) -> QPen:
    p = QPen(c, width)
    p.setStyle(Qt.PenStyle.DashLine)
    return p


def painter(w: QWidget) -> QPainter:
    p = QPainter(w)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return p


def fit_scale(content_w: float, content_h: float, area: QRectF) -> tuple[float, float, float]:
    """Scale + offset to fit content (w,h) centered in area. -> (scale, ox, oy)."""
    if content_w <= 0 or content_h <= 0:
        return 1.0, area.x(), area.y()
    s = min(area.width() / content_w, area.height() / content_h)
    ox = area.x() + (area.width() - content_w * s) / 2
    oy = area.y() + (area.height() - content_h * s) / 2
    return s, ox, oy
