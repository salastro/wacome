"""Pressure curve, click threshold and a live drawing test."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSlider,
                               QSpinBox, QVBoxLayout)

from ..profile import CURVE_PRESETS
from .context import Ctx, SettingsTab
from .widgets.curve_editor import CurveEditor
from .widgets.penstate import pen_state
from .widgets.test_canvas import TestCanvas


class PressureTab(SettingsTab):
    def __init__(self, ctx: Ctx, parent=None):
        super().__init__(ctx, parent)
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        cbox = QGroupBox("Pressure curve")
        cl = QVBoxLayout(cbox)
        self.editor = CurveEditor()
        self.editor.curveChanged.connect(self._curve_dragged)
        cl.addWidget(self.editor, 1)
        presets = QHBoxLayout()
        for name, curve in CURVE_PRESETS.items():
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, c=curve: self._set_curve(list(c)))
            presets.addWidget(b)
        cl.addLayout(presets)
        grid = QGridLayout()
        self.spins = []
        for i, lbl in enumerate(("Handle 1 x", "y", "Handle 2 x", "y")):
            sb = QSpinBox()
            sb.setRange(0, 100)
            sb.valueChanged.connect(self._spin_changed)
            grid.addWidget(QLabel(lbl), 0, i * 2)
            grid.addWidget(sb, 0, i * 2 + 1)
            self.spins.append(sb)
        cl.addLayout(grid)
        hint = QLabel("Drag the handles. Curve above the diagonal makes the pen <b>softer</b> "
                      "(less force for thick strokes); below makes it <b>firmer</b>.")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        left.addWidget(cbox, 1)

        tbox = QGroupBox("Click threshold")
        tl = QHBoxLayout(tbox)
        self.threshold = QSlider(Qt.Orientation.Horizontal)
        self.threshold.setRange(1, 2047)
        self.threshold.valueChanged.connect(self._threshold_changed)
        self.threshold_lbl = QLabel()
        self.threshold_lbl.setMinimumWidth(150)
        tl.addWidget(QLabel("light"))
        tl.addWidget(self.threshold, 1)
        tl.addWidget(QLabel("heavy"))
        tl.addWidget(self.threshold_lbl)
        left.addWidget(tbox)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        test = QGroupBox("Try it")
        vl = QVBoxLayout(test)
        self.note = QLabel()
        self.note.setWordWrap(True)
        vl.addWidget(self.note)
        self.canvas = TestCanvas(hint="Draw here — stroke width follows pressure\n"
                                      "The red dot on the curve shows your current pressure")
        vl.addWidget(self.canvas, 1)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.canvas.clear)
        vl.addWidget(clear, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(test)
        root.addLayout(right, 1)

        pen_state().sample.connect(self._sample)
        self.canvas.pressureSample.connect(lambda p: self.editor.set_marker(p if p > 0 else None))

    def _sample(self, pressure, *_):
        self.editor.set_marker(pressure if pressure > 0 else None)

    def refresh(self) -> None:
        c = self.pending.pressure_curve
        self.editor.set_curves(c, self.applied.pressure_curve)
        for sb, v in zip(self.spins, c):
            sb.blockSignals(True)
            sb.setValue(v)
            sb.blockSignals(False)
        th = self.pending.threshold if self.pending.threshold is not None else 27
        self.threshold.blockSignals(True)
        self.threshold.setValue(th)
        self.threshold.blockSignals(False)
        self.threshold_lbl.setText(f"{th}  ({th / 2048 * 100:.1f}% force)")
        dirty = (self.pending.pressure_curve != self.applied.pressure_curve
                 or self.pending.threshold != self.applied.threshold)
        self.note.setText("<span style='color:#ffa62b'>The test area uses the <b>applied</b> curve — "
                          "click Apply (or enable Live) to feel your changes.</span>" if dirty else
                          "Stroke width and opacity follow the pressure reported by the driver.")

    def _set_curve(self, c) -> None:
        self.pending.pressure_curve = c
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _curve_dragged(self, c) -> None:
        self._set_curve(c)

    def _spin_changed(self) -> None:
        self._set_curve([sb.value() for sb in self.spins])

    def _threshold_changed(self, v: int) -> None:
        self.pending.threshold = v
        self.load(self.pending, self.applied)
        self.emit_changed()
