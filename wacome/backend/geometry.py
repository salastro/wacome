"""Pure geometry helpers: rectangles, rotation and aspect fitting."""

from __future__ import annotations

from dataclasses import dataclass

ROTATIONS = ("none", "cw", "half", "ccw")


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @classmethod
    def from_corners(cls, x1, y1, x2, y2) -> "Rect":
        return cls(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def ratio(self) -> float:
        return self.w / self.h if self.h else 1.0

    def corners(self) -> list[int]:
        return [round(self.x), round(self.y), round(self.x2), round(self.y2)]

    def rounded(self) -> "Rect":
        return Rect(round(self.x), round(self.y), round(self.w), round(self.h))

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x2 and self.y <= py < self.y2

    def geometry_string(self) -> str:
        """X geometry string as accepted by ``xsetwacom MapToOutput``."""
        r = self.rounded()
        return f"{int(r.w)}x{int(r.h)}+{int(r.x)}+{int(r.y)}"

    def clamp_into(self, outer: "Rect") -> "Rect":
        w = min(self.w, outer.w)
        h = min(self.h, outer.h)
        x = min(max(self.x, outer.x), outer.x2 - w)
        y = min(max(self.y, outer.y), outer.y2 - h)
        return Rect(x, y, w, h)


def bounding(rects) -> Rect:
    rects = list(rects)
    if not rects:
        return Rect(0, 0, 0, 0)
    x1 = min(r.x for r in rects)
    y1 = min(r.y for r in rects)
    x2 = max(r.x2 for r in rects)
    y2 = max(r.y2 for r in rects)
    return Rect(x1, y1, x2 - x1, y2 - y1)


def swaps_axes(rotation: str) -> bool:
    return rotation in ("cw", "ccw")


# --- rotation -------------------------------------------------------------
# "Visual" coordinates are how the tablet looks to the user after rotating it
# physically, i.e. the frame in which pen motion matches screen motion.
# Rotate=cw means the tablet was turned 90 degrees clockwise: its top edge is
# now on the right.

def visual_size(full: Rect, rotation: str) -> tuple[float, float]:
    return (full.h, full.w) if swaps_axes(rotation) else (full.w, full.h)


def point_to_visual(px, py, full: Rect, rotation: str) -> tuple[float, float]:
    x, y = px - full.x, py - full.y
    W, H = full.w, full.h
    if rotation == "cw":
        return H - y, x
    if rotation == "ccw":
        return y, W - x
    if rotation == "half":
        return W - x, H - y
    return x, y


def point_from_visual(vx, vy, full: Rect, rotation: str) -> tuple[float, float]:
    W, H = full.w, full.h
    if rotation == "cw":
        x, y = vy, H - vx
    elif rotation == "ccw":
        x, y = W - vy, vx
    elif rotation == "half":
        x, y = W - vx, H - vy
    else:
        x, y = vx, vy
    return x + full.x, y + full.y


def rect_to_visual(r: Rect, full: Rect, rotation: str) -> Rect:
    ax, ay = point_to_visual(r.x, r.y, full, rotation)
    bx, by = point_to_visual(r.x2, r.y2, full, rotation)
    return Rect.from_corners(ax, ay, bx, by)


def rect_from_visual(r: Rect, full: Rect, rotation: str) -> Rect:
    ax, ay = point_from_visual(r.x, r.y, full, rotation)
    bx, by = point_from_visual(r.x2, r.y2, full, rotation)
    return Rect.from_corners(ax, ay, bx, by)


def aspect_fit(full: Rect, target_ratio: float, rotation: str = "none",
               anchor: str = "center") -> Rect:
    """Largest tablet area (tablet coords) whose *visual* aspect equals target_ratio.

    ``anchor`` is "center" or "topleft" (top-left as the user sees the tablet).
    """
    vw, vh = visual_size(full, rotation)
    if vw <= 0 or vh <= 0 or target_ratio <= 0:
        return full
    if vw / vh > target_ratio:
        w, h = vh * target_ratio, vh
    else:
        w, h = vw, vw / target_ratio
    if anchor == "topleft":
        x, y = 0.0, 0.0
    else:
        x, y = (vw - w) / 2, (vh - h) / 2
    return rect_from_visual(Rect(x, y, w, h), full, rotation).rounded()


# --- pressure curve --------------------------------------------------------

def bezier_point(t: float, curve) -> tuple[float, float]:
    """Cubic bezier from (0,0) to (100,100) with control points from curve."""
    x1, y1, x2, y2 = curve
    mt = 1 - t
    x = 3 * mt * mt * t * x1 + 3 * mt * t * t * x2 + t ** 3 * 100
    y = 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t ** 3 * 100
    return x, y


def _solve(curve, value: float, axis: int) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if bezier_point(mid, curve)[axis] < value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def curve_y_at(curve, x: float) -> float:
    """Output pressure (0-100) for physical input x (0-100)."""
    return bezier_point(_solve(curve, x, 0), curve)[1]


def curve_x_at(curve, y: float) -> float:
    """Physical input (0-100) that produced output pressure y (0-100)."""
    return bezier_point(_solve(curve, y, 1), curve)[0]
