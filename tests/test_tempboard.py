from multiboard.discovery import RuleArea, discover
from multiboard.ownership import classify
from multiboard.sexpr import parse
from multiboard.tempboard import render, write_temp_board


def _prepare(text):
    root = parse(text)
    return root, classify(root, discover(root).areas)


def _heads(root):
    return [c.head for c in root.children if c.kind == "list"]


def test_main_board_keeps_only_its_own_items(panel_text):
    root, cls = _prepare(panel_text)
    out = render(panel_text, root, cls, "main")
    board = parse(out)  # still a valid document
    nets = [n.find("net").text_arg(0) for n in board.find_all("segment")]
    assert nets == ["net_a", "net_a", "net_a"]
    assert board.find("footprint") is not None
    assert board.find("via") is None  # the via belongs to the other board
    assert board.find("gr_text") is None  # unowned
    assert [r.find("layer").text_arg(0) for r in board.find_all("gr_rect")] == ["Edge.Cuts"]
    assert board.find("gr_poly") is None  # the other board's outline


def test_rule_areas_are_removed_but_the_shared_pour_is_kept(panel_text):
    root, cls = _prepare(panel_text)
    board = parse(render(panel_text, root, cls, "side"))
    zones = board.find_all("zone")
    assert len(zones) == 1
    assert zones[0].find("net").text_arg(0) == "GND"
    assert "custom_property" not in render(panel_text, root, cls, "side")


def test_header_and_plot_settings_are_untouched(panel_text):
    root, cls = _prepare(panel_text)
    out = render(panel_text, root, cls, "main")
    header = panel_text[:panel_text.index("\t(gr_poly")]
    assert out.startswith(header)
    assert '(outputdirectory "fab_out/")' in out


def test_group_keeps_only_members_that_survive(panel_text):
    root, cls = _prepare(panel_text)
    main = parse(render(panel_text, root, cls, "main")).find("group")
    side = parse(render(panel_text, root, cls, "side")).find("group")
    assert [m.value for m in main.find("members").args] == ["346e08cf-7415-42eb-bb78-1031069228c5"]
    assert [m.value for m in side.find("members").args] == ["51bd658a-7b2a-4431-8a11-d2f859ec97f1"]


def test_generated_items_keep_only_members_that_survive():
    text = ('(kicad_pcb\n\t(segment (start 1 1) (end 2 2) (uuid "s1"))\n'
            '\t(segment (start 21 1) (end 22 2) (uuid "s2"))\n'
            '\t(generated (uuid "gen") (type tuning_pattern) (members "s1" "s2"))\n)\n')
    root = parse(text)
    areas = [RuleArea("left", (((0, 0), (10, 0), (10, 10), (0, 10)),), None, None),
             RuleArea("right", (((20, 0), (30, 0), (30, 10), (20, 10)),), None, None)]
    cls = classify(root, areas)
    left = parse(render(text, root, cls, "left"))
    assert [m.value for m in left.find("generated").find("members").args] == ["s1"]
    assert [n.find("uuid").text_arg(0) for n in left.find_all("segment")] == ["s1"]


def test_dropping_everything_but_metadata_is_still_valid_text(panel_text):
    root, cls = _prepare(panel_text)
    assert parse(render(panel_text, root, cls, "nobody")).find("version") is not None


def test_write_temp_board_names_the_file_after_the_board_and_copies_the_project(panel_text, tmp_path):
    root, cls = _prepare(panel_text)
    project = tmp_path / "snap.kicad_pro"
    project.write_text('{"text_variables": {"REV": "B"}}', encoding="utf-8")
    board = write_temp_board(panel_text, root, cls, "main", tmp_path / "scratch", project)
    assert board == tmp_path / "scratch" / "main" / "main.kicad_pcb"
    assert (tmp_path / "scratch" / "main" / "main.kicad_pro").read_text(encoding="utf-8") == project.read_text(encoding="utf-8")
    assert parse(board.read_bytes().decode("utf-8")).find("footprint") is not None


def test_write_temp_board_without_a_project(panel_text, tmp_path):
    root, cls = _prepare(panel_text)
    board = write_temp_board(panel_text, root, cls, "main", tmp_path, None)
    assert board.is_file() and not (board.parent / "main.kicad_pro").exists()


def test_line_endings_survive_a_crlf_board(panel_text, tmp_path):
    crlf = panel_text.replace("\n", "\r\n")
    root, cls = _prepare(crlf)
    out = render(crlf, root, cls, "main")
    assert "\n" not in out.replace("\r\n", "")
