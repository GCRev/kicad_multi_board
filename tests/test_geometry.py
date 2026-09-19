from multiboard.geometry import point_in_polygon, polygons_intersect, segments_intersect

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]
L_SHAPE = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]


def test_point_inside_outside_and_on_boundary():
    assert point_in_polygon((5, 5), SQUARE)
    assert not point_in_polygon((11, 5), SQUARE)
    assert point_in_polygon((0, 5), SQUARE)  # on an edge
    assert point_in_polygon((10, 10), SQUARE)  # on a vertex


def test_point_in_concave_polygon():
    assert point_in_polygon((2, 8), L_SHAPE)
    assert not point_in_polygon((8, 8), L_SHAPE)  # in the notch


def test_segments_intersect_cases():
    assert segments_intersect((0, 0), (4, 4), (0, 4), (4, 0))  # crossing
    assert segments_intersect((0, 0), (4, 0), (4, 0), (8, 0))  # touching end to end
    assert segments_intersect((0, 0), (6, 0), (2, 0), (4, 0))  # collinear overlap
    assert not segments_intersect((0, 0), (1, 0), (2, 0), (3, 0))  # collinear gap
    assert not segments_intersect((0, 0), (4, 0), (0, 1), (4, 1))  # parallel


def test_polygons_overlapping_partially():
    other = [(5, 5), (15, 5), (15, 15), (5, 15)]
    assert polygons_intersect(SQUARE, other)


def test_polygon_containing_the_other_either_way():
    inner = [(2, 2), (3, 2), (3, 3), (2, 3)]
    assert polygons_intersect(SQUARE, inner)
    assert polygons_intersect(inner, SQUARE)


def test_crossing_rectangles_with_no_vertex_inside_the_other():
    horizontal = [(0, 4), (10, 4), (10, 6), (0, 6)]
    vertical = [(4, 0), (6, 0), (6, 10), (4, 10)]
    assert polygons_intersect(horizontal, vertical)


def test_disjoint_and_touching_polygons():
    far = [(20, 0), (30, 0), (30, 10), (20, 10)]
    touching = [(10, 0), (20, 0), (20, 10), (10, 10)]
    assert not polygons_intersect(SQUARE, far)
    assert polygons_intersect(SQUARE, touching)


def test_degenerate_polygon_never_intersects():
    assert not polygons_intersect(SQUARE, [(1, 1), (2, 2)])
