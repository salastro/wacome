"""Main window: device/profile toolbar, settings tabs and the command log."""

from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDockWidget, QHBoxLayout, QInputDialog, QLabel,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QStackedWidget,
                               QTabWidget, QToolBar, QVBoxLayout, QWidget)

from .. import autostart
from .. import profile as prof
from ..backend import params
from ..backend.runner import Result, Runner
from .advanced_tab import AdvancedTab
from .buttons_tab import ButtonsTab
from .context import Ctx
from .mapping_tab import MappingTab
from .pressure_tab import PressureTab
from .theme import ACCENT, PENDING, WARN
from .watcher import Watcher
from .widgets import screen_flash

DEVICE_ITEM = "— Current device settings —"


class MainWindow(QMainWindow):
    def __init__(self, dry_run: bool = False):
        super().__init__()
        self.setWindowTitle("wacome — Wacom tablet settings" + ("  [dry run]" if dry_run else ""))
        self.resize(1280, 820)
        self.runner = Runner(dry_run=dry_run)
        self.ctx = Ctx(self.runner)
        self.applied = prof.Profile()
        self.pending = prof.Profile()
        self.session_applied = False
        self._first_tablets = True
        self._first_monitors = True

        self._build_log_dock()
        self.runner.add_listener(self._log)
        self._build_toolbar()

        self.tabs = QTabWidget()
        self.tab_list = [
            (MappingTab(self.ctx), "Screen && Area"),
            (PressureTab(self.ctx), "Pressure"),
            (ButtonsTab(self.ctx), "Buttons"),
            (AdvancedTab(self.ctx), "Advanced"),
        ]
        for tab, title in self.tab_list:
            self.tabs.addTab(tab, title)
            tab.changed.connect(self._on_tab_changed)
        self.mapping: MappingTab = self.tab_list[0][0]

        self.empty = QLabel("<h2>No tablet connected</h2><p>Plug in a Wacom tablet — it will be picked up "
                            "automatically.</p>")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.tabs)
        self.setCentralWidget(self.stack)

        self.dirty_lbl = QLabel()
        self.statusBar().addPermanentWidget(self.dirty_lbl)

        self._live_timer = QTimer(self, singleShot=True, interval=250, timeout=self.apply)

        self.watcher = Watcher(self.runner)
        self.watcher.tabletsChanged.connect(self._on_tablets)
        self.watcher.monitorsChanged.connect(self._on_monitors)
        self._reload_profiles()
        self.watcher.start()
        self._update_dirty()

    # --- construction ----------------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addWidget(QLabel(" Tablet "))
        self.tablet_combo = QComboBox()
        self.tablet_combo.setMinimumWidth(200)
        self.tablet_combo.currentIndexChanged.connect(self._tablet_selected)
        tb.addWidget(self.tablet_combo)
        tb.addSeparator()

        tb.addWidget(QLabel(" Profile "))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.activated.connect(self._profile_selected)
        tb.addWidget(self.profile_combo)
        save = QAction("Save", self, shortcut=QKeySequence.StandardKey.Save, triggered=self.save)
        save_as = QAction("Save as…", self, triggered=self.save_as)
        self.delete_act = QAction("Delete", self, triggered=self.delete_profile)
        for a in (save, save_as, self.delete_act):
            tb.addAction(a)
        self.default_cb = QCheckBox("Default")
        self.default_cb.setToolTip("Apply this profile automatically when the tablet is plugged in or at login")
        self.default_cb.toggled.connect(self._default_toggled)
        tb.addWidget(self.default_cb)
        tb.addSeparator()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setShortcut(QKeySequence("Ctrl+Return"))
        self.apply_btn.setToolTip("Send the pending changes to the tablet (Ctrl+Enter)")
        f = self.apply_btn.font()
        f.setBold(True)
        self.apply_btn.setFont(f)
        self.apply_btn.clicked.connect(self.apply)
        tb.addWidget(self.apply_btn)
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.setToolTip("Discard pending changes and re-read the tablet")
        self.revert_btn.clicked.connect(self.revert)
        tb.addWidget(self.revert_btn)
        self.live_cb = QCheckBox("Live")
        self.live_cb.setToolTip("Apply every change immediately")
        self.live_cb.toggled.connect(lambda on: on and self._is_dirty() and self._live_timer.start())
        tb.addWidget(self.live_cb)
        tb.addSeparator()

        self.login_cb = QCheckBox("Apply on login")
        self.login_cb.setToolTip("Install an autostart entry that applies the default profile at login "
                                 "and re-applies it on hotplug / monitor changes")
        self.login_cb.setChecked(autostart.is_enabled())
        self.login_cb.toggled.connect(self._login_toggled)
        tb.addWidget(self.login_cb)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        log_act = self.log_dock.toggleViewAction()
        log_act.setText("Commands")
        tb.addAction(log_act)

    def _build_log_dock(self) -> None:
        self.log_dock = QDockWidget("Commands sent to the driver", self)
        self.log_dock.setObjectName("log")
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log_view.setMaximumBlockCount(2000)
        lay.addWidget(self.log_view)
        row = QHBoxLayout()
        copy = QPushButton("Copy as script")
        copy.clicked.connect(self._copy_log)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.log_view.clear)
        row.addStretch(1)
        row.addWidget(copy)
        row.addWidget(clear)
        lay.addLayout(row)
        self.log_dock.setWidget(w)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.resizeDocks([self.log_dock], [150], Qt.Orientation.Vertical)

    # --- logging -------------------------------------------------------------------------
    def _log(self, res: Result, _write: bool) -> None:
        ts = time.strftime("%H:%M:%S")
        cmd = html.escape(res.cmdline)
        if res.ok:
            line = f"<span style='color:gray'>{ts}</span> $ {cmd}"
            if self.runner.dry_run:
                line += " <span style='color:gray'>(dry run)</span>"
        else:
            err = html.escape((res.stderr or res.stdout).strip())
            line = (f"<span style='color:gray'>{ts}</span> <span style='color:{WARN.name()}'>$ {cmd}"
                    f"<br>&nbsp;&nbsp;✖ {err}</span>")
        self.log_view.appendHtml(line)

    def _note(self, text: str, color=None) -> None:
        ts = time.strftime("%H:%M:%S")
        c = (color or ACCENT).name()
        self.log_view.appendHtml(f"<span style='color:gray'>{ts}</span> <span style='color:{c}'># "
                                 f"{html.escape(text)}</span>")

    def _copy_log(self) -> None:
        from PySide6.QtWidgets import QApplication
        lines = ["#!/bin/sh"] + [ln.split("$ ", 1)[1] for ln in self.log_view.toPlainText().splitlines()
                                 if "$ " in ln]
        QApplication.clipboard().setText("\n".join(lines) + "\n")
        self.statusBar().showMessage("Commands copied to clipboard", 3000)

    # --- device / monitor events ----------------------------------------------------------
    def _on_tablets(self, tablets, new_names) -> None:
        current = self.ctx.tablet.name if self.ctx.tablet else None
        self.tablet_combo.blockSignals(True)
        self.tablet_combo.clear()
        for t in tablets:
            self.tablet_combo.addItem(t.name, t.name)
        idx = self.tablet_combo.findData(current) if current else -1
        self.tablet_combo.setCurrentIndex(idx if idx >= 0 else (0 if tablets else -1))
        self.tablet_combo.blockSignals(False)

        first = self._first_tablets
        self._first_tablets = False
        chosen = next((t for t in tablets if t.name == self.tablet_combo.currentData()), None)
        if chosen is None:
            if self.ctx.tablet:
                self._note(f"{self.ctx.tablet.name} disconnected", PENDING)
            self.ctx.tablet = None
            self.stack.setCurrentWidget(self.empty)
            self._update_dirty()
            return

        if not first and chosen.name in new_names:
            self._note(f"{chosen.name} connected", ACCENT)
            self.ctx.tablet = chosen
            self.ctx.full_area = self._read_full_area()
            if self.session_applied:
                self._note("re-applying this session's settings")
                self._push(self.applied, flash=False)
            elif (name := prof.default_profile_name()):
                self._note(f"applying default profile {name!r}")
                self._push(self._load_named(name), flash=False)
        self._select_tablet(chosen, keep_pending=self.ctx.tablet is not None
                            and self.ctx.tablet.name == chosen.name and not first)

    def _tablet_selected(self) -> None:
        name = self.tablet_combo.currentData()
        t = next((t for t in self.watcher.tablets if t.name == name), None)
        if t:
            self._select_tablet(t, keep_pending=False)

    def _read_full_area(self):
        t = self.ctx.tablet
        dev = t.stylus or (t.pen_devices() or [None])[0] if t else None
        return params.full_area(self.runner, dev.name) if dev else None

    def _select_tablet(self, tablet, keep_pending: bool) -> None:
        self.ctx.tablet = tablet
        self.ctx.full_area = self._read_full_area()
        self.ctx.monitors = self.watcher.monitors
        if keep_pending and self.session_applied:
            pending = self.pending
        else:
            pending = None
        self.applied = prof.from_device(tablet, self.runner, self.ctx.monitors)
        self.applied.full_area = self.ctx.full_area.corners() if self.ctx.full_area else None
        if pending is None:
            self.pending = self.applied.copy()
            self.profile_combo.setCurrentIndex(0)
        self.stack.setCurrentWidget(self.tabs)
        self._load_tabs()
        self._update_profile_controls()

    def _on_monitors(self, monitors) -> None:
        first = self._first_monitors
        self._first_monitors = False
        self.ctx.monitors = monitors
        if not first:
            self._note("monitor layout changed: " + ", ".join(m.name for m in monitors) or "none", PENDING)
            if self.ctx.tablet and self.session_applied:
                self._push(self.applied, flash=True)
        if self.ctx.tablet:
            for tab, _ in self.tab_list:
                tab.context_changed()

    # --- profile handling -------------------------------------------------------------------
    def _load_named(self, name: str) -> prof.Profile:
        p = prof.load_profile(name)
        if self.ctx.full_area:
            p.full_area = self.ctx.full_area.corners()
        return p

    def _reload_profiles(self, select: str | None = None) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem(DEVICE_ITEM, None)
        default = prof.default_profile_name()
        for n in prof.list_profiles():
            self.profile_combo.addItem(f"{n}  ★" if n == default else n, n)
        if select:
            self.profile_combo.setCurrentIndex(max(self.profile_combo.findData(select), 0))
        self.profile_combo.blockSignals(False)
        self._update_profile_controls()

    def _profile_selected(self) -> None:
        name = self.profile_combo.currentData()
        if name is None:
            self.pending = self.applied.copy()
        else:
            try:
                self.pending = self._load_named(name)
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "wacome", f"Cannot load profile {name!r}:\n{e}")
                return
        self._load_tabs()
        self._update_profile_controls()
        if self.live_cb.isChecked():
            self._live_timer.start()

    def _update_profile_controls(self) -> None:
        name = self.profile_combo.currentData()
        self.delete_act.setEnabled(name is not None)
        self.default_cb.blockSignals(True)
        self.default_cb.setEnabled(name is not None)
        self.default_cb.setChecked(name is not None and name == prof.default_profile_name())
        self.default_cb.blockSignals(False)

    def save(self) -> None:
        name = self.profile_combo.currentData()
        if name is None:
            self.save_as()
            return
        prof.save_profile(name, self.pending)
        self.statusBar().showMessage(f"Saved profile {name!r}", 3000)

    def save_as(self) -> None:
        name, ok = QInputDialog.getText(self, "Save profile", "Profile name:")
        name = name.strip()
        if not ok or not name:
            return
        if name in prof.list_profiles() and QMessageBox.question(
                self, "wacome", f"Overwrite profile {name!r}?") != QMessageBox.StandardButton.Yes:
            return
        prof.save_profile(name, self.pending)
        if not prof.default_profile_name():
            prof.set_default_profile(name)
        self._reload_profiles(select=name)
        self.statusBar().showMessage(f"Saved profile {name!r}", 3000)

    def delete_profile(self) -> None:
        name = self.profile_combo.currentData()
        if name is None or QMessageBox.question(
                self, "wacome", f"Delete profile {name!r}?") != QMessageBox.StandardButton.Yes:
            return
        prof.delete_profile(name)
        if prof.load_settings().get("default") == name:
            prof.set_default_profile(None)
        self._reload_profiles()

    def _default_toggled(self, on: bool) -> None:
        name = self.profile_combo.currentData()
        prof.set_default_profile(name if on else None)
        self._reload_profiles(select=name)

    def _login_toggled(self, on: bool) -> None:
        if on:
            path = autostart.enable(watch=True)
            self._note(f"autostart entry written: {path}")
            if not prof.default_profile_name():
                QMessageBox.information(self, "wacome", "Autostart is on, but no default profile is set yet.\n"
                                        "Save a profile and tick “Default” so there is something to apply.")
        else:
            autostart.disable()
            self._note("autostart entry removed")

    # --- apply / revert -------------------------------------------------------------------
    def _load_tabs(self) -> None:
        for tab, _ in self.tab_list:
            tab.load(self.pending, self.applied)
        self._update_dirty()

    def _on_tab_changed(self) -> None:
        sender = self.sender()
        for tab, _ in self.tab_list:  # keep other tabs consistent (e.g. rotation)
            if tab is not sender:
                tab.load(self.pending, self.applied)
        self._update_dirty()
        if self.live_cb.isChecked():
            self._live_timer.start()

    def _norm(self, p: prof.Profile) -> prof.Profile:
        q = p.copy()
        q.full_area = None
        return q

    def _is_dirty(self) -> bool:
        return self._norm(self.pending) != self._norm(self.applied)

    def _update_dirty(self) -> None:
        dirty = self._is_dirty() and self.ctx.tablet is not None
        self.apply_btn.setEnabled(dirty)
        self.revert_btn.setEnabled(self.ctx.tablet is not None)
        if dirty:
            self.dirty_lbl.setText(f"<span style='color:{PENDING.name()}'>● pending changes</span>")
        elif self.ctx.tablet:
            self.dirty_lbl.setText(f"<span style='color:{ACCENT.name()}'>✔ tablet up to date</span>")
        else:
            self.dirty_lbl.setText("no tablet")

    def _push(self, p: prof.Profile, flash: bool) -> list[str]:
        msgs = prof.apply(p, self.ctx.tablet, self.runner, self.ctx.monitors)
        for m in msgs:
            self._note(m, WARN)
        if flash:
            region = prof.resolve_target(p, self.ctx.monitors)[0]
            screen_flash.flash(region, self.ctx.tablet.name, "tablet mapped here", ACCENT, ms=700)
        return msgs

    def apply(self) -> None:
        if not self.ctx.tablet:
            return
        before = self.applied
        mapping_changed = (before.target != self.pending.target or before.area != self.pending.area
                           or before.rotate != self.pending.rotate or before.keep_aspect != self.pending.keep_aspect)
        msgs = self._push(self.pending, flash=mapping_changed and not self.live_cb.isChecked())
        self.applied = self.pending.copy()
        self.session_applied = True
        self._load_tabs()
        if msgs:
            self.statusBar().showMessage(f"Applied with {len(msgs)} warning(s) — see the command log", 6000)
            self.log_dock.show()
        else:
            self.statusBar().showMessage("Applied", 2000)

    def revert(self) -> None:
        if self.ctx.tablet:
            self._select_tablet(self.ctx.tablet, keep_pending=False)
            self.statusBar().showMessage("Re-read settings from the tablet", 2000)

    def closeEvent(self, e):
        if self._is_dirty() and self.ctx.tablet:
            r = QMessageBox.question(self, "wacome", "There are changes that were not applied. Quit anyway?")
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        e.accept()
