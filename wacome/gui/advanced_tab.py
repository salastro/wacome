"""Tracking mode, smoothing and touch toggles."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QSpinBox, QVBoxLayout

from .context import Ctx, SettingsTab


class AdvancedTab(SettingsTab):
    def __init__(self, ctx: Ctx, parent=None):
        super().__init__(ctx, parent)
        root = QVBoxLayout(self)

        track = QGroupBox("Tracking")
        f = QFormLayout(track)
        self.mode = QComboBox()
        self.mode.addItem("Absolute — pen position = screen position (pen mode)", "Absolute")
        self.mode.addItem("Relative — pen moves the cursor like a mouse", "Relative")
        self.mode.currentIndexChanged.connect(self._changed)
        f.addRow("Mode", self.mode)
        self.suppress = QSpinBox()
        self.suppress.setRange(0, 100)
        self.suppress.setToolTip("Ignore movements smaller than this many tablet units (jitter filter)")
        self.suppress.valueChanged.connect(self._changed)
        f.addRow("Suppress (jitter)", self.suppress)
        self.raw = QSpinBox()
        self.raw.setRange(1, 20)
        self.raw.setToolTip("Number of raw samples averaged: higher = smoother but laggier")
        self.raw.valueChanged.connect(self._changed)
        f.addRow("RawSample (smoothing)", self.raw)
        root.addWidget(track)

        touch = QGroupBox("Touch")
        tf = QFormLayout(touch)
        self.touch = QCheckBox("Enable finger touch")
        self.touch.toggled.connect(self._changed)
        self.gesture = QCheckBox("Enable multi-touch gestures")
        self.gesture.toggled.connect(self._changed)
        self.touch_note = QLabel()
        tf.addRow(self.touch)
        tf.addRow(self.gesture)
        tf.addRow(self.touch_note)
        root.addWidget(touch)
        root.addStretch(1)

    def refresh(self) -> None:
        p = self.pending
        widgets = (self.mode, self.suppress, self.raw, self.touch, self.gesture)
        for w in widgets:
            w.blockSignals(True)
        self.mode.setCurrentIndex(max(self.mode.findData(p.mode), 0))
        self.suppress.setValue(p.suppress if p.suppress is not None else 2)
        self.raw.setValue(p.raw_sample if p.raw_sample is not None else 4)
        has_touch = bool(self.ctx.tablet and self.ctx.tablet.touch)
        self.touch.setChecked(bool(p.touch))
        self.gesture.setChecked(bool(p.gesture))
        self.touch.setEnabled(has_touch)
        self.gesture.setEnabled(has_touch and bool(p.touch))
        self.touch_note.setText("" if has_touch else "This tablet has no touch sensor.")
        for w in widgets:
            w.blockSignals(False)

    def _changed(self, *_):
        p = self.pending
        p.mode = self.mode.currentData()
        p.suppress = self.suppress.value()
        p.raw_sample = self.raw.value()
        if self.ctx.tablet and self.ctx.tablet.touch:
            p.touch = self.touch.isChecked()
            p.gesture = self.gesture.isChecked()
        self.gesture.setEnabled(bool(self.ctx.tablet and self.ctx.tablet.touch) and self.touch.isChecked())
        self.emit_changed()
