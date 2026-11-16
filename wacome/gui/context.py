"""State shared between the main window and the settings tabs."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ..backend.devices import Tablet
from ..backend.geometry import Rect
from ..backend.monitors import Monitor
from ..backend.runner import Runner
from ..profile import Profile


@dataclass
class Ctx:
    runner: Runner
    tablet: Tablet | None = None
    monitors: list[Monitor] = field(default_factory=list)
    full_area: Rect | None = None


class SettingsTab(QWidget):
    """Tabs edit ``self.pending`` in place and emit ``changed``."""

    changed = Signal()

    def __init__(self, ctx: Ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.pending = Profile()
        self.applied = Profile()
        self._loading = False

    def load(self, pending: Profile, applied: Profile) -> None:
        self.pending, self.applied = pending, applied
        self._loading = True
        try:
            self.refresh()
        finally:
            self._loading = False

    def refresh(self) -> None:  # update widgets from self.pending / self.applied
        pass

    def context_changed(self) -> None:  # tablet or monitors changed
        self.load(self.pending, self.applied)

    def emit_changed(self) -> None:
        if not self._loading:
            self.changed.emit()
