import os
from pathlib import Path

from multiboard.exporter import CommandResult
from multiboard.plan import Snapshot, build_plan
from multiboard.report import render
from multiboard.runner import execute

GOLDEN = Path(__file__).parent / "golden" / "dry_run_panel.txt"
FAKE_CLI = "C:/fake/kicad-cli.exe"


def _normalise(text: str, board_dir: Path) -> str:
    text = text.replace(str(board_dir), "<BOARD_DIR>").replace("\\", "/")
    # list2cmdline quotes arguments that contain spaces; remove the quotes so the golden file comparison works
    return text.replace('"', "")


def _plan(panel_path, tmp_path):
    return build_plan(Snapshot(panel_path, None, panel_path), FAKE_CLI, (10, 99), tmp_path / "no-config")


def test_dry_run_report_matches_the_golden_file(panel_path, tmp_path):
    text = _normalise(render(_plan(panel_path, tmp_path), None, dry_run=True), panel_path.parent)
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8", newline="\n")
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_dry_run_report_matches_the_golden_file_when_the_project_path_has_a_space(tmp_path):
    board = tmp_path / "my project" / "panel.kicad_pcb"
    board.parent.mkdir()
    board.write_bytes((Path(__file__).parent / "fixtures" / "panel.kicad_pcb").read_bytes())
    text = _normalise(render(_plan(board, tmp_path), None, dry_run=True), board.parent)
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_report_lists_skipped_areas_with_the_property_keys_found(panel_path, tmp_path):
    panel_path.write_bytes(panel_path.read_bytes().replace(b'"board_name" "side"', b'"Property0" "side"'))
    text = render(_plan(panel_path, tmp_path), None, dry_run=True)
    assert "SKIPPED RULE AREAS" in text
    assert "no 'board_name' property; properties found: Property0" in text


def test_report_flags_errors_and_says_a_real_run_will_not_start(panel_path, tmp_path):
    plan = build_plan(Snapshot(panel_path, None, panel_path), None, None, tmp_path / "no-config")
    text = render(plan, None, dry_run=True)
    assert "kicad-cli   : NOT FOUND" in text
    assert "a real run will not start until these are fixed" in text
    assert "No errors." not in text


def test_real_run_report_shows_per_board_outcome(panel_path, tmp_path):
    def cli(command):
        out = Path(command[command.index("-o") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "x-F_Cu.gbr").write_text("x")
        return CommandResult(1, "", "no good") if command[-1].endswith("side.kicad_pcb") else CommandResult(0)

    plan = _plan(panel_path, tmp_path)
    text = render(plan, execute(plan, tmp_path / "work", cli), dry_run=False)
    assert "RESULT: 1 of 2 board(s) exported" in text
    assert "[main] OK" in text and "[side] FAILED" in text and "no good" in text


def test_refused_run_says_so(panel_path, tmp_path):
    plan = build_plan(Snapshot(panel_path, None, panel_path), None, None, tmp_path / "no-config")
    text = render(plan, execute(plan, tmp_path / "work"), dry_run=False)
    assert "refused to run because the plan has errors; nothing was written" in text
