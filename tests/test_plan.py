from pathlib import Path

import pytest

from multiboard.plan import Snapshot, build_plan

CLI = "kicad-cli"
VERSION = (10, 99)
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def no_config(tmp_path) -> Path:
    """A config home with no saved dialog state."""
    return tmp_path / "empty-config"


def _snapshot(board: Path) -> Snapshot:
    return Snapshot(board, None, board)


def _plan(board: Path, config: Path, cli=CLI, version=VERSION):
    return build_plan(_snapshot(board), cli, version, config)


def _edit(board: Path, old: str, new: str) -> Path:
    board.write_bytes(board.read_bytes().decode("utf-8").replace(old, new).encode("utf-8"))
    return board


def test_plan_for_the_panel(panel_path, no_config):
    plan = _plan(panel_path, no_config)
    assert plan.errors == []
    assert plan.root == panel_path.parent / "fab_out"
    assert [b.name for b in plan.boards] == ["main", "side"]
    main, side = plan.boards
    assert main.folder == plan.root / "main" and main.zip_path == plan.root / "main.zip"
    assert main.counts == {"footprint": 1, "gr_rect": 1, "group": 1, "segment": 3, "zone": 1}
    assert side.counts == {"gr_poly": 1, "group": 1, "segment": 2, "via": 1, "zone": 1}
    assert main.shared_zones == ["zone at (99, 74) [d0229f9b]"] == side.shared_zones


def test_warnings_cover_straddlers_unowned_items_and_missing_drill_state(panel_path, no_config):
    warnings = _plan(panel_path, no_config).warnings
    assert any("segment at (120, 80)" in w and "straddles the edge of 'main'" in w for w in warnings)
    assert "1 item(s) are inside no rule area and will be excluded" in warnings
    assert any("drill dialog state not found" in w for w in warnings)


def test_drill_flags_come_from_the_dialog_state_for_the_matching_version(panel_path, tmp_path):
    (tmp_path / "cfg" / "10.99").mkdir(parents=True)
    (tmp_path / "cfg" / "10.99" / "kicad_common.json").write_bytes((FIXTURES / "drill_dialog_state.json").read_bytes())
    plan = _plan(panel_path, tmp_path / "cfg")
    assert "--excellon-separate-th" in plan.drill.argv()
    assert plan.warnings == [w for w in plan.warnings if "drill" not in w]


def test_untagged_rule_area_is_skipped_not_an_error(panel_path, no_config):
    _edit(panel_path, '(custom_property "board_name" "side")', '(custom_property "Property0" "side")')
    plan = _plan(panel_path, no_config)
    assert plan.errors == []
    assert [b.name for b in plan.boards] == ["main"]
    assert plan.discovery.skipped[0].keys == ("Property0",)


def test_a_windows_device_name_is_planned_with_a_warning_not_an_error(panel_path, no_config):
    _edit(panel_path, '"board_name" "side"', '"board_name" "aux"')
    plan = _plan(panel_path, no_config)
    assert plan.errors == []
    assert [b.name for b in plan.boards] == ["main", "aux"]
    assert plan.boards[1].folder == plan.root / "aux" and plan.boards[1].zip_path == plan.root / "aux.zip"
    assert any("'aux'" in w and "Windows device name" in w for w in plan.warnings)


def test_no_tagged_areas_is_an_error(panel_path, no_config):
    _edit(panel_path, '"board_name"', '"other"')
    assert any("no rule areas" in e for e in _plan(panel_path, no_config).errors)


def test_duplicate_names_are_reported_as_errors(panel_path, no_config):
    _edit(panel_path, '"board_name" "side"', '"board_name" "MAIN"')
    assert any("duplicate" in e for e in _plan(panel_path, no_config).errors)


def test_overlapping_rule_areas_make_ownership_ambiguous(panel_path, no_config):
    _edit(panel_path, "(xy 126 74) (xy 149 74) (xy 149 101) (xy 126 101)", "(xy 110 74) (xy 149 74) (xy 149 101) (xy 110 101)")
    errors = _plan(panel_path, no_config).errors
    assert any("more than one rule area (main, side)" in e for e in errors)


def test_missing_cli_and_version_mismatch_are_errors(panel_path, no_config):
    assert "kicad-cli was not found" in _plan(panel_path, no_config, cli=None, version=None).errors
    mismatch = _plan(panel_path, no_config, version=(10, 0)).errors
    assert any("10.0" in e and "10.99" in e for e in mismatch)
    assert any("could not determine" in e for e in _plan(panel_path, no_config, version=None).errors)


def test_a_newer_cli_than_the_board_warns_but_does_not_block(panel_path, no_config):
    plan = _plan(panel_path, no_config, version=(11, 0))
    assert not any("kicad-cli is version" in e for e in plan.errors)
    assert any("kicad-cli is version 11.0" in w for w in plan.warnings)


def test_empty_output_directory_falls_back_to_fab(panel_path, no_config):
    _edit(panel_path, '(outputdirectory "fab_out/")', '(outputdirectory "")')
    assert _plan(panel_path, no_config).root == panel_path.parent / "fab"


def test_unexpandable_output_directory_is_an_error(panel_path, no_config):
    _edit(panel_path, '"fab_out/"', '"${OTHER}/x"')
    plan = _plan(panel_path, no_config)
    assert plan.root is None and plan.boards == []
    assert any("variable" in e for e in plan.errors)


def test_existing_files_and_zip_are_noticed(panel_path, no_config):
    root = panel_path.parent / "fab_out"
    (root / "main").mkdir(parents=True)
    (root / "main" / "old.gbr").write_text("x")
    (root / "main.zip").write_text("x")
    main = _plan(panel_path, no_config).boards[0]
    assert main.existing_files == ["old.gbr"] and main.zip_exists is True
    side = _plan(panel_path, no_config).boards[1]
    assert side.existing_files == [] and side.zip_exists is False


def test_output_root_resolves_against_the_real_board_not_the_snapshot(panel_path, no_config, tmp_path):
    snapshot_board = tmp_path / "scratch" / "snapshot.kicad_pcb"
    snapshot_board.parent.mkdir()
    snapshot_board.write_bytes(panel_path.read_bytes())
    plan = build_plan(Snapshot(snapshot_board, None, panel_path), CLI, VERSION, no_config)
    assert plan.root == panel_path.parent / "fab_out"


def test_an_unreadable_output_folder_does_not_stop_the_plan(panel_path, no_config, monkeypatch):
    (panel_path.parent / "fab_out" / "main").mkdir(parents=True)
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self.name == "main":
            raise PermissionError(13, "denied", str(self))
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    main = _plan(panel_path, no_config).boards[0]
    assert main.name == "main" and main.existing_files == []
