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


def run_action(dry_run: bool, runner: exporter.Runner = exporter.run) -> int:
    """Snapshot the open board, run the pipeline, and show the report. Returns the exit code."""
    report_dir = Path(tempfile.gettempdir()) / "multiboard-report"  # replaced once KiCad names one
    name = "dry_run_report.txt" if dry_run else "export_report.txt"
    try:
        from kipy import KiCad  # imported here so the rest of the package needs no kipy

        kicad = KiCad()
        report_dir = Path(kicad.get_plugin_settings_path(IDENTIFIER))
        board = kicad.get_board()
        project_dir = board.get_project().path
        if not project_dir:
            raise RuntimeError("KiCad did not report the project directory of the open board")
        real_board = Path(project_dir) / board.name
        cli = kicad.get_kicad_binary_path("kicad-cli")

        scratch = Path(tempfile.mkdtemp(prefix="multiboard-"))
        try:
            snapshot_board = scratch / "snapshot.kicad_pcb"
            board.save_as(str(snapshot_board), overwrite=True, include_project=True)
            snapshot = Snapshot(snapshot_board, _project_file(scratch), real_board)
            plan, result = run_pipeline(snapshot, cli, dry_run, scratch / "work", runner=runner)
            text = report.render(plan, result, dry_run)
            code = exit_code(plan, result)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    except Exception:  # noqa: BLE001 - the user only sees the report, so failures must reach it
        text = "Multi-board fabrication export failed unexpectedly:\n\n" + traceback.format_exc()
        code = 3

    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / name
    path.write_text(text, encoding="utf-8")
    open_in_viewer(path)
    return code
