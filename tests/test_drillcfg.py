import json
from pathlib import Path

import pytest

from multiboard.drillcfg import config_home, load_state, resolve

FIXTURE = Path(__file__).parent / "fixtures" / "drill_dialog_state.json"


@pytest.fixture
def saved_state() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["dialog"]["controls"]["Generate Drill Files"]


def test_users_saved_state_resolves_to_the_documented_flags(saved_state):
    config = resolve(saved_state, use_aux_origin=False)
    assert config.argv() == ["--format", "excellon", "--excellon-units", "mm",
                             "--excellon-zeros-format", "decimal", "--excellon-oval-format", "route",
                             "--excellon-separate-th", "--drill-origin", "absolute"]
    assert config.warnings == []
    assert [f.source for f in config.flags] == ["dialog"] * 5 + ["board"]


def test_every_option_maps_to_its_flag(saved_state):
    saved_state.update({"wxCheckBox_0": True, "wxCheckBox_1": True, "wxCheckBox_2": True,
                        "wxCheckBox_3": True, "wxCheckBox_4": True, "wxCheckBox_5": True,
                        "wxChoice_0": 4, "wxChoice_2": 1, "wxChoice_3": 2})
    argv = resolve(saved_state, use_aux_origin=True).argv()
    assert argv == ["--format", "excellon", "--excellon-units", "in",
                    "--excellon-zeros-format", "suppresstrailing", "--excellon-oval-format", "alternate",
                    "--excellon-mirror-y", "--excellon-min-header",
                    "--generate-tenting", "--generate-map", "--map-format", "pdf",
                    "--drill-origin", "plot"]  # merged PTH/NPTH means no --excellon-separate-th


@pytest.mark.parametrize("index,name", [(0, "ps"), (1, "gerberx2"), (2, "dxf"), (3, "svg"), (4, "pdf")])
def test_map_format_index(saved_state, index, name):
    saved_state.update({"wxCheckBox_5": True, "wxChoice_0": index})
    argv = resolve(saved_state, False).argv()
    assert argv[argv.index("--map-format") + 1] == name


def test_gerber_x2_drill_skips_excellon_only_flags(saved_state):
    saved_state.update({"wxRadioButton_0": False, "wxRadioButton_1": True, "wxCheckBox_4": True})
    assert resolve(saved_state, False).argv() == ["--format", "gerber", "--generate-tenting",
                                                  "--drill-origin", "absolute"]


@pytest.mark.parametrize("damage", [
    lambda s: s.pop("wxChoice_2"),
    lambda s: s.__setitem__("wxCheckBox_1", "yes"),
    lambda s: s.__setitem__("wxChoice_3", True),
    lambda s: s.__setitem__("wxChoice_3", 9),
    lambda s: s.__setitem__("wxRadioButton_1", True),  # both radios selected
    lambda s: s.update({"wxRadioButton_0": False}),  # neither selected
])
def test_unexpected_shape_falls_back_to_defaults_with_a_warning(saved_state, damage):
    damage(saved_state)
    config = resolve(saved_state, use_aux_origin=False)
    assert config.argv() == ["--drill-origin", "absolute"]
    assert config.flags[0].source == "board"
    assert "expected layout" in config.warnings[0]


def test_missing_state_falls_back_to_defaults_with_a_warning():
    config = resolve(None, use_aux_origin=True)
    assert config.argv() == ["--drill-origin", "plot"]
    assert "not found" in config.warnings[0]


def test_config_home_per_platform(tmp_path):
    home = tmp_path / "home"
    assert config_home({"KICAD_CONFIG_HOME": "/custom"}, "linux", home) == Path("/custom")
    assert config_home({"APPDATA": "C:/Roaming"}, "win32", home) == Path("C:/Roaming/kicad")
    assert config_home({}, "win32", home) == home / "AppData" / "Roaming" / "kicad"
    assert config_home({}, "darwin", home) == home / "Library" / "Preferences" / "kicad"
    assert config_home({}, "linux", home) == home / ".config" / "kicad"
    assert config_home({"XDG_CONFIG_HOME": "/xdg"}, "linux", home) == Path("/xdg/kicad")


def test_load_state_reads_the_versioned_file(tmp_path, saved_state):
    directory = tmp_path / "10.99"
    directory.mkdir()
    (directory / "kicad_common.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    assert load_state((10, 99), tmp_path) == saved_state
    assert load_state((10, 0), tmp_path) is None  # no such version directory
    assert load_state(None, tmp_path) is None


def _write_controls(tmp_path, controls):
    (tmp_path / "10.99").mkdir(exist_ok=True)
    (tmp_path / "10.99" / "kicad_common.json").write_text(
        json.dumps({"dialog": {"controls": controls}}), encoding="utf-8")


def test_load_state_finds_the_block_under_a_translated_title(tmp_path, saved_state):
    """KiCad keys the block by the localized dialog title, e.g. 'Bohrdateien erzeugen'."""
    _write_controls(tmp_path, {"Bohrdateien erzeugen": saved_state, "Plot": {"wxChoice_0": 1}})
    assert load_state((10, 99), tmp_path) == saved_state


def test_load_state_does_not_guess_when_no_block_or_several_blocks_have_the_shape(tmp_path, saved_state):
    _write_controls(tmp_path, {"Plot": {"wxChoice_0": 1}})
    assert load_state((10, 99), tmp_path) is None
    _write_controls(tmp_path, {"Bohrdateien erzeugen": saved_state, "Percage": dict(saved_state)})
    assert load_state((10, 99), tmp_path) is None


def test_the_english_title_wins_over_the_shape_scan(tmp_path, saved_state):
    other = dict(saved_state, wxChoice_2=1)
    _write_controls(tmp_path, {"Generate Drill Files": saved_state, "Bohrdateien erzeugen": other})
    assert load_state((10, 99), tmp_path) == saved_state


@pytest.mark.parametrize("content", ["not json", "{}", '{"dialog": {"controls": {}}}', '{"dialog": []}',
                                     '{"dialog": {"controls": {"Generate Drill Files": 5}}}'])
def test_load_state_tolerates_bad_files(tmp_path, content):
    (tmp_path / "10.99").mkdir()
    (tmp_path / "10.99" / "kicad_common.json").write_text(content, encoding="utf-8")
    assert load_state((10, 99), tmp_path) is None
