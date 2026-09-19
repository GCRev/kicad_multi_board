import pytest

from multiboard.sexpr import ATOM, LIST, STRING, ParseError, apply_edits, delete_node, parse


def test_parse_structure_and_accessors():
    root = parse('(kicad_pcb (version 20260901) (zone (layer "Edge.Cuts") (net "a b")))')
    assert root.kind == LIST and root.head == "kicad_pcb"
    assert root.find("version").text_arg(0) == "20260901"
    zone = root.find("zone")
    assert zone.find("layer").args[0].kind == STRING
    assert zone.find("layer").text_arg(0) == "Edge.Cuts"
    assert zone.find("net").text_arg(0) == "a b"
    assert root.children[0].kind == ATOM
    assert root.find("missing") is None


def test_parse_unescapes_strings():
    root = parse(r'(x "a\"b" "c\\d")')
    assert root.text_arg(0) == 'a"b'
    assert root.text_arg(1) == "c\\d"


def test_spans_point_at_source_text():
    text = '(a (b 1) (c "two"))'
    root = parse(text)
    b = root.find("b")
    assert text[b.start:b.end] == "(b 1)"
    assert text[root.start:root.end] == text


def test_find_all_returns_every_match_in_order():
    root = parse("(a (p 1) (q 2) (p 3))")
    assert [n.text_arg(0) for n in root.find_all("p")] == ["1", "3"]


@pytest.mark.parametrize("text", ["(a (b)", "(a))", '(a "open)', "", "atom", "(a) (b)"])
def test_malformed_input_raises(text):
    with pytest.raises(ParseError):
        parse(text)


def test_no_edits_round_trips_exactly(panel_text):
    assert apply_edits(panel_text, []) == panel_text
    assert parse(panel_text).end == len(panel_text.rstrip())


def test_crlf_text_is_preserved():
    text = "(a\r\n\t(b 1)\r\n\t(c 2)\r\n)\r\n"
    root = parse(text)
    out = apply_edits(text, [delete_node(text, root.find("b"))])
    assert out == "(a\r\n\t(c 2)\r\n)\r\n"


def test_delete_node_removes_leading_whitespace():
    text = "(a\n\t(b 1)\n\t(c 2)\n\t(d 3)\n)\n"
    root = parse(text)
    out = apply_edits(text, [delete_node(text, root.find("c"))])
    assert out == "(a\n\t(b 1)\n\t(d 3)\n)\n"
    assert parse(out).find("c") is None


def test_delete_adjacent_nodes():
    text = "(a\n\t(b 1)\n\t(c 2)\n\t(d 3)\n)\n"
    root = parse(text)
    edits = [delete_node(text, root.find("b")), delete_node(text, root.find("c"))]
    assert apply_edits(text, edits) == "(a\n\t(d 3)\n)\n"


def test_delete_string_argument_inside_a_list():
    text = '(members "x" "y" "z")'
    root = parse(text)
    out = apply_edits(text, [delete_node(text, root.args[1])])
    assert out == '(members "x" "z")'


def test_overlapping_edits_are_rejected():
    text = "(a (b (c 1)))"
    root = parse(text)
    b = root.find("b")
    with pytest.raises(ValueError):
        apply_edits(text, [delete_node(text, b), delete_node(text, b.find("c"))])
