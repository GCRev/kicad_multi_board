"""Builds the full plan: what will be exported where, and what is wrong with the board."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import drillcfg, exporter
from .boardinfo import BoardInfo, read_board_info, resolve_root
from .discovery import Discovery, RuleArea, discover, where
from .ownership import Classification, classify, describe, kept_for
from .sexpr import Node, parse


@dataclass(frozen=True)
class Snapshot:
    """The board as the plugin reads it.

    ``board_path`` is a private copy that is parsed; ``real_board_path`` is the user's actual file,
    used only to resolve where the output goes.
    """
    board_path: Path
    project_path: Optional[Path]
    real_board_path: Path


@dataclass
class BoardPlan:
    area: RuleArea
    folder: Path
    zip_path: Path
    counts: dict[str, int]  # kept items by kind
    shared_zones: list[str]  # zones included by intersection
    existing_files: list[str]  # files already in the folder
    zip_exists: bool

    @property
    def name(self) -> str:
        return self.area.name


@dataclass
class Plan:
    snapshot: Snapshot
    text: str
    root_node: Node
    discovery: Discovery
    classification: Classification
    info: BoardInfo
    root: Optional[Path]
    boards: list[BoardPlan]
    drill: drillcfg.DrillConfig
    cli: Optional[str]
    cli_version: Optional[tuple[int, int]]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_plan(snapshot: Snapshot, cli: Optional[str], cli_version: Optional[tuple[int, int]],
               config_home: Optional[Path] = None) -> Plan:
    """Read the snapshot and work out every board's export without writing anything."""
    text = snapshot.board_path.read_bytes().decode("utf-8")
    root_node = parse(text)
    discovery = discover(root_node)
    classification = classify(root_node, discovery.areas)
    info = read_board_info(root_node)
    errors = list(discovery.errors)
    warnings = list(discovery.warnings)

    if not discovery.areas and not discovery.errors:
        errors.append("no rule areas on Edge.Cuts with a 'board_name' property were found")

    if cli is None:
        errors.append("kicad-cli was not found")
    else:
        problem, caution = exporter.check_version(cli_version, info.generator_version)
        if problem:
            errors.append(problem)
        if caution:
            warnings.append(caution)

    root: Optional[Path] = None
    try:
        root = resolve_root(info.output_directory, snapshot.real_board_path.parent)
    except ValueError as exc:
        errors.append(str(exc))

    for item, names in classification.ambiguous:
        errors.append(f"{describe(item)} is inside more than one rule area ({', '.join(names)})")
    for name, item in classification.straddlers:
        warnings.append(f"{describe(item)} straddles the edge of '{name}'")
    for item in classification.unrecognised:
        warnings.append(f"unrecognised item type '{item.kind}' assigned by its first coordinate: {describe(item)}")
    if classification.unowned:
        warnings.append(f"{len(classification.unowned)} item(s) are inside no rule area and will be excluded")

    home = config_home if config_home is not None else drillcfg.config_home()
    drill = drillcfg.resolve(drillcfg.load_state(cli_version, home), info.use_aux_origin)
    warnings += drill.warnings

    boards: list[BoardPlan] = []
    if root is not None:
        for area in discovery.areas:
            boards.append(_plan_board(area, root, classification))

    return Plan(snapshot, text, root_node, discovery, classification, info, root, boards, drill,
                cli, cli_version, errors, warnings)


def _plan_board(area: RuleArea, root: Path, classification: Classification) -> BoardPlan:
    kept, _ = kept_for(classification, area.name)
    items = [i for i in classification.items if i.index in kept]
    folder = root / area.name
    try:
        existing = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    except OSError:
        existing = []  # unreadable now; the export itself will fail for this board and say why
    zip_path = root / f"{area.name}.zip"
    return BoardPlan(
        area=area,
        folder=folder,
        zip_path=zip_path,
        counts=dict(sorted(Counter(i.kind for i in items).items())),
        shared_zones=[describe(i) for i in items if i.kind == "zone" and len(classification.owners[i.index]) > 1],
        existing_files=existing,
        zip_exists=zip_path.is_file(),
    )


def board_where(area: RuleArea) -> str:
    return where(area.location, area.uuid)
