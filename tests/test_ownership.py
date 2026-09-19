import pytest

from multiboard.discovery import RuleArea, discover
from multiboard.ownership import classify, describe, kept_for
from multiboard.sexpr import parse


def _area(name, x0, y0, x1, y1) -> RuleArea:
    return RuleArea(name, (((x0, y0), (x1, y0), (x1, y1), (x0, y1)),), None, (x0, y0))


LEFT = _area("left", 0, 0, 10, 10)
RIGHT = _area("right", 20, 0, 30, 10)


def _classify(body: str, *areas):
    """Classify a mini board. Item indexes count the head atom, so the first item is index 1."""
    return classify(parse("(kicad_pcb " + body + ")"), areas or (LEFT, RIGHT))


def test_via_and_text_are_owned_by_their_position():
    r = _classify('(via (at 5 5)) (gr_text "x" (at 25 5 0)) (via (at 15 5))')
    assert r.owners[1] == ["left"]
    assert r.owners[2] == ["right"]
    assert [describe(i) for i in r.unowned] == ["via at (15, 5)"]


def test_track_is_owned_by_its_first_point_and_reported_when_it_straddles():
    r = _classify("(segment (start 5 5) (end 15 5)) (segment (start 6 5) (end 8 5))")
    assert r.owners[1] == ["left"] and r.owners[2] == ["left"]
    assert [(name, describe(i)) for name, i in r.straddlers] == [("left", "segment at (5, 5)")]


def test_item_in_two_overlapping_areas_is_ambiguous_and_owned_by_nobody():
    r = _classify("(via (at 5 5))", _area("a", 0, 0, 10, 10), _area("b", 4, 4, 8, 8))
    assert r.owners[1] == []
    assert [(describe(i), names) for i, names in r.ambiguous] == [("via at (5, 5)", ["a", "b"])]


def test_zone_belongs_to_every_area_it_intersects():
    zone = '(zone (net "GND") (layers "F.Cu") (polygon (pts (xy -5 -5) (xy 35 -5) (xy 35 15) (xy -5 15))))'
    r = _classify(zone)
    assert r.owners[1] == ["left", "right"]
    assert r.unowned == []


def test_zone_that_touches_no_area_is_unowned():
    zone = '(zone (layers "F.Cu") (polygon (pts (xy 12 0) (xy 18 0) (xy 18 10) (xy 12 10))))'
    r = _classify(zone)
    assert r.owners[1] == [] and len(r.unowned) == 1


def test_non_edge_cuts_keepout_is_treated_like_a_zone():
    keepout = ('(zone (layers "F.Cu") (keepout (tracks not_allowed)) '
               '(polygon (pts (xy 1 1) (xy 3 1) (xy 3 3) (xy 1 3))))')
    assert _classify(keepout).owners[1] == ["left"]


def test_edge_cuts_rule_areas_are_never_candidates():
    r = _classify('(zone (layer "Edge.Cuts") (polygon (pts (xy 0 0) (xy 9 0) (xy 9 9))))')
    assert r.edge_zone_indexes == {1}
    assert r.items == []


def test_metadata_is_ignored_and_unknown_items_are_handled_by_coordinates():
    r = _classify('(paper "A4") (setup (x 1)) (bezier_track (start 5 5) (end 6 6)) (mystery_flag yes)')
    assert [i.kind for i in r.items] == ["bezier_track"]
    assert r.owners[3] == ["left"]
    assert [i.kind for i in r.unrecognised] == ["bezier_track"]
    assert r.kept_verbatim == ["mystery_flag"]


def test_footprint_uses_its_own_position_not_its_pads():
    r = _classify('(footprint "F" (at 5 5) (pad "1" (at 99 99)))')
    assert r.owners[1] == ["left"]
    assert r.straddlers == []


def test_groups_survive_with_only_their_own_members():
    body = ('(segment (start 1 1) (end 2 2) (uuid "s1")) (segment (start 21 1) (end 22 2) (uuid "s2")) '
            '(group "g" (uuid "g1") (members "s1" "s2")) '
            '(group "outer" (uuid "g2") (members "g1")) '
            '(group "empty" (uuid "g3") (members "nothing"))')
    r = _classify(body)
    left_kept, left_uuids = kept_for(r, "left")
    right_kept, _ = kept_for(r, "right")
    assert left_kept == {1, 3, 4}  # s1, g1, and g2 through g1; g3 has no surviving member
    assert right_kept == {2, 3, 4}
    assert {"s1", "g1", "g2"} <= left_uuids and "s2" not in left_uuids


def test_the_panel_fixture(panel_text):
    root = parse(panel_text)
    r = classify(root, discover(root).areas)
    by_kind = {}
    for item in r.items:
        by_kind.setdefault(item.kind, []).append(item)
    owners = lambda item: r.owners.get(item.index)  # noqa: E731
    assert sorted(owners(i)[0] for i in by_kind["segment"]) == ["main", "main", "main", "side", "side"]
    assert owners(by_kind["footprint"][0]) == ["main"]
    assert owners(by_kind["via"][0]) == ["side"]
    assert owners(by_kind["zone"][0]) == ["main", "side"]
    assert [describe(i) for i in r.unowned] == ["gr_text at (125, 103) [c0000000]"]
    assert [(n, describe(i)) for n, i in r.straddlers] == [("main", "segment at (120, 80) [b0000000]")]
    assert r.ambiguous == []
    assert len(r.edge_zone_indexes) == 2


def test_tuning_patterns_follow_their_members_like_groups():
    body = ('(segment (start 1 1) (end 2 2) (uuid "s1")) (segment (start 21 1) (end 22 2) (uuid "s2")) '
            '(generated (uuid "gen") (type tuning_pattern) (end (xy 5 5)) (members "s1" "s2"))')
    r = _classify(body)
    assert [i.kind for i in r.items if i.container] == ["generated"]
    assert r.unrecognised == []  # generated items are a known container
    assert kept_for(r, "left")[0] == {1, 3}
    assert kept_for(r, "right")[0] == {2, 3}


def test_unknown_member_based_node_is_treated_as_a_container_and_reported():
    r = _classify('(segment (start 1 1) (end 2 2) (uuid "s1")) (chain_thing (members "s1"))')
    assert [i.kind for i in r.unrecognised] == ["chain_thing"]
    assert kept_for(r, "left")[0] == {1, 2}


def test_table_is_assigned_by_its_first_cell():
    r = _classify('(table (column_count 1) (cells (table_cell "a" (start 5 5) (end 8 8))))')
    assert r.owners[1] == ["left"]
    assert r.unrecognised == [] and r.kept_verbatim == []


def test_known_item_without_any_coordinates_is_unowned_rather_than_dropped_silently():
    r = _classify('(gr_line (layer "F.Cu"))')
    assert [describe(i) for i in r.unowned] == ["gr_line"]
