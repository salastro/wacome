"""Scaled picture of the monitor layout showing where the tablet maps."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QCursor, QFont, QGuiApplication, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...backend.geometry import Rect
from ...backend.monitors import Monitor, desktop_rect
from ..theme import ACCENT, CURSOR, PENDING, alpha, base, dashed, fg, fit_scale, mid, painter
from .penstate import pen_state


class DesktopView(QWidget):
    monitorClicked = Signal(str)
    regionDrawn = Signal(object)      # Rect in X pixels
    cursorMoved = Signal(object)      # (x, y) in X pixels, or None
    geometryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.monitors: list[Monitor] = []
        self.applied: Rect | None = None
        self.pending: Rect | None = None
        self.selected_output: str | None = None
        self.hover: str | None = None
        self.cursor: tuple[float, float] | None = None
        self._drag_start: QPointF | None = None
        self._drag_now: QPointF | None = None
        self._timer = QTimer(self, interval=33, timeout=self._poll_cursor)
        self._timer.start()
        pen_state().proximityChanged.connect(lambda _: self.update())

    # --- data ---------------------------------------------------------------
    def set_monitors(self, monitors: list[Monitor]) -> None:
        self.monitors = list(monitors)
        self.update()
        self.geometryChanged.emit()

    def set_regions(self, applied: Rect | None, pending: Rect | None, selected_output: str | None) -> None:
        self.applied, self.pending, self.selected_output = applied, pending, selected_output
        self.update()
        self.geometryChanged.emit()

    # --- coordinate transforms ---------------------------------------------
    def _xf(self):
        desk = desktop_rect(self.monitors) if self.monitors else Rect(0, 0, 1920, 1080)
        area = QRectF(self.rect()).adjusted(12, 12, -12, -28)
        return fit_scale(desk.w, desk.h, area)

    def to_widget(self, r: Rect) -> QRectF:
        s, ox, oy = self._xf()
        return QRectF(ox + r.x * s, oy + r.y * s, r.w * s, r.h * s)

    def to_desktop(self, pt: QPointF) -> tuple[float, float]:
        s, ox, oy = self._xf()
        return (pt.x() - ox) / s, (pt.y() - oy) / s

    def pending_widget_rect(self) -> QRectF | None:
        return self.to_widget(self.pending) if self.pending else None

    def _monitor_at(self, pt: QPointF) -> Monitor | None:
        x, y = self.to_desktop(pt)
        return next((m for m in self.monitors if m.rect.contains(x, y)), None)

    # --- live pointer --------------------------------------------------------
    def _poll_cursor(self) -> None:
        if not self.isVisible():
            return
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        d = screen.devicePixelRatio() if screen else 1.0
        c = (pos.x() * d, pos.y() * d)
        if c != self.cursor:
            self.cursor = c
            self.cursorMoved.emit(c)
            self.update()

    # --- mouse ---------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.position()
            self._drag_now = e.position()

    def mouseMoveEvent(self, e):
        m = self._monitor_at(e.position())
        name = m.name if m else None
        if name != self.hover:
            self.hover = name
            self.update()
        if self._drag_start is not None:
            self._drag_now = e.position()
            self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag_start is None or e.button() != Qt.MouseButton.LeftButton:
            return
        a, b = self._drag_start, e.position()
        self._drag_start = self._drag_now = None
        self.update()
        if (a - b).manhattanLength() < 8:
            m = self._monitor_at(b)
            if m:
                self.monitorClicked.emit(m.name)
            return
        x1, y1 = self.to_desktop(a)
        x2, y2 = self.to_desktop(b)
        r = Rect.from_corners(x1, y1, x2, y2)
        desk = desktop_rect(self.monitors)
        r = Rect(max(r.x, 0), max(r.y, 0), r.w, r.h)
        r = Rect(r.x, r.y, min(r.w, desk.w - r.x), min(r.h, desk.h - r.y)).rounded()
        if r.w >= 32 and r.h >= 32:
            self.regionDrawn.emit(r)

    # --- painting --------------------------------------------------------------
    def paintEvent(self, _):
        p = painter(self)
        text = fg(self)
        small = QFont(self.font())
        small.setPointSizeF(max(self.font().pointSizeF() - 1, 7))

        for i, m in enumerate(self.monitors, 1):
            r = self.to_widget(m.rect).adjusted(2, 2, -2, -2)
            fill = mid(self) if m.name != self.hover else mid(self).lighter(115)
            fill.setAlpha(110)
            p.setPen(QPen(fg(self, 120), 1.5))
            p.setBrush(fill)
            p.drawRoundedRect(r, 6, 6)
            # big index number (matches "Identify" overlay)
            big = QFont(self.font())
            big.setBold(True)
            big.setPointSizeF(max(min(r.height() / 3.2, 48), 9))
            p.setFont(big)
            p.setPen(fg(self, 45))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(i))
            p.setFont(small)
            p.setPen(fg(self, 200))
            label = f"{m.name}{'  ★' if m.primary else ''}\n{int(m.rect.w)}×{int(m.rect.h)}"
            p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)

        if self.applied:
            r = self.to_widget(self.applied)
            p.setPen(QPen(ACCENT, 2.5))
            p.setBrush(alpha(ACCENT, 70))
            p.drawRect(r)
        if self.pending and self.pending != self.applied:
            r = self.to_widget(self.pending)
            p.setPen(dashed(PENDING, 2.5))
            p.setBrush(QBrush(alpha(PENDING, 45), Qt.BrushStyle.BDiagPattern))
            p.drawRect(r)
            p.setFont(small)
            p.setPen(PENDING)
            p.drawText(r.adjusted(6, 0, -6, -4), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                       "pending")

        if self._drag_start is not None and self._drag_now is not None:
            p.setPen(dashed(text, 1.5))
            p.setBrush(alpha(PENDING, 40))
            p.drawRect(QRectF(self._drag_start, self._drag_now).normalized())

        if self.cursor:
            s, ox, oy = self._xf()
            c = QPointF(ox + self.cursor[0] * s, oy + self.cursor[1] * s)
            prox = pen_state().in_proximity
            rad = 7 if prox else 4
            if prox:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(CURSOR, 60))
                p.drawEllipse(c, rad * 2.2, rad * 2.2)
            p.setPen(QPen(base(self), 1.5))
            p.setBrush(CURSOR if prox else fg(self, 160))
            p.drawEllipse(c, rad, rad)

        # legend
        p.setFont(small)
        y = self.height() - 10
        x = 12
        for color, label, style in ((ACCENT, "applied mapping", Qt.PenStyle.SolidLine),
                                    (PENDING, "pending (click Apply)", Qt.PenStyle.DashLine),
                                    (CURSOR, "pointer / pen", None)):
            if style is None:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawEllipse(QPointF(x + 6, y - 4), 4, 4)
            else:
                pen = QPen(color, 2.5)
                pen.setStyle(style)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawLine(QPointF(x, y - 4), QPointF(x + 14, y - 4))
            p.setPen(fg(self, 170))
            p.drawText(QPointF(x + 18, y), label)
            x += 26 + p.fontMetrics().horizontalAdvance(label)
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.geometryChanged.emit()
