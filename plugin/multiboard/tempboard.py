"""Writes the filtered per-board copy of the panel that kicad-cli plots."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from .ownership import Classification, kept_for
from .sexpr import Edit, Node, apply_edits, delete_node


def render(text: str, root: Node, classification: Classification, name: str) -> str:
    """The panel's text with everything that does not belong to board ``name`` removed.

    The header, layers and setup (including pcbplotparams) are never touched, so the board's
    saved plot settings carry over. Rule areas on Edge.Cuts are always removed.
    """
    kept, uuids = kept_for(classification, name)
    edits: list[Edit] = []
    for index in classification.edge_zone_indexes:
        edits.append(delete_node(text, root.children[index]))
    for item in classification.items:
        if item.index not in kept:
            edits.append(delete_node(text, item.node))
        elif item.container:
            members = item.node.find("members")
            for member in (members.args if members else []):
                if member.value not in uuids:
                    edits.append(delete_node(text, member))
    return apply_edits(text, edits)


def write_temp_board(text: str, root: Node, classification: Classification, name: str,
                     scratch: Path, project_path: Optional[Path]) -> Path:
    """Write ``<scratch>/<name>/<name>.kicad_pcb`` (and the project beside it); return the board path.

    The file is named after the board so kicad-cli's output file names carry it.
    """
    folder = scratch / name
    folder.mkdir(parents=True, exist_ok=True)
    board = folder / f"{name}.kicad_pcb"
    board.write_bytes(render(text, root, classification, name).encode("utf-8"))
    if project_path is not None and project_path.is_file():
        shutil.copyfile(project_path, folder / f"{name}.kicad_pro")
    return board
