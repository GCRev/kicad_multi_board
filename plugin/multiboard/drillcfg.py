"""Resolves drill-export options from the drill dialog's remembered state.

KiCad keeps the "Generate Drill Files" dialog's control values in the user's kicad_common.json
under dialog.controls, keyed by widget class and creation order (``wxChoice_2`` is the third
wxChoice created). Only the output directory and aux origin are also stored in the board, so the
rest can only come from here. If the block is missing or does not have the expected shape (a
newer KiCad may have reordered the dialog) every option falls back to kicad-cli's default.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

DIALOG_TITLE = "Generate Drill Files"

_UNITS = ["mm", "in"]
_ZEROS = ["decimal", "suppressleading", "suppresstrailing", "keep"]
_MAP_FORMATS = ["ps", "gerberx2", "dxf", "svg", "pdf"]

_EXPECTED = ({f"wxRadioButton_{i}": bool for i in range(2)}
             | {f"wxCheckBox_{i}": bool for i in range(6)}
             | {f"wxChoice_{i}": int for i in range(4)})
_CHOICE_RANGES = {"wxChoice_0": len(_MAP_FORMATS), "wxChoice_1": 2, "wxChoice_2": len(_UNITS),
                  "wxChoice_3": len(_ZEROS)}


@dataclass(frozen=True)
class DrillFlag:
    args: tuple[str, ...]
    source: str  # "dialog", "board" or "default"


@dataclass
class DrillConfig:
    flags: list[DrillFlag] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def argv(self) -> list[str]:
        return [arg for flag in self.flags for arg in flag.args]


def config_home(env: Optional[Mapping[str, str]] = None, platform: Optional[str] = None,
                home: Optional[Path] = None) -> Path:
    """KiCad's per-user configuration root (the directory that contains ``10.99`` etc.)."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if env.get("KICAD_CONFIG_HOME"):
        return Path(env["KICAD_CONFIG_HOME"])
    home = Path.home() if home is None else home
    if platform == "win32":
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "kicad"
    if platform == "darwin":
        return home / "Library" / "Preferences" / "kicad"
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "kicad"


def load_state(version: Optional[tuple[int, int]], home: Path) -> Optional[dict]:
    """The drill dialog's saved block from ``<home>/<major.minor>/kicad_common.json``, or None."""
    if version is None:
        return None
    path = home / f"{version[0]}.{version[1]}" / "kicad_common.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        block = data["dialog"]["controls"][DIALOG_TITLE]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return block if isinstance(block, dict) else None


def _shape_ok(state: dict) -> bool:
    for key, expected in _EXPECTED.items():
        value = state.get(key)
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            return False
    if state["wxRadioButton_0"] == state["wxRadioButton_1"]:
        return False  # exactly one of Excellon / Gerber X2 must be selected
    return all(0 <= state[key] < limit for key, limit in _CHOICE_RANGES.items())


def resolve(state: Optional[dict], use_aux_origin: bool) -> DrillConfig:
    """Map the dialog state (and the board's aux-origin setting) to kicad-cli drill flags."""
    config = DrillConfig()
    origin = DrillFlag(("--drill-origin", "plot" if use_aux_origin else "absolute"), "board")

    if state is None or not _shape_ok(state):
        why = "not found" if state is None else "does not have the expected layout"
        config.warnings.append(f"drill dialog state {why}; using kicad-cli defaults for drill options")
        config.flags.append(origin)
        return config

    def add(*args: str) -> None:
        config.flags.append(DrillFlag(args, "dialog"))

    excellon = state["wxRadioButton_0"]
    add("--format", "excellon" if excellon else "gerber")
    if excellon:
        add("--excellon-units", _UNITS[state["wxChoice_2"]])
        add("--excellon-zeros-format", _ZEROS[state["wxChoice_3"]])
        add("--excellon-oval-format", "alternate" if state["wxCheckBox_3"] else "route")
        if state["wxCheckBox_0"]:
            add("--excellon-mirror-y")
        if state["wxCheckBox_1"]:
            add("--excellon-min-header")
        if not state["wxCheckBox_2"]:  # the checkbox is "PTH and NPTH in single file"
            add("--excellon-separate-th")
    if state["wxCheckBox_4"]:
        add("--generate-tenting")
    if state["wxCheckBox_5"]:
        add("--generate-map")
        add("--map-format", _MAP_FORMATS[state["wxChoice_0"]])
    config.flags.append(origin)
    return config
