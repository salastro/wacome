"""QApplication bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .widgets.penstate import pen_state


def run_gui(dry_run: bool = False, problem: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("wacome")
    app.setApplicationDisplayName("wacome")
    app.setDesktopFileName("wacome")
    app.setWindowIcon(QIcon.fromTheme("input-tablet"))
    app.installEventFilter(pen_state())
    if problem:
        QMessageBox.critical(None, "wacome", problem)
        return 1
    from .main_window import MainWindow
    w = MainWindow(dry_run=dry_run)
    w.show()
    return app.exec()
