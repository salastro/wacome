"""Drawing of the pen with clickable button hotspots and their actions."""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..theme import ACCENT, CURSOR, PENDING, alpha, base, fg, painter

TITLES = {
    ("stylus", "1"): "Tip",
    ("stylus", "2"): "Lower side button",
    ("stylus", "3"): "Upper side button",
    ("eraser", "1"): "Eraser",
}


class PenDiagram(QWidget):
    hotspotClicked = Signal(str, str)   # role, button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMouseTracking(True)
        self.actions: dict[tuple[str, str], tuple[str, bool]] = {}  # key -> (description, changed)
        self.has_eraser = True
        self.selected: tuple[str, str] | None = ("stylus", "3")
        self.hover: tuple[str, str] | None = None
        self._flash: dict[tuple[str, str], float] = {}
        self._timer = QTimer(self, interval=30, timeout=self._tick)

    def set_actions(self, actions: dict, has_eraser: bool) -> None:
        self.actions, self.has_eraser = actions, has_eraser
        self.update()

    def set_selected(self, key) -> None:
        self.selected = key
        self.update()

    def flash(self, key) -> None:
        self._flash[key] = time.monotonic()
        self._timer.start()

    def _tick(self) -> None:
        now = time.monotonic()
        self._flash = {k: t for k, t in self._flash.items() if now - t < 0.8}
        if not self._flash:
            self._timer.stop()
        self.update()

    # geometry ----------------------------------------------------------------------
    def _geom(self):
        W, H = self.width(), self.height()
        T = min(H * 0.16, W * 0.06)
        cy = H * 0.52
        x0, x1 = W * 0.06, W * 0.94
        L = x1 - x0
        tip_end = x0 + L * 0.13
        body_end = x1 - L * 0.07 if self.has_eraser else x1
        hot = {
            ("stylus", "1"): QRectF(x0 - 4, cy - T * 0.5, tip_end - x0 + 4, T),
            ("stylus", "2"): QRectF(x0 + L * 0.22, cy - T / 2 - T * 0.32, L * 0.08, T * 0.42),
            ("stylus", "3"): QRectF(x0 + L * 0.32, cy - T / 2 - T * 0.32, L * 0.08, T * 0.42),
        }
        if self.has_eraser:
            hot[("eraser", "1")] = QRectF(body_end, cy - T / 2, x1 - body_end, T)
        return T, cy, x0, x1, tip_end, body_end, hot

    def _hit(self, pt: QPointF):
        *_, hot = self._geom()
        for k, r in hot.items():
            if r.adjusted(-6, -6, 6, 6).contains(pt):
                return k
        for k, r in self._label_rects().items():
            if r.contains(pt):
                return k
        return None

    def _label_rects(self):
        T, cy, x0, x1, tip_end, body_end, hot = self._geom()
        W = self.width()
        lw, lh = min(W * 0.27, 210), 44
        out = {
            ("stylus", "1"): QRectF(x0, cy + T * 0.5 + 34, lw, lh),
            ("stylus", "2"): QRectF(max(hot[("stylus", "2")].center().x() - lw * 0.8, 4), 8, lw, lh),
            ("stylus", "3"): QRectF(hot[("stylus", "3")].center().x() + lw * 0.15, 8, lw, lh),
        }
        if self.has_eraser:
            out[("eraser", "1")] = QRectF(x1 - lw, cy + T * 0.5 + 34, lw, lh)
        return out

    # events ------------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        k = self._hit(e.position())
        if k != self.hover:
            self.hover = k
            self.setCursor(Qt.CursorShape.PointingHandCursor if k else Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, e):
        k = self._hit(e.position())
        if k:
            self.selected = k
            self.hotspotClicked.emit(*k)
            self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    # painting ----------------------------------------------------------------------
    def _spot_color(self, k) -> QColor:
        if k in self._flash:
            a = 1 - (time.monotonic() - self._flash[k]) / 0.8
            return alpha(CURSOR, int(80 + 175 * max(a, 0)))
        if k == self.selected:
            return ACCENT
        if self.actions.get(k, ("", False))[1]:
            return PENDING
        if k == self.hover:
            return QColor("#8a8f98")
        return QColor("#5b6068")

    def paintEvent(self, _):
        p = painter(self)
        T, cy, x0, x1, tip_end, body_end, hot = self._geom()

        # body
        grad = QLinearGradient(0, cy - T / 2, 0, cy + T / 2)
        grad.setColorAt(0, QColor("#4a4f58"))
        grad.setColorAt(0.5, QColor("#2b2e34"))
        grad.setColorAt(1, QColor("#1d1f23"))
        body = QPainterPath()
        body.addRoundedRect(QRectF(tip_end - 2, cy - T / 2, body_end - tip_end + 2, T), T / 4, T / 4)
        # tip cone
        cone = QPainterPath(QPointF(x0, cy))
        cone.lineTo(tip_end, cy - T / 2)
        cone.lineTo(tip_end, cy + T / 2)
        cone.closeSubpath()
        p.setPen(QPen(fg(self, 80), 1))
        p.setBrush(grad)
        p.drawPath(body)

        tip_col = self._spot_color(("stylus", "1"))
        p.setBrush(tip_col if tip_col != QColor("#5b6068") else QColor("#3a3d44"))
        p.drawPath(cone)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#c9ccd1"))
        p.drawEllipse(QPointF(x0 + 2, cy), 2.5, 2.5)

        # side buttons
        for k in (("stylus", "2"), ("stylus", "3")):
            r = hot[k]
            p.setPen(QPen(QColor(0, 0, 0, 120), 1))
            p.setBrush(self._spot_color(k))
            p.drawRoundedRect(r, r.height() / 2.5, r.height() / 2.5)

        if self.has_eraser:
            r = hot[("eraser", "1")]
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(-T / 4, 0, 0, 0), T / 2.2, T / 2.2)
            p.setPen(QPen(QColor(0, 0, 0, 120), 1))
            p.setBrush(self._spot_color(("eraser", "1")))
            p.drawPath(path)

        # callouts
        title_font = QFont(self.font())
        title_font.setBold(True)
        small = QFont(self.font())
        small.setPointSizeF(max(self.font().pointSizeF() - 1, 7))
        for k, lr in self._label_rects().items():
            anchor = hot[k].center()
            target = QPointF(lr.center().x(), lr.bottom() if lr.bottom() < anchor.y() else lr.top())
            col = self._spot_color(k)
            p.setPen(QPen(alpha(col, 200), 1.5))
            p.drawLine(anchor, target)
            p.setBrush(alpha(base(self), 235))
            p.drawRoundedRect(lr, 6, 6)
            desc, changed = self.actions.get(k, ("—", False))
            p.setFont(small)
            p.setPen(fg(self, 150))
            p.drawText(lr.adjusted(8, 4, -8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       TITLES[k] + ("  • edited" if changed else ""))
            p.setFont(title_font)
            p.setPen(fg(self))
            p.drawText(lr.adjusted(8, 0, -8, -5), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                       p.fontMetrics().elidedText(desc, Qt.TextElideMode.ElideRight, int(lr.width() - 16)))
        p.end()
