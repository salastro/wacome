"""Entry point: GUI by default, plus headless --apply / --daemon / --list."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

from . import profile as prof
from .backend.devices import list_tablets
from .backend.monitors import list_monitors
from .backend.runner import Runner


def environment_problem() -> str | None:
    if not shutil.which("xsetwacom"):
        return "xsetwacom was not found. Install xf86-input-wacom (package: xf86-input-wacom / xserver-xorg-input-wacom)."
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or (
            os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")):
        return "This is a Wayland session. xsetwacom only works on X11; use your compositor's tablet settings instead."
    if not os.environ.get("DISPLAY"):
        return "No X display (DISPLAY is unset)."
    return None


def _print_log(res, _write):
    status = "" if res.ok else f"   # FAILED: {(res.stderr or res.stdout).strip()}"
    print(f"$ {res.cmdline}{status}")


def cmd_list(runner: Runner) -> int:
    tablets = list_tablets(runner)
    monitors = list_monitors(runner)
    print("Tablets:")
    for t in tablets or []:
        print(f"  {t.name}")
        for role, d in t.devices.items():
            print(f"    {role:<7} {d.name} (id {d.id})")
    if not tablets:
        print("  (none)")
    print("Monitors:")
    for m in monitors:
        print(f"  {m.name:<10} {m.rect.geometry_string()}{'  primary' if m.primary else ''}")
    print("Profiles:")
    default = prof.default_profile_name()
    for n in prof.list_profiles():
        print(f"  {n}{'  (default)' if n == default else ''}")
    return 0


def _resolve_profile(name: str | None) -> tuple[str, prof.Profile] | None:
    name = name or prof.default_profile_name()
    if not name:
        print("No profile given and no default profile set.", file=sys.stderr)
        return None
    try:
        return name, prof.load_profile(name)
    except (OSError, ValueError) as e:
        print(f"Cannot load profile {name!r}: {e}", file=sys.stderr)
        return None


def cmd_apply(runner: Runner, name: str | None) -> int:
    loaded = _resolve_profile(name)
    if not loaded:
        return 1
    name, p = loaded
    tablets = list_tablets(runner)
    if not tablets:
        print("No tablet connected.", file=sys.stderr)
        return 1
    monitors = list_monitors(runner)
    rc = 0
    for t in tablets:
        print(f"Applying {name!r} to {t.name}")
        for msg in prof.apply(p, t, runner, monitors):
            print(f"  warning: {msg}", file=sys.stderr)
            rc = 2
    return rc


def cmd_daemon(runner: Runner, name: str | None, interval: float) -> int:
    """Apply now, then re-apply whenever a tablet appears or monitors change."""
    seen_tablets: set = set()
    seen_monitors = None
    while True:
        tablets = list_tablets(runner)
        monitors = list_monitors(runner)
        sig_t = {t.signature() for t in tablets}
        sig_m = tuple(monitors)
        new = sig_t - seen_tablets
        if tablets and (new or sig_m != seen_monitors):
            loaded = _resolve_profile(name)
            if loaded:
                for t in tablets:
                    for msg in prof.apply(loaded[1], t, runner, monitors):
                        print(f"warning: {msg}", file=sys.stderr)
        seen_tablets, seen_monitors = sig_t, sig_m
        time.sleep(interval)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wacome", description="Visual xsetwacom configuration")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", nargs="?", const="", metavar="PROFILE",
                   help="apply a profile (default profile if omitted) and exit")
    g.add_argument("--daemon", nargs="?", const="", metavar="PROFILE",
                   help="apply a profile and re-apply on tablet hotplug / monitor changes")
    g.add_argument("--list", action="store_true", help="list tablets, monitors and profiles")
    ap.add_argument("--dry-run", action="store_true", help="print commands without changing anything")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every command")
    args = ap.parse_args(argv)

    headless = args.apply is not None or args.daemon is not None or args.list
    problem = environment_problem()
    if headless:
        if problem:
            print(problem, file=sys.stderr)
            return 1
        runner = Runner(dry_run=args.dry_run)
        if args.verbose or args.dry_run:
            runner.add_listener(_print_log)
        if args.list:
            return cmd_list(runner)
        if args.apply is not None:
            return cmd_apply(runner, args.apply or None)
        try:
            return cmd_daemon(runner, args.daemon or None, 2.0)
        except KeyboardInterrupt:
            return 0

    from .gui.app import run_gui  # Qt is imported only for the GUI
    return run_gui(dry_run=args.dry_run, problem=problem)


if __name__ == "__main__":
    sys.exit(main())
