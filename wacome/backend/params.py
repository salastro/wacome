"""Typed get/set wrappers around ``xsetwacom`` parameters."""

from __future__ import annotations

import re

from .geometry import Rect
from .runner import Result, Runner


def get(runner: Runner, device: str, param: str, *args) -> str | None:
    res = runner.run(["xsetwacom", "--get", device, param, *map(str, args)])
    if not res.ok or "does not exist" in res.stderr or "no longer" in res.stderr:
        return None
    return res.stdout.strip()


def set_(runner: Runner, device: str, param: str, *values) -> Result:
    return runner.run(["xsetwacom", "--set", device, param, *map(str, values)], write=True)


def _ints(text: str | None, n: int) -> list[int] | None:
    if not text:
        return None
    try:
        vals = [int(v) for v in text.split()]
    except ValueError:
        return None
    return vals if len(vals) == n else None


def get_area(runner, device) -> Rect | None:
    v = _ints(get(runner, device, "Area"), 4)
    return Rect.from_corners(*v) if v else None


def set_area(runner, device, area: Rect) -> Result:
    return set_(runner, device, "Area", *area.corners())


def full_area(runner: Runner, device: str) -> Rect | None:
    """Native tablet area: reset, read, then restore the user's area."""
    current = _ints(get(runner, device, "Area"), 4)
    if runner.dry_run:
        return Rect.from_corners(*current) if current else None
    runner.run(["xsetwacom", "--set", device, "ResetArea"], log=False)
    full = _ints(get(runner, device, "Area"), 4)
    if current and current != full:
        runner.run(["xsetwacom", "--set", device, "Area", *map(str, current)], log=False)
    return Rect.from_corners(*full) if full else None


def get_curve(runner, device) -> list[int] | None:
    return _ints(get(runner, device, "PressureCurve"), 4)


def get_int(runner, device, param) -> int | None:
    v = _ints(get(runner, device, param), 1)
    return v[0] if v else None


def get_bool(runner, device, param) -> bool | None:
    v = get(runner, device, param)
    if v is None:
        return None
    return v.lower() == "on"


def get_button(runner, device, n) -> str | None:
    return get(runner, device, "Button", n)


_CTM = re.compile(r"Coordinate Transformation Matrix \(\d+\):\s*(.+)")


def get_transform_matrix(runner: Runner, device: str) -> list[float] | None:
    res = runner.run(["xinput", "list-props", device])
    if not res.ok:
        return None
    return parse_transform_matrix(res.stdout)


def parse_transform_matrix(text: str) -> list[float] | None:
    m = _CTM.search(text)
    if not m:
        return None
    try:
        vals = [float(v) for v in m.group(1).split(",")]
    except ValueError:
        return None
    return vals if len(vals) == 9 else None


def matrix_to_region(matrix: list[float], desktop: Rect) -> Rect | None:
    """Region of the X screen a device is mapped to (ignores rotation terms)."""
    a, b, c, d, e, f, *_ = matrix
    if abs(b) > 1e-6 or abs(d) > 1e-6:
        return None  # rotated matrix: not produced by MapToOutput
    return Rect(c * desktop.w, f * desktop.h, a * desktop.w, e * desktop.h).rounded()
