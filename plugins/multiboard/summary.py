"""The figures and one-line status shown above the report in the export window.

Kept apart from the wx code so it can be tested without a display.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .plan import Plan
from .runner import RunResult


@dataclass(frozen=True)
class Summary:
    board_file: str
    output_root: str
    kicad_cli: str
    boards: int
    items: int
    unowned: int
    skipped: int
    errors: int
    warnings: int
    can_export: bool
    status: str

    def counts_line(self) -> str:
        return (f"Boards {self.boards}   Items {self.items}   Unowned {self.unowned}   "
                f"Skipped areas {self.skipped}   Errors {self.errors}   Warnings {self.warnings}")


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _status(plan: Plan, result: Optional[RunResult]) -> str:
    if result is None:
        if plan.errors:
            return (f"Blocked by {_plural(len(plan.errors), 'error')}. "
                    "Fix the board in KiCad, then click Refresh.")
        return f"Ready to export {_plural(len(plan.boards), 'board')}."
    if result.refused:
        return "Refused to run because the plan has errors; nothing was written."
    failed = sum(1 for board in result.boards if not board.ok)
    done = len(result.boards) - failed
    if failed:
        return f"Exported {done} of {len(result.boards)}; {failed} failed. See the report below."
    return f"Exported {done} of {len(result.boards)} boards."


def summarize(plan: Plan, result: Optional[RunResult] = None) -> Summary:
    version = f"{plan.cli_version[0]}.{plan.cli_version[1]}" if plan.cli_version else "unknown version"
    return Summary(
        board_file=str(plan.snapshot.real_board_path),
        output_root=str(plan.root) if plan.root is not None else "(not resolved)",
        kicad_cli=f"{plan.cli} ({version})" if plan.cli else "NOT FOUND",
        boards=len(plan.boards),
        items=len(plan.classification.items),
        unowned=len(plan.classification.unowned),
        skipped=len(plan.discovery.skipped),
        errors=len(plan.errors),
        warnings=len(plan.warnings),
        can_export=not plan.errors and bool(plan.boards),
        status=_status(plan, result),
    )
