"""Finds the rule areas that mark out each board and validates the names they carry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .geometry import Point
from .pcbnodes import custom_properties, is_edge_cuts_zone, node_uuid, zone_polygons
from .sexpr import Node

BOARD_NAME_KEY = "board_name"

_RESERVED_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL",
                          *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD_CHARACTERS = set('\\/:*?"<>|') | {chr(c) for c in range(32)}


def validate_name(name: str) -> Optional[str]:
    """Why ``name`` cannot be used as a folder and zip name, or None if it can."""
    if not name:
        return "is empty"
    bad = sorted(c for c in set(name) if c in _BAD_CHARACTERS)
    if bad:
        return "contains reserved character(s) " + " ".join(repr(c) for c in bad)
    if name.endswith("."):
        return "ends with a dot"
    return None


def name_warning(name: str) -> Optional[str]:
    """Why a valid ``name`` may still not work everywhere, or None.

    Windows device names (AUX, CON, ...) are accepted: current Windows 11 creates such folders and
    zips without complaint. Older Windows versions and some tools do not, so the user is told.
    """
    if name.split(".")[0].upper() in _RESERVED_DEVICE_NAMES:
        return ("is a Windows device name; older Windows versions and some tools cannot use it "
                "as a folder or zip name")
    return None


@dataclass(frozen=True)
class RuleArea:
    name: str
    polygons: tuple[tuple[Point, ...], ...]
    uuid: Optional[str]
    location: Optional[Point]  # first vertex, for messages


@dataclass(frozen=True)
class SkippedZone:
    reason: str
    keys: tuple[str, ...]  # custom property keys found on the zone
    location: Optional[Point]
    uuid: Optional[str]


@dataclass
class Discovery:
    areas: list[RuleArea] = field(default_factory=list)
    skipped: list[SkippedZone] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def where(location: Optional[Point], uuid: Optional[str]) -> str:
    place = f"at ({location[0]:g}, {location[1]:g})" if location else "with no outline"
    return f"{place} [{uuid[:8]}]" if uuid else place


def discover(root: Node) -> Discovery:
    """Scan the board's top-level zones for tagged rule areas on Edge.Cuts."""
    result = Discovery()
    seen: dict[str, RuleArea] = {}
    for child in root.children:
        if not is_edge_cuts_zone(child):
            continue
        properties = custom_properties(child)
        polygons = zone_polygons(child)
        location = polygons[0][0] if polygons else None
        uuid = node_uuid(child)

        if BOARD_NAME_KEY not in properties:
            result.skipped.append(SkippedZone(f"no '{BOARD_NAME_KEY}' property", tuple(properties), location, uuid))
            continue

        name = properties[BOARD_NAME_KEY].strip()
        problem = validate_name(name)
        if problem is None and not polygons:
            problem = "belongs to a rule area with no polygon outline"
        if problem:
            result.errors.append(f"rule area {where(location, uuid)}: {BOARD_NAME_KEY} {name!r} {problem}")
            continue

        earlier = seen.get(name.casefold())
        if earlier:
            result.errors.append(
                f"duplicate {BOARD_NAME_KEY} {name!r} at {where(location, uuid)} "
                f"(already used at {where(earlier.location, earlier.uuid)}); names are compared case-insensitively")
            continue

        area = RuleArea(name, tuple(tuple(p) for p in polygons), uuid, location)
        seen[name.casefold()] = area
        result.areas.append(area)
        warning = name_warning(name)
        if warning:
            result.warnings.append(f"rule area {where(location, uuid)}: {BOARD_NAME_KEY} {name!r} {warning}")
    return result
