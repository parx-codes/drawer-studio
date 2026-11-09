"""Geometry and bounded-work checks for interactive orthogonal routing."""
from statistics import median
from time import perf_counter

import pytest
from PySide6.QtCore import QPointF, QRectF

from drawer import routing


def _coordinates(path):
    return [(point.x(), point.y()) for point in path]


def _on_border(point, rect):
    return (rect.left() <= point.x() <= rect.right() and rect.top() <= point.y() <= rect.bottom()
            and (point.x() in (rect.left(), rect.right()) or point.y() in (rect.top(), rect.bottom())))


def _assert_clear_orthogonal(path, source, target, obstacles=()):
    assert len(path) >= 2
    assert _on_border(path[0], source)
    assert _on_border(path[-1], target)
    interiors = [source.adjusted(1, 1, -1, -1), target.adjusted(1, 1, -1, -1)]
    for a, b in zip(path, path[1:]):
        assert a != b
        assert a.x() == b.x() or a.y() == b.y()
        assert not any(routing.intersects(a, b, rect) for rect in interiors + list(obstacles))


@pytest.mark.parametrize("target", [
    QRectF(480, 0, 160, 76), QRectF(-480, 0, 160, 76),
    QRectF(0, 350, 160, 76), QRectF(0, -350, 160, 76),
])
def test_unobstructed_aligned_nodes_use_one_segment(target):
    source = QRectF(0, 0, 160, 76)
    path = routing.route(source, target, [])
    _assert_clear_orthogonal(path, source, target)
    assert len(path) == 2


def _assert_outward_endpoint(path, rect, source=True):
    endpoint, neighbor = (path[0], path[1]) if source else (path[-1], path[-2])
    direction = neighbor-endpoint
    normals = [normal for point, normal in routing.ports(rect) if point == endpoint]
    assert normals
    normal = normals[0]
    assert direction.x()*normal.x() + direction.y()*normal.y() > 0
    assert abs(direction.x()*normal.y() - direction.y()*normal.x()) < .01


def test_aligned_top_borders_do_not_create_tangential_top_to_top_shortcut():
    source, target = QRectF(0, 100, 160, 76), QRectF(320, 100, 140, 84)
    path = routing.route(source, target, [])
    _assert_clear_orthogonal(path, source, target)
    assert path[0] == QPointF(source.right(), source.center().y())
    assert path[-1] == QPointF(target.left(), target.center().y())
    _assert_outward_endpoint(path, source)
    _assert_outward_endpoint(path, target, source=False)


@pytest.mark.parametrize("source,target", [
    (QRectF(0, 0, 160, 76), QRectF(480, 0, 160, 76)),
    (QRectF(0, 0, 160, 76), QRectF(-480, 0, 160, 76)),
    (QRectF(0, 0, 160, 76), QRectF(0, 350, 160, 76)),
    (QRectF(0, 0, 160, 76), QRectF(0, -350, 160, 76)),
    (QRectF(0, 100, 160, 76), QRectF(320, 100, 140, 84)),
    (QRectF(0, 100, 160, 76), QRectF(0, 400, 140, 84)),
])
def test_routes_leave_and_enter_ports_along_outward_normals(source, target):
    for lane in range(4):
        path = routing.route(source, target, [], lane=lane)
        _assert_outward_endpoint(path, source)
        _assert_outward_endpoint(path, target, source=False)


@pytest.mark.parametrize("target", [
    QRectF(350, 220, 140, 84), QRectF(-350, 220, 140, 84),
    QRectF(350, -220, 140, 84), QRectF(-350, -220, 140, 84),
])
def test_diagonal_nodes_have_no_diagonal_segments_or_endpoint_crossing(target):
    source = QRectF(0, 0, 160, 76)
    _assert_clear_orthogonal(routing.route(source, target, []), source, target)


@pytest.mark.parametrize("blocker", [QRectF(240, -80, 100, 236), QRectF(210, -200, 160, 450)])
def test_large_blocker_gets_a_real_detour(blocker):
    source, target = QRectF(0, 0, 160, 76), QRectF(480, 0, 160, 76)
    path = routing.route(source, target, [blocker])
    _assert_clear_orthogonal(path, source, target, [blocker])
    assert any(point.y() < blocker.top() or point.y() > blocker.bottom() for point in path)


@pytest.mark.parametrize("target", [QRectF(480, 0, 160, 76), QRectF(350, 220, 140, 84)])
def test_recursive_parallel_lanes_use_distinct_ports(target):
    source = QRectF(0, 0, 160, 76)
    paths = [routing.route(source, target, [], lane=lane) for lane in range(4)]
    for path in paths:
        _assert_clear_orthogonal(path, source, target)
    assert len({(path[0].x(), path[0].y()) for path in paths}) == 4
    assert len({(path[-1].x(), path[-1].y()) for path in paths}) == 4


def test_coincident_nodes_still_produce_renderable_nonempty_segments():
    rect = QRectF(0, 0, 160, 76)
    path = routing.route(rect, rect, [])
    assert len(path) >= 2
    assert all(a != b and (a.x() == b.x() or a.y() == b.y())
               for a, b in zip(path, path[1:]))


def test_remote_obstacles_do_not_increase_candidate_scoring(monkeypatch):
    source, target = QRectF(0, 0, 160, 76), QRectF(350, 220, 140, 84)
    calls = []
    original = routing._score

    def score(points, rects):
        calls.append(len(rects))
        return original(points, rects)

    monkeypatch.setattr(routing, "_score", score)
    baseline = routing.route(source, target, [])
    baseline_work = calls[:]
    calls.clear()
    remote = [QRectF(10000 + (i % 100)*200, 10000 + (i // 100)*200, 160, 76)
              for i in range(10000)]
    result = routing.route(source, target, remote)
    assert _coordinates(result) == _coordinates(baseline)
    assert calls == baseline_work


def test_medium_diagram_refresh_routing_is_interactive():
    entities = [QRectF((i % 5)*440, (i // 5)*350, 160, 76) for i in range(20)]
    relations = [QRectF((entities[i].center().x() + entities[i+1].center().x())/2 - 70,
                       (entities[i].center().y() + entities[i+1].center().y())/2 - 42,
                       140, 84) for i in range(19)]
    rectangles = entities + relations
    cases = [(entities[i+j], relations[i]) for i in range(19) for j in (0, 1)]
    samples = []
    for _ in range(3):
        start = perf_counter()
        for source, target in cases:
            obstacles = [rect.adjusted(-8, -8, 8, 8) for rect in rectangles
                         if rect is not source and rect is not target]
            path = routing.route(source, target, obstacles)
            assert len(path) >= 2
        samples.append(perf_counter() - start)
    # Deliberately generous for slow CI: the original algorithm takes ~11s;
    # the bounded search takes ~11ms here for all 38 connections combined.
    assert median(samples) < .5


def test_segment_touching_border_is_allowed_but_interior_is_blocked():
    rect = QRectF(0, 0, 100, 100)
    assert not routing.intersects(QPointF(-10, 0), QPointF(110, 0), rect)
    assert routing.intersects(QPointF(-10, 50), QPointF(110, 50), rect)
    assert routing.intersects(QPointF(50, -10), QPointF(50, 110), rect)
