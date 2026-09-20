"""KiCad IPC glue: the only module that talks to a running KiCad (through kipy).

Everything else in the package works on files, so it can be tested without KiCad.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Optional

from . import exporter, report
from .plan import Snapshot
from .runner import exit_code, run_pipeline

IDENTIFIER = "io.github.multiboard-fab-export"


def open_in_viewer(path: Path) -> None:
    """Show the report in the system's default text viewer. Best effort."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - opening our own report file
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def _project_file(directory: Path) -> Optional[Path]:
    found = sorted(directory.glob("*.kicad_pro"))
    return found[0] if found else None


class KiCadSession:
    """A connection to the running KiCad, and the means to snapshot the board it has open."""

    def __init__(self) -> None:
        from kipy import KiCad  # imported here so the rest of the package needs no kipy

        self._kicad = KiCad()
        self.settings_dir = Path(self._kicad.get_plugin_settings_path(IDENTIFIER))

    def snapshot(self, scratch: Path) -> tuple[Snapshot, Optional[str]]:
        """Save a private copy of the open board into ``scratch``; return it and the kicad-cli path."""
        board = self._kicad.get_board()
        project_dir = board.get_project().path
        if not project_dir:
            raise RuntimeError("KiCad did not report the project directory of the open board")
        cli = self._kicad.get_kicad_binary_path("kicad-cli")
        snapshot_board = scratch / "snapshot.kicad_pcb"
        board.save_as(str(snapshot_board), overwrite=True, include_project=True)
        return Snapshot(snapshot_board, _project_file(scratch), Path(project_dir) / board.name), cli


def _write_report(text: str, name: str, directories: list[Path]) -> Optional[Path]:
    """Write the report into the first directory that works; None if none do."""
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / name
            path.write_bytes(text.encode("utf-8", errors="replace"))
            return path
        except Exception:  # noqa: BLE001 - try the next location
            continue
    return None


def run_action(dry_run: bool, runner: exporter.Runner = exporter.run, notice: str = "") -> int:
    """Snapshot the open board, run the pipeline, and show the report as a file. Returns the exit code.

    This is the path without a window: the export dialog needs wxPython, and falls back to this when it
    is missing. ``notice`` is put above the report.
    """
    fallback_dir = Path(tempfile.gettempdir()) / "multiboard-report"
    report_dir = fallback_dir  # replaced once KiCad names one
    name = "dry_run_report.txt" if dry_run else "export_report.txt"
    try:
        session = KiCadSession()
        report_dir = session.settings_dir
        scratch = Path(tempfile.mkdtemp(prefix="multiboard-"))
        try:
            snapshot, cli = session.snapshot(scratch)
            plan, result = run_pipeline(snapshot, cli, dry_run, scratch / "work", runner=runner)
            text = report.render(plan, result, dry_run)
            code = exit_code(plan, result)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    except Exception:  # noqa: BLE001 - the user only sees the report, so failures must reach it
        text = "Multi-board fabrication export failed unexpectedly:\n\n" + traceback.format_exc()
        code = 3

    directories = [report_dir] if report_dir == fallback_dir else [report_dir, fallback_dir]
    path = _write_report(notice + text, name, directories)
    if path is not None:
        try:
            open_in_viewer(path)
        except Exception:  # noqa: BLE001 - the report is already written; the viewer is a convenience
            pass
    return code


def run_ui() -> int:
    """The action's entry point: the export window, or a dry-run report file if there is no wxPython."""
    try:
        from . import dialog
    except ImportError as exc:
        return run_action(
            dry_run=True,
            notice=f"The export window needs wxPython, which could not be imported ({exc}).\n"
                   "This is the dry-run report only; nothing was exported.\n\n")
    return dialog.run()
