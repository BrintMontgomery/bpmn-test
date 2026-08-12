"""Shared, deterministic geometry checks for BPMN diagrams and layouts."""

from __future__ import annotations

from dataclasses import dataclass

Bounds = tuple[float, float, float, float]
Point = tuple[float, float]


@dataclass(frozen=True)
class GeometryFinding:
    """A geometry problem with the offending elements and their bounds."""

    kind: str
    first: str
    second: str
    first_bounds: Bounds | None = None
    second_bounds: Bounds | None = None


@dataclass(frozen=True)
class GeometryReport:
    findings: tuple[GeometryFinding, ...]
    checks: int


def _overlaps(first: Bounds, second: Bounds, pad: float = 0.0) -> bool:
    return (
        first[0] < second[0] + second[2] - pad
        and second[0] + pad < first[0] + first[2]
        and first[1] < second[1] + second[3] - pad
        and second[1] + pad < first[1] + first[3]
    )


def _segment_bounds(first: Point, second: Point) -> Bounds:
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        abs(first[0] - second[0]),
        abs(first[1] - second[1]),
    )


def _segment_crosses(
    first: Point, second: Point, box: Bounds, pad: float = 4.0
) -> bool:
    lo_x, hi_x = sorted((first[0], second[0]))
    lo_y, hi_y = sorted((first[1], second[1]))
    return (
        lo_x < box[0] + box[2] - pad
        and box[0] + pad < hi_x
        and lo_y < box[1] + box[3] - pad
        and box[1] + pad < hi_y
    )


def _edge_owns(edge_id: str, obstacle_id: str) -> bool:
    """Whether an obstacle is one of the edge's own endpoints or labels.

    Flow ids embed their endpoint ids (``Flow_<source>__<target>``, see
    ``bpmn_engine.flow_id``), so a substring test identifies the shapes an edge
    is expected to touch and must not be reported as crossing.
    """
    return obstacle_id.split(" label", 1)[0] in edge_id


def check_geometry(
    boxes: dict[str, Bounds],
    labels: dict[str, Bounds],
    edges: dict[str, list[Point]],
    *,
    pad: float = 4.0,
) -> GeometryReport:
    """Return geometry findings without formatting or raising errors.

    ``boxes``, ``labels`` and ``edges`` must belong to one coordinate plane.
    Keeping the plane boundary outside this function prevents comparisons
    between independent BPMN coordinate spaces.
    """

    findings: list[GeometryFinding] = []
    checks = 0

    box_items = sorted(boxes.items())
    for index, (first_id, first_box) in enumerate(box_items):
        for second_id, second_box in box_items[index + 1:]:
            checks += 1
            if _overlaps(first_box, second_box):
                findings.append(GeometryFinding(
                    "shape overlap", first_id, second_id,
                    first_box, second_box,
                ))

    obstacles = dict(boxes)
    obstacles.update(labels)
    sorted_obstacles = sorted(obstacles.items())
    for edge_id, points in sorted(edges.items()):
        for first, second in zip(points, points[1:]):
            segment = _segment_bounds(first, second)
            for obstacle_id, obstacle_box in sorted_obstacles:
                if _edge_owns(edge_id, obstacle_id):
                    continue
                checks += 1
                if _segment_crosses(first, second, obstacle_box, pad):
                    findings.append(GeometryFinding(
                        "edge crossing", edge_id, obstacle_id,
                        segment, obstacle_box,
                    ))

    for label_id, label_box in sorted(labels.items()):
        owner = label_id.split(" label", 1)[0]
        for obstacle_id, obstacle_box in sorted_obstacles:
            if obstacle_id == label_id or obstacle_id.split(" label", 1)[0] == owner:
                continue
            checks += 1
            if _overlaps(label_box, obstacle_box, pad=pad):
                findings.append(GeometryFinding(
                    "label overlap", label_id, obstacle_id,
                    label_box, obstacle_box,
                ))

    return GeometryReport(tuple(findings), checks)


def format_finding(finding: GeometryFinding) -> str:
    """Format a finding using the validator's long-standing CLI wording."""

    if finding.kind == "shape overlap":
        return f"shapes {finding.first} and {finding.second} overlap"
    if finding.kind == "edge crossing":
        return f"edge {finding.first} passes through {finding.second}"
    if finding.kind == "label overlap":
        return f"{finding.first} overlaps {finding.second}"
    return f"{finding.kind}: {finding.first} and {finding.second}"
