"""Board-level settings the export depends on, read from the board's own plot parameters."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .sexpr import Node


@dataclass(frozen=True)
class BoardInfo:
    generator_version: Optional[str]  # e.g. "10.99"; None if absent
    output_directory: str  # pcbplotparams outputdirectory, "" when unset
    use_aux_origin: bool  # pcbplotparams useauxorigin


def read_board_info(root: Node) -> BoardInfo:
    version = root.find("generator_version")
    setup = root.find("setup")
    params = setup.find("pcbplotparams") if setup else None
    out_dir = params.find("outputdirectory") if params else None
    aux = params.find("useauxorigin") if params else None
    return BoardInfo(
        generator_version=version.text_arg(0) if version else None,
        output_directory=(out_dir.text_arg(0) or "") if out_dir else "",
        use_aux_origin=bool(aux and aux.text_arg(0) == "yes"),
    )


def resolve_root(output_directory: str, board_dir: Path) -> Path:
    """Where per-board folders go: the dialogs' output directory, relative to the board's folder.

    Empty means ``<board dir>/fab``. ``${KIPRJMOD}`` is expanded; any other variable is an error
    rather than a literal folder named ``${...}``.
    """
    raw = output_directory.strip().replace("\\", "/")
    if not raw:
        return board_dir / "fab"
    raw = raw.replace("${KIPRJMOD}", board_dir.as_posix())
    if "${" in raw or "$(" in raw:
        raise ValueError(f"output directory {output_directory!r} contains a variable this plugin cannot expand")
    path = Path(raw)
    if not path.is_absolute():
        path = board_dir / path
    return Path(os.path.normpath(path))
