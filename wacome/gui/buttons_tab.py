"""Pen / eraser / pad button mapping with a visual diagram."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QKeySequenceEdit,
                               QLabel, QLineEdit, QPushButton, QStackedWidget, QToolButton, QVBoxLayout,
                               QWidget)

from ..backend import actions as act
from ..profile import ERASER_BUTTONS, PAD_BUTTONS, PAD_EXTRAS, STYLUS_BUTTONS
from .context import Ctx, SettingsTab
from .widgets.pen_diagram import TITLES, PenDiagram
from .widgets.penstate import pen_state
from .widgets.test_canvas import TestCanvas

_SPECIAL_KEYS = {
    Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "Return", Qt.Key.Key_Enter: "Return",
    Qt.Key.Key_Escape: "Escape", Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Backspace: "BackSpace",
    Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "Prior", Qt.Key.Key_PageDown: "Next",
    Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right", Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Minus: "minus", Qt.Key.Key_Plus: "plus", Qt.Key.Key_Equal: "equal",
    Qt.Key.Key_BracketLeft: "bracketleft", Qt.Key.Key_BracketRight: "bracketright",
    Qt.Key.Key_Comma: "comma", Qt.Key.Key_Period: "period", Qt.Key.Key_Slash: "slash",
    Qt.Key.Key_Backslash: "backslash", Qt.Key.Key_Semicolon: "semicolon",
    Qt.Key.Key_Apostrophe: "apostrophe", Qt.Key.Key_QuoteLeft: "grave", Qt.Key.Key_Print: "Print",
}


def keys_from_sequence(seq: QKeySequence) -> list[str]:
    if seq.isEmpty():
        return []
    combo = seq[0]
    key, mods = combo.key(), combo.keyboardModifiers()
    out = []
    for flag, name in ((Qt.KeyboardModifier.ControlModifier, "ctrl"),
                       (Qt.KeyboardModifier.ShiftModifier, "shift"),
                       (Qt.KeyboardModifier.AltModifier, "alt"),
                       (Qt.KeyboardModifier.MetaModifier, "super")):
        if mods & flag:
            out.append(name)
    k = int(key.value) if hasattr(key, "value") else int(key)
    if Qt.Key.Key_A.value <= k <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= k <= Qt.Key.Key_9.value:
        out.append(chr(k).lower())
    elif Qt.Key.Key_F1.value <= k <= Qt.Key.Key_F35.value:
        out.append(f"F{k - Qt.Key.Key_F1.value + 1}")
    elif key in _SPECIAL_KEYS:
        out.append(_SPECIAL_KEYS[key])
    else:
        text = QKeySequence(key).toString()
        if text:
            out.append(text.lower() if len(text) == 1 else text)
    return out


def sequence_from_keys(keys: list[str]) -> QKeySequence:
    names = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "super": "Meta", "meta": "Meta"}
    rev = {v: k for k, v in _SPECIAL_KEYS.items()}
    parts = []
    for k in keys:
        if k.lower() in names:
            parts.append(names[k.lower()])
        elif k in rev:
            parts.append(QKeySequence(rev[k]).toString())
        else:
            parts.append(k.upper() if len(k) == 1 else k)
    return QKeySequence("+".join(parts))


class ActionEditor(QGroupBox):
    actionChanged = Signal(str)

    KINDS = [("mouse", "Mouse button"), ("key", "Keyboard shortcut"), ("pan", "Pan / scroll (drag to scroll)"),
             ("disabled", "Disabled"), ("custom", "Custom xsetwacom action")]

    def __init__(self):
        super().__init__("Action")
        f = QFormLayout(self)
        self.kind = QComboBox()
        for k, label in self.KINDS:
            self.kind.addItem(label, k)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        f.addRow("Does", self.kind)

        self.stack = QStackedWidget()
        self.mouse = QComboBox()
        for n, label in act.MOUSE_BUTTONS.items():
            self.mouse.addItem(f"{label} (button {n})", n)
        self.mouse.currentIndexChanged.connect(self._emit)
        self.keyedit = QKeySequenceEdit()
        if hasattr(self.keyedit, "setMaximumSequenceLength"):
            self.keyedit.setMaximumSequenceLength(1)
        self.keyedit.keySequenceChanged.connect(self._emit)
        key_row = QWidget()
        kl = QHBoxLayout(key_row)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.addWidget(self.keyedit, 1)
        clr = QPushButton("Clear")
        clr.clicked.connect(self.keyedit.clear)
        kl.addWidget(clr)
        self.custom = QLineEdit()
        self.custom.setPlaceholderText("e.g. key +ctrl +shift z -shift -ctrl")
        self.custom.editingFinished.connect(self._emit)
        for w in (self.mouse, key_row, QLabel("Hold the button and move the pen to scroll."),
                  QLabel("The button does nothing."), self.custom):
            self.stack.addWidget(w)
        f.addRow(self.stack)
        self.preview = QLabel()
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview.setWordWrap(True)
        f.addRow(self.preview)
        self._loading = False

    def set_value(self, title: str, value: str, device: str, param: list[str]) -> None:
        self._loading = True
        self.setTitle(f"Action — {title}")
        self._device, self._param = device, param
        kind = act.classify(value)
        self.kind.setCurrentIndex([k for k, _ in self.KINDS].index(kind))
        self.stack.setCurrentIndex(self.kind.currentIndex())
        if kind == "mouse":
            self.mouse.setCurrentIndex(max(self.mouse.findData(act.mouse_number(value)), 0))
        elif kind == "key":
            self.keyedit.setKeySequence(sequence_from_keys(act.key_list(value)))
        self.custom.setText(value.strip())
        self._loading = False
        self._show_preview(value)

    def _show_preview(self, value: str) -> None:
        import shlex
        cmd = shlex.join(["xsetwacom", "--set", getattr(self, "_device", "<device>"),
                          *getattr(self, "_param", ["Button", "N"]), value])
        self.preview.setText(f"<small><code>{cmd}</code></small>")

    def _kind_changed(self) -> None:
        self.stack.setCurrentIndex(self.kind.currentIndex())
        self._emit()

    def value(self) -> str:
        kind = self.kind.currentData()
        if kind == "mouse":
            return act.mouse(self.mouse.currentData())
        if kind == "key":
            return act.keystroke(keys_from_sequence(self.keyedit.keySequence()))
        if kind == "pan":
            return act.PAN
        if kind == "disabled":
            return act.DISABLED
        return self.custom.text().strip() or act.DISABLED

    def _emit(self, *_):
        if self._loading:
            return
        kind = self.kind.currentData()
        # wait until something is captured/typed, otherwise "key" with no keys
        # would round-trip to "Disabled" and flip the editor away from the user
        if (kind == "key" and not keys_from_sequence(self.keyedit.keySequence())) or \
                (kind == "custom" and not self.custom.text().strip()):
            self.preview.setText("<small>Press the shortcut to assign…</small>" if kind == "key"
                                 else "<small>Type an xsetwacom action…</small>")
            if kind == "key":
                self.keyedit.setFocus()
            return
        v = self.value()
        self._show_preview(v)
        self.actionChanged.emit(v)


class ButtonsTab(SettingsTab):
    def __init__(self, ctx: Ctx, parent=None):
        super().__init__(ctx, parent)
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        pen_box = QGroupBox("Pen — click a part to change what it does")
        pl = QVBoxLayout(pen_box)
        self.diagram = PenDiagram()
        self.diagram.hotspotClicked.connect(lambda r, b: self._select((r, b)))
        pl.addWidget(self.diagram)
        left.addWidget(pen_box)

        self.pad_box = QGroupBox("Tablet buttons (ExpressKeys)")
        self.pad_grid = QGridLayout(self.pad_box)
        self.pad_buttons: dict[str, QToolButton] = {}
        for i, b in enumerate(PAD_BUTTONS + PAD_EXTRAS):
            tb = QToolButton()
            tb.setCheckable(True)
            tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            tb.setMinimumSize(110, 44)
            tb.clicked.connect(lambda _=False, b=b: self._select(("pad", b)))
            self.pad_grid.addWidget(tb, i // 5, i % 5)
            self.pad_buttons[b] = tb
        left.addWidget(self.pad_box)

        test_box = QGroupBox("Test — press pen buttons over this area; the matching part lights up")
        tl = QVBoxLayout(test_box)
        self.canvas = TestCanvas(hint="Hover and press the pen's buttons here")
        self.canvas.setMinimumHeight(120)
        tl.addWidget(self.canvas)
        left.addWidget(test_box, 1)
        root.addLayout(left, 1)

        self.editor = ActionEditor()
        self.editor.setFixedWidth(330)
        self.editor.actionChanged.connect(self._action_changed)
        right = QVBoxLayout()
        right.addWidget(self.editor)
        right.addStretch(1)
        root.addLayout(right)

        self.selected = ("stylus", "3")
        pen_state().buttonPressed.connect(self._physical_button)

    # --- helpers --------------------------------------------------------------------------
    def _keys(self):
        t = self.ctx.tablet
        keys = [("stylus", b) for b in STYLUS_BUTTONS]
        if not t or t.eraser:
            keys += [("eraser", b) for b in ERASER_BUTTONS]
        if t and t.pad:
            keys += [("pad", b) for b in PAD_BUTTONS + PAD_EXTRAS]
        return keys

    def _value(self, prof, key) -> str:
        role, b = key
        default = act.mouse(int(b)) if b.isdigit() else act.DISABLED
        return prof.buttons.get(role, {}).get(b, default)

    def _title(self, key) -> str:
        if key in TITLES:
            return TITLES[key]
        return f"Tablet button {key[1]}" if key[1].isdigit() else key[1]

    # --- refresh --------------------------------------------------------------------------
    def refresh(self) -> None:
        t = self.ctx.tablet
        keys = self._keys()
        if self.selected not in keys:
            self.selected = ("stylus", "3")
        info = {}
        for k in keys:
            v = self._value(self.pending, k)
            info[k] = (act.describe(v), v.strip() != self._value(self.applied, k).strip())
        self.diagram.set_actions(info, has_eraser=not t or bool(t.eraser))
        self.diagram.set_selected(self.selected if self.selected[0] != "pad" else None)
        self.pad_box.setVisible(bool(t and t.pad))
        for b, tb in self.pad_buttons.items():
            k = ("pad", b)
            if k in info:
                desc, changed = info[k]
                tb.setText(f"{self._title(k)}\n{desc}{' •' if changed else ''}")
            tb.setChecked(k == self.selected)
        dev = t.devices.get(self.selected[0]) if t else None
        b = self.selected[1]
        param = ["Button", b] if b.isdigit() else [b]
        self.editor.set_value(self._title(self.selected), self._value(self.pending, self.selected),
                              dev.name if dev else "<device>", param)

    def _select(self, key) -> None:
        self.selected = key
        self.load(self.pending, self.applied)

    def _action_changed(self, value: str) -> None:
        role, b = self.selected
        self.pending.buttons.setdefault(role, {})[b] = value
        self.load(self.pending, self.applied)
        self.emit_changed()

    def _physical_button(self, n: int) -> None:
        """Light up whichever pen part currently produces X button n."""
        tool = pen_state().tool
        candidates = [k for k in self._keys() if k[0] != "pad"]
        for k in candidates:
            v = self._value(self.applied, k)
            if act.classify(v) == "mouse" and act.mouse_number(v) == n:
                if k[0] == "eraser" and tool != "eraser":
                    continue
                if k[0] == "stylus" and k[1] == "1" and tool == "eraser":
                    continue
                self.diagram.flash(k)
                return
