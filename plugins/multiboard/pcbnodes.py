"""Readers for the KiCad-specific shapes found in .kicad_pcb s-expressions."""
from __future__ import annotations

from typing import Optional

from .geometry import Point
from .sexpr import ATOM, LIST, STRING, Node


def _xy(node: Node) -> Optional[Point]:
    """(x y) point from a node such as (xy 1 2) or (at 1 2 90); None if not numeric."""
    args = node.args
    if len(args) < 2:
        return None
    try:
        return float(args[0].value), float(args[1].value)
    except ValueError:
        return None


def pts_points(pts: Node) -> list[Point]:
    """Vertices of a (pts ...) list. An (arc (start) (mid) (end)) entry contributes those three."""
    points: list[Point] = []
    for child in pts.children:
        if child.kind != LIST:
            continue
        if child.head == "xy":
            point = _xy(child)
            if point:
                points.append(point)
        elif child.head == "arc":
            for part in ("start", "mid", "end"):
                sub = child.find(part)
                point = _xy(sub) if sub else None
                if point:
                    points.append(point)
    return points


def zone_polygons(zone: Node) -> list[list[Point]]:
    """Every outline polygon of a zone that has at least three vertices."""
    polygons = []
    for polygon in zone.find_all("polygon"):
        pts = polygon.find("pts")
        vertices = pts_points(pts) if pts else []
        if len(vertices) >= 3:
            polygons.append(vertices)
    return polygons


def layer_names(node: Node) -> list[str]:
    """Names in (layer "X") and (layers "A" "B") children."""
    names: list[str] = []
    for key in ("layer", "layers"):
        child = node.find(key)
        if child:
            names += [a.value for a in child.args if a.kind in (ATOM, STRING)]
    return names


def is_edge_cuts_zone(node: Node) -> bool:
    """True for a zone on Edge.Cuts, which is how KiCad stores a rule area drawn on that layer."""
    return node.kind == LIST and node.head == "zone" and "Edge.Cuts" in layer_names(node)


def custom_properties(node: Node) -> dict[str, str]:
    """The (custom_property "key" "value") children of a node."""
    properties: dict[str, str] = {}
    for prop in node.find_all("custom_property"):
        key, value = prop.text_arg(0), prop.text_arg(1)
        if key is not None:
            properties[key] = value if value is not None else ""
    return properties


def node_uuid(node: Node) -> Optional[str]:
    uuid = node.find("uuid")
    return uuid.text_arg(0) if uuid else None


def item_points(node: Node) -> list[Point]:
    """Defining points of a board item, anchor first.

    Order is at, start, center, mid, end, then the (pts ...) vertices. Only direct children are
    read, so a footprint yields its own (at) and not those of its pads. Works for every item type
    that has coordinates, including ones this plugin has never heard of.
    """
    points: list[Point] = []
    for key in ("at", "start", "center", "mid", "end"):
        child = node.find(key)
        point = _xy(child) if child else None
        if point:
            points.append(point)
    pts = node.find("pts")
    if pts:
        points += pts_points(pts)
    return points


def first_nested_point(node: Node) -> Optional[Point]:
    """First coordinate found anywhere inside ``node``, depth-first in document order.

    A fallback for items such as tables whose coordinates sit in nested children (their cells).
    """
    for child in node.children:
        if child.kind != LIST:
            continue
        if child.head in ("at", "start", "center", "mid", "end", "xy"):
            point = _xy(child)
            if point:
                return point
        point = first_nested_point(child)
        if point:
            return point
    return None
