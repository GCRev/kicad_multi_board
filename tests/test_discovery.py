import pytest

from multiboard.discovery import discover, name_warning, validate_name
from multiboard.sexpr import parse


def _zone(name_prop: str, x0=0, x1=10, layer="Edge.Cuts", uuid="aaaaaaaa-0000") -> str:
    return (f'(zone (layer "{layer}") (uuid "{uuid}") '
            f'(polygon (pts (xy {x0} 0) (xy {x1} 0) (xy {x1} 5) (xy {x0} 5))) {name_prop})')


def _board(*zones: str):
    return parse("(kicad_pcb " + " ".join(zones) + ")")


def test_finds_tagged_rule_areas_on_the_panel(panel_text):
    result = discover(parse(panel_text))
    assert [a.name for a in result.areas] == ["main", "side"]
    assert result.errors == []
    assert result.skipped == []
    main = result.areas[0]
    assert main.polygons == (((99.0, 74.0), (124.0, 74.0), (124.0, 101.0), (99.0, 101.0)),)
    assert main.uuid == "0dd5ab04-c788-4b75-bb57-5f6637ff9815"


def test_untagged_rule_area_is_skipped_with_the_keys_that_were_found():
    result = discover(_board(_zone('(custom_property "Property0" "aux")')))
    assert result.areas == []
    assert len(result.skipped) == 1
    assert result.skipped[0].keys == ("Property0",)
    assert "board_name" in result.skipped[0].reason


def test_zones_that_are_not_on_edge_cuts_are_ignored():
    result = discover(_board(_zone('(custom_property "board_name" "x")', layer="F.Cu")))
    assert result.areas == [] and result.skipped == [] and result.errors == []


def test_name_is_trimmed():
    result = discover(_board(_zone('(custom_property "board_name" "  main  ")')))
    assert result.areas[0].name == "main"


def test_duplicate_names_are_an_error_case_insensitively():
    result = discover(_board(_zone('(custom_property "board_name" "Main")', uuid="11111111-0"),
                             _zone('(custom_property "board_name" "main")', x0=20, x1=30, uuid="22222222-0")))
    assert [a.name for a in result.areas] == ["Main"]
    assert len(result.errors) == 1
    assert "duplicate" in result.errors[0] and "11111111" in result.errors[0]


def test_invalid_name_is_an_error_not_a_repair():
    result = discover(_board(_zone('(custom_property "board_name" "a/b")')))
    assert result.areas == []
    assert "reserved character" in result.errors[0]


def test_rule_area_without_a_polygon_is_an_error():
    board = _board('(zone (layer "Edge.Cuts") (custom_property "board_name" "x"))')
    assert "no polygon" in discover(board).errors[0]


@pytest.mark.parametrize("name", ["main", "board 2", "rev-A_1.2", "ünïcode"])
def test_valid_names(name):
    assert validate_name(name) is None


@pytest.mark.parametrize("name,fragment", [
    ("", "empty"),
    ("a:b", "reserved character"),
    ('a"b', "reserved character"),
    ("a\tb", "reserved character"),
    ("name.", "dot"),
])
def test_invalid_names(name, fragment):
    assert fragment in validate_name(name)


@pytest.mark.parametrize("name", ["aux", "AUX", "con", "NUL.txt", "com3", "LPT9"])
def test_windows_device_names_are_valid_but_get_a_warning(name):
    assert validate_name(name) is None
    assert "Windows device name" in name_warning(name)


@pytest.mark.parametrize("name", ["main", "auxiliary", "aux2", "my-aux", "com10", "nulled"])
def test_ordinary_names_get_no_warning(name):
    assert name_warning(name) is None


def test_a_device_name_is_accepted_as_a_board_with_a_warning():
    result = discover(_board(_zone('(custom_property "board_name" "aux")', uuid="cccccccc-0")))
    assert [a.name for a in result.areas] == ["aux"]
    assert result.errors == []
    assert len(result.warnings) == 1
    assert "'aux'" in result.warnings[0] and "Windows device name" in result.warnings[0]
    assert "cccccccc" in result.warnings[0]


def test_ordinary_names_leave_discovery_warnings_empty(panel_text):
    assert discover(parse(panel_text)).warnings == []
