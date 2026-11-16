"""Screen mapping, tablet area and orientation."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPen
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QPushButton, QRadioButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from ..backend.geometry import ROTATIONS, Rect, rect_to_visual, visual_size
from ..backend.monitors import desktop_rect
from ..profile import effective_area, resolve_target
from .context import Ctx, SettingsTab
from .theme import ACCENT, PENDING, WARN, OK, alpha, painter
from .widgets import screen_flash
from .widgets.desktop_view import DesktopView
from .widgets.tablet_view import TabletView

ROT_LABELS = {"none": "Normal", "cw": "90° clockwise", "half": "180° (left-handed)", "ccw": "90° counter-clockwise"}


class _Links(QWidget):
    """Transparent overlay connecting tablet-area corners to screen-region corners."""

    def __init__(self, parent, desk: DesktopView, tab: TabletView):
        super().__init__(parent)
        self.desk, self.tab = desk, tab
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.color = ACCENT

    def paintEvent(self, _):
        a = self.tab.pending_widget_rect()
        b = self.desk.pending_widget_rect()
        if a is None or b is None:
            return
        p = painter(self)
        pen = QPen(alpha(self.color, 110), 1.2)
        pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        for ca, cb in ((a.topLeft(), b.topLeft()), (a.topRight(), b.topRight()),
                       (a.bottomLeft(), b.bottomLeft()), (a.bottomRight(), b.bottomRight())):
            pa = QPointF(self.tab.mapTo(self.parentWidget(), ca.toPoint()))
            pb = QPointF(self.desk.mapTo(self.parentWidget(), cb.toPoint()))
            p.drawLine(pa, pb)
        p.end()


class _Views(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(28)
        self.desktop = DesktopView()
        self.tablet = TabletView()
        cap1 = QLabel("<b>Screens</b> — click a monitor to map the tablet to it, drag to map to a custom region")
        cap2 = QLabel("<b>Tablet</b> — drag the area or its corners to use only part of the surface "
                      "(▲ marks the tablet's top edge)")
        for c in (cap1, cap2):
            c.setWordWrap(True)
        lay.addWidget(cap1)
        lay.addWidget(self.desktop, 3)
        lay.addWidget(cap2)
        lay.addWidget(self.tablet, 2)
        self.links = _Links(self, self.desktop, self.tablet)
        self.desktop.geometryChanged.connect(self.links.update)
        self.tablet.geometryChanged.connect(self.links.update)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.links.setGeometry(self.rect())
        self.links.raise_()


class MappingTab(SettingsTab):
    def __init__(self, ctx: Ctx, parent=None):
        super().__init__(ctx, parent)
        root = QHBoxLayout(self)
        self.views = _Views()
        root.addWidget(self.views, 1)

        panel = QWidget()
        side = QVBoxLayout(panel)
        side.setContentsMargins(0, 0, 0, 0)

        # --- target --------------------------------------------------------------
        self.target_box = QGroupBox("Map tablet to")
        self.target_lay = QVBoxLayout(self.target_box)
        self.target_group = QButtonGroup(self)
        self.target_group.idClicked.connect(self._target_clicked)
        self.target_ids: dict[int, dict] = {}
        self.region_spins = [QSpinBox() for _ in range(4)]
        self.region_row = QWidget()
        g = QGridLayout(self.region_row)
        g.setContentsMargins(18, 0, 0, 0)
        for i, (lbl, sb) in enumerate(zip(("X", "Y", "W", "H"), self.region_spins)):
            sb.setRange(0, 32768)
            sb.setKeyboardTracking(False)
            sb.valueChanged.connect(self._region_spin_changed)
            g.addWidget(QLabel(lbl), i // 2, (i % 2) * 2)
            g.addWidget(sb, i // 2, (i % 2) * 2 + 1)
        btns = QHBoxLayout()
        ident = QPushButton("Identify monitors")
        ident.setToolTip("Show each monitor's number on the real screens")
        ident.clicked.connect(self.identify_monitors)
        show = QPushButton("Show on screen")
        show.setToolTip("Highlight the region the tablet will map to")
        show.clicked.connect(self.show_on_screen)
        btns.addWidget(ident)
        btns.addWidget(show)
        side.addWidget(self.target_box)
        side.addLayout(btns)

        # --- area ------------------------------------------------------------------
        area_box = QGroupBox("Tablet area")
        af = QFormLayout(area_box)
        self.keep_aspect = QCheckBox("Keep proportions (no stretching)")
        self.keep_aspect.setToolTip("Trim the tablet area so a circle drawn on the tablet stays a circle on screen")
        self.keep_aspect.toggled.connect(self._keep_aspect_toggled)
        af.addRow(self.keep_aspect)
        self.anchor = QComboBox()
        self.anchor.addItem("Centered", "center")
        self.anchor.addItem("Top-left", "topleft")
        self.anchor.currentIndexChanged.connect(self._anchor_changed)
        af.addRow("Position", self.anchor)
        self.area_spins = [QSpinBox() for _ in range(4)]
        grid = QGridLayout()
        for i, (lbl, sb) in enumerate(zip(("Left", "Top", "Right", "Bottom"), self.area_spins)):
            sb.setRange(0, 200000)
            sb.setKeyboardTracking(False)
            sb.valueChanged.connect(self._area_spin_changed)
            grid.addWidget(QLabel(lbl), i // 2, (i % 2) * 2)
            grid.addWidget(sb, i // 2, (i % 2) * 2 + 1)
        af.addRow(grid)
        full_btn = QPushButton("Use whole surface")
        full_btn.clicked.connect(self._reset_area)
        af.addRow(full_btn)
        self.ratio_info = QLabel()
        self.ratio_info.setWordWrap(True)
        af.addRow(self.ratio_info)
        side.addWidget(area_box)

        # --- orientation -------------------------------------------------------------
        rot_box = QGroupBox("Orientation")
        rl = QVBoxLayout(rot_box)
        self.rot_group = QButtonGroup(self)
        for i, r in enumerate(ROTATIONS):
            b = QRadioButton(ROT_LABELS[r])
            self.rot_group.addButton(b, i)
            rl.addWidget(b)
        self.rot_group.idClicked.connect(self._rotation_clicked)
        side.addWidget(rot_box)
        side.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setFixedWidth(330)
        root.addWidget(scroll)

        d, t = self.views.desktop, self.views.tablet
        d.monitorClicked.connect(self._monitor_clicked)
        d.regionDrawn.connect(self._region_drawn)
        d.cursorMoved.connect(self._cursor_moved)
        t.areaEdited.connect(self._area_dragged)

    # --- derived geometry ----------------------------------------------------------
    @property
    def full(self) -> Rect:
        return self.ctx.full_area or Rect(0, 0, 21600, 13500)

    def regions(self) -> tuple[Rect, Rect]:
        mons = self.ctx.monitors
        return resolve_target(self.applied, mons)[0], resolve_target(self.pending, mons)[0]

    def areas(self) -> tuple[Rect, Rect]:
        ra, rp = self.regions()
        return effective_area(self.applied, self.full, ra), effective_area(self.pending, self.full, rp)

    # --- refresh -----------------------------------------------------------------------
    def _rebuild_targets(self) -> None:
        for b in self.target_group.buttons():
            self.target_group.removeButton(b)
            b.deleteLater()
        while self.target_lay.count():
            item = self.target_lay.takeAt(0)
            if item.widget() and item.widget() is not self.region_row:
                item.widget().deleteLater()
        self.target_ids.clear()
        mons = self.ctx.monitors
        entries = []
        for i, m in enumerate(mons, 1):
            label = f"{i}. {m.name} — {int(m.rect.w)}×{int(m.rect.h)}{' (primary)' if m.primary else ''}"
            entries.append((label, {"kind": "output", "name": m.name}))
        if len(mons) > 1:
            d = desktop_rect(mons)
            entries.append((f"All monitors — {int(d.w)}×{int(d.h)}", {"kind": "desktop"}))
        entries.append(("Custom region", {"kind": "region"}))
        for i, (label, target) in enumerate(entries):
            b = QRadioButton(label)
            self.target_group.addButton(b, i)
            self.target_lay.addWidget(b)
            self.target_ids[i] = target
        self.target_lay.addWidget(self.region_row)

    def _current_target_id(self) -> int | None:
        t = self.pending.target
        kind = t.get("kind")
        if len(self.ctx.monitors) == 1 and kind == "desktop":
            kind, t = "output", {"kind": "output", "name": self.ctx.monitors[0].name}
        for i, tt in self.target_ids.items():
            if tt["kind"] == kind and (kind != "output" or tt["name"] == t.get("name")):
                return i
        if kind == "output":  # disconnected monitor
            return None
        return None

    def refresh(self) -> None:
        if len(self.target_ids) != len(self.ctx.monitors) + (2 if len(self.ctx.monitors) > 1 else 1) \
                or any(t.get("name") not in {m.name for m in self.ctx.monitors}
                       for t in self.target_ids.values() if t["kind"] == "output"):
            self._rebuild_targets()
        tid = self._current_target_id()
        if tid is not None:
            self.target_group.button(tid).setChecked(True)
        is_region = self.pending.target.get("kind") == "region"
        self.region_row.setEnabled(is_region)
        reg_a, reg_p = self.regions()
        area_a, area_p = self.areas()
        for sb, v in zip(self.region_spins, (reg_p.x, reg_p.y, reg_p.w, reg_p.h)):
            sb.blockSignals(True)
            sb.setValue(int(v))
            sb.blockSignals(False)
        for sb, v in zip(self.area_spins, area_p.corners()):
            sb.blockSignals(True)
            sb.setMaximum(int(max(self.full.x2, self.full.y2)))
            sb.setValue(int(v))
            sb.blockSignals(False)
        self.keep_aspect.blockSignals(True)
        self.keep_aspect.setChecked(self.pending.keep_aspect)
        self.keep_aspect.blockSignals(False)
        self.anchor.blockSignals(True)
        self.anchor.setCurrentIndex(max(self.anchor.findData(self.pending.anchor), 0))
        self.anchor.setEnabled(self.pending.keep_aspect)
        self.anchor.blockSignals(False)
        self.rot_group.button(ROTATIONS.index(self.pending.rotate)).setChecked(True)

        d, t = self.views.desktop, self.views.tablet
        d.set_monitors(self.ctx.monitors)
        sel = self.pending.target.get("name") if self.pending.target.get("kind") == "output" else None
        d.set_regions(reg_a, reg_p, sel)
        t.set_tablet(self.full, self.pending.rotate)
        ratio = reg_p.ratio if self.pending.keep_aspect else None
        t.set_areas(area_a, area_p, ratio)
        self.views.links.color = PENDING if (area_p != area_a or reg_p != reg_a) else ACCENT
        self.views.links.update()
        self._update_ratio_info(area_p, reg_p)

    def _update_ratio_info(self, area: Rect, region: Rect) -> None:
        v = rect_to_visual(area, self.full, self.pending.rotate)
        if not (v.h and region.h):
            self.ratio_info.setText("")
            return
        stretch = (region.ratio / v.ratio - 1) * 100
        vw, vh = visual_size(self.full, self.pending.rotate)
        used = v.w * v.h / (vw * vh) * 100 if vw and vh else 100
        if abs(stretch) < 1:
            msg = f"<span style='color:{OK.name()}'>✔ No distortion</span>"
        else:
            axis = "wider" if stretch > 0 else "taller"
            msg = (f"<span style='color:{WARN.name()}'>⚠ Shapes appear {abs(stretch):.0f}% {axis} "
                   f"on screen</span>")
        self.ratio_info.setText(f"{msg}<br>Tablet area {v.w / v.h:.2f}:1 → screen {region.ratio:.2f}:1"
                                f"<br>Using {used:.0f}% of the surface")

    # --- handlers --------------------------------------------------------------------------
    def _set_target(self, target: dict) -> None:
        self.pending.target = target
        if self.pending.keep_aspect:
            self.pending.area = None
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _target_clicked(self, i: int) -> None:
        t = dict(self.target_ids[i])
        if t["kind"] == "region":
            cur = resolve_target(self.pending, self.ctx.monitors)[0]
            t["rect"] = [cur.x, cur.y, cur.w, cur.h]
        self._set_target(t)

    def _monitor_clicked(self, name: str) -> None:
        if len(self.ctx.monitors) == 1:
            self._set_target({"kind": "desktop"})
        else:
            self._set_target({"kind": "output", "name": name})

    def _region_drawn(self, r: Rect) -> None:
        self._set_target({"kind": "region", "rect": [r.x, r.y, r.w, r.h]})

    def _region_spin_changed(self) -> None:
        x, y, w, h = (sb.value() for sb in self.region_spins)
        if w > 0 and h > 0:
            self._set_target({"kind": "region", "rect": [x, y, w, h]})

    def _keep_aspect_toggled(self, on: bool) -> None:
        self.pending.keep_aspect = on
        self.pending.area = None
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _anchor_changed(self) -> None:
        self.pending.anchor = self.anchor.currentData()
        self.pending.area = None
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _rotation_clicked(self, i: int) -> None:
        self.pending.rotate = ROTATIONS[i]
        if self.pending.keep_aspect:
            self.pending.area = None
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _reset_area(self) -> None:
        self.pending.area = None
        self.pending.keep_aspect = False
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _area_dragged(self, r: Rect) -> None:
        self.pending.area = r.corners()
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _area_spin_changed(self) -> None:
        x1, y1, x2, y2 = (sb.value() for sb in self.area_spins)
        if x2 > x1 and y2 > y1:
            self.pending.area = [x1, y1, x2, y2]
            self.load(self.pending, self.applied)
            self.emit_changed()

    def _cursor_moved(self, pos) -> None:
        t = self.views.tablet
        reg_a, _ = self.regions()
        area_a, _ = self.areas()
        if not pos or not reg_a.contains(*pos):
            t.set_pen(None)
            return
        u = (pos[0] - reg_a.x) / reg_a.w
        v = (pos[1] - reg_a.y) / reg_a.h
        va = rect_to_visual(area_a, self.full, self.applied.rotate)
        if self.applied.rotate != self.pending.rotate:
            t.set_pen(None)
            return
        t.set_pen((va.x + u * va.w, va.y + v * va.h))

    # --- on-screen visualisation -------------------------------------------------------
    def identify_monitors(self) -> None:
        for i, m in enumerate(self.ctx.monitors, 1):
            screen_flash.flash(m.rect, str(i), m.name, ACCENT, ms=1400, big=True)

    def show_on_screen(self) -> None:
        _, reg = self.regions()
        name = self.ctx.tablet.name if self.ctx.tablet else "Tablet"
        screen_flash.flash(reg, name, "tablet maps here", PENDING if reg != self.regions()[0] else ACCENT,
                           ms=1200)
