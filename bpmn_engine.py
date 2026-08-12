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
from dataclasses import dataclass, field
from pathlib import Path


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
    col: int
    name: str
    phase: str
    subrow: int = 0
    ttype: str = "manual"  # manual | user | send | receive (task kinds only)
    doc: list[str] = field(default_factory=list)
    note: str | None = None


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

    bounds: dict[str, tuple[float, float, float, float]]
    ann_bounds: dict[str, tuple[float, float, float, float]]
    lane_box: dict[str, tuple[float, float]]
    row_top: dict[str, float]
    pool: tuple[float, float, float, float] | None
    col_center: list[float]
    offsets: dict[tuple[str, str], float]

    def row_center(self, lane_id: str, subrow: int) -> float:
        return self.row_top[lane_id] + subrow * ROW_PITCH + ROW_PITCH / 2


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


def compute_layout(model: ProcessModel, scope: Scope | None = None) -> Layout:
    """Assign absolute geometry to every node, lane, and pool in a scope."""
    scope = scope or Scope.top_level(model)
    nodes = _scope_nodes(model, scope)
    lanes = _scope_lanes(model, scope)

    # Column widths are driven by the widest element in each column, so
    # gateway-only and event-only columns stay narrow.
    max_col = max(node.col for node in nodes)
    col_w = [0] * (max_col + 1)
    for node in nodes:
        col_w[node.col] = max(col_w[node.col], node_size(node)[0])

    col_center = []
    x = POOL_X + POOL_HEADER + COL_GAP
    for column in range(max_col + 1):
        col_center.append(x + col_w[column] / 2)
        x += col_w[column] + COL_GAP
    pool_w = x - POOL_X

    # A lane is tall enough for its deepest sub-row, plus one extra sub-row
    # for text annotations when the lane carries any. The annotation-band
    # placement is process data because each process can need a different
    # corridor strategy.
    base_rows: dict[str, int] = {lane_id: 1 for lane_id, _ in lanes}
    for node in nodes:
        base_rows[node.lane] = max(base_rows[node.lane], node.subrow + 1)

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
        cx = col_center[node.col]
        cy = row_top[node.lane] + node.subrow * ROW_PITCH + ROW_PITCH / 2
        bounds[node.id] = (cx - width / 2, cy - height / 2, width, height)

    # Text annotations sit in their lane's reserved band.
    ann_bounds: dict[str, tuple[float, float, float, float]] = {}
    for node in nodes:
        if not node.note:
            continue
        height = annotation_height(node.note)
        cx = col_center[node.col]
        cy = ann_center[node.lane]
        ann_bounds[node.id] = (cx - ANN_W / 2, cy - height / 2, ANN_W, height)

    # A wide annotation on a narrow trailing column can overhang the pool.
    if ann_bounds:
        right = max(x + width for x, _, width, _ in ann_bounds.values())
        pool_w = max(pool_w, right + COL_GAP - POOL_X)

    return Layout(
        bounds=bounds,
        ann_bounds=ann_bounds,
        lane_box=lane_box,
        row_top=row_top,
        pool=(POOL_X, POOL_Y, pool_w, pool_h) if scope.include_pool else None,
        col_center=col_center,
        offsets=corridor_offsets(model, scope),
    )


def corridor_offsets(
    model: ProcessModel, scope: Scope | None = None
) -> dict[tuple[str, str], float]:
    """Stagger vertical runs of edges converging on one target."""
    scope = scope or Scope.top_level(model)
    nodes = model.by_id()
    grouped: dict[str, list[Edge]] = {}
    for edge in _scope_edges(model, scope):
        if edge.loop:
            continue
        if (nodes[edge.source].lane != nodes[edge.target].lane
                or nodes[edge.source].subrow != nodes[edge.target].subrow):
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
        loop_y = lay.row_top[src.lane] + (src.subrow + 1) * ROW_PITCH
        return [(scx, sy + sh), (scx, loop_y), (tcx, loop_y), (tcx, ty + th)]

    if abs(scy - tcy) < 1:
        return [(sx + sw, scy), (tx, tcy)]

    # Orthogonal dog-leg. The long horizontal run stays on the source's own
    # sub-row, and the vertical run drops through the empty column gap
    # immediately before the target.
    corridor = tx - COL_GAP / 2 + lay.offsets.get((src.id, tgt.id), 0)
    corridor = max(corridor, sx + sw + 10)
    return [(sx + sw, scy), (corridor, scy), (corridor, tcy), (tx, tcy)]


def event_label_bounds(
    node: Node, x: float, y: float, w: float, h: float, lay: Layout
) -> tuple[float, float, float, float]:
    """Fit event captions between neighboring columns."""
    centers = lay.col_center
    room = []
    if node.col > 0:
        room.append(centers[node.col] - centers[node.col - 1])
    if node.col + 1 < len(centers):
        room.append(centers[node.col + 1] - centers[node.col])
    width = max(70.0, min(110.0, min(room) - 8)) if room else 110.0
    lines = max(1, -(-len(node.name) // max(8, int(width / 6.4))))
    height = lines * 13 + 4

    # On a branch sub-row the space below carries return traffic, so the
    # caption goes above the event instead.
    if node.subrow > 0:
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
