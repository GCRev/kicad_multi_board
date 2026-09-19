"""Small 2D polygon helpers. Coordinates are board millimetres; polygons are vertex lists."""
from __future__ import annotations

from typing import Sequence

Point = tuple[float, float]
Polygon = Sequence[Point]

_EPS = 1e-9


def _orient(a: Point, b: Point, c: Point) -> int:
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(value) < _EPS:
        return 0
    return 1 if value > 0 else -1


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    """True if ``p`` lies on segment ab (collinear and within its bounding box)."""
    if _orient(a, b, p) != 0:
        return False
    return (min(a[0], b[0]) - _EPS <= p[0] <= max(a[0], b[0]) + _EPS
            and min(a[1], b[1]) - _EPS <= p[1] <= max(a[1], b[1]) + _EPS)


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Ray casting. Points on the boundary count as inside."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if _on_segment(point, a, b):
            return True
        if (a[1] > y) != (b[1] > y):
            crossing_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < crossing_x:
                inside = not inside
    return inside


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """True if segments p1p2 and p3p4 share at least one point (touching counts)."""
    o1, o2 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    o3, o4 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    return (_on_segment(p3, p1, p2) or _on_segment(p4, p1, p2)
            or _on_segment(p1, p3, p4) or _on_segment(p2, p3, p4))


def polygons_intersect(a: Polygon, b: Polygon) -> bool:
    """True if the two filled polygons overlap or touch, including one containing the other."""
    if len(a) < 3 or len(b) < 3:
        return False
    if any(point_in_polygon(p, b) for p in a) or any(point_in_polygon(p, a) for p in b):
        return True
    for i in range(len(a)):
        for j in range(len(b)):
            if segments_intersect(a[i], a[(i + 1) % len(a)], b[j], b[(j + 1) % len(b)]):
                return True
    return False
