"""Discover tablets via ``xsetwacom --list devices``."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .runner import Runner

_LINE = re.compile(r"^(?P<name>.*?)\s+id:\s*(?P<id>\d+)\s+type:\s*(?P<type>\S+)")
# "Wacom One by Wacom M Pen stylus" -> "Wacom One by Wacom M"
_SUFFIX = re.compile(
    r"\s+(Pen|Pad|Finger|Touch|Cursor)?\s*(stylus|eraser|pad|touch|cursor|Pen \(0x[0-9a-f]+\))\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Device:
    name: str
    id: int
    type: str  # STYLUS, ERASER, PAD, TOUCH, CURSOR

    @property
    def role(self) -> str:
        return self.type.lower()


@dataclass
class Tablet:
    name: str
    devices: dict[str, Device] = field(default_factory=dict)  # role -> device

    @property
    def stylus(self) -> Device | None:
        return self.devices.get("stylus")

    @property
    def eraser(self) -> Device | None:
        return self.devices.get("eraser")

    @property
    def pad(self) -> Device | None:
        return self.devices.get("pad")

    @property
    def touch(self) -> Device | None:
        return self.devices.get("touch")

    def pointer_devices(self) -> list[Device]:
        """Devices that move the cursor and therefore take Area/MapToOutput."""
        return [d for r in ("stylus", "eraser", "cursor", "touch")
                if (d := self.devices.get(r))]

    def pen_devices(self) -> list[Device]:
        return [d for r in ("stylus", "eraser") if (d := self.devices.get(r))]

    def signature(self) -> tuple:
        return (self.name, tuple(sorted((r, d.name) for r, d in self.devices.items())))


def tablet_name(device_name: str) -> str:
    stripped = _SUFFIX.sub("", device_name).strip()
    return stripped or device_name


def parse_devices(text: str) -> list[Device]:
    out = []
    for line in text.splitlines():
        m = _LINE.match(line.strip())
        if m:
            out.append(Device(m["name"].strip(), int(m["id"]), m["type"].upper()))
    return out


def group_tablets(devices: list[Device]) -> list[Tablet]:
    tablets: dict[str, Tablet] = {}
    for d in devices:
        t = tablets.setdefault(tablet_name(d.name), Tablet(tablet_name(d.name)))
        t.devices.setdefault(d.role, d)
    return list(tablets.values())


def list_tablets(runner: Runner) -> list[Tablet]:
    res = runner.run(["xsetwacom", "--list", "devices"])
    if not res.ok:
        return []
    return group_tablets(parse_devices(res.stdout))
