"""XDG autostart entry that re-applies the default profile on login."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def autostart_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "autostart" / "wacome.desktop"


def command(*args: str) -> tuple[str, str | None]:
    """(Exec line, working dir) for launching wacome with args."""
    exe = shutil.which("wacome")
    if exe:
        return shlex.join([exe, *args]), None
    return shlex.join([sys.executable, "-m", "wacome", *args]), str(PROJECT_ROOT)


def is_enabled() -> bool:
    return autostart_path().exists()


def enable(watch: bool = True) -> Path:
    exec_line, workdir = command("--daemon" if watch else "--apply")
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=wacome (apply tablet profile)",
        "Comment=Apply the default wacome profile to Wacom tablets",
        f"Exec={exec_line}",
        "Terminal=false",
        "NoDisplay=true",
        "X-GNOME-Autostart-enabled=true",
    ]
    if workdir:
        lines.append(f"Path={workdir}")
    path = autostart_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def disable() -> None:
    autostart_path().unlink(missing_ok=True)
