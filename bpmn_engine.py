"""Shared layout, BPMN XML, and Mermaid engine.

Process modules provide a :class:`ProcessModel`; this module deliberately
contains no process-specific nodes, lanes, or identifiers.  The geometry
defaults live here, while every process-specific exception is represented in
the model data.
"""

from __future__ import annotations

import re
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from geometry import GeometryFinding, check_geometry


# --------------------------------------------------------------------------
# Geometry defaults
# --------------------------------------------------------------------------

TASK_W, TASK_H = 140, 80
GW_W, GW_H = 50, 50
EV_W, EV_H = 36, 36
ANN_W = 280
ANN_LINE = 15
ANN_CHARS = 44

COL_GAP = 78
ROW_PITCH = 150
GW_LBL_W = 140
LANE_PAD = 15
POOL_HEADER = 30
POOL_X = 200
POOL_Y = 260
EXTERNAL_POOL_W = 320
EXTERNAL_POOL_H = 60
EXTERNAL_POOL_GAP_ABOVE = 110
MESSAGE_LABEL_W = 140
MESSAGE_LABEL_H = 27
MESSAGE_LABEL_DX = 6
MESSAGE_LABEL_DY = 22

LBL_W, LBL_H = 30, 18


# --------------------------------------------------------------------------
# Process data
# --------------------------------------------------------------------------


@dataclass
class Node:
    id: str
    kind: str  # task | gateway_x | gateway_p | start_message
               # | catch_timer | catch_message | end
    lane: str
    name: str
    phase: str
    ttype: str = "manual"  # manual | user | send | receive (task kinds only)
    doc: list[str] = field(default_factory=list)
    note: str | None = None
    parent: str | None = None  # containing subprocess id; None -> top level


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    condition: str = ""  # empty -> this branch is the gateway default
    loop: bool = False  # route backwards, underneath the sub-row


@dataclass
class ExternalPool:
    """A participant pool outside the process, positioned over an anchor."""

    id: str
    name: str
    anchor: str
    width: float = EXTERNAL_POOL_W
    height: float = EXTERNAL_POOL_H
    gap_above: float = EXTERNAL_POOL_GAP_ABOVE
    mermaid_id: str | None = None


@dataclass
class MessageFlow:
    """A collaboration message flow and its label geometry policy."""

    id: str
    source: str
    target: str
    name: str = ""
    mermaid_name: str | None = None
    label_width: float = MESSAGE_LABEL_W
    label_height: float = MESSAGE_LABEL_H
    label_dx: float = MESSAGE_LABEL_DX
    label_dy: float = MESSAGE_LABEL_DY


@dataclass(frozen=True)
class ProcessOption:
    """Structured option metadata shared by generators and previews."""

    key: str
    title: str
    trigger: str
    gateway: str
    effect: str


@dataclass(frozen=True)
class PreviewMetadata:
    """Presentation copy that belongs to a process, not the renderer."""

    title: str
    heading: str
    eyebrow: str
    lede: str
    owner: str
    version: str
    issued: str
    notation: str = "BPMN 2.0"
    structure_title: str = "Process structure"
    structure_intro: str = ""
    variation_title: str = "Options and gateways"
    variation_intro: str = ""
    constraints_title: str = "Notes carried onto the diagram"
    constraints_intro: str = ""
    footer: str = ""


@dataclass
class ProcessModel:
    """All process-specific input consumed by the shared engine."""

    lanes: list[tuple[str, str]]
    phases: list[tuple[str, str]]
    nodes: list[Node]
    edges: list[Edge]
    process_id: str
    participant_name: str
    process_doc: str
    process_name: str
    participant_id: str
    collaboration_id: str
    definitions_id: str
    exporter: str
    ann_above: set[str] = field(default_factory=set)
    lane_classes: dict[str, str] = field(default_factory=dict)
    mermaid_class_defs: list[str] = field(default_factory=list)
    external_pools: list[ExternalPool] = field(default_factory=list)
    message_flows: list[MessageFlow] = field(default_factory=list)
    exporter_version: str = "1.0"
    target_namespace: str = (
        "http://oklahoma.gov/odmhsas/ofc/bpmn"
    )
    lane_set_id: str | None = None
    diagram_id: str | None = None
    plane_id: str | None = None
    options: list[ProcessOption] = field(default_factory=list)
    preview: PreviewMetadata | None = None

    def by_id(self) -> dict[str, Node]:
        return {node.id: node for node in self.nodes}

    @property
    def resolved_lane_set_id(self) -> str:
        return self.lane_set_id or f"LaneSet_{self.process_id.removeprefix('Process_')}"

    @property
    def resolved_diagram_id(self) -> str:
        return self.diagram_id or f"BPMNDiagram_{self.process_id.removeprefix('Process_')}"

    @property
    def resolved_plane_id(self) -> str:
        return self.plane_id or f"BPMNPlane_{self.process_id.removeprefix('Process_')}"


@dataclass(frozen=True)
class Scope:
    """A coordinate and process scope.

    Phase 1 uses one top-level scope.  The explicit node/lane ownership and
    pool flag let later decomposition add nested planes without changing the
    layout function signatures.
    """

    id: str
    node_ids: tuple[str, ...]
    lane_ids: tuple[str, ...]
    include_pool: bool = True

    @classmethod
    def top_level(cls, model: ProcessModel) -> "Scope":
        return cls(
            id=model.process_id,
            node_ids=tuple(node.id for node in model.nodes),
            lane_ids=tuple(lane_id for lane_id, _ in model.lanes),
            include_pool=True,
        )


