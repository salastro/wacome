"""App-wide live pen state, fed by tablet events anywhere in the app."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Signal


class PenState(QObject):
    proximityChanged = Signal(bool)
    sample = Signal(float, str, int, float, float)  # pressure, tool, buttons, xtilt, ytilt
    buttonPressed = Signal(int)                      # X button number seen by Qt

    def __init__(self):
        super().__init__()
        self.in_proximity = False
        self.pressure = 0.0
        self.tool = "stylus"

    def set_proximity(self, on: bool) -> None:
        if on != self.in_proximity:
            self.in_proximity = on
            self.proximityChanged.emit(on)

    def eventFilter(self, obj, ev) -> bool:  # installed on QApplication
        t = ev.type()
        if t == QEvent.Type.TabletEnterProximity:
            self.set_proximity(True)
        elif t == QEvent.Type.TabletLeaveProximity:
            self.set_proximity(False)
        return False


_INSTANCE: PenState | None = None


def pen_state() -> PenState:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = PenState()
    return _INSTANCE
