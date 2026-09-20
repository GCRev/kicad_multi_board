from multiboard.plan import Snapshot, build_plan
from multiboard.runner import BoardResult, RunResult
from multiboard.summary import summarize


def _plan(panel_path, tmp_path, cli="C:/fake/kicad-cli.exe"):
    snapshot = Snapshot(panel_path, None, panel_path)
    return build_plan(snapshot, cli, (10, 99) if cli else None, tmp_path)


def test_summary_counts_the_panel(panel_path, tmp_path):
    summary = summarize(_plan(panel_path, tmp_path))
    assert summary.boards == 2
    assert summary.unowned >= 1  # the fixture's "PANEL" text sits in no rule area
    assert summary.items > summary.unowned
    assert summary.errors == 0 and summary.can_export
    assert summary.board_file == str(panel_path)
    assert summary.kicad_cli == "C:/fake/kicad-cli.exe (10.99)"
    assert summary.status == "Ready to export 2 boards."
    assert summary.counts_line().startswith("Boards 2   Items ")


def test_errors_block_export_and_the_status_says_how_to_recover(panel_path, tmp_path):
    summary = summarize(_plan(panel_path, tmp_path, cli=None))
    assert summary.kicad_cli == "NOT FOUND"
    assert summary.errors >= 1 and not summary.can_export
    assert summary.status.startswith("Blocked by ") and "Refresh" in summary.status


def test_status_after_an_export(panel_path, tmp_path):
    plan = _plan(panel_path, tmp_path)
    good = RunResult([BoardResult("main", ok=True), BoardResult("side", ok=True)])
    assert summarize(plan, good).status == "Exported 2 of 2 boards."
    partial = RunResult([BoardResult("main", ok=True), BoardResult("side", ok=False, message="boom")])
    assert summarize(plan, partial).status == "Exported 1 of 2; 1 failed. See the report below."
    assert "nothing was written" in summarize(plan, RunResult(refused=True)).status
