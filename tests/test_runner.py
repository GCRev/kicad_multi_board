import re
import zipfile
from pathlib import Path

from multiboard.exporter import CommandResult
from multiboard.plan import Snapshot
from multiboard.runner import exit_code, run_pipeline


class FakeCli:
    """Stands in for kicad-cli: reports a version and writes plausible output files."""

    def __init__(self, version="10.99.0", fail=None, raises=None, only_junk=False):
        self.version, self.fail, self.raises, self.only_junk = version, fail, raises, only_junk
        self.calls: list[list[str]] = []

    def __call__(self, command):
        self.calls.append(command)
        if command[1:] == ["--version"]:
            return CommandResult(0, self.version + "\n")
        if self.raises:
            raise self.raises
        board = Path(command[-1])
        name = board.stem
        kind = command[3]
        if self.fail == (name, kind):
            return CommandResult(1, "", "boom: could not plot")
        out = Path(command[command.index("-o") + 1])
        out.mkdir(parents=True, exist_ok=True)
        files = ["notes.txt"] if self.only_junk else (
            [f"{name}-F_Cu.gbr", f"{name}-job.gbrjob", f"{name}-Edge_Cuts.gbr", "readme.txt"]
            if kind == "gerbers" else [f"{name}-PTH.drl"])
        for filename in files:
            (out / filename).write_text(f"{kind} for {name}")
        return CommandResult(0, "ok")


def _run(board: Path, tmp_path: Path, fake: FakeCli, dry_run=False):
    snapshot = Snapshot(board, None, board)
    return run_pipeline(snapshot, "kicad-cli", dry_run, tmp_path / "work", tmp_path / "no-config", fake)


def test_full_run_writes_folders_and_flat_whitelisted_zips(panel_path, tmp_path):
    fake = FakeCli()
    plan, result = _run(panel_path, tmp_path, fake)
    assert exit_code(plan, result) == 0
    root = panel_path.parent / "fab_out"
    for name in ("main", "side"):
        assert (root / name / f"{name}-F_Cu.gbr").is_file()
        with zipfile.ZipFile(root / f"{name}.zip") as archive:
            assert sorted(archive.namelist()) == sorted(
                [f"{name}-F_Cu.gbr", f"{name}-job.gbrjob", f"{name}-Edge_Cuts.gbr", f"{name}-PTH.drl"])
    main = next(b for b in result.boards if b.name == "main")
    assert main.ignored == ["readme.txt"]


def test_each_board_gets_its_own_temp_board_named_after_it(panel_path, tmp_path):
    fake = FakeCli()
    _run(panel_path, tmp_path, fake)
    plotted = [Path(c[-1]) for c in fake.calls if c[1:4] == ["pcb", "export", "gerbers"]]
    assert [p.name for p in plotted] == ["main.kicad_pcb", "side.kicad_pcb"]
    assert plotted[0].parent.name == "main"


def test_dry_run_writes_nothing_and_never_exports(panel_path, tmp_path):
    fake = FakeCli()
    plan, result = _run(panel_path, tmp_path, fake, dry_run=True)
    assert result is None and exit_code(plan, result) == 0
    assert fake.calls == [["kicad-cli", "--version"]]
    assert not (panel_path.parent / "fab_out").exists()
    assert not (tmp_path / "work").exists()


def test_a_plan_with_errors_is_refused_and_writes_nothing(panel_path, tmp_path):
    fake = FakeCli(version="10.0.1")  # version mismatch is an error
    plan, result = _run(panel_path, tmp_path, fake)
    assert result.refused and result.boards == []
    assert exit_code(plan, result) == 2
    assert not (panel_path.parent / "fab_out").exists()
    assert all(c[1:] == ["--version"] for c in fake.calls)


def test_one_boards_failure_does_not_stop_the_others_or_leave_a_zip(panel_path, tmp_path):
    fake = FakeCli(fail=("main", "gerbers"))
    plan, result = _run(panel_path, tmp_path, fake)
    main, side = result.boards
    assert not main.ok and "kicad-cli gerbers failed (exit 1)" in main.message and "boom" in main.message
    assert side.ok
    assert not (panel_path.parent / "fab_out" / "main.zip").exists()
    assert (panel_path.parent / "fab_out" / "side.zip").is_file()
    assert exit_code(plan, result) == 1


def test_stale_files_stay_out_of_the_zip_and_are_reported(panel_path, tmp_path):
    old = panel_path.parent / "fab_out" / "main" / "old-layer.gbr"
    old.parent.mkdir(parents=True)
    old.write_text("from an earlier configuration")
    plan, result = _run(panel_path, tmp_path, FakeCli())
    main = result.boards[0]
    assert main.stale == ["old-layer.gbr"]
    with zipfile.ZipFile(main.zip_path) as archive:
        assert "old-layer.gbr" not in archive.namelist()
    assert old.read_text() == "from an earlier configuration"  # never deleted or modified


def test_no_zippable_output_is_a_failure(panel_path, tmp_path):
    plan, result = _run(panel_path, tmp_path, FakeCli(only_junk=True))
    assert all(not b.ok for b in result.boards)
    assert "no files that can go in the zip" in result.boards[0].message
    assert not (panel_path.parent / "fab_out" / "main.zip").exists()


def test_unexpected_exceptions_become_a_board_failure(panel_path, tmp_path):
    plan, result = _run(panel_path, tmp_path, FakeCli(raises=OSError("disk full")))
    assert re.search(r"OSError: disk full", result.boards[0].message)
    assert exit_code(plan, result) == 1


def test_drill_flags_are_passed_to_the_drill_command(panel_path, tmp_path):
    fake = FakeCli()
    _run(panel_path, tmp_path, fake)
    drill = next(c for c in fake.calls if c[1:4] == ["pcb", "export", "drill"])
    assert drill[drill.index("--drill-origin") + 1] == "absolute"
