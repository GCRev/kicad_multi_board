"""Renders a plan (and, for a real run, its result) as plain text."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from . import exporter
from .ownership import describe
from .plan import Plan, board_where
from .runner import RunResult


def _cmd(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def render(plan: Plan, result: Optional[RunResult], dry_run: bool) -> str:
    lines: list[str] = []
    add = lines.append
    add("Multi-board fabrication export - " + ("DRY RUN (nothing is written)" if dry_run else "RESULT"))
    add(f"Board file  : {plan.snapshot.real_board_path}")
    if plan.root is not None:
        note = "" if plan.info.output_directory.strip() else "  (no output directory saved; using default)"
        add(f"Output root : {plan.root}{note}")
    version = f"{plan.cli_version[0]}.{plan.cli_version[1]}" if plan.cli_version else "unknown version"
    add(f"kicad-cli   : {plan.cli or 'NOT FOUND'} ({version})")
    add("Drill flags :")
    for flag in plan.drill.flags:
        add(f"  {_cmd(list(flag.args)):<40} [{flag.source}]")

    add("")
    add(f"BOARDS ({len(plan.boards)})")
    placeholder_root = Path("<temp>")
    for board in plan.boards:
        add(f"  [{board.name}]  rule area {board_where(board.area)}")
        add(f"    folder : {board.folder}")
        add(f"    zip    : {board.zip_path}" + ("  (exists; will be replaced)" if board.zip_exists else ""))
        add("    items  : " + (", ".join(f"{k} x{n}" for k, n in board.counts.items()) or "none"))
        for zone in board.shared_zones:
            add(f"    shared : {zone} (also in another board)")
        if board.existing_files:
            add(f"    already in folder (kept; only files re-produced by this run are zipped): "
                f"{', '.join(board.existing_files)}")
        if plan.cli:
            temp = placeholder_root / board.name / f"{board.name}.kicad_pcb"
            add("    commands:")
            add("      " + _cmd(exporter.gerber_command(plan.cli, temp, board.folder)))
            add("      " + _cmd(exporter.drill_command(plan.cli, temp, board.folder, plan.drill.argv())))

    if plan.discovery.skipped:
        add("")
        add("SKIPPED RULE AREAS")
        for zone in plan.discovery.skipped:
            place = f"at ({zone.location[0]:g}, {zone.location[1]:g})" if zone.location else "with no outline"
            keys = f"; properties found: {', '.join(zone.keys)}" if zone.keys else "; no properties"
            add(f"  {place}: {zone.reason}{keys}")

    if plan.classification.unowned:
        add("")
        add("UNOWNED ITEMS (in no rule area; excluded from every board)")
        for item in plan.classification.unowned:
            add(f"  {describe(item)}")

    if plan.classification.kept_verbatim:
        add("")
        add("UNRECOGNISED NODES WITHOUT COORDINATES (kept unchanged in every board)")
        add("  " + ", ".join(sorted(set(plan.classification.kept_verbatim))))

    if plan.errors:
        add("")
        add(f"ERRORS ({len(plan.errors)}) - a real run will not start until these are fixed")
        lines.extend(f"  {message}" for message in plan.errors)
    if plan.warnings:
        add("")
        add(f"WARNINGS ({len(plan.warnings)})")
        lines.extend(f"  {message}" for message in plan.warnings)

    if result is not None:
        add("")
        if result.refused:
            add("RESULT: refused to run because the plan has errors; nothing was written.")
        else:
            failed = sum(1 for b in result.boards if not b.ok)
            add(f"RESULT: {len(result.boards) - failed} of {len(result.boards)} board(s) exported")
            for board in result.boards:
                if board.ok:
                    add(f"  [{board.name}] OK  {board.zip_path}  ({len(board.zipped)} files)")
                    if board.ignored:
                        add(f"    produced but not zipped (not on the whitelist): {', '.join(board.ignored)}")
                    if board.stale:
                        add(f"    left alone, not zipped (stale): {', '.join(board.stale)}")
                else:
                    add(f"  [{board.name}] FAILED  {board.message}")
    elif not plan.errors:
        add("")
        add("No errors. Run the export to write these files.")
    return "\n".join(lines) + "\n"