@dataclass
class Layout:
    """Absolute geometry for one scope."""

    placements: dict[str, "Placement"]
    bounds: dict[str, tuple[float, float, float, float]]
    ann_bounds: dict[str, tuple[float, float, float, float]]
    lane_box: dict[str, tuple[float, float]]
    row_top: dict[str, float]
    pool: tuple[float, float, float, float] | None
    col_center: list[float]
    offsets: dict[tuple[str, str], float]
    corridors: dict[tuple[str, str], float]

    def row_center(self, lane_id: str, subrow: int) -> float:
        return self.row_top[lane_id] + subrow * ROW_PITCH + ROW_PITCH / 2

    def placement(self, node_id: str) -> "Placement":
        return self.placements[node_id]


@dataclass(frozen=True)
class Placement:
    """Automatically computed column and sub-row for one node."""

    col: int
    subrow: int = 0


class LayoutError(ValueError):
    """Raised when a process cannot be laid out safely."""


N = Node
E = Edge


def _scope_nodes(model: ProcessModel, scope: Scope) -> list[Node]:
    allowed = set(scope.node_ids)
    return [node for node in model.nodes if node.id in allowed]


def _scope_edges(model: ProcessModel, scope: Scope) -> list[Edge]:
    allowed = set(scope.node_ids)
    return [
        edge for edge in model.edges
        if edge.source in allowed and edge.target in allowed
    ]


def _scope_lanes(model: ProcessModel, scope: Scope) -> list[tuple[str, str]]:
    allowed = set(scope.lane_ids)
    return [lane for lane in model.lanes if lane[0] in allowed]


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


def node_size(node: Node) -> tuple[int, int]:
    if node.kind == "task":
        return TASK_W, TASK_H
    if node.kind.startswith("gateway"):
        return GW_W, GW_H
    return EV_W, EV_H


