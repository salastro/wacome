"""Scratch pad that renders pen input: pressure, tilt, tool and buttons."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPointingDevice
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..theme import ACCENT, CURSOR, alpha, base, fg, painter
from .penstate import pen_state

_QT_TO_X = {
    Qt.MouseButton.LeftButton: 1,
    Qt.MouseButton.MiddleButton: 2,
    Qt.MouseButton.RightButton: 3,
    Qt.MouseButton.BackButton: 8,
    Qt.MouseButton.ForwardButton: 9,
}

BAR_W = 26


class TestCanvas(QWidget):
    pressureSample = Signal(float)     # 0..1, None-like -1 when lifted

    def __init__(self, parent=None, hint: str = "Draw here with the pen"):
        super().__init__(parent)
        self.setMinimumSize(200, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TabletTracking)
        self.hint = hint
        self._pix = QPixmap()
        self._last: QPointF | None = None
        self._last_w = 1.0
        self.pressure = 0.0
        self.tilt = (0.0, 0.0)
        self.tool = "stylus"
        self.hovering = False
        self.empty = True
        self.last_button: int | None = None

    def clear(self) -> None:
        self._pix.fill(Qt.GlobalColor.transparent)
        self.empty = True
        self.update()

    def _ensure_pix(self) -> None:
        size = self.size() * self.devicePixelRatioF()
        if self._pix.size() != size:
            old = self._pix
            self._pix = QPixmap(size)
            self._pix.setDevicePixelRatio(self.devicePixelRatioF())
            self._pix.fill(Qt.GlobalColor.transparent)
            if not old.isNull():
                QPainter(self._pix).drawPixmap(0, 0, old)

    def _stroke(self, pt: QPointF, pressure: float) -> None:
        self._ensure_pix()
        w = 1 + pressure * 22
        p = QPainter(self._pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.tool == "eraser":
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            pen = QPen(Qt.GlobalColor.black, w * 1.5)
        else:
            c = QColor(fg(self))
            c.setAlphaF(0.35 + 0.65 * pressure)
            pen = QPen(c, (w + self._last_w) / 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if self._last is None:
            p.drawPoint(pt)
        else:
            p.drawLine(self._last, pt)
        p.end()
        self._last, self._last_w = pt, w
        self.empty = False

    def _press_button(self, qt_button) -> None:
        n = _QT_TO_X.get(qt_button)
        if n:
            self.last_button = n
            pen_state().buttonPressed.emit(n)

    # --- events --------------------------------------------------------------------
    def tabletEvent(self, e):
        st = pen_state()
        st.set_proximity(True)
        self.tool = "eraser" if e.pointerType() == QPointingDevice.PointerType.Eraser else "stylus"
        self.tilt = (e.xTilt(), e.yTilt())
        t = e.type()
        if t == QEvent.Type.TabletPress:
            self._press_button(e.button())
            self._last = None
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.pressure = e.pressure()
            self._stroke(e.position(), self.pressure)
        else:
            self.pressure = 0.0
            self._last = None
        if t == QEvent.Type.TabletRelease:
            self._last = None
            self.pressure = 0.0
        self.hovering = True
        st.pressure, st.tool = self.pressure, self.tool
        st.sample.emit(self.pressure, self.tool, int(e.buttons().value), *self.tilt)
        self.pressureSample.emit(self.pressure)
        e.accept()
        self.update()

    def mousePressEvent(self, e):
        self._press_button(e.button())
        self._last = None
        if e.button() == Qt.MouseButton.LeftButton:
            self.pressure = 0.5
            self._stroke(e.position(), 0.5)
            self.update()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._stroke(e.position(), 0.5)
            self.update()

    def mouseReleaseEvent(self, _):
        self._last = None
        self.pressure = 0.0
        self.update()

    def leaveEvent(self, _):
        self.hovering = False
        self.pressureSample.emit(-1.0)
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._ensure_pix()

    # --- painting ------------------------------------------------------------------
    def paintEvent(self, _):
        p = painter(self)
        canvas = QRectF(self.rect()).adjusted(0, 0, -BAR_W - 6, 0)
        p.setPen(QPen(fg(self, 60), 1))
        p.setBrush(base(self))
        p.drawRoundedRect(canvas.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.save()
        p.setClipRect(canvas)
        if not self._pix.isNull():
            p.drawPixmap(0, 0, self._pix)
        p.restore()
        if self.empty:
            p.setPen(fg(self, 90))
            p.drawText(canvas, Qt.AlignmentFlag.AlignCenter, self.hint)

        small = QFont(self.font())
        small.setPointSizeF(max(self.font().pointSizeF() - 1, 7))
        p.setFont(small)
        p.setPen(fg(self, 150))
        info = f"{'Eraser' if self.tool == 'eraser' else 'Pen tip'}   tilt {self.tilt[0]:+.0f}° {self.tilt[1]:+.0f}°"
        if self.last_button:
            info += f"   last button: {self.last_button}"
        p.drawText(canvas.adjusted(8, 4, -8, -4), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, info)

        # pressure bar
        bar = QRectF(self.width() - BAR_W, 0, BAR_W, self.height() - 18)
        p.setPen(QPen(fg(self, 60), 1))
        p.setBrush(base(self))
        p.drawRoundedRect(bar, 4, 4)
        h = bar.height() * self.pressure
        fill = QRectF(bar.x() + 3, bar.bottom() - 3 - max(h - 6, 0), bar.width() - 6, max(h - 6, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(CURSOR if self.pressure > 0.95 else ACCENT)
        p.drawRoundedRect(fill, 3, 3)
        p.setPen(fg(self, 160))
        p.drawText(QRectF(bar.x() - 6, bar.bottom(), bar.width() + 12, 18), Qt.AlignmentFlag.AlignCenter,
                   f"{self.pressure * 100:.0f}%")

        # tilt gauge
        if self.hovering and (self.tilt[0] or self.tilt[1]):
            c = QPointF(canvas.right() - 30, canvas.top() + 30)
            p.setPen(QPen(fg(self, 60), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, 20, 20)
            p.setPen(QPen(alpha(CURSOR, 220), 3))
            p.drawLine(c, c + QPointF(self.tilt[0] / 60 * 20, self.tilt[1] / 60 * 20))
        p.end()
