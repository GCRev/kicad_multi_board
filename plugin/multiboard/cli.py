"""Command-line entry: ``python -m multiboard board.kicad_pcb [--dry-run]``.

Runs the same pipeline as the KiCad actions, on a saved board file and without KiCad running.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from . import report
from .plan import Snapshot
from .runner import exit_code, run_pipeline


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="multiboard", description=__doc__.splitlines()[0])
    parser.add_argument("board", type=Path, help="the panel's .kicad_pcb file")
    parser.add_argument("--dry-run", action="store_true", help="report what would be exported; write nothing")
    parser.add_argument("--kicad-cli", default=os.environ.get("KICAD_CLI"),
                        help="path to kicad-cli (default: $KICAD_CLI)")
    parser.add_argument("--config-home", type=Path, default=None,
                        help="KiCad user config root holding <major.minor>/kicad_common.json")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    board = args.board.resolve()
    if not board.is_file():
        print(f"board file not found: {board}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="multiboard-") as tmp:
        scratch = Path(tmp)
        snapshot_board = scratch / "snapshot.kicad_pcb"
        shutil.copyfile(board, snapshot_board)
        project = board.with_suffix(".kicad_pro")
        snapshot_project = None
        if project.is_file():
            snapshot_project = scratch / "snapshot.kicad_pro"
            shutil.copyfile(project, snapshot_project)
        snapshot = Snapshot(snapshot_board, snapshot_project, board)
        plan, result = run_pipeline(snapshot, args.kicad_cli, args.dry_run, scratch / "work", args.config_home)
        print(report.render(plan, result, args.dry_run), end="")
        return exit_code(plan, result)
