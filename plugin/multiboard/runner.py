"""Runs a plan: writes each board's temp file, exports it, and zips the result."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import exporter, packager, tempboard
from .plan import BoardPlan, Plan, Snapshot, build_plan


@dataclass
class BoardResult:
    name: str
    ok: bool
    message: str = ""
    zip_path: Optional[Path] = None
    zipped: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)  # produced but not whitelisted
    stale: list[str] = field(default_factory=list)  # already there, left alone


@dataclass
class RunResult:
    boards: list[BoardResult] = field(default_factory=list)
    refused: bool = False  # the plan had errors, so nothing was written


def _tail(result: exporter.CommandResult) -> str:
    return (result.stderr.strip() or result.stdout.strip())[-600:]


def _export_board(plan: Plan, board: BoardPlan, scratch: Path, runner: exporter.Runner) -> BoardResult:
    result = BoardResult(board.name, ok=False)
    try:
        temp = tempboard.write_temp_board(plan.text, plan.root_node, plan.classification, board.name,
                                          scratch, plan.snapshot.project_path)
        board.folder.mkdir(parents=True, exist_ok=True)
        before = packager.snapshot_dir(board.folder)
        commands = [exporter.gerber_command(plan.cli, temp, board.folder),
                    exporter.drill_command(plan.cli, temp, board.folder, plan.drill.argv())]
        for command in commands:
            outcome = runner(command)
            if outcome.returncode != 0:
                result.message = f"kicad-cli {command[3]} failed (exit {outcome.returncode}): {_tail(outcome)}"
                return result
        produced, result.stale = packager.classify_files(before, packager.snapshot_dir(board.folder))
        members, result.ignored = packager.select_members(produced)
        if not members:
            result.message = "kicad-cli produced no files that can go in the zip"
            return result
        packager.build_zip(board.folder, board.zip_path, members)
        result.zip_path, result.zipped, result.ok = board.zip_path, members, True
    except Exception as exc:  # noqa: BLE001 - one board's failure must not stop the others
        result.message = f"{type(exc).__name__}: {exc}"
    return result


def execute(plan: Plan, scratch: Path, runner: exporter.Runner = exporter.run) -> RunResult:
    """Export every board. Refuses, writing nothing, if the plan has errors."""
    if plan.errors:
        return RunResult(refused=True)
    return RunResult([_export_board(plan, board, scratch, runner) for board in plan.boards])


def run_pipeline(snapshot: Snapshot, cli: Optional[str], dry_run: bool, scratch: Path,
                 config_home: Optional[Path] = None, runner: exporter.Runner = exporter.run
                 ) -> tuple[Plan, Optional[RunResult]]:
    """The whole job. A dry run builds the plan and stops."""
    version = exporter.cli_version(cli, runner) if cli else None
    plan = build_plan(snapshot, cli, version, config_home)
    return plan, (None if dry_run else execute(plan, scratch, runner))


def exit_code(plan: Plan, result: Optional[RunResult]) -> int:
    """0 success, 1 a board failed, 2 the plan has errors."""
    if plan.errors:
        return 2
    if result is not None and any(not board.ok for board in result.boards):
        return 1
    return 0
