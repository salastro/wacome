"""Interactive pressure-curve (cubic bezier) editor."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...backend.geometry import bezier_point, curve_x_at
from ..theme import ACCENT, CURSOR, PENDING, alpha, base, dashed, fg, painter


class CurveEditor(QWidget):
    curveChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.pending = [0, 0, 100, 100]
        self.applied = [0, 0, 100, 100]
        self.marker: float | None = None   # reported pressure 0..1 from the device
        self._drag: int | None = None      # 0 = first handle, 1 = second

    def set_curves(self, pending, applied) -> None:
        self.pending, self.applied = list(pending), list(applied)
        self.update()

    def set_marker(self, pressure: float | None) -> None:
        self.marker = pressure
        self.update()

    # plot area ------------------------------------------------------------------
    def _plot(self) -> QRectF:
        side = min(self.width() - 50, self.height() - 44)
        return QRectF(40, 10, side, side)

    def _to_w(self, x, y) -> QPointF:
        r = self._plot()
        return QPointF(r.x() + x / 100 * r.width(), r.bottom() - y / 100 * r.height())

    def _from_w(self, pt: QPointF) -> tuple[int, int]:
        r = self._plot()
        x = (pt.x() - r.x()) / r.width() * 100
        y = (r.bottom() - pt.y()) / r.height() * 100
        return round(min(max(x, 0), 100)), round(min(max(y, 0), 100))

    def _handles(self):
        x1, y1, x2, y2 = self.pending
        return [self._to_w(x1, y1), self._to_w(x2, y2)]

    def mousePressEvent(self, e):
        for i, h in enumerate(self._handles()):
            if (h - e.position()).manhattanLength() < 16:
                self._drag = i
                return

    def mouseMoveEvent(self, e):
        if self._drag is None:
            near = any((h - e.position()).manhattanLength() < 16 for h in self._handles())
            self.setCursor(Qt.CursorShape.OpenHandCursor if near else Qt.CursorShape.ArrowCursor)
            return
        x, y = self._from_w(e.position())
        c = list(self.pending)
        c[self._drag * 2], c[self._drag * 2 + 1] = x, y
        self.pending = c
        self.update()
        self.curveChanged.emit(c)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def _path(self, curve) -> QPainterPath:
        path = QPainterPath(self._to_w(0, 0))
        for i in range(1, 65):
            path.lineTo(self._to_w(*bezier_point(i / 64, curve)))
        return path

    def paintEvent(self, _):
        p = painter(self)
        r = self._plot()
        p.fillRect(r, base(self))
        p.setPen(QPen(fg(self, 30), 1))
        for i in range(1, 4):
            p.drawLine(self._to_w(i * 25, 0), self._to_w(i * 25, 100))
            p.drawLine(self._to_w(0, i * 25), self._to_w(100, i * 25))
        p.setPen(QPen(fg(self, 100), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.setPen(dashed(fg(self, 70), 1))
        p.drawLine(self._to_w(0, 0), self._to_w(100, 100))

        small = QFont(self.font())
        small.setPointSizeF(max(self.font().pointSizeF() - 1, 7))
        p.setFont(small)
        p.setPen(fg(self, 160))
        p.drawText(QRectF(r.x(), r.bottom() + 4, r.width(), 18), Qt.AlignmentFlag.AlignCenter,
                   "how hard you press →")
        p.save()
        p.translate(r.x() - 8, r.bottom())
        p.rotate(-90)
        p.drawText(QRectF(0, -18, r.height(), 18), Qt.AlignmentFlag.AlignCenter, "pressure apps receive →")
        p.restore()

        changed = self.pending != self.applied
        if changed:
            p.setPen(QPen(alpha(ACCENT, 140), 2))
            p.drawPath(self._path(self.applied))

        col = PENDING if changed else ACCENT
        x1, y1, x2, y2 = self.pending
        h1, h2 = self._handles()
        p.setPen(QPen(fg(self, 90), 1))
        p.drawLine(self._to_w(0, 0), h1)
        p.drawLine(self._to_w(100, 100), h2)
        p.setPen(QPen(col, 3))
        p.drawPath(self._path(self.pending))
        p.setPen(QPen(base(self), 2))
        p.setBrush(col)
        for h in (h1, h2):
            p.drawEllipse(h, 7, 7)

        if self.marker is not None:
            y = self.marker * 100
            x = curve_x_at(self.applied, y)
            pt = self._to_w(x, y)
            p.setPen(dashed(alpha(CURSOR, 160), 1))
            p.drawLine(QPointF(r.x(), pt.y()), pt)
            p.drawLine(QPointF(pt.x(), r.bottom()), pt)
            p.setPen(QPen(base(self), 2))
            p.setBrush(CURSOR)
            p.drawEllipse(pt, 6, 6)
            p.setPen(CURSOR)
            p.drawText(QPointF(r.x() + 4, pt.y() - 4), f"{y:.0f}%")
        p.setPen(fg(self, 120))
        p.drawText(QRectF(r.right() - 160, r.bottom() - 22, 156, 18),
                   Qt.AlignmentFlag.AlignRight, f"PressureCurve {x1} {y1} {x2} {y2}")
        p.end()