def annotation_height(note: str) -> float:
    """Tall enough that bpmn-js's wrapped text stays inside the bracket."""
    lines = -(-len(note) // ANN_CHARS)
    return max(50, lines * ANN_LINE + 18)


def _topological_layout_data(
    model: ProcessModel, scope: Scope
) -> tuple[dict[str, int], list[str]]:
    """Return longest-path columns and a deterministic forward topological order."""
    nodes = _scope_nodes(model, scope)
    if not nodes:
        raise LayoutError(f"scope {scope.id} contains no nodes")

    by_id = {node.id: node for node in nodes}
    forward = [edge for edge in _scope_edges(model, scope) if not edge.loop]
    adjacency: dict[str, list[str]] = {node.id: [] for node in nodes}
    incoming: dict[str, list[Edge]] = {node.id: [] for node in nodes}
    indegree = {node.id: 0 for node in nodes}
    for edge in forward:
        adjacency[edge.source].append(edge.target)
        incoming[edge.target].append(edge)
        indegree[edge.target] += 1

    starts = [node for node in nodes if node.kind == "start_message"]
    if len(starts) != 1:
        raise LayoutError(
            f"scope {scope.id} must have exactly one start event; "
            f"found {len(starts)}"
        )
    start = starts[0]
    roots = [node.id for node in nodes if indegree[node.id] == 0]
    if roots != [start.id]:
        raise LayoutError(
            f"scope {scope.id} has forward roots besides {start.id}: "
            f"{[root for root in roots if root != start.id]}"
        )

    phase_order = {phase_id: index for index, (phase_id, _) in enumerate(model.phases)}
    if len(phase_order) != len(model.phases):
        raise LayoutError(f"scope {scope.id} has duplicate phase identifiers")
    for node in nodes:
        if node.phase not in phase_order:
            raise LayoutError(
                f"node {node.id} refers to unknown phase {node.phase}"
            )
    for edge in forward:
        source_phase = phase_order[by_id[edge.source].phase]
        target_phase = phase_order[by_id[edge.target].phase]
        if source_phase > target_phase:
            raise LayoutError(
                f"edge {edge.source}->{edge.target} moves from later phase "
                f"{by_id[edge.source].phase} to earlier phase "
                f"{by_id[edge.target].phase}"
            )

    queue = deque([start.id])
    columns = {start.id: 0}
    order: list[str] = []
    while queue:
        source = queue.popleft()
        order.append(source)
        for target in adjacency[source]:
            columns[target] = max(
                columns.get(target, 0), columns[source] + 1
            )
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    if len(order) != len(nodes):
        remaining = [node.id for node in nodes if node.id not in order]
        raise LayoutError(
            f"scope {scope.id} has a cycle after loop edges are ignored: "
            f"{remaining}"
        )

    # A later phase may share a column with the immediately preceding phase,
    # but it may not begin to the left of any earlier phase. Equality keeps
    # compact diagrams compact while still enforcing the authored ordering.
    latest_previous = -1
    for phase_id, _ in model.phases:
        members = [node for node in nodes if node.phase == phase_id]
        if not members:
            continue
        minimum = min(columns[node.id] for node in members)
        if minimum < latest_previous:
            offender = min(members, key=lambda node: columns[node.id])
            raise LayoutError(
                f"phase {phase_id} places {offender.id} at column "
                f"{columns[offender.id]}, left of an earlier phase ending "
                f"at column {latest_previous}"
            )
        latest_previous = max(columns[node.id] for node in members)

    return columns, order


def _reachable(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency[current])
    return seen


def _auto_placements(model: ProcessModel, scope: Scope) -> dict[str, Placement]:
    """Compute columns, semantic branch depth, and deterministic row colors."""
    columns, order = _topological_layout_data(model, scope)
    nodes = _scope_nodes(model, scope)
    by_id = {node.id: node for node in nodes}
    forward = [edge for edge in _scope_edges(model, scope) if not edge.loop]
    adjacency: dict[str, list[str]] = {node.id: [] for node in nodes}
    incoming: dict[str, list[Edge]] = {node.id: [] for node in nodes}
    for edge in forward:
        adjacency[edge.source].append(edge.target)
        incoming[edge.target].append(edge)

    # Propagate branch nesting through the DAG. A conditioned exclusive
    # branch increases depth; an unconditioned/default edge preserves it. At
    # a reconvergence, the shallowest incoming path is the shared baseline.
    branch_depth: dict[str, int] = {}
    for node_id in order:
        if not incoming[node_id]:
            branch_depth[node_id] = 0
            continue
        candidates: list[int] = []
        for edge in incoming[node_id]:
            source = by_id[edge.source]
            increment = int(source.kind == "gateway_x" and bool(edge.condition))
            candidates.append(branch_depth[edge.source] + increment)
        branch_depth[node_id] = min(candidates) if len(candidates) > 1 else candidates[0]

    # Build branch regions from unique forward reachability. Shared join nodes
    # are excluded, so branch depth naturally ends at the join. The branch
    # depth threshold also trims loop-backed option paths whose forward graph
    # has no ordinary reconvergence.
    branch_tokens: list[dict[str, object]] = []
    for gateway in nodes:
        outgoing = [edge for edge in forward if edge.source == gateway.id]
        if len(outgoing) < 2:
            continue
        if gateway.kind == "gateway_x":
            branches = [edge for edge in outgoing if edge.condition]
        elif gateway.kind == "gateway_p":
            branches = outgoing
        else:
            branches = []
        if not branches:
            continue
        reach_by_edge = {
            id(edge): _reachable(edge.target, adjacency) for edge in outgoing
        }
        for edge in branches:
            other_reach: set[str] = set()
            for other in outgoing:
                if other != edge:
                    other_reach.update(reach_by_edge[id(other)])
            unique = reach_by_edge[id(edge)] - other_reach
            desired = branch_depth[gateway.id]
            if gateway.kind == "gateway_x" and edge.condition:
                desired += 1
                unique = {
                    node_id for node_id in unique
                    if branch_depth[node_id] >= desired
                }
            if not unique:
                continue
            for lane_id, _ in _scope_lanes(model, scope):
                lane_nodes = unique & {
                    node.id for node in nodes if node.lane == lane_id
                }
                if not lane_nodes:
                    continue
                branch_tokens.append({
                    "key": (gateway.id, edge.target, lane_id),
                    "start": min(columns[node_id] for node_id in lane_nodes),
                    "end": max(columns[node_id] for node_id in lane_nodes),
                    "desired": desired,
                    "nodes": lane_nodes,
                })

    # Interval coloring is deterministic and keeps overlapping option spans
    # on separate rows even when their individual nodes do not share a column.
    colors: dict[tuple[str, str, str], int] = {}
    for lane_id, _ in _scope_lanes(model, scope):
        tokens = [token for token in branch_tokens if token["key"][2] == lane_id]
        tokens.sort(key=lambda token: (token["start"], token["end"], token["key"]))
        assigned: list[tuple[int, int, int]] = []
        for token in tokens:
            color = int(token["desired"])
            while any(
                color == previous_color
                and token["start"] <= previous_end
                and previous_start <= token["end"]
                for previous_start, previous_end, previous_color in assigned
            ):
                color += 1
            key = token["key"]
            colors[key] = color
            assigned.append((token["start"], token["end"], color))

    subrows = dict(branch_depth)
    for token in branch_tokens:
        color = colors[token["key"]]
        for node_id in token["nodes"]:
            subrows[node_id] = max(subrows[node_id], color)

    # Resolve any same-lane/same-column point conflict left by unusual graph
    # shapes or parallel branches. The first model node keeps the lower row;
    # later nodes take the next free row in stable model order.
    by_lane_col: dict[tuple[str, int], list[Node]] = {}
    for node in nodes:
        by_lane_col.setdefault((node.lane, columns[node.id]), []).append(node)
    for group in by_lane_col.values():
        used: set[int] = set()
        for node in group:
            row = subrows[node.id]
            while row in used:
                row += 1
            subrows[node.id] = row
            used.add(row)

    return {
        node.id: Placement(columns[node.id], subrows[node.id])
        for node in nodes
    }


def _build_layout(
    model: ProcessModel, scope: Scope, placements: dict[str, Placement]
) -> Layout:
    """Build absolute geometry from already-computed placements."""
    nodes = _scope_nodes(model, scope)
    lanes = _scope_lanes(model, scope)

    max_col = max(placement.col for placement in placements.values())
    col_w = [0] * (max_col + 1)
    for node in nodes:
        col = placements[node.id].col
        col_w[col] = max(col_w[col], node_size(node)[0])

    col_center = []
    x = POOL_X + POOL_HEADER + COL_GAP
    for column in range(max_col + 1):
        col_center.append(x + col_w[column] / 2)
        x += col_w[column] + COL_GAP
    pool_w = x - POOL_X

    base_rows: dict[str, int] = {lane_id: 1 for lane_id, _ in lanes}
    for node in nodes:
        base_rows[node.lane] = max(
            base_rows[node.lane], placements[node.id].subrow + 1
        )

    ann_band: dict[str, float] = {lane_id: 0.0 for lane_id, _ in lanes}
    for node in nodes:
        if node.note:
            ann_band[node.lane] = max(
                ann_band[node.lane], annotation_height(node.note) + 26
            )

    lane_box: dict[str, tuple[float, float]] = {}
    row_top: dict[str, float] = {}
    ann_center: dict[str, float] = {}
    y = POOL_Y
    for lane_id, _ in lanes:
        band = ann_band[lane_id]
        height = LANE_PAD * 2 + base_rows[lane_id] * ROW_PITCH + band
        lane_box[lane_id] = (y, height)
        if band and lane_id in model.ann_above:
            ann_center[lane_id] = y + LANE_PAD + band / 2
            row_top[lane_id] = y + LANE_PAD + band
        else:
            row_top[lane_id] = y + LANE_PAD
            if band:
                ann_center[lane_id] = (
                    y + LANE_PAD + base_rows[lane_id] * ROW_PITCH + band / 2
                )
        y += height
    pool_h = y - POOL_Y

    bounds: dict[str, tuple[float, float, float, float]] = {}
    for node in nodes:
        width, height = node_size(node)
        placement = placements[node.id]
        cx = col_center[placement.col]
        cy = row_top[node.lane] + placement.subrow * ROW_PITCH + ROW_PITCH / 2
        bounds[node.id] = (cx - width / 2, cy - height / 2, width, height)

    ann_bounds: dict[str, tuple[float, float, float, float]] = {}
    for node in nodes:
        if not node.note:
            continue
        height = annotation_height(node.note)
        cx = col_center[placements[node.id].col]
        cy = ann_center[node.lane]
        ann_bounds[node.id] = (cx - ANN_W / 2, cy - height / 2, ANN_W, height)

    if ann_bounds:
        right = max(x + width for x, _, width, _ in ann_bounds.values())
        pool_w = max(pool_w, right + COL_GAP - POOL_X)

    offsets = corridor_offsets(model, scope, placements)
    corridors: dict[tuple[str, str], float] = {}
    by_id = model.by_id()
    for edge in _scope_edges(model, scope):
        if edge.loop:
            continue
        source, target = by_id[edge.source], by_id[edge.target]
        source_place = placements[source.id]
        target_place = placements[target.id]
        if source.lane == target.lane and source_place.subrow == target_place.subrow:
            continue
        sx, sy, sw, sh = bounds[source.id]
        tx, _, _, _ = bounds[target.id]
        corridors[(edge.source, edge.target)] = max(
            tx - COL_GAP / 2 + offsets.get((edge.source, edge.target), 0),
            sx + sw + 10,
        )

    return Layout(
        placements=placements,
        bounds=bounds,
        ann_bounds=ann_bounds,
        lane_box=lane_box,
        row_top=row_top,
        pool=(POOL_X, POOL_Y, pool_w, pool_h) if scope.include_pool else None,
        col_center=col_center,
        offsets=offsets,
        corridors=corridors,
    )


def compute_layout(model: ProcessModel, scope: Scope | None = None) -> Layout:
    """Compute deterministic, collision-safe geometry for one scope."""
    scope = scope or Scope.top_level(model)
    placements = _auto_placements(model, scope)
    layout = _build_layout(model, scope, placements)
    findings = layout_findings(model, scope, layout)
    if findings:
        placements = _repair_placements(model, scope, placements, findings)
        layout = _build_layout(model, scope, placements)
        findings = layout_findings(model, scope, layout)
        if findings:
            first = findings[0]
            raise LayoutError(
                f"unresolved layout collision ({first.kind}) between "
                f"{first.first} and {first.second} in scope {scope.id}"
            )
    return layout


def corridor_offsets(
    model: ProcessModel,
    scope: Scope | None = None,
    placements: dict[str, Placement] | None = None,
) -> dict[tuple[str, str], float]:
    """Stagger vertical runs of edges converging on one target."""
    scope = scope or Scope.top_level(model)
    placements = placements or _auto_placements(model, scope)
    nodes = model.by_id()
    grouped: dict[str, list[Edge]] = {}
    for edge in _scope_edges(model, scope):
        if edge.loop:
            continue
        if (nodes[edge.source].lane != nodes[edge.target].lane
                or placements[edge.source].subrow
                != placements[edge.target].subrow):
            grouped.setdefault(edge.target, []).append(edge)
    out: dict[tuple[str, str], float] = {}
    for target, group in grouped.items():
        for index, edge in enumerate(group):
            out[(edge.source, target)] = (
                index - (len(group) - 1) / 2
            ) * 12
    return out


def edge_waypoints(
    model: ProcessModel, edge: Edge, lay: Layout
) -> list[tuple[float, float]]:
    nodes = model.by_id()
    src, tgt = nodes[edge.source], nodes[edge.target]
    sx, sy, sw, sh = lay.bounds[src.id]
    tx, ty, tw, th = lay.bounds[tgt.id]
    scy, tcy = sy + sh / 2, ty + th / 2
    scx, tcx = sx + sw / 2, tx + tw / 2

    if edge.loop:
        # Route backwards underneath the source sub-row, along the empty
        # boundary the layout leaves between sub-rows.
        loop_y = (
            lay.row_top[src.lane]
            + (lay.placement(src.id).subrow + 1) * ROW_PITCH
        )
        return [(scx, sy + sh), (scx, loop_y), (tcx, loop_y), (tcx, ty + th)]

    if abs(scy - tcy) < 1:
        return [(sx + sw, scy), (tx, tcy)]

    # Orthogonal dog-leg. The long horizontal run stays on the source's own
    # sub-row, and the vertical run drops through the empty column gap
    # immediately before the target.
    corridor = lay.corridors.get((src.id, tgt.id))
    if corridor is None:
        corridor = tx - COL_GAP / 2 + lay.offsets.get((src.id, tgt.id), 0)
        corridor = max(corridor, sx + sw + 10)
    return [(sx + sw, scy), (corridor, scy), (corridor, tcy), (tx, tcy)]


def event_label_bounds(
    node: Node, x: float, y: float, w: float, h: float, lay: Layout
) -> tuple[float, float, float, float]:
    """Fit event captions between neighboring columns."""
    centers = lay.col_center
    room = []
    col = lay.placement(node.id).col
    if col > 0:
        room.append(centers[col] - centers[col - 1])
    if col + 1 < len(centers):
        room.append(centers[col + 1] - centers[col])
    width = max(70.0, min(110.0, min(room) - 8)) if room else 110.0
    lines = max(1, -(-len(node.name) // max(8, int(width / 6.4))))
    height = lines * 13 + 4

    # On a branch sub-row the space below carries return traffic, so the
    # caption goes above the event instead.
    if lay.placement(node.id).subrow > 0:
        return (x + w / 2 - width / 2, y - height - 5, width, height)
    return (x + w / 2 - width / 2, y + h + 5, width, height)


def edge_label_bounds(
    model: ProcessModel,
    edge: Edge,
    pts: list[tuple[float, float]],
    lay: Layout,
) -> tuple[float, float, float, float]:
    """Place a branch label on the segment that distinguishes its branch."""
    nodes = model.by_id()
    src, tgt = nodes[edge.source], nodes[edge.target]

    if edge.loop:
        mx = (pts[1][0] + pts[2][0]) / 2
        return (mx - LBL_W / 2, pts[1][1] + 3, LBL_W, LBL_H)

    if len(pts) == 2:
        mx = (pts[0][0] + pts[1][0]) / 2
        return (mx - LBL_W / 2, pts[0][1] - LBL_H - 6, LBL_W, LBL_H)

    scy, tcy = pts[0][1], pts[-1][1]
    y = scy + 6 if tcy > scy else scy - LBL_H - 6
    return ((pts[0][0] + pts[1][0]) / 2 - LBL_W / 2,
            y, LBL_W, LBL_H)


# --------------------------------------------------------------------------
# In-memory geometry gate and deterministic repair
# --------------------------------------------------------------------------


def _layout_labels(
    model: ProcessModel, scope: Scope, lay: Layout
) -> dict[str, tuple[float, float, float, float]]:
    labels: dict[str, tuple[float, float, float, float]] = {}
    for node in _scope_nodes(model, scope):
        x, y, w, h = lay.bounds[node.id]
        if node.name and node.kind in (
            "start_message", "end", "catch_timer", "catch_message"
        ):
            labels[f"{node.id} label"] = event_label_bounds(
                node, x, y, w, h, lay
            )
        elif node.name and node.kind.startswith("gateway"):
            lines = max(1, -(-len(node.name) // 21))
            height = lines * 13 + 4
            labels[f"{node.id} label"] = (
                x + w / 2 - GW_LBL_W / 2,
                y - height - 8,
                GW_LBL_W,
                height,
            )

    for edge in _scope_edges(model, scope):
        points = edge_waypoints(model, edge, lay)
        if edge.label:
            labels[f"{flow_id(edge)} label"] = edge_label_bounds(
                model, edge, points, lay
            )

    if scope.include_pool:
        external_bounds = {
            pool.id: _external_pool_bounds(model, pool, lay)
            for pool in model.external_pools
        }
        by_id = model.by_id()
        for message in model.message_flows:
            source = external_bounds.get(message.source)
            if source is None:
                source = lay.bounds.get(message.source)
            target = lay.bounds.get(message.target)
            if target is None:
                target = external_bounds.get(message.target)
            if source is None or target is None:
                continue
            sx, sy, sw, sh = source
            tx, ty, tw, th = target
            points = [(sx + sw / 2, sy + sh), (tx + tw / 2, ty)]
            if message.name:
                labels[f"{message.id} label"] = (
                    sx + sw / 2 + message.label_dx,
                    sy + sh + message.label_dy,
                    message.label_width,
                    message.label_height,
                )
    return labels


def _layout_edges(
    model: ProcessModel, scope: Scope, lay: Layout
) -> list[tuple[str, list[tuple[float, float]]]]:
    edges = [
        (flow_id(edge), edge_waypoints(model, edge, lay))
        for edge in _scope_edges(model, scope)
    ]
    by_id = model.by_id()
    for node in _scope_nodes(model, scope):
        if not node.note:
            continue
        nx, ny, nw, nh = lay.bounds[node.id]
        ax, ay, aw, ah = lay.ann_bounds[node.id]
        if ay < ny:
            points = [(nx + nw / 2, ny), (ax + aw / 2, ay + ah)]
        else:
            points = [(nx + nw / 2, ny + nh), (ax + aw / 2, ay)]
        edges.append((f"Assoc_{node.id}", points))

    if scope.include_pool:
        external_bounds = {
            pool.id: _external_pool_bounds(model, pool, lay)
            for pool in model.external_pools
        }
        for message in model.message_flows:
            source = external_bounds.get(message.source) or lay.bounds.get(message.source)
            target = lay.bounds.get(message.target) or external_bounds.get(message.target)
            if source is None or target is None:
                continue
            sx, sy, sw, sh = source
            tx, ty, tw, th = target
            edges.append((
                message.id,
                [(sx + sw / 2, sy + sh), (tx + tw / 2, ty)],
            ))
    return edges


def layout_findings(
    model: ProcessModel, scope: Scope, lay: Layout
) -> list[GeometryFinding]:
    """Return validator-like geometry findings without XML round trips."""
    boxes = dict(lay.bounds)
    boxes.update({f"Ann_{node_id}": bounds for node_id, bounds in lay.ann_bounds.items()})
    labels = _layout_labels(model, scope, lay)
    edges = dict(_layout_edges(model, scope, lay))
    return list(check_geometry(boxes, labels, edges).findings)


def _placement_order_valid(
    model: ProcessModel, scope: Scope, placements: dict[str, Placement]
) -> bool:
    by_id = model.by_id()
    for edge in _scope_edges(model, scope):
        if edge.loop:
            continue
        if placements[edge.source].col >= placements[edge.target].col:
            return False
    phase_order = {phase_id: index for index, (phase_id, _) in enumerate(model.phases)}
    latest_previous = -1
    nodes = _scope_nodes(model, scope)
    for phase_id, _ in model.phases:
        members = [node for node in nodes if node.phase == phase_id]
        if not members:
            continue
        minimum = min(placements[node.id].col for node in members)
        if minimum < latest_previous:
            return False
        latest_previous = max(placements[node.id].col for node in members)
    return all(
        by_id[node.id].phase in phase_order
        for node in nodes
    )


def _repair_placements(
    model: ProcessModel,
    scope: Scope,
    initial: dict[str, Placement],
    initial_findings: list[GeometryFinding],
) -> dict[str, Placement]:
    """Use a bounded, stable fallback for geometry the construction misses."""
    nodes = _scope_nodes(model, scope)
    node_index = {node.id: index for index, node in enumerate(nodes)}
    current = dict(initial)
    current_findings = initial_findings
    max_attempts = max(32, 4 * len(nodes))
    forward_adjacency: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in _scope_edges(model, scope):
        if not edge.loop:
            forward_adjacency[edge.source].append(edge.target)

    def node_candidates(finding: GeometryFinding) -> list[str]:
        candidates: list[str] = []
        for value in (finding.first, finding.second):
            owner = value.split(" label", 1)[0]
            if owner.startswith("Ann_"):
                owner = owner.removeprefix("Ann_")
            if owner in node_index and owner not in candidates:
                candidates.append(owner)
            if owner.startswith("Flow_"):
                flow = owner.removeprefix("Flow_")
                source, separator, target = flow.partition("__")
                for endpoint in (source, target) if separator else ():
                    if endpoint in node_index and endpoint not in candidates:
                        candidates.append(endpoint)
            if owner.startswith("Assoc_"):
                endpoint = owner.removeprefix("Assoc_")
                if endpoint in node_index and endpoint not in candidates:
                    candidates.append(endpoint)
        return sorted(candidates, key=lambda node_id: node_index[node_id])

    def score(findings: list[GeometryFinding], placements: dict[str, Placement]):
        return (
            len(findings),
            sum(placement.subrow for placement in placements.values()),
            max(placement.col for placement in placements.values()),
        )

    for _ in range(max_attempts):
        current_score = score(current_findings, current)
        candidates = node_candidates(current_findings[0])
        if not candidates:
            break
        improved = False
        for node_id in candidates:
            old = current[node_id]
            proposals = [
                (node_id, Placement(old.col, old.subrow + 1)),
                (node_id, Placement(old.col + 1, old.subrow)),
            ]
            for proposal_node, proposal in proposals:
                candidate = dict(current)
                if proposal.col != old.col:
                    descendants = _reachable(proposal_node, forward_adjacency)
                else:
                    descendants = {proposal_node}
                for descendant in descendants:
                    placement = candidate[descendant]
                    candidate[descendant] = Placement(
                        placement.col + (proposal.col - old.col),
                        placement.subrow if descendant != proposal_node else proposal.subrow,
                    )
                if not _placement_order_valid(model, scope, candidate):
                    continue
                candidate_layout = _build_layout(model, scope, candidate)
                candidate_findings = layout_findings(model, scope, candidate_layout)
                if score(candidate_findings, candidate) < current_score:
                    current = candidate
                    current_findings = candidate_findings
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
        if not current_findings:
            return current
    return current


# --------------------------------------------------------------------------
# BPMN XML emitter
# --------------------------------------------------------------------------


NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


TASK_ELEMENT = {
    "manual": "manualTask",
    "user": "userTask",
    "send": "sendTask",
    "receive": "receiveTask",
}


def element_tag(node: Node) -> str:
    if node.kind == "task":
        return TASK_ELEMENT[node.ttype]
    if node.kind == "gateway_x":
        return "exclusiveGateway"
    if node.kind == "gateway_p":
        return "parallelGateway"
    if node.kind == "start_message":
        return "startEvent"
    if node.kind == "end":
        return "endEvent"
    return "intermediateCatchEvent"


def flow_id(edge: Edge) -> str:
    return f"Flow_{edge.source}__{edge.target}"


def add_doc(parent: ET.Element, lines: list[str]) -> None:
    if not lines:
        return
    doc = ET.SubElement(parent, q("bpmn", "documentation"))
    doc.text = "\n".join(f"- {line}" for line in lines)


def _external_pool_bounds(
    model: ProcessModel, pool: ExternalPool, lay: Layout
) -> tuple[float, float, float, float]:
    anchor_x, _, anchor_w, _ = lay.bounds[pool.anchor]
    x = anchor_x + anchor_w / 2 - pool.width / 2
    y = POOL_Y - pool.height - pool.gap_above
    return x, y, pool.width, pool.height


def _emit_collaboration(
    defs: ET.Element, model: ProcessModel, scope: Scope
) -> None:
    if not scope.include_pool:
        return
    collab = ET.SubElement(defs, q("bpmn", "collaboration"),
                           {"id": model.collaboration_id})
    for pool in model.external_pools:
        ET.SubElement(collab, q("bpmn", "participant"), {
            "id": pool.id,
            "name": pool.name,
        })
    ET.SubElement(collab, q("bpmn", "participant"), {
        "id": model.participant_id,
        "name": model.participant_name,
        "processRef": model.process_id,
    })
    for message in model.message_flows:
        ET.SubElement(collab, q("bpmn", "messageFlow"), {
            "id": message.id,
            "name": message.name,
            "sourceRef": message.source,
            "targetRef": message.target,
        })


def _emit_process(
    defs: ET.Element, model: ProcessModel, scope: Scope
) -> None:
    proc = ET.SubElement(defs, q("bpmn", "process"), {
        "id": model.process_id,
        "name": model.process_name,
        "isExecutable": "false",
    })
    add_doc(proc, [model.process_doc])

    nodes = _scope_nodes(model, scope)
    edges = _scope_edges(model, scope)
    lanes = _scope_lanes(model, scope)

    lane_set = ET.SubElement(proc, q("bpmn", "laneSet"),
                             {"id": model.resolved_lane_set_id})
    for lane_id, lane_name in lanes:
        lane = ET.SubElement(lane_set, q("bpmn", "lane"), {
            "id": lane_id,
            "name": lane_name,
        })
        for node in nodes:
            if node.lane == lane_id:
                ET.SubElement(lane, q("bpmn", "flowNodeRef")).text = node.id

    incoming: dict[str, list[str]] = {node.id: [] for node in nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        outgoing[edge.source].append(flow_id(edge))
        incoming[edge.target].append(flow_id(edge))

    # An exclusive gateway's unconditioned branch is its default flow.
    defaults: dict[str, str] = {}
    by_id = model.by_id()
    for edge in edges:
        source = by_id[edge.source]
        if (source.kind == "gateway_x" and len(outgoing[source.id]) > 1
                and not edge.condition):
            defaults[source.id] = flow_id(edge)

    for node in nodes:
        attrs = {"id": node.id}
        if node.name:
            attrs["name"] = node.name
        if node.id in defaults:
            attrs["default"] = defaults[node.id]
        element = ET.SubElement(proc, q("bpmn", element_tag(node)), attrs)
        add_doc(element, node.doc)
        for fid in incoming[node.id]:
            ET.SubElement(element, q("bpmn", "incoming")).text = fid
        for fid in outgoing[node.id]:
            ET.SubElement(element, q("bpmn", "outgoing")).text = fid
        if node.kind in ("start_message", "catch_message"):
            ET.SubElement(element, q("bpmn", "messageEventDefinition"),
                          {"id": f"MsgDef_{node.id}"})
        elif node.kind == "catch_timer":
            timer = ET.SubElement(element, q("bpmn", "timerEventDefinition"),
                                  {"id": f"TimerDef_{node.id}"})
            date = ET.SubElement(timer, q("bpmn", "timeDate"))
            date.text = "Day of the scheduled admission"

    for edge in edges:
        attrs = {
            "id": flow_id(edge),
            "sourceRef": edge.source,
            "targetRef": edge.target,
        }
        if edge.label:
            attrs["name"] = edge.label
        flow = ET.SubElement(proc, q("bpmn", "sequenceFlow"), attrs)
        if edge.condition:
            cond = ET.SubElement(flow, q("bpmn", "conditionExpression"))
            cond.text = edge.condition

    for node in nodes:
        if not node.note:
            continue
        ann = ET.SubElement(proc, q("bpmn", "textAnnotation"),
                            {"id": f"Ann_{node.id}"})
        ET.SubElement(ann, q("bpmn", "text")).text = node.note
        ET.SubElement(proc, q("bpmn", "association"), {
            "id": f"Assoc_{node.id}",
            "sourceRef": node.id,
            "targetRef": f"Ann_{node.id}",
        })


def build_xml(
    model: ProcessModel, lay: Layout, scope: Scope | None = None
) -> ET.Element:
    """Build BPMN definitions for one process scope."""
    scope = scope or Scope.top_level(model)
    defs = ET.Element(q("bpmn", "definitions"), {
        "id": model.definitions_id,
        "targetNamespace": model.target_namespace,
        "exporter": model.exporter,
        "exporterVersion": model.exporter_version,
    })

    _emit_collaboration(defs, model, scope)
    _emit_process(defs, model, scope)

    diagram = ET.SubElement(defs, q("bpmndi", "BPMNDiagram"),
                            {"id": model.resolved_diagram_id})
    plane_element = (model.collaboration_id
                     if scope.include_pool else scope.id)
    plane = ET.SubElement(diagram, q("bpmndi", "BPMNPlane"), {
        "id": model.resolved_plane_id,
        "bpmnElement": plane_element,
    })

    def shape(
        bpmn_element: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        horizontal: bool | None = None,
        marker: bool = False,
        label: tuple[float, float, float, float] | None = None,
    ) -> None:
        attrs = {
            "id": f"Shape_{bpmn_element}",
            "bpmnElement": bpmn_element,
        }
        if horizontal is not None:
            attrs["isHorizontal"] = "true" if horizontal else "false"
        if marker:
            attrs["isMarkerVisible"] = "true"
        sh = ET.SubElement(plane, q("bpmndi", "BPMNShape"), attrs)
        ET.SubElement(sh, q("dc", "Bounds"), {
            "x": f"{x:.0f}",
            "y": f"{y:.0f}",
            "width": f"{w:.0f}",
            "height": f"{h:.0f}",
        })
        if label:
            lbl = ET.SubElement(sh, q("bpmndi", "BPMNLabel"))
            ET.SubElement(lbl, q("dc", "Bounds"), {
                "x": f"{label[0]:.0f}",
                "y": f"{label[1]:.0f}",
                "width": f"{label[2]:.0f}",
                "height": f"{label[3]:.0f}",
            })

    external_bounds: dict[str, tuple[float, float, float, float]] = {}
    if scope.include_pool and lay.pool is not None:
        for pool in model.external_pools:
            bounds = _external_pool_bounds(model, pool, lay)
            external_bounds[pool.id] = bounds
            shape(pool.id, *bounds, horizontal=True)

        px, py, pw, ph = lay.pool
        shape(model.participant_id, px, py, pw, ph, horizontal=True)

        for lane_id, _ in _scope_lanes(model, scope):
            top, height = lay.lane_box[lane_id]
            shape(lane_id, px + POOL_HEADER, top, pw - POOL_HEADER, height,
                  horizontal=True)

    nodes = _scope_nodes(model, scope)
    for node in nodes:
        x, y, w, h = lay.bounds[node.id]
        label = None
        if node.name and node.kind in (
            "start_message", "end", "catch_timer", "catch_message"
        ):
            label = event_label_bounds(node, x, y, w, h, lay)
        elif node.name and node.kind.startswith("gateway"):
            lines = max(1, -(-len(node.name) // 21))
            gh = lines * 13 + 4
            label = (x + w / 2 - GW_LBL_W / 2, y - gh - 8, GW_LBL_W, gh)
        shape(node.id, x, y, w, h,
              marker=(node.kind == "gateway_x"), label=label)

    for node in nodes:
        if node.note:
            x, y, w, h = lay.ann_bounds[node.id]
            shape(f"Ann_{node.id}", x, y, w, h)

    def edge_di(
        bpmn_element: str,
        points: list[tuple[float, float]],
        label: tuple[float, float, float, float] | None = None,
    ) -> None:
        edge = ET.SubElement(plane, q("bpmndi", "BPMNEdge"), {
            "id": f"Edge_{bpmn_element}",
            "bpmnElement": bpmn_element,
        })
        for wx, wy in points:
            ET.SubElement(edge, q("di", "waypoint"), {
                "x": f"{wx:.0f}",
                "y": f"{wy:.0f}",
            })
        if label:
            edge_label = ET.SubElement(edge, q("bpmndi", "BPMNLabel"))
            ET.SubElement(edge_label, q("dc", "Bounds"), {
                "x": f"{label[0]:.0f}",
                "y": f"{label[1]:.0f}",
                "width": f"{label[2]:.0f}",
                "height": f"{label[3]:.0f}",
            })

    # Message-flow DI follows the same order as collaboration input.
    for message in model.message_flows:
        source = external_bounds.get(message.source)
        if source is None:
            source = lay.bounds[message.source]
        target = (lay.bounds.get(message.target)
                  or external_bounds[message.target])
        sx, sy, sw, sh = source
        tx, ty, tw, th = target
        points = [
            (sx + sw / 2, sy + sh),
            (tx + tw / 2, ty),
        ]
        label = (
            sx + sw / 2 + message.label_dx,
            sy + sh + message.label_dy,
            message.label_width,
            message.label_height,
        ) if message.name else None
        edge_di(message.id, points, label)

    by_id = model.by_id()
    for edge in _scope_edges(model, scope):
        points = edge_waypoints(model, edge, lay)
        label = (edge_label_bounds(model, edge, points, lay)
                 if edge.label else None)
        edge_di(flow_id(edge), points, label)

    for node in nodes:
        if not node.note:
            continue
        nx, ny, nw, nh = lay.bounds[node.id]
        ax, ay, aw, ah = lay.ann_bounds[node.id]
        if ay < ny:
            edge_di(f"Assoc_{node.id}", [(nx + nw / 2, ny),
                                          (ax + aw / 2, ay + ah)])
        else:
            edge_di(f"Assoc_{node.id}", [(nx + nw / 2, ny + nh),
                                          (ax + aw / 2, ay)])

    return defs


def write_bpmn(
    path: Path, model: ProcessModel, lay: Layout, scope: Scope | None = None
) -> None:
    raw = ET.tostring(build_xml(model, lay, scope), encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="UTF-8")
    text = pretty.decode("utf-8")
    text = "\n".join(line for line in text.splitlines() if line.strip())
    path.write_text(text + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Mermaid emitter
# --------------------------------------------------------------------------


def mermaid_label(text: str) -> str:
    """Mermaid chokes on quotes, brackets and parentheses inside labels."""
    text = text.replace('"', "'")
    return re.sub(r"[\[\]{}()<>|]", "", text)


def wrap(text: str, width: int = 26) -> str:
    words, lines, cur = text.split(), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return "<br/>".join(lines)


def mermaid_node(node: Node) -> str:
    if node.kind.startswith("gateway"):
        label = node.name or ("Merge" if node.kind == "gateway_x" else "Join")
        return f'{node.id}{{"{wrap(mermaid_label(label), 20)}"}}'
    if node.kind in ("start_message", "end", "catch_timer", "catch_message"):
        return f'{node.id}(["{wrap(mermaid_label(node.name), 24)}"])'
    return f'{node.id}["{wrap(mermaid_label(node.name))}"]'


def build_mermaid(
    model: ProcessModel, scope: Scope | None = None
) -> str:
    scope = scope or Scope.top_level(model)
    nodes = _scope_nodes(model, scope)
    edges = _scope_edges(model, scope)
    node_ids = {node.id for node in nodes}

    out = ["flowchart TB"]
    phase_names = dict(model.phases)
    for phase_id, phase_name in model.phases:
        members = [node for node in nodes if node.phase == phase_id]
        if not members:
            continue
        out.append(f'  subgraph {phase_id}["{phase_names[phase_id]}"]')
        out.append("    direction LR")
        for node in members:
            out.append(f"    {mermaid_node(node)}")
        out.append("  end")

    for pool in model.external_pools:
        display_id = pool.mermaid_id or pool.id
        out.append(f"  {display_id}([{pool.name}]):::ext")
    for message in model.message_flows:
        source = next(
            (pool.mermaid_id or pool.id for pool in model.external_pools
             if pool.id == message.source),
            message.source,
        )
        message_name = message.mermaid_name or message.name
        out.append(f"  {source} -. {message_name} .-> {message.target}")

    for edge in edges:
        if edge.label:
            out.append(f"  {edge.source} -->|{mermaid_label(edge.label)}| "
                       f"{edge.target}")
        else:
            out.append(f"  {edge.source} --> {edge.target}")

    out.extend(model.mermaid_class_defs)
    for lane_id, class_name in model.lane_classes.items():
        ids = [node.id for node in nodes if node.lane == lane_id]
        if ids:
            out.append(f"  class {','.join(ids)} {class_name};")
    return "\n".join(out)
