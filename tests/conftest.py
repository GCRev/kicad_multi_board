"""Shared test helpers."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def panel_text() -> str:
    """The synthetic two-board panel, decoded exactly as the plugin decodes board files."""
    return (FIXTURES / "panel.kicad_pcb").read_bytes().decode("utf-8")


@pytest.fixture
def panel_path(tmp_path: Path) -> Path:
    """A writable copy of the panel with its own directory, like a real project."""
    board = tmp_path / "project" / "panel.kicad_pcb"
    board.parent.mkdir()
    board.write_bytes((FIXTURES / "panel.kicad_pcb").read_bytes())
    return board


@pytest.fixture
def kicad_cli() -> str:
    """Path to a real kicad-cli. Integration tests are skipped when KICAD_CLI is not set."""
    path = os.environ.get("KICAD_CLI")
    if not path:
        pytest.skip("set KICAD_CLI to run integration tests")
    return path
