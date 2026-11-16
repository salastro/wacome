"""Profiles: a full description of a tablet configuration, stored as JSON."""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .backend import params
from .backend.devices import Tablet
from .backend.geometry import ROTATIONS, Rect, aspect_fit
from .backend.monitors import Monitor, desktop_rect, find_monitor, primary_monitor
from .backend.runner import Runner

STYLUS_BUTTONS = ["1", "2", "3"]
ERASER_BUTTONS = ["1"]
PAD_BUTTONS = ["1", "2", "3", "8", "9", "10", "11", "12", "13"]
PAD_EXTRAS = ["AbsWheelUp", "AbsWheelDown", "StripLeftUp", "StripLeftDown",
              "StripRightUp", "StripRightDown"]

LINEAR = [0, 0, 100, 100]
CURVE_PRESETS = {
    "Very soft": [0, 75, 25, 100],
    "Soft": [0, 40, 60, 100],
    "Linear": LINEAR,
    "Firm": [40, 0, 100, 60],
    "Very firm": [75, 0, 100, 25],
}


@dataclass
class Profile:
    # where the tablet maps: {"kind": "desktop"} | {"kind": "output", "name": ...}
    # | {"kind": "region", "rect": [x, y, w, h]}
    target: dict = field(default_factory=lambda: {"kind": "desktop"})
    area: list[int] | None = None          # tablet coords x1 y1 x2 y2; None = auto
    keep_aspect: bool = False
    anchor: str = "center"                 # center | topleft
    rotate: str = "none"
    pressure_curve: list[int] = field(default_factory=lambda: list(LINEAR))
    threshold: int | None = None
    buttons: dict[str, dict[str, str]] = field(default_factory=dict)  # role -> {btn: action}
    mode: str = "Absolute"
    suppress: int | None = None
    raw_sample: int | None = None
    touch: bool | None = None
    gesture: bool | None = None
    full_area: list[int] | None = None     # cached native area, for headless apply

    def copy(self) -> "Profile":
        return copy.deepcopy(self)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        known = {f.name for f in fields(cls)}
        p = cls(**{k: v for k, v in data.items() if k in known})
        if p.rotate not in ROTATIONS:
            p.rotate = "none"
        return p


# --- resolution ------------------------------------------------------------

def resolve_target(p: Profile, monitors: list[Monitor]) -> tuple[Rect, str, list[str]]:
    """-> (screen region, MapToOutput argument, warnings)."""
    warnings: list[str] = []
    desk = desktop_rect(monitors) if monitors else Rect(0, 0, 0, 0)
    kind = p.target.get("kind", "desktop")
    if kind == "output":
        name = p.target.get("name", "")
        mon = find_monitor(monitors, name)
        if mon is None:
            mon = primary_monitor(monitors)
            if mon is None:
                return desk, "desktop", [f"Monitor {name!r} not connected; no monitors found"]
            warnings.append(f"Monitor {name!r} not connected; using {mon.name} instead")
        if len(monitors) == 1:
            return mon.rect, "desktop", warnings
        return mon.rect, mon.rect.geometry_string(), warnings
    if kind == "region" and p.target.get("rect"):
        r = Rect(*p.target["rect"])
        if desk.w and desk.h:
            r = r.clamp_into(desk)
        return r, r.geometry_string(), warnings
    return desk, "desktop", warnings


def effective_area(p: Profile, full: Rect, region: Rect) -> Rect:
    if p.area:
        return Rect.from_corners(*p.area)
    if p.keep_aspect and region.w and region.h:
        return aspect_fit(full, region.ratio, p.rotate, p.anchor)
    return full


# --- apply / read ------------------------------------------------------------

