"""Builds and runs the kicad-cli commands that produce a board's plot and drill files."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[list[str]], CommandResult]


def run(command: list[str], timeout: int = 900) -> CommandResult:
    """Run a command, capturing its output."""
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def gerber_command(cli: str, board: Path, out_dir: Path) -> list[str]:
    """Plot with the board's saved plot settings, refilling zones inside this board's outline."""
    return [cli, "pcb", "export", "gerbers", "--board-plot-params", "--check-zones",
            "-o", str(out_dir), str(board)]


def drill_command(cli: str, board: Path, out_dir: Path, drill_args: list[str]) -> list[str]:
    return [cli, "pcb", "export", "drill", *drill_args, "-o", str(out_dir), str(board)]


def cli_version(cli: str, runner: Runner = run) -> Optional[tuple[int, int]]:
    """(major, minor) reported by ``kicad-cli --version``, or None if it cannot be determined."""
    try:
        result = runner([cli, "--version"])
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\.(\d+)", result.stdout) if result.returncode == 0 else None
    return (int(match.group(1)), int(match.group(2))) if match else None


def check_version(version: Optional[tuple[int, int]], generator_version: Optional[str]
                  ) -> tuple[Optional[str], Optional[str]]:
    """(error, warning) about kicad-cli reading this board.

    A kicad-cli older than the board's writer cannot open it, so that is an error. A newer one
    reads older boards, so a difference in that direction is only a warning.
    """
    if version is None:
        return "could not determine the kicad-cli version (is the path correct?)", None
    match = re.match(r"(\d+)\.(\d+)", generator_version or "")
    if not match:
        return None, None  # the board does not say which version wrote it; nothing to compare
    board = (int(match.group(1)), int(match.group(2)))
    if board > version:
        return (f"kicad-cli is version {version[0]}.{version[1]} but the board was written by "
                f"{board[0]}.{board[1]}, which it cannot read; use a kicad-cli that is "
                f"{board[0]}.{board[1]} or newer"), None
    if board < version:
        return None, (f"kicad-cli is version {version[0]}.{version[1]} but the board was written by "
                      f"{board[0]}.{board[1]}; it should read the board, but check the outputs")
    return None, None
