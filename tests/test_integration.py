"""End-to-end tests against a real kicad-cli. Skipped unless KICAD_CLI is set.

The fixture panel is written by KiCad 10.99, so KICAD_CLI must be a 10.99 build.
"""
import hashlib
import re
import zipfile
from pathlib import Path

import pytest

from multiboard import cli as multiboard_cli
from multiboard import exporter
from multiboard.discovery import discover
from multiboard.ownership import classify
from multiboard.sexpr import parse
from multiboard.tempboard import render, write_temp_board

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / "fixtures"
COORDINATE = re.compile(r"X(-?\d+)Y-?\d+D0[123]")  # gerber 4.6 format; captures X only
TOLERANCE = 1e-3


def _x_range(gerber: Path) -> tuple[float, float]:
    xs = [int(m) / 1e6 for m in COORDINATE.findall(gerber.read_text(errors="ignore"))]
    assert xs, f"no coordinates in {gerber.name}"
    return min(xs), max(xs)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def config_home(tmp_path, kicad_cli) -> Path:
    """A KiCad config root holding the user's saved drill dialog state for this kicad-cli version."""
    major, minor = exporter.cli_version(kicad_cli)
    directory = tmp_path / "config" / f"{major}.{minor}"
    directory.mkdir(parents=True)
    (directory / "kicad_common.json").write_bytes((FIXTURES / "drill_dialog_state.json").read_bytes())
    return tmp_path / "config"


def _run(panel: Path, kicad_cli: str, config_home: Path, *extra: str) -> int:
    return multiboard_cli.main([str(panel), "--kicad-cli", kicad_cli, "--config-home", str(config_home), *extra])


def test_no_boards_copper_leaks_into_its_neighbour(panel_path, kicad_cli, config_home, capsys):
    """main spans x 100 to 122.5 and side x 127.5 to 147.5, with the shared GND pour across both.

    main also owns a deliberately straddling track that ends at x=125 (the plugin warns about it),
    so main's copper may reach 125 but never side's pour, which starts at 128.
    """
    assert _run(panel_path, kicad_cli, config_home) == 0, capsys.readouterr().out
    root = panel_path.parent / "fab_out"
    low, high = _x_range(root / "main" / "main-F_Cu.gbr")
    assert low >= 100 - TOLERANCE and high <= 125 + TOLERANCE
    low, high = _x_range(root / "side" / "side-F_Cu.gbr")
    assert low >= 127.5 - TOLERANCE and high <= 147.5 + TOLERANCE


def test_control_without_refill_the_neighbours_copper_does_leak(panel_path, kicad_cli, tmp_path):
    """Proves the test above can fail: skip --check-zones and main's plot spans the whole panel."""
    text = panel_path.read_bytes().decode("utf-8")
    root = parse(text)
    board = write_temp_board(text, root, classify(root, discover(root).areas), "main", tmp_path / "work", None)
    out = tmp_path / "leaky"
    command = [kicad_cli, "pcb", "export", "gerbers", "--board-plot-params", "-o", str(out), str(board)]
    assert exporter.run(command).returncode == 0
    assert _x_range(out / "main-F_Cu.gbr")[1] > 140


def _plot_normalised(kicad_cli: str, board_text: str, folder: Path) -> dict[str, list[str]]:
    folder.mkdir(parents=True)
    board = folder / "main.kicad_pcb"
    board.write_bytes(board_text.encode("utf-8"))
    out = folder / "out"
    assert exporter.run(exporter.gerber_command(kicad_cli, board, out)).returncode == 0
    volatile = re.compile(r"CreationDate|Created by|GenerationSoftware|ProjectId")
    return {p.name: [line for line in p.read_text(errors="ignore").splitlines() if not volatile.search(line)]
            for p in sorted(out.glob("*.gbr"))}


def test_dropping_the_rule_area_does_not_change_any_plot_layer(panel_path, kicad_cli, tmp_path):
    text = panel_path.read_bytes().decode("utf-8")
    root = parse(text)
    classification = classify(root, discover(root).areas)
    without = render(text, root, classification, "main")
    area = next(c for c in root.children if c.kind == "list" and c.head == "zone"
                and 'board_name" "main"' in text[c.start:c.end])
    body = without.rstrip()
    assert body.endswith(")")
    with_area = body[:-1] + "\t" + text[area.start:area.end] + "\n)\n"
    assert "custom_property" not in without and "custom_property" in with_area

    a = _plot_normalised(kicad_cli, with_area, tmp_path / "with")
    b = _plot_normalised(kicad_cli, without, tmp_path / "without")
    assert a.keys() == b.keys() and len(a) == 9
    assert a == b


def test_full_export_layout_zip_contents_and_drill_files(panel_path, kicad_cli, config_home, capsys):
    before = _digest(panel_path)
    assert _run(panel_path, kicad_cli, config_home) == 0, capsys.readouterr().out
    root = panel_path.parent / "fab_out"

    main_files = {p.name for p in (root / "main").iterdir()}
    assert {"main-F_Cu.gbr", "main-B_Cu.gbr", "main-Edge_Cuts.gbr", "main-job.gbrjob"} <= main_files
    assert {"main-PTH.drl", "main-NPTH.drl"} <= main_files  # dialog state says separate PTH/NPTH

    with zipfile.ZipFile(root / "main.zip") as archive:
        names = set(archive.namelist())
    assert names == main_files  # flat, and everything kicad-cli produced is on the whitelist
    assert not any(n.endswith((".kicad_pcb", ".kicad_pro")) for n in names)

    assert "C0.800" in (root / "main" / "main-PTH.drl").read_text()  # main's pad
    side_drill = (root / "side" / "side-PTH.drl").read_text()
    assert "C0.300" in side_drill and "C0.800" not in side_drill  # side's via only

    assert (root / "side.zip").is_file()
    assert _digest(panel_path) == before  # the user's board is never modified


def test_dry_run_reports_and_writes_nothing(panel_path, kicad_cli, config_home, capsys):
    assert _run(panel_path, kicad_cli, config_home, "--dry-run") == 0
    output = capsys.readouterr().out
    assert "DRY RUN" in output and "[main]" in output and "[side]" in output
    assert "--excellon-separate-th" in output  # resolved from the dialog state
    assert not (panel_path.parent / "fab_out").exists()
    assert {p.name for p in panel_path.parent.iterdir()} == {"panel.kicad_pcb"}


def test_a_second_run_replaces_outputs_and_reports_no_stale_files(panel_path, kicad_cli, config_home, capsys):
    assert _run(panel_path, kicad_cli, config_home) == 0
    capsys.readouterr()
    assert _run(panel_path, kicad_cli, config_home) == 0
    output = capsys.readouterr().out
    assert "RESULT: 2 of 2 board(s) exported" in output
    assert "stale" not in output
