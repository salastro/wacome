"""Single choke point for every external command wacome runs."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass
class Result:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def cmdline(self) -> str:
        return shlex.join(self.argv)


LogFn = Callable[[Result, bool], None]  # (result, is_write)


class CommandError(RuntimeError):
    def __init__(self, result: Result):
        msg = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
        super().__init__(f"{result.cmdline}: {msg}")
        self.result = result


class Runner:
    """Runs commands as argv lists (never through a shell).

    Write commands (``write=True``) are logged to listeners and skipped in
    dry-run mode; reads are executed even in dry-run so the UI stays accurate.
    """

    def __init__(self, dry_run: bool = False, timeout: float = 5.0):
        self.dry_run = dry_run
        self.timeout = timeout
        self._listeners: list[LogFn] = []

    def add_listener(self, fn: LogFn) -> None:
        self._listeners.append(fn)

    def run(self, argv: Sequence[str], *, write: bool = False, log: bool | None = None,
            check: bool = False) -> Result:
        argv = [str(a) for a in argv]
        if write and self.dry_run:
            res = Result(argv, 0, "", "(dry run)")
        else:
            try:
                p = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout)
                res = Result(argv, p.returncode, p.stdout, p.stderr)
            except FileNotFoundError:
                res = Result(argv, 127, "", f"{argv[0]}: command not found")
            except subprocess.TimeoutExpired:
                res = Result(argv, 124, "", "timed out")
        # xsetwacom reports some failures on stderr with exit code 0
        if res.returncode == 0 and write and res.stderr.strip() and not self.dry_run:
            res.returncode = 1
        if log is None:
            log = write
        if log:
            for fn in self._listeners:
                fn(res, write)
        if check and not res.ok:
            raise CommandError(res)
        return res
