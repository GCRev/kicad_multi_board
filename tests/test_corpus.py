"""Parse, classify and render every board under qa/data/pcbnew; each result must still parse.

Skipped unless KICAD_SOURCE points at a KiCad source checkout. Reads about 150 MB, takes about a minute.
"""
import os
from pathlib import Path

import pytest

from multiboard.discovery import RuleArea
from multiboard.ownership import classify
from multiboard.sexpr import ParseError, apply_edits, parse
from multiboard.tempboard import render

# Files in the KiCad tree that are not valid boards: a placeholder, and a file with trailing junk.
NOT_BOARDS = {"fakeboard.kicad_pcb", "teardrop_offcenter_two_segment.kicad_pcb"}

EVERYTHING = RuleArea("all", (((-1e7, -1e7), (1e7, -1e7), (1e7, 1e7), (-1e7, 1e7)),), None, None)
NOTHING = RuleArea("none", (((1e8, 1e8), (1e8 + 1, 1e8), (1e8 + 1, 1e8 + 1)),), None, None)


@pytest.fixture(scope="module")
def corpus() -> list[Path]:
    source = os.environ.get("KICAD_SOURCE")
    if not source:
        pytest.skip("set KICAD_SOURCE to a KiCad source checkout to run the corpus check")
    files = sorted((Path(source) / "qa" / "data" / "pcbnew").rglob("*.kicad_pcb"))
    if not files:
        pytest.skip(f"no boards found under {source}\\qa\\data\\pcbnew")
    return files


def test_every_board_parses_classifies_and_renders(corpus):
    problems = []
    checked = 0
    for path in corpus:
        try:
            text = path.read_bytes().decode("utf-8")
            root = parse(text)
        except (UnicodeDecodeError, ParseError):
            if path.name not in NOT_BOARDS:
                problems.append(f"{path.name}: does not parse")
            continue
        if root.head != "kicad_pcb":
            continue
        checked += 1
        try:
            assert apply_edits(text, []) == text
            classification = classify(root, [EVERYTHING, NOTHING])
            for name in ("all", "none"):
                parse(render(text, root, classification, name))
        except Exception as exc:  # noqa: BLE001 - collect every failing file, not just the first
            problems.append(f"{path.name}: {type(exc).__name__}: {exc}")
    assert checked > 100, f"only {checked} boards checked; is KICAD_SOURCE correct?"
    assert problems == []
