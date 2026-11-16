"""Button action strings: parse, build and describe xsetwacom ``Button`` values."""

from __future__ import annotations

MOUSE_BUTTONS = {
    1: "Left click",
    2: "Middle click",
    3: "Right click",
    4: "Scroll up",
    5: "Scroll down",
    6: "Scroll left",
    7: "Scroll right",
    8: "Back",
    9: "Forward",
}

MODIFIERS = ("ctrl", "shift", "alt", "super", "meta", "altgr")

_PRETTY_KEYS = {
    "ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "super": "Super", "meta": "Meta",
    "altgr": "AltGr", "space": "Space", "tab": "Tab", "return": "Enter",
    "backspace": "Backspace", "esc": "Esc", "escape": "Esc", "delete": "Del",
    "minus": "-", "plus": "+", "equal": "=", "bracketleft": "[", "bracketright": "]",
    "comma": ",", "period": ".", "slash": "/",
}

DISABLED = "button 0"
PAN = "pan"


def mouse(n: int) -> str:
    return f"button +{n}"


def keystroke(keys: list[str]) -> str:
    """keys like ["ctrl", "shift", "z"] -> "key +ctrl +shift z -shift -ctrl"."""
    keys = [k.lower() for k in keys if k]
    if not keys:
        return DISABLED
    mods = [k for k in keys[:-1]]
    last = keys[-1]
    parts = [f"+{m}" for m in mods] + [last] + [f"-{m}" for m in reversed(mods)]
    return "key " + " ".join(parts)


def classify(value: str) -> str:
    """Return one of: mouse, key, pan, disabled, custom."""
    v = (value or "").strip().lower()
    toks = v.split()
    if not toks or toks == ["0"] or toks in (["button", "0"], ["button", "+0"]):
        return "disabled"
    if toks == ["pan"]:
        return "pan"
    if toks[0] == "button" and len(toks) == 2 and toks[1].lstrip("+").isdigit():
        return "mouse"
    if toks[0].isdigit() and len(toks) == 1:
        return "mouse"
    if toks[0] == "key":
        return "key"
    return "custom"


def mouse_number(value: str) -> int:
    toks = value.strip().lower().split()
    tok = toks[-1].lstrip("+") if toks else "0"
    return int(tok) if tok.isdigit() else 0


def key_list(value: str) -> list[str]:
    """Best-effort inverse of keystroke(): "key +ctrl z -ctrl" -> ["ctrl", "z"]."""
    toks = value.strip().split()[1:]
    held, out = [], []
    for t in toks:
        if t.startswith("+"):
            held.append(t[1:])
        elif t.startswith("-"):
            continue
        else:
            out.append(t)
    return held + out


def _pretty_key(k: str) -> str:
    k = k.lower()
    if k in _PRETTY_KEYS:
        return _PRETTY_KEYS[k]
    return k.upper() if len(k) == 1 else k.capitalize()


def describe(value: str) -> str:
    kind = classify(value)
    if kind == "disabled":
        return "Disabled"
    if kind == "pan":
        return "Pan / scroll"
    if kind == "mouse":
        n = mouse_number(value)
        return MOUSE_BUTTONS.get(n, f"Mouse button {n}")
    if kind == "key":
        return "+".join(_pretty_key(k) for k in key_list(value)) or "Key"
    return value.strip()