def apply(p: Profile, tablet: Tablet, runner: Runner, monitors: list[Monitor]) -> list[str]:
    """Push a profile to the tablet. Returns human-readable warnings/errors."""
    msgs: list[str] = []

    def do(dev: str, param: str, *vals):
        res = params.set_(runner, dev, param, *vals)
        if not res.ok:
            msgs.append(f"{param} on {dev}: {(res.stderr or res.stdout).strip()}")

    pens = tablet.pen_devices()
    stylus = tablet.stylus or (pens[0] if pens else None)
    region, map_arg, warn = resolve_target(p, monitors)
    msgs += warn

    if stylus:
        full = Rect.from_corners(*p.full_area) if p.full_area else params.full_area(runner, stylus.name)
        for dev in pens:
            do(dev.name, "Rotate", p.rotate)
        if full:
            area = effective_area(p, full, region)
            for dev in pens:
                do(dev.name, "Area", *area.corners())
        for dev in pens:
            do(dev.name, "PressureCurve", *p.pressure_curve)
            if p.threshold is not None:
                do(dev.name, "Threshold", p.threshold)
            if p.mode:
                do(dev.name, "Mode", p.mode)
        if p.suppress is not None:
            do(stylus.name, "Suppress", p.suppress)
        if p.raw_sample is not None:
            do(stylus.name, "RawSample", p.raw_sample)

    for dev in tablet.pointer_devices():
        do(dev.name, "MapToOutput", map_arg)

    for role, mapping in p.buttons.items():
        dev = tablet.devices.get(role)
        if not dev:
            continue
        for btn, action in mapping.items():
            if btn.isdigit():
                do(dev.name, "Button", btn, action)
            else:
                do(dev.name, btn, action)

    if tablet.touch:
        if p.touch is not None:
            do(tablet.touch.name, "Touch", "on" if p.touch else "off")
        if p.gesture is not None:
            do(tablet.touch.name, "Gesture", "on" if p.gesture else "off")
    return msgs


def read_buttons(tablet: Tablet, runner: Runner) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    spec = {"stylus": STYLUS_BUTTONS, "eraser": ERASER_BUTTONS, "pad": PAD_BUTTONS}
    for role, btns in spec.items():
        dev = tablet.devices.get(role)
        if not dev:
            continue
        m = {}
        for b in btns:
            v = params.get_button(runner, dev.name, b)
            if v is not None:
                m[b] = v
        if role == "pad":
            for extra in PAD_EXTRAS:
                v = params.get(runner, dev.name, extra)
                if v:
                    m[extra] = v
        out[role] = m
    return out


def from_device(tablet: Tablet, runner: Runner, monitors: list[Monitor]) -> Profile:
    """Snapshot the tablet's live configuration as a Profile."""
    p = Profile()
    stylus = tablet.stylus or (tablet.pen_devices() or [None])[0]
    if stylus:
        n = stylus.name
        full = params.full_area(runner, n)
        area = params.get_area(runner, n)
        p.full_area = full.corners() if full else None
        p.area = area.corners() if area and full and area != full else None
        p.rotate = params.get(runner, n, "Rotate") or "none"
        p.pressure_curve = params.get_curve(runner, n) or list(LINEAR)
        p.threshold = params.get_int(runner, n, "Threshold")
        p.mode = (params.get(runner, n, "Mode") or "Absolute").capitalize()
        p.suppress = params.get_int(runner, n, "Suppress")
        p.raw_sample = params.get_int(runner, n, "RawSample")
        matrix = params.get_transform_matrix(runner, n)
        if matrix and monitors:
            p.target = target_from_region(params.matrix_to_region(matrix, desktop_rect(monitors)),
                                          monitors)
    if tablet.touch:
        p.touch = params.get_bool(runner, tablet.touch.name, "Touch")
        p.gesture = params.get_bool(runner, tablet.touch.name, "Gesture")
    p.buttons = read_buttons(tablet, runner)
    return p


def target_from_region(region: Rect | None, monitors: list[Monitor]) -> dict:
    if region is None:
        return {"kind": "desktop"}
    desk = desktop_rect(monitors)

    def close(a: Rect, b: Rect) -> bool:
        return all(abs(u - v) <= 2 for u, v in zip((a.x, a.y, a.w, a.h), (b.x, b.y, b.w, b.h)))

    if close(region, desk):
        return {"kind": "desktop"}
    for m in monitors:
        if close(region, m.rect):
            return {"kind": "output", "name": m.name}
    return {"kind": "region", "rect": [region.x, region.y, region.w, region.h]}


# --- storage ---------------------------------------------------------------

def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "wacome"


def profiles_dir() -> Path:
    return config_dir() / "profiles"


_SAFE = re.compile(r"[^A-Za-z0-9 _.-]")


def _path(name: str) -> Path:
    safe = _SAFE.sub("_", name).strip(". ") or "profile"
    return profiles_dir() / f"{safe}.json"


def list_profiles() -> list[str]:
    d = profiles_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def load_profile(name: str) -> Profile:
    return Profile.from_dict(json.loads(_path(name).read_text()))


def save_profile(name: str, p: Profile) -> Path:
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(p.to_json())
    tmp.replace(path)
    return path


def delete_profile(name: str) -> None:
    _path(name).unlink(missing_ok=True)


def _settings_path() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(_settings_path().read_text())
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def default_profile_name() -> str | None:
    name = load_settings().get("default")
    return name if name in list_profiles() else None


def set_default_profile(name: str | None) -> None:
    s = load_settings()
    s["default"] = name
    save_settings(s)
