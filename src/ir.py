"""Versioned JSON intermediate representation for BPMN process models.

The JSON Schema beside this module documents the wire contract.  Validation
here intentionally uses only the standard library so a user can load an IR
without installing an additional package.  The checks that JSON Schema cannot
express (references between arrays and gateway branch invariants) are applied
before the result is handed to the layout engine.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bpmn_engine import (
    EXTERNAL_POOL_GAP_ABOVE,
    EXTERNAL_POOL_H,
    EXTERNAL_POOL_W,
    MESSAGE_LABEL_DX,
    MESSAGE_LABEL_DY,
    MESSAGE_LABEL_H,
    MESSAGE_LABEL_W,
    ExternalPool,
    Edge,
    MessageFlow,
    Node,
    ProcessModel,
    DecompositionConfig,
    DocumentSpec,
    ProcessBundle,
)


IR_SCHEMA_PATH = Path(__file__).with_name("ir_schema.json")
SCHEMA_VERSION = 1
NODE_KINDS = frozenset({
    "task",
    "gateway_x",
    "gateway_p",
    "start_message",
    "catch_timer",
    "catch_message",
    "end",
    "subprocess",
    "call_activity",
    "link_throw",
    "link_catch",
})
TASK_TYPES = frozenset({"manual", "user", "send", "receive"})


class IRValidationError(ValueError):
    """Raised when an IR document cannot be converted into a process model."""


def _fail(path: str, message: str) -> None:
    raise IRValidationError(f"{path}: {message}")


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, "expected an object")
    return dict(value)


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(path, "expected an array")
    return value


def _string(value: Any, path: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        _fail(path, "expected a string")
    if not allow_empty and not value:
        _fail(path, "must not be empty")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail(path, "expected a boolean")
    return value


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "expected a number")
    if minimum is not None and value < minimum:
        _fail(path, f"must be at least {minimum}")
    return value


def _keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _fail(path, f"unknown field(s): {', '.join(unknown)}")


def _required(value: dict[str, Any], required: set[str], path: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        _fail(path, f"missing required field(s): {', '.join(missing)}")


def _unique(ids: list[str], path: str) -> None:
    seen: set[str] = set()
    for index, item in enumerate(ids):
        if item in seen:
            _fail(f"{path}[{index}]", f"duplicate id {item!r}")
        seen.add(item)


def _read_document(path_or_mapping: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(path_or_mapping, Mapping):
        return _object(path_or_mapping, "IR")
    if not isinstance(path_or_mapping, (str, Path)):
        _fail("IR", "expected a mapping, path, or JSON filename")
    path = Path(path_or_mapping)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise IRValidationError(f"IR file {str(path)!r} could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise IRValidationError(
            f"IR file {str(path)!r} is not valid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    return _object(raw, "IR")


def _validate_and_normalize(document: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "process_id", "participant_name", "process_doc",
        "process_name", "participant_id", "collaboration_id", "definitions_id",
        "exporter", "exporter_version", "target_namespace", "ann_above",
        "lane_classes", "mermaid_class_defs", "lanes", "phases", "nodes",
        "edges", "external_pools", "message_flows", "documents",
        "decomposition",
    }
    required = {
        "schema_version", "process_id", "participant_name", "process_doc",
        "lanes", "phases", "nodes", "edges",
    }
    _keys(document, allowed, "IR")
    _required(document, required, "IR")

    if document["schema_version"] != SCHEMA_VERSION:
        _fail("schema_version", f"expected {SCHEMA_VERSION}")
    for field in ("process_id", "participant_name"):
        _string(document[field], field, allow_empty=False)
    _string(document["process_doc"], "process_doc")

    documents_raw = _array(document.get("documents", []), "documents")
    documents: list[dict[str, str]] = []
    document_ids: list[str] = []
    for index, raw_document in enumerate(documents_raw):
        path = f"documents[{index}]"
        item = _object(raw_document, path)
        _keys(item, {"id", "file", "role"}, path)
        _required(item, {"id", "file"}, path)
        document_id = _string(item["id"], f"{path}.id", allow_empty=False)
        filename = _string(item["file"], f"{path}.file", allow_empty=False)
        role = _string(item.get("role", "main"), f"{path}.role", allow_empty=False)
        if role not in {"main", "global"}:
            _fail(f"{path}.role", "must be one of ['global', 'main']")
        documents.append({"id": document_id, "file": filename, "role": role})
        document_ids.append(document_id)
    _unique(document_ids, "documents")

    decomposition_raw = _object(
        document.get("decomposition", {}), "decomposition"
    )
    _keys(decomposition_raw, {
        "mode", "max_nodes_per_plane", "max_columns", "max_pool_width",
        "collapse_phases", "max_lanes_per_collapsed_phase",
    }, "decomposition")
    mode = decomposition_raw.get("mode", "off")
    if mode not in {"off", "auto"}:
        _fail("decomposition.mode", "must be one of ['auto', 'off']")
    max_nodes = decomposition_raw.get("max_nodes_per_plane", 50)
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or max_nodes < 1:
        _fail("decomposition.max_nodes_per_plane", "must be a positive integer")
    max_columns = decomposition_raw.get("max_columns", 14)
    if isinstance(max_columns, bool) or not isinstance(max_columns, int) or max_columns < 1:
        _fail("decomposition.max_columns", "must be a positive integer")
    max_width = decomposition_raw.get("max_pool_width", 3200)
    _number(max_width, "decomposition.max_pool_width", minimum=1)
    max_lanes = decomposition_raw.get("max_lanes_per_collapsed_phase", 3)
    if isinstance(max_lanes, bool) or not isinstance(max_lanes, int) or max_lanes < 1:
        _fail("decomposition.max_lanes_per_collapsed_phase", "must be a positive integer")
    collapse_phases = _array(
        decomposition_raw.get("collapse_phases", []),
        "decomposition.collapse_phases",
    )
    for index, phase_id in enumerate(collapse_phases):
        _string(phase_id, f"decomposition.collapse_phases[{index}]", allow_empty=False)
    for field in (
        "process_name", "participant_id", "collaboration_id", "definitions_id",
        "exporter", "exporter_version", "target_namespace",
    ):
        if field in document:
            _string(document[field], field, allow_empty=False)

    lanes_raw = _array(document["lanes"], "lanes")
    if not lanes_raw:
        _fail("lanes", "must contain at least one lane")
    lanes: list[dict[str, Any]] = []
    lane_ids: list[str] = []
    for index, raw_lane in enumerate(lanes_raw):
        path = f"lanes[{index}]"
        lane = _object(raw_lane, path)
        _keys(lane, {"id", "name", "ann_above"}, path)
        _required(lane, {"id", "name"}, path)
        lane_id = _string(lane["id"], f"{path}.id", allow_empty=False)
        name = _string(lane["name"], f"{path}.name")
        ann_above = lane.get("ann_above", False)
        _bool(ann_above, f"{path}.ann_above")
        lanes.append({"id": lane_id, "name": name, "ann_above": ann_above})
        lane_ids.append(lane_id)
    _unique(lane_ids, "lanes")

    phases_raw = _array(document["phases"], "phases")
    if not phases_raw:
        _fail("phases", "must contain at least one phase")
    phases: list[dict[str, str]] = []
    phase_ids: list[str] = []
    for index, raw_phase in enumerate(phases_raw):
        path = f"phases[{index}]"
        phase = _object(raw_phase, path)
        _keys(phase, {"id", "name"}, path)
        _required(phase, {"id", "name"}, path)
        phase_id = _string(phase["id"], f"{path}.id", allow_empty=False)
        name = _string(phase["name"], f"{path}.name")
        phases.append({"id": phase_id, "name": name})
        phase_ids.append(phase_id)
    _unique(phase_ids, "phases")
    phase_id_set_for_config = set(phase_ids)
    for index, phase_id in enumerate(collapse_phases):
        if phase_id not in phase_id_set_for_config:
            _fail(f"decomposition.collapse_phases[{index}]", f"unknown phase {phase_id!r}")

    nodes_raw = _array(document["nodes"], "nodes")
    if not nodes_raw:
        _fail("nodes", "must contain at least one node")
    nodes: list[dict[str, Any]] = []
    node_ids: list[str] = []
    for index, raw_node in enumerate(nodes_raw):
        path = f"nodes[{index}]"
        node = _object(raw_node, path)
        _keys(node, {
            "id", "kind", "lane", "phase", "name", "ttype", "doc", "note",
            "parent", "collapsed", "called_element", "link_name",
        }, path)
        _required(node, {"id", "kind", "lane", "phase", "name"}, path)
        node_id = _string(node["id"], f"{path}.id", allow_empty=False)
        kind = _string(node["kind"], f"{path}.kind")
        if kind not in NODE_KINDS:
            _fail(f"{path}.kind", f"must be one of {sorted(NODE_KINDS)}")
        lane = _string(node["lane"], f"{path}.lane", allow_empty=False)
        phase = _string(node["phase"], f"{path}.phase", allow_empty=False)
        name = _string(node["name"], f"{path}.name")

        if kind == "task":
            ttype = node.get("ttype", "manual")
            _string(ttype, f"{path}.ttype")
            if ttype not in TASK_TYPES:
                _fail(f"{path}.ttype", f"must be one of {sorted(TASK_TYPES)}")
        elif "ttype" in node:
            _fail(f"{path}.ttype", "is only valid for task nodes")
        else:
            ttype = "manual"

        doc = node.get("doc", [])
        _array(doc, f"{path}.doc")
        for doc_index, line in enumerate(doc):
            _string(line, f"{path}.doc[{doc_index}]")
        note = node.get("note")
        if note is not None:
            _string(note, f"{path}.note")
        parent = node.get("parent")
        if parent is not None:
            _string(parent, f"{path}.parent", allow_empty=False)

        collapsed = node.get("collapsed", False)
        _bool(collapsed, f"{path}.collapsed")
        called_element = node.get("called_element")
        link_name = node.get("link_name")
        if kind == "subprocess":
            if called_element is not None or link_name is not None:
                _fail(path, "subprocess cannot have called_element or link_name")
        elif collapsed:
            _fail(f"{path}.collapsed", "is only valid for subprocess nodes")
        if kind == "call_activity":
            if called_element is None:
                _fail(f"{path}.called_element", "is required for call_activity nodes")
            _string(called_element, f"{path}.called_element", allow_empty=False)
        elif called_element is not None:
            _fail(f"{path}.called_element", "is only valid for call_activity nodes")
        if kind in {"link_throw", "link_catch"}:
            if link_name is None:
                _fail(f"{path}.link_name", "is required for link events")
            _string(link_name, f"{path}.link_name", allow_empty=False)
        elif link_name is not None:
            _fail(f"{path}.link_name", "is only valid for link events")

        normalized = {
            "id": node_id, "kind": kind, "lane": lane, "phase": phase,
            "name": name, "ttype": ttype, "doc": list(doc), "note": note,
            "parent": parent, "collapsed": collapsed,
            "called_element": called_element, "link_name": link_name,
        }
        nodes.append(normalized)
        node_ids.append(node_id)
    _unique(node_ids, "nodes")
    node_id_set = set(node_ids)
    lane_id_set = set(lane_ids)
    phase_id_set = set(phase_ids)
    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        if node["lane"] not in lane_id_set:
            _fail(f"{path}.lane", f"unknown lane {node['lane']!r}")
        if node["phase"] not in phase_id_set:
            _fail(f"{path}.phase", f"unknown phase {node['phase']!r}")
        if node["parent"] is not None and node["parent"] not in node_id_set:
            _fail(f"{path}.parent", f"unknown parent {node['parent']!r}")
        if node["called_element"] is not None and documents:
            if node["called_element"] not in document_ids:
                _fail(
                    f"{path}.called_element",
                    f"unknown document {node['called_element']!r}",
                )

    parent_by_id = {node["id"]: node["parent"] for node in nodes}
    for node_id in node_ids:
        trail: list[str] = []
        current: str | None = node_id
        while current is not None:
            if current in trail:
                cycle = " -> ".join(trail[trail.index(current):] + [current])
                _fail("nodes.parent", f"contains a cycle: {cycle}")
            trail.append(current)
            current = parent_by_id[current]

    edges_raw = _array(document["edges"], "edges")
    edges: list[dict[str, Any]] = []
    flow_ids: list[str] = []
    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in node_ids}
    for index, raw_edge in enumerate(edges_raw):
        path = f"edges[{index}]"
        edge = _object(raw_edge, path)
        _keys(edge, {"source", "target", "label", "condition", "loop"}, path)
        _required(edge, {"source", "target"}, path)
        source = _string(edge["source"], f"{path}.source", allow_empty=False)
        target = _string(edge["target"], f"{path}.target", allow_empty=False)
        if source not in node_id_set:
            _fail(f"{path}.source", f"unknown node {source!r}")
        if target not in node_id_set:
            _fail(f"{path}.target", f"unknown node {target!r}")
        label = edge.get("label", "")
        condition = edge.get("condition", "")
        loop = edge.get("loop", False)
        _string(label, f"{path}.label")
        _string(condition, f"{path}.condition")
        _bool(loop, f"{path}.loop")
        flow_id = f"Flow_{source}__{target}"
        if flow_id in flow_ids:
            _fail(path, f"duplicate generated flow id {flow_id!r}")
        flow_ids.append(flow_id)
        normalized = {
            "source": source, "target": target, "label": label,
            "condition": condition, "loop": loop,
        }
        edges.append(normalized)
        outgoing[source].append(normalized)

    node_by_id = {node["id"]: node for node in nodes}
    for node_id, branches in outgoing.items():
        if node_by_id[node_id]["kind"] != "gateway_x" or len(branches) < 2:
            continue
        defaults = [branch for branch in branches if branch["condition"] == ""]
        if len(defaults) != 1:
            _fail(
                f"nodes[{node_ids.index(node_id)}]",
                "exclusive gateway must have exactly one outgoing edge "
                "with an empty condition",
            )
        for branch in branches:
            if branch is not defaults[0] and branch["condition"] == "":
                _fail(
                    "edges",
                    f"non-default branch {branch['source']}->{branch['target']} "
                    "must have a condition",
                )

    pools_raw = _array(document.get("external_pools", []), "external_pools")
    pools: list[dict[str, Any]] = []
    pool_ids: list[str] = []
    for index, raw_pool in enumerate(pools_raw):
        path = f"external_pools[{index}]"
        pool = _object(raw_pool, path)
        _keys(pool, {"id", "name", "anchor", "width", "height", "gap_above", "mermaid_id"}, path)
        _required(pool, {"id", "name", "anchor"}, path)
        pool_id = _string(pool["id"], f"{path}.id", allow_empty=False)
        name = _string(pool["name"], f"{path}.name")
        anchor = _string(pool["anchor"], f"{path}.anchor", allow_empty=False)
        if anchor not in node_id_set:
            _fail(f"{path}.anchor", f"unknown node {anchor!r}")
        width = _number(pool.get("width", EXTERNAL_POOL_W), f"{path}.width", minimum=0)
        height = _number(pool.get("height", EXTERNAL_POOL_H), f"{path}.height", minimum=0)
        gap_above = _number(pool.get("gap_above", EXTERNAL_POOL_GAP_ABOVE), f"{path}.gap_above", minimum=0)
        mermaid_id = pool.get("mermaid_id")
        if mermaid_id is not None:
            _string(mermaid_id, f"{path}.mermaid_id", allow_empty=False)
        pools.append({
            "id": pool_id, "name": name, "anchor": anchor, "width": width,
            "height": height, "gap_above": gap_above, "mermaid_id": mermaid_id,
        })
        pool_ids.append(pool_id)
    _unique(pool_ids, "external_pools")
    if set(pool_ids) & node_id_set:
        _fail("external_pools", "pool ids must not duplicate node ids")

    message_raw = _array(document.get("message_flows", []), "message_flows")
    messages: list[dict[str, Any]] = []
    message_ids: list[str] = []
    endpoint_ids = node_id_set | set(pool_ids)
    for index, raw_message in enumerate(message_raw):
        path = f"message_flows[{index}]"
        message = _object(raw_message, path)
        _keys(message, {"id", "source", "target", "name", "mermaid_name", "label_width", "label_height", "label_dx", "label_dy"}, path)
        _required(message, {"source", "target"}, path)
        source = _string(message["source"], f"{path}.source", allow_empty=False)
        target = _string(message["target"], f"{path}.target", allow_empty=False)
        if source not in endpoint_ids:
            _fail(f"{path}.source", f"unknown message endpoint {source!r}")
        if target not in endpoint_ids:
            _fail(f"{path}.target", f"unknown message endpoint {target!r}")
        message_id = message.get("id", f"MessageFlow_{source}__{target}")
        _string(message_id, f"{path}.id", allow_empty=False)
        if message_id in message_ids:
            _fail(path, f"duplicate message-flow id {message_id!r}")
        message_ids.append(message_id)
        name = message.get("name", "")
        mermaid_name = message.get("mermaid_name")
        _string(name, f"{path}.name")
        if mermaid_name is not None:
            _string(mermaid_name, f"{path}.mermaid_name")
        label_width = _number(message.get("label_width", MESSAGE_LABEL_W), f"{path}.label_width", minimum=0)
        label_height = _number(message.get("label_height", MESSAGE_LABEL_H), f"{path}.label_height", minimum=0)
        label_dx = _number(message.get("label_dx", MESSAGE_LABEL_DX), f"{path}.label_dx")
        label_dy = _number(message.get("label_dy", MESSAGE_LABEL_DY), f"{path}.label_dy")
        messages.append({
            "id": message_id, "source": source, "target": target, "name": name,
            "mermaid_name": mermaid_name, "label_width": label_width,
            "label_height": label_height, "label_dx": label_dx, "label_dy": label_dy,
        })

    ann_above = document.get("ann_above", [])
    _array(ann_above, "ann_above")
    for index, lane_id in enumerate(ann_above):
        _string(lane_id, f"ann_above[{index}]", allow_empty=False)
        if lane_id not in lane_id_set:
            _fail(f"ann_above[{index}]", f"unknown lane {lane_id!r}")
    lane_classes = document.get("lane_classes", {})
    lane_classes = _object(lane_classes, "lane_classes")
    for lane_id, class_name in lane_classes.items():
        if lane_id not in lane_id_set:
            _fail("lane_classes", f"unknown lane {lane_id!r}")
        _string(class_name, f"lane_classes.{lane_id}", allow_empty=False)
    mermaid_class_defs = document.get("mermaid_class_defs", [])
    _array(mermaid_class_defs, "mermaid_class_defs")
    for index, class_def in enumerate(mermaid_class_defs):
        _string(class_def, f"mermaid_class_defs[{index}]")

    normalized = dict(document)
    normalized.update({
        "lanes": lanes,
        "phases": phases,
        "nodes": nodes,
        "edges": edges,
        "external_pools": pools,
        "message_flows": messages,
        "ann_above": list(ann_above),
        "lane_classes": lane_classes,
        "mermaid_class_defs": list(mermaid_class_defs),
        "documents": documents,
        "decomposition": {
            "mode": mode,
            "max_nodes_per_plane": max_nodes,
            "max_columns": max_columns,
            "max_pool_width": max_width,
            "collapse_phases": list(collapse_phases),
            "max_lanes_per_collapsed_phase": max_lanes,
        },
    })
    return normalized


def load_ir(path_or_mapping: str | Path | Mapping[str, Any]) -> ProcessModel:
    """Load and validate a version-1 IR document into a ``ProcessModel``."""

    document = _validate_and_normalize(_read_document(path_or_mapping))
    process_id = document["process_id"]
    suffix = process_id.removeprefix("Process_")
    lanes = [(lane["id"], lane["name"]) for lane in document["lanes"]]
    ann_above = set(document["ann_above"])
    ann_above.update(lane["id"] for lane in document["lanes"] if lane["ann_above"])
    nodes = [
        Node(
            id=node["id"], kind=node["kind"], lane=node["lane"],
            name=node["name"], phase=node["phase"], ttype=node["ttype"],
            doc=node["doc"], note=node["note"], parent=node["parent"],
            collapsed=node["collapsed"], called_element=node["called_element"],
            link_name=node["link_name"],
        )
        for node in document["nodes"]
    ]
    edges = [Edge(**edge) for edge in document["edges"]]
    pools = [ExternalPool(**pool) for pool in document["external_pools"]]
    messages = [MessageFlow(**message) for message in document["message_flows"]]
    return ProcessModel(
        lanes=lanes,
        phases=[(phase["id"], phase["name"]) for phase in document["phases"]],
        nodes=nodes,
        edges=edges,
        process_id=process_id,
        participant_name=document["participant_name"],
        process_doc=document["process_doc"],
        process_name=document.get("process_name", document["participant_name"]),
        participant_id=document.get("participant_id", f"Participant_{suffix}"),
        collaboration_id=document.get("collaboration_id", f"Collaboration_{suffix}"),
        definitions_id=document.get("definitions_id", f"Definitions_{suffix}"),
        exporter=document.get("exporter", "ir.py"),
        ann_above=ann_above,
        lane_classes=document["lane_classes"],
        mermaid_class_defs=document["mermaid_class_defs"],
        external_pools=pools,
        message_flows=messages,
        exporter_version=document.get("exporter_version", "1.0"),
        target_namespace=document.get(
            "target_namespace", "http://oklahoma.gov/odmhsas/ofc/bpmn"
        ),
        decomposition=DecompositionConfig(
            mode=document["decomposition"]["mode"],
            max_nodes_per_plane=document["decomposition"]["max_nodes_per_plane"],
            max_columns=document["decomposition"]["max_columns"],
            max_pool_width=document["decomposition"]["max_pool_width"],
            collapse_phases=tuple(document["decomposition"]["collapse_phases"]),
            max_lanes_per_collapsed_phase=document["decomposition"][
                "max_lanes_per_collapsed_phase"
            ],
        ),
        documents=tuple(DocumentSpec(**item) for item in document["documents"]),
    )


def model_to_document(model: ProcessModel) -> dict[str, Any]:
    """Return a deterministic IR document for an in-memory process model.

    This is intentionally the inverse of :func:`load_ir` for migration and
    fixture-authoring workflows.  Presentation-only fields such as preview
    metadata and options are not part of the versioned IR contract.
    """

    nodes: list[dict[str, Any]] = []
    for node in model.nodes:
        item: dict[str, Any] = {
            "id": node.id,
            "kind": node.kind,
            "lane": node.lane,
            "phase": node.phase,
            "name": node.name,
        }
        if node.kind == "task":
            item["ttype"] = node.ttype
        if node.doc:
            item["doc"] = list(node.doc)
        if node.note is not None:
            item["note"] = node.note
        if node.parent is not None:
            item["parent"] = node.parent
        if node.collapsed:
            item["collapsed"] = True
        if node.called_element is not None:
            item["called_element"] = node.called_element
        if node.link_name is not None:
            item["link_name"] = node.link_name
        nodes.append(item)

    edges: list[dict[str, Any]] = []
    for edge in model.edges:
        item: dict[str, Any] = {"source": edge.source, "target": edge.target}
        if edge.label:
            item["label"] = edge.label
        if edge.condition:
            item["condition"] = edge.condition
        if edge.loop:
            item["loop"] = True
        edges.append(item)

    return {
        "schema_version": SCHEMA_VERSION,
        "process_id": model.process_id,
        "participant_name": model.participant_name,
        "process_doc": model.process_doc,
        "process_name": model.process_name,
        "participant_id": model.participant_id,
        "collaboration_id": model.collaboration_id,
        "definitions_id": model.definitions_id,
        "exporter": "ir.json",
        "exporter_version": model.exporter_version,
        "target_namespace": model.target_namespace,
        "ann_above": sorted(model.ann_above),
        "lane_classes": dict(model.lane_classes),
        "mermaid_class_defs": list(model.mermaid_class_defs),
        "lanes": [
            {"id": lane_id, "name": lane_name}
            for lane_id, lane_name in model.lanes
        ],
        "phases": [
            {"id": phase_id, "name": phase_name}
            for phase_id, phase_name in model.phases
        ],
        "nodes": nodes,
        "edges": edges,
        "external_pools": [asdict(pool) for pool in model.external_pools],
        "message_flows": [asdict(flow) for flow in model.message_flows],
        "documents": [asdict(document) for document in model.documents],
        "decomposition": {
            "mode": model.decomposition.mode,
            "max_nodes_per_plane": model.decomposition.max_nodes_per_plane,
            "max_columns": model.decomposition.max_columns,
            "max_pool_width": model.decomposition.max_pool_width,
            "collapse_phases": list(model.decomposition.collapse_phases),
            "max_lanes_per_collapsed_phase": (
                model.decomposition.max_lanes_per_collapsed_phase
            ),
        },
    }


def validate_ir(path_or_mapping: str | Path | Mapping[str, Any]) -> None:
    """Validate an IR document without constructing an engine model."""

    _validate_and_normalize(_read_document(path_or_mapping))


def load_bundle(
    documents: list[str | Path | Mapping[str, Any]],
) -> ProcessBundle:
    """Load a main IR document and any separately modeled global processes."""
    if not documents:
        raise IRValidationError("bundle must contain at least one IR document")
    models = [load_ir(document) for document in documents]
    specs = models[0].documents
    if not specs:
        specs = tuple(
            DocumentSpec(
                model.process_id,
                f"{model.process_id}.bpmn",
                "main" if index == 0 else "global",
            )
            for index, model in enumerate(models)
        )
    return ProcessBundle(models=models, documents=specs)
