from pathlib import Path

import pytest

from multiboard.boardinfo import read_board_info, resolve_root
from multiboard.pcbnodes import (custom_properties, first_nested_point, is_edge_cuts_zone, item_points,
                                 layer_names, node_uuid, pts_points, zone_polygons)
from multiboard.sexpr import parse


def test_pts_points_reads_xy_and_arcs():
    pts = parse("(pts (xy 1 2) (arc (start 3 4) (mid 5 6) (end 7 8)) (xy 9 10))")
    assert pts_points(pts) == [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]


def test_zone_polygons_keeps_multiple_outlines_and_drops_degenerate_ones():
    zone = parse("(zone (polygon (pts (xy 0 0) (xy 1 0) (xy 1 1))) (polygon (pts (xy 0 0) (xy 1 1))) "
                 "(polygon (pts (xy 5 5) (xy 6 5) (xy 6 6))))")
    assert zone_polygons(zone) == [[(0, 0), (1, 0), (1, 1)], [(5, 5), (6, 5), (6, 6)]]


def test_layer_names_and_edge_cuts_zone_detection():
    rule_area = parse('(zone (layer "Edge.Cuts"))')
    copper = parse('(zone (layers "F.Cu" "B.Cu"))')
    single_copper = parse('(zone (layer "F.Cu"))')
    assert layer_names(copper) == ["F.Cu", "B.Cu"]
    assert is_edge_cuts_zone(rule_area)
    assert not is_edge_cuts_zone(copper)
    assert not is_edge_cuts_zone(single_copper)
    assert not is_edge_cuts_zone(parse('(segment (layer "Edge.Cuts"))'))


def test_custom_properties_and_uuid():
    zone = parse('(zone (uuid "abc") (custom_property "board_name" "main") (custom_property "x" "1"))')
    assert custom_properties(zone) == {"board_name": "main", "x": "1"}
    assert node_uuid(zone) == "abc"
    assert node_uuid(parse("(zone)")) is None


@pytest.mark.parametrize("text,expected", [
    ("(segment (start 1 2) (end 3 4))", [(1, 2), (3, 4)]),
    ("(via (at 5 6) (size 0.6))", [(5, 6)]),
    ("(gr_circle (center 7 8) (end 9 8))", [(7, 8), (9, 8)]),
    ("(gr_arc (start 1 1) (mid 2 2) (end 3 1))", [(1, 1), (2, 2), (3, 1)]),
    ("(gr_poly (pts (xy 1 1) (xy 2 1) (xy 2 2)))", [(1, 1), (2, 1), (2, 2)]),
    ("(footprint \"F\" (at 10 20 90) (pad \"1\" (at 99 99)))", [(10, 20)]),
    ("(embedded_fonts no)", []),
])
def test_item_points(text, expected):
    assert item_points(parse(text)) == expected


def test_first_nested_point_finds_the_first_coordinate_in_document_order():
    table = parse('(table (column_count 2) (cells (table_cell "a" (start 25 24.5) (end 41 28)) '
                  '(table_cell "b" (start 41 24.5))))')
    assert first_nested_point(table) == (25, 24.5)
    assert first_nested_point(parse("(x (y 1) (z))")) is None


def test_read_board_info_from_the_panel(panel_text):
    info = read_board_info(parse(panel_text))
    assert info.generator_version == "10.99"
    assert info.output_directory == "fab_out/"
    assert info.use_aux_origin is False


def test_read_board_info_defaults_when_settings_are_missing():
    info = read_board_info(parse("(kicad_pcb (version 1))"))
    assert (info.generator_version, info.output_directory, info.use_aux_origin) == (None, "", False)


def test_read_board_info_aux_origin_yes():
    root = parse("(kicad_pcb (setup (pcbplotparams (useauxorigin yes) (outputdirectory \"o\"))))")
    assert read_board_info(root).use_aux_origin is True


def test_resolve_root(tmp_path):
    base = tmp_path / "proj"
    assert resolve_root("", base) == base / "fab"
    assert resolve_root("  ", base) == base / "fab"
    assert resolve_root("out/", base) == base / "out"
    assert resolve_root("..\\shared\\fab", base) == tmp_path / "shared" / "fab"
    assert resolve_root("${KIPRJMOD}/gerbers", base) == base / "gerbers"
    absolute = tmp_path / "elsewhere"
    assert resolve_root(str(absolute), base) == absolute


def test_resolve_root_rejects_unknown_variables(tmp_path):
    with pytest.raises(ValueError):
        resolve_root("${OTHER}/out", tmp_path)
