"""Monitor layout via ``xrandr --listactivemonitors``."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .geometry import Rect, bounding
from .runner import Runner

# " 0: +*eDP-1 1920/344x1080/194+0+0  eDP-1"
_LINE = re.compile(
    r"^\s*\d+:\s+\+?(?P<primary>\*?)(?P<name>\S+)\s+"
    r"(?P<w>\d+)/(?P<mmw>\d+)x(?P<h>\d+)/(?P<mmh>\d+)\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
)


@dataclass(frozen=True)
class Monitor:
    name: str
    rect: Rect
    primary: bool = False
    mm_w: int = 0
    mm_h: int = 0

    @property
    def label(self) -> str:
        return f"{self.name}  {int(self.rect.w)}x{int(self.rect.h)}"


def parse_monitors(text: str) -> list[Monitor]:
    out = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if m:
            out.append(Monitor(
                name=m["name"],
                rect=Rect(int(m["x"]), int(m["y"]), int(m["w"]), int(m["h"])),
                primary=bool(m["primary"]),
                mm_w=int(m["mmw"]), mm_h=int(m["mmh"]),
            ))
    return out


def list_monitors(runner: Runner) -> list[Monitor]:
    res = runner.run(["xrandr", "--listactivemonitors"])
    if not res.ok:
        return []
    return parse_monitors(res.stdout)


def desktop_rect(monitors: list[Monitor]) -> Rect:
    """The X screen spanned by all monitors (origin is always 0,0 in X)."""
    b = bounding(m.rect for m in monitors)
    return Rect(0, 0, b.x2, b.y2)


def primary_monitor(monitors: list[Monitor]) -> Monitor | None:
    for m in monitors:
        if m.primary:
            return m
    return monitors[0] if monitors else None


def find_monitor(monitors: list[Monitor], name: str) -> Monitor | None:
    return next((m for m in monitors if m.name == name), None)
