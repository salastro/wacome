import pytest

from wacome import profile as prof
from wacome.backend.devices import group_tablets, parse_devices
from wacome.backend.geometry import Rect
from wacome.backend.monitors import parse_monitors
from wacome.backend.runner import Result, Runner

from .test_backend import XRANDR

STYLUS = "Wacom One by Wacom M Pen stylus"
ERASER = "Wacom One by Wacom M Pen eraser"


class FakeRunner(Runner):
    def __init__(self):
        super().__init__()
        self.writes = []

    def run(self, argv, *, write=False, log=None, check=False):
        argv = [str(a) for a in argv]
        if write:
            self.writes.append(argv)
        return Result(argv, 0, "", "")


@pytest.fixture
def tablet():
    return group_tablets(parse_devices(f"{STYLUS}\tid: 10\ttype: STYLUS\n{ERASER}\tid: 11\ttype: ERASER\n"))[0]


@pytest.fixture
def monitors():
    return parse_monitors(XRANDR)


def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = prof.Profile(target={"kind": "output", "name": "HDMI-1-0"}, keep_aspect=True,
                     buttons={"stylus": {"3": "key +ctrl z -ctrl"}})
    prof.save_profile("Art", p)
    assert prof.list_profiles() == ["Art"]
    assert prof.load_profile("Art") == p
    prof.set_default_profile("Art")
    assert prof.default_profile_name() == "Art"


def test_apply_argv(tablet, monitors):
    r = FakeRunner()
    p = prof.Profile(target={"kind": "output", "name": "HDMI-1-0"}, keep_aspect=True,
                     full_area=[0, 0, 21600, 13500], threshold=26,
                     buttons={"stylus": {"3": "key +ctrl z -ctrl"}})
    assert prof.apply(p, tablet, r, monitors) == []
    w = r.writes
    assert ["xsetwacom", "--set", STYLUS, "Rotate", "none"] in w
    assert ["xsetwacom", "--set", STYLUS, "Area", "0", "675", "21600", "12825"] in w
    assert ["xsetwacom", "--set", ERASER, "MapToOutput", "1920x1080+1920+0"] in w
    assert ["xsetwacom", "--set", STYLUS, "Button", "3", "key +ctrl z -ctrl"] in w
    assert ["xsetwacom", "--set", STYLUS, "Threshold", "26"] in w
    # rotate precedes area precedes map
    idx = [a[3] for a in w if a[2] == STYLUS]
    assert idx.index("Rotate") < idx.index("Area") < idx.index("MapToOutput")


def test_missing_output_falls_back(tablet, monitors):
    region, arg, warn = prof.resolve_target(prof.Profile(target={"kind": "output", "name": "DP-9"}), monitors)
    assert region == Rect(0, 0, 1920, 1080) and warn
    region, arg, _ = prof.resolve_target(prof.Profile(), monitors)
    assert arg == "desktop" and region.w == 3840


def test_single_monitor_uses_desktop(monitors):
    _, arg, _ = prof.resolve_target(prof.Profile(target={"kind": "output", "name": "eDP-1"}), monitors[:1])
    assert arg == "desktop"


def test_target_from_region(monitors):
    assert prof.target_from_region(Rect(1920, 0, 1920, 1080), monitors) == {"kind": "output", "name": "HDMI-1-0"}
    assert prof.target_from_region(Rect(0, 0, 3840, 1080), monitors) == {"kind": "desktop"}
    assert prof.target_from_region(Rect(10, 10, 100, 100), monitors)["kind"] == "region"
