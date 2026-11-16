"""Polls for tablet hotplug and monitor layout changes."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from ..backend.devices import list_tablets
from ..backend.monitors import list_monitors
from ..backend.runner import Runner


class Watcher(QObject):
    tabletsChanged = Signal(list, list)   # tablets, names newly connected
    monitorsChanged = Signal(list)

    def __init__(self, runner: Runner, interval_ms: int = 2000):
        super().__init__()
        self.runner = runner
        self.tablets: list = []
        self.monitors: list = []
        self._sig_t: set = set()
        self._timer = QTimer(self, interval=interval_ms, timeout=self.poll)

    def start(self) -> None:
        self.poll()
        self._timer.start()

    def poll(self) -> None:
        tablets = list_tablets(self.runner)
        monitors = list_monitors(self.runner)
        sig_t = {t.signature() for t in tablets}
        if monitors != self.monitors:  # monitors first: tablet setup needs the layout
            self.monitors = monitors
            self.monitorsChanged.emit(monitors)
        if sig_t != self._sig_t:
            new = [t.name for t in tablets if t.signature() not in self._sig_t]
            self._sig_t = sig_t
            self.tablets = tablets
            self.tabletsChanged.emit(tablets, new)
