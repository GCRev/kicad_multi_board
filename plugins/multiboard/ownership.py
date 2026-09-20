"""Decides which board each top-level item of the panel belongs to."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .discovery import RuleArea
from .geometry import Point, point_in_polygon, polygons_intersect
from .pcbnodes import first_nested_point, is_edge_cuts_zone, item_points, node_uuid, zone_polygons
from .sexpr import LIST, STRING, Node

# Top-level nodes that describe the board rather than sit on it. Always kept verbatim.
METADATA = {"version", "generator", "generator_version", "general", "paper", "title_block", "layers",
            "setup", "net", "embedded_fonts", "embedded_files", "property"}

# Item types this plugin knows. Anything else with coordinates is still assigned (by its first
# point) but is reported as unrecognised.
KNOWN_ITEMS = {"footprint", "via", "segment", "arc", "gr_line", "gr_rect", "gr_circle", "gr_arc",
               "gr_curve", "gr_poly", "gr_text", "gr_text_box", "dimension", "image", "target",
               "table"}

# Items defined by a (members "uuid" ...) list rather than by a position: groups, and generated
# items such as tuning patterns. They follow their members.
KNOWN_CONTAINERS = {"group", "generated"}


@dataclass(frozen=True)
class Item:
    index: int  # position among the root's children
    kind: str
    node: Node
    uuid: str | None
    points: tuple[Point, ...]  # defining points, anchor first
    polygons: tuple[tuple[Point, ...], ...] = ()  # zone outlines
    members: tuple[str, ...] = ()  # member uuids of a container
    container: bool = False  # follows its members instead of having a position


@dataclass
class Classification:
    items: list[Item] = field(default_factory=list)  # every item the plugin decides about
    edge_zone_indexes: set[int] = field(default_factory=set)  # rule areas: never copied
    owners: dict[int, list[str]] = field(default_factory=dict)  # item index -> owning board names
    unowned: list[Item] = field(default_factory=list)
    straddlers: list[tuple[str, Item]] = field(default_factory=list)
    ambiguous: list[tuple[Item, list[str]]] = field(default_factory=list)
    unrecognised: list[Item] = field(default_factory=list)
    kept_verbatim: list[str] = field(default_factory=list)  # unknown nodes with no coordinates


def describe(item: Item) -> str:
    """Short human description, e.g. ``segment at (108, 90) [346e08cf]``."""
    point = item.points[0] if item.points else (item.polygons[0][0] if item.polygons else None)
    place = f" at ({point[0]:g}, {point[1]:g})" if point else ""
    tag = f" [{item.uuid[:8]}]" if item.uuid else ""
    return f"{item.kind}{place}{tag}"


def _inside(point: Point, area: RuleArea) -> bool:
    return any(point_in_polygon(point, polygon) for polygon in area.polygons)


def classify(root: Node, areas: Sequence[RuleArea]) -> Classification:
    """Assign every top-level item to zero, one or several boards."""
    result = Classification()
    for index, child in enumerate(root.children):
        if child.kind != LIST or child.head is None or child.head in METADATA:
            continue
        kind = child.head
        uuid = node_uuid(child)

        if is_edge_cuts_zone(child):
            result.edge_zone_indexes.add(index)
            continue

        members = child.find("members")
        if kind == "group" or (members is not None and not item_points(child) and kind != "zone"):
            names = tuple(a.value for a in members.args if a.kind == STRING) if members else ()
            item = Item(index, kind, child, uuid, (), members=names, container=True)
            result.items.append(item)
            if kind not in KNOWN_CONTAINERS:
                result.unrecognised.append(item)
            continue

        if kind == "zone":
            polygons = tuple(tuple(p) for p in zone_polygons(child))
            item = Item(index, kind, child, uuid, (), polygons)
            result.items.append(item)
            names = [a.name for a in areas
                     if any(polygons_intersect(zp, rp) for zp in polygons for rp in a.polygons)]
            result.owners[index] = names
            if not names:
                result.unowned.append(item)
            continue

        points = tuple(item_points(child))
        if not points and kind != "footprint":
            # A footprint's nested coordinates are relative to it, so they say nothing about where it sits.
            nested = first_nested_point(child)
            points = (nested,) if nested else ()
        if not points and kind not in KNOWN_ITEMS:
            result.kept_verbatim.append(kind)
            continue
        item = Item(index, kind, child, uuid, points)
        result.items.append(item)
        if kind not in KNOWN_ITEMS:
            result.unrecognised.append(item)

        matches = [a for a in areas if points and _inside(points[0], a)]
        if len(matches) > 1:
            result.ambiguous.append((item, [a.name for a in matches]))
            result.owners[index] = []
        elif not matches:
            result.unowned.append(item)
            result.owners[index] = []
        else:
            owner = matches[0]
            result.owners[index] = [owner.name]
            if any(not _inside(p, owner) for p in points[1:]):
                result.straddlers.append((owner.name, item))
    return result


def kept_for(classification: Classification, name: str) -> tuple[set[int], set[str]]:
    """Item indexes and uuids that belong in the temp board for ``name``.

    A container (group, tuning pattern) survives if at least one of its members does, including
    through nested containers.
    """
    kept = {i.index for i in classification.items
            if not i.container and name in classification.owners.get(i.index, [])}
    uuids = {i.uuid for i in classification.items if i.index in kept and i.uuid}
    containers = [i for i in classification.items if i.container]
    changed = True
    while changed:
        changed = False
        for container in containers:
            if container.index not in kept and any(m in uuids for m in container.members):
                kept.add(container.index)
                if container.uuid:
                    uuids.add(container.uuid)
                changed = True
    return kept, uuids
