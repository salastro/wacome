from wacome.backend import actions, params
from wacome.backend.devices import group_tablets, parse_devices, tablet_name
from wacome.backend.geometry import (Rect, aspect_fit, curve_x_at, curve_y_at, point_from_visual,
                                     point_to_visual, rect_from_visual, rect_to_visual)
from wacome.backend.monitors import desktop_rect, parse_monitors

DEVICES = """Wacom One by Wacom M Pen stylus \tid: 10\ttype: STYLUS    
Wacom One by Wacom M Pen eraser \tid: 11\ttype: ERASER    
Wacom Intuos Pro M Pad pad      \tid: 14\ttype: PAD
Wacom Intuos Pro M Finger touch \tid: 15\ttype: TOUCH
Wacom Intuos Pro M Pen stylus   \tid: 16\ttype: STYLUS
"""

XRANDR = """Monitors: 2
 0: +*eDP-1 1920/344x1080/194+0+0  eDP-1
 1: +HDMI-1-0 1920/508x1080/286+1920+0  HDMI-1-0
"""

CTM = ("\tDevice Enabled (166):\t1\n\tCoordinate Transformation Matrix (181):\t"
       "0.500000, 0.000000, 0.500000, 0.000000, 1.000000, 0.000000, 0.000000, 0.000000, 1.000000\n")


def test_parse_devices_and_group():
    devs = parse_devices(DEVICES)
    assert [d.id for d in devs] == [10, 11, 14, 15, 16]
    assert devs[0].name == "Wacom One by Wacom M Pen stylus"
    tablets = group_tablets(devs)
    assert [t.name for t in tablets] == ["Wacom One by Wacom M", "Wacom Intuos Pro M"]
    pro = tablets[1]
    assert set(pro.devices) == {"pad", "touch", "stylus"}
    assert tablets[0].eraser.id == 11
    assert tablet_name("Wacom Intuos BT M Pen Pen (0x1234abcd)") == "Wacom Intuos BT M"


def test_parse_monitors():
    mons = parse_monitors(XRANDR)
    assert [m.name for m in mons] == ["eDP-1", "HDMI-1-0"]
    assert mons[0].primary and not mons[1].primary
    assert mons[1].rect == Rect(1920, 0, 1920, 1080)
    assert desktop_rect(mons) == Rect(0, 0, 3840, 1080)


def test_matrix_to_region():
    m = params.parse_transform_matrix(CTM)
    assert params.matrix_to_region(m, Rect(0, 0, 3840, 1080)) == Rect(1920, 0, 1920, 1080)


def test_geometry_string():
    assert Rect(1920, 0, 1920, 1080).geometry_string() == "1920x1080+1920+0"


def test_rotation_roundtrip():
    full = Rect(0, 0, 21600, 13500)
    r = Rect(100, 200, 3000, 4000)
    for rot in ("none", "cw", "half", "ccw"):
        assert rect_from_visual(rect_to_visual(r, full, rot), full, rot) == r
        x, y = point_from_visual(*point_to_visual(5, 7, full, rot), full, rot)
        assert (round(x), round(y)) == (5, 7)
    # cw: tablet top edge ends up on the right
    assert point_to_visual(0, 0, full, "cw") == (13500, 0)
    assert rect_to_visual(full, full, "cw") == Rect(0, 0, 13500, 21600)


def test_aspect_fit():
    full = Rect(0, 0, 21600, 13500)  # 16:10
    a = aspect_fit(full, 16 / 9)
    assert a.w == 21600 and a.h == 12150 and a.y == 675
    a = aspect_fit(full, 16 / 9, anchor="topleft")
    assert (a.x, a.y) == (0, 0)
    a = aspect_fit(full, 32 / 9)  # dual 1080p: wide
    assert a.w == 21600 and round(a.h) == 6075
    # rotated: visual tablet is 13500 x 21600, fit 16:9 -> width-limited
    a = aspect_fit(full, 16 / 9, rotation="cw")
    v = rect_to_visual(a, full, "cw")
    assert v.w == 13500 and abs(v.w / v.h - 16 / 9) < 0.01


def test_curve():
    lin = [0, 0, 100, 100]
    assert abs(curve_y_at(lin, 50) - 50) < 0.5
    soft = [0, 40, 60, 100]
    assert curve_y_at(soft, 50) > 55
    y = curve_y_at(soft, 30)
    assert abs(curve_x_at(soft, y) - 30) < 0.5


def test_actions():
    assert actions.keystroke(["ctrl", "shift", "z"]) == "key +ctrl +shift z -shift -ctrl"
    assert actions.describe("key +ctrl +shift z -shift -ctrl") == "Ctrl+Shift+Z"
    assert actions.describe("button +3 ") == "Right click"
    assert actions.classify("button +3") == "mouse"
    assert actions.classify("0") == "disabled"
    assert actions.classify("pan") == "pan"
    assert actions.key_list("key +ctrl z -ctrl") == ["ctrl", "z"]
