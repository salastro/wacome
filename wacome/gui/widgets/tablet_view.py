"""Picture of the tablet surface with an editable active area."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...backend.geometry import Rect, point_to_visual, rect_from_visual, rect_to_visual, visual_size
from ..theme import ACCENT, CURSOR, PENDING, alpha, dashed, fg, fit_scale, painter
from .penstate import pen_state

HANDLE = 7


class TabletView(QWidget):
    areaEdited = Signal(object)   # Rect in tablet coordinates
    geometryChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.full = Rect(0, 0, 21600, 13500)
        self.rotation = "none"
        self.applied: Rect | None = None
        self.pending: Rect | None = None
        self.ratio: float | None = None      # visual aspect lock while dragging
        self.pen: tuple[float, float] | None = None   # visual tablet coords
        self.enabled_edit = True
        self._drag: str | None = None        # "move" | "tl" | "tr" | "bl" | "br"
        self._drag_origin: QPointF | None = None
        self._drag_rect: Rect | None = None   # visual coords at drag start
        pen_state().proximityChanged.connect(lambda _: self.update())

    # --- data -----------------------------------------------------------------
    def set_tablet(self, full: Rect, rotation: str) -> None:
        self.full, self.rotation = full, rotation
        self.update()
        self.geometryChanged.emit()

    def set_areas(self, applied: Rect | None, pending: Rect | None, ratio: float | None) -> None:
        self.applied, self.pending, self.ratio = applied, pending, ratio
        self.update()
        self.geometryChanged.emit()

    def set_pen(self, visual_pt: tuple[float, float] | None) -> None:
        if visual_pt != self.pen:
            self.pen = visual_pt
            self.update()

    # --- transforms ------------------------------------------------------------
    def _xf(self):
        vw, vh = visual_size(self.full, self.rotation)
        bezel = 0.07 * max(vw, vh)
        area = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        s, ox, oy = fit_scale(vw + 2 * bezel, vh + 2 * bezel, area)
        return s, ox + bezel * s, oy + bezel * s, bezel

    def vis_to_widget(self, r: Rect) -> QRectF:
        s, ox, oy, _ = self._xf()
        return QRectF(ox + r.x * s, oy + r.y * s, r.w * s, r.h * s)

    def widget_to_vis(self, pt: QPointF) -> tuple[float, float]:
        s, ox, oy, _ = self._xf()
        return (pt.x() - ox) / s, (pt.y() - oy) / s

    def pending_widget_rect(self) -> QRectF | None:
        if not self.pending:
            return None
        return self.vis_to_widget(rect_to_visual(self.pending, self.full, self.rotation))

    # --- editing ---------------------------------------------------------------
    def _hit(self, pt: QPointF) -> str | None:
        r = self.pending_widget_rect()
        if r is None:
            return None
        corners = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}
        for k, c in corners.items():
            if abs(pt.x() - c.x()) <= HANDLE + 2 and abs(pt.y() - c.y()) <= HANDLE + 2:
                return k
        return "move" if r.contains(pt) else None

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.enabled_edit:
            return
        self._drag = self._hit(e.position())
        if self._drag:
            self._drag_origin = e.position()
            self._drag_rect = rect_to_visual(self.pending, self.full, self.rotation)

    def mouseMoveEvent(self, e):
        if not self._drag:
            hit = self._hit(e.position()) if self.enabled_edit else None
            cursors = {"move": Qt.CursorShape.SizeAllCursor, "tl": Qt.CursorShape.SizeFDiagCursor,
                       "br": Qt.CursorShape.SizeFDiagCursor, "tr": Qt.CursorShape.SizeBDiagCursor,
                       "bl": Qt.CursorShape.SizeBDiagCursor}
            self.setCursor(cursors.get(hit, Qt.CursorShape.ArrowCursor))
            return
        vw, vh = visual_size(self.full, self.rotation)
        s = self._xf()[0]
        dx = (e.position().x() - self._drag_origin.x()) / s
        dy = (e.position().y() - self._drag_origin.y()) / s
        r = self._drag_rect
        if self._drag == "move":
            nr = Rect(r.x + dx, r.y + dy, r.w, r.h).clamp_into(Rect(0, 0, vw, vh))
        else:
            # anchor = opposite corner
            ax = r.x2 if "l" in self._drag else r.x
            ay = r.y2 if "t" in self._drag else r.y
            mx, my = self.widget_to_vis(e.position())
            mx, my = min(max(mx, 0), vw), min(max(my, 0), vh)
            w, h = max(abs(mx - ax), vw * 0.05), max(abs(my - ay), vh * 0.05)
            if self.ratio:
                if w / h > self.ratio:
                    w = h * self.ratio
                else:
                    h = w / self.ratio
                # keep inside the surface
                maxw = ax if "l" in self._drag else vw - ax
                maxh = ay if "t" in self._drag else vh - ay
                k = min(1.0, maxw / w, maxh / h)
                w, h = w * k, h * k
            x = ax - w if "l" in self._drag else ax
            y = ay - h if "t" in self._drag else ay
            nr = Rect(x, y, w, h).clamp_into(Rect(0, 0, vw, vh))
        self.areaEdited.emit(rect_from_visual(nr, self.full, self.rotation).rounded())

    def mouseReleaseEvent(self, _):
        self._drag = None

    # --- painting ----------------------------------------------------------------
    def paintEvent(self, _):
        p = painter(self)
        s, ox, oy, bezel = self._xf()
        vw, vh = visual_size(self.full, self.rotation)
        surface = QRectF(ox, oy, vw * s, vh * s)
        body = surface.adjusted(-bezel * s, -bezel * s, bezel * s, bezel * s)

        p.setPen(QPen(fg(self, 90), 1.5))
        p.setBrush(QColor("#2a2d33"))
        p.drawRoundedRect(body, 14, 14)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor("#363a42"))
        p.drawRect(surface)

        # marker on the tablet's original top edge (shows rotation)
        tx, ty = point_to_visual(self.full.x + self.full.w / 2, self.full.y, self.full, self.rotation)
        cx, cy = ox + tx * s, oy + ty * s
        center = surface.center()
        dirx, diry = cx - center.x(), cy - center.y()
        n = max((dirx ** 2 + diry ** 2) ** 0.5, 1)
        dirx, diry = dirx / n, diry / n
        tip = QPointF(cx + dirx * bezel * s * 0.75, cy + diry * bezel * s * 0.75)
        side = QPointF(-diry * 6, dirx * 6)
        back = QPointF(cx + dirx * bezel * s * 0.25, cy + diry * bezel * s * 0.25)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawPolygon(QPolygonF([tip, back + side, back - side]))

        small = QFont(self.font())
        small.setPointSizeF(max(self.font().pointSizeF() - 1, 7))
        p.setFont(small)

        if self.applied:
            r = self.vis_to_widget(rect_to_visual(self.applied, self.full, self.rotation))
            p.setPen(QPen(ACCENT, 2))
            p.setBrush(alpha(ACCENT, 70))
            p.drawRect(r)
        if self.pending:
            r = self.pending_widget_rect()
            changed = self.pending != self.applied
            col = PENDING if changed else ACCENT
            p.setPen(dashed(col, 2) if changed else QPen(col, 2))
            p.setBrush(QBrush(alpha(PENDING, 45), Qt.BrushStyle.BDiagPattern) if changed
                       else Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            if self.enabled_edit:
                p.setPen(QPen(QColor("white"), 1))
                p.setBrush(col)
                for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                    p.drawRect(QRectF(c.x() - HANDLE / 2, c.y() - HANDLE / 2, HANDLE, HANDLE))
            p.setPen(QColor(255, 255, 255, 200))
            pr = self.pending
            p.drawText(r.adjusted(6, 4, -6, -4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       f"{int(pr.w)}×{int(pr.h)}")

        if self.pen:
            c = QPointF(ox + self.pen[0] * s, oy + self.pen[1] * s)
            prox = pen_state().in_proximity
            if prox:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(CURSOR, 70))
                p.drawEllipse(c, 13, 13)
            p.setPen(QPen(QColor("white"), 1.5))
            p.setBrush(CURSOR if prox else QColor(255, 255, 255, 140))
            p.drawEllipse(c, 6 if prox else 4, 6 if prox else 4)

        rot_label = {"none": "", "cw": "rotated 90° CW", "half": "rotated 180°", "ccw": "rotated 90° CCW"}
        if rot_label[self.rotation]:
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(body.adjusted(10, 0, -10, -4), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                       rot_label[self.rotation])
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.geometryChanged.emit()
