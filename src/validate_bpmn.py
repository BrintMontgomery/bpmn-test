"""Structural validation for generated BPMN 2.0 documents and bundles."""

from __future__ import annotations

import logging
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from geometry import Bounds, check_geometry, format_finding
from logging_setup import configure

configure()
logger = logging.getLogger(__name__)

BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"
DC = "{http://www.omg.org/spec/DD/20100524/DC}"

FLOW_NODE_TAGS = {
    "task", "manualTask", "userTask", "sendTask", "receiveTask",
    "serviceTask", "scriptTask", "businessRuleTask", "subProcess",
    "callActivity", "startEvent", "endEvent", "intermediateCatchEvent",
    "intermediateThrowEvent", "boundaryEvent", "exclusiveGateway",
    "parallelGateway", "inclusiveGateway", "eventBasedGateway",
    "complexGateway",
}
GATEWAY_TAGS = {
    "exclusiveGateway", "parallelGateway", "inclusiveGateway",
    "eventBasedGateway", "complexGateway",
}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass(frozen=True)
class ScopeInfo:
    element: ET.Element
    process: ET.Element
    parent: "ScopeInfo | None"

    @property
    def id(self) -> str:
        return self.element.get("id") or ""


def _scope_tree(process: ET.Element) -> list[ScopeInfo]:
    scopes: list[ScopeInfo] = []

    def visit(element: ET.Element, parent: ScopeInfo | None) -> None:
        info = ScopeInfo(element, process, parent)
        scopes.append(info)
        for child in element:
            if local(child.tag) == "subProcess":
                visit(child, info)

    visit(process, None)
    return scopes


@dataclass(frozen=True)
class ScopeItems:
    """The elements a scope owns directly, excluding nested subprocesses."""

    nodes: dict[str, ET.Element]
    flows: list[ET.Element]
    annotations: set[str]
    associations: list[ET.Element]


def _direct_scope_items(scope: ScopeInfo) -> ScopeItems:
    return ScopeItems(
        nodes={
            child.get("id"): child
            for child in scope.element
            if local(child.tag) in FLOW_NODE_TAGS and child.get("id")
        },
        flows=[child for child in scope.element
               if local(child.tag) == "sequenceFlow"],
        annotations={
            child.get("id") for child in scope.element
            if local(child.tag) == "textAnnotation" and child.get("id")
        },
        associations=[child for child in scope.element
                      if local(child.tag) == "association"],
    )


def _link_definition(event: ET.Element) -> ET.Element | None:
    if local(event.tag) not in ("intermediateThrowEvent", "intermediateCatchEvent"):
        return None
    return next((child for child in event
                 if local(child.tag) == "linkEventDefinition"), None)


def _bounds(element: ET.Element) -> Bounds | None:
    value = element if local(element.tag) == "Bounds" else element.find(f"{DC}Bounds")
    if value is None:
        return None
    try:
        return tuple(float(value.get(key, "0"))
                     for key in ("x", "y", "width", "height"))  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


class Validator:
    def __init__(
        self,
        path: Path,
        *,
        bundle_process_ids: set[str] | None = None,
        called_process_ids: set[str] | None = None,
    ) -> None:
        self.path = Path(path)
        self.root = ET.parse(self.path).getroot()
        self.errors: list[str] = []
        self.checks = 0
        self.collab = next((el for el in self.root
                            if local(el.tag) == "collaboration"), None)

        local_processes = [el for el in self.root
                           if local(el.tag) == "process"]
        local_ids = {el.get("id") for el in local_processes if el.get("id")}
        local_called = {
            el.get("calledElement")
            for process in local_processes
            for el in process.iter()
            if local(el.tag) == "callActivity" and el.get("calledElement")
        }
        self.bundle_process_ids = bundle_process_ids or local_ids
        self.called_process_ids = called_process_ids or local_called

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def check(self, condition: bool, msg: str) -> None:
        self.checks += 1
        if not condition:
            self.fail(msg)

    def run(self) -> bool:
        processes = [el for el in self.root
                     if local(el.tag) == "process"]
        collab = self.collab
        if not processes:
            self.fail("missing bpmn:process")
            return self.report()

        participants = {
            el.get("id"): el for el in (collab if collab is not None else [])
            if local(el.tag) == "participant" and el.get("id")
        }
        msg_flows = [el for el in (collab if collab is not None else [])
                     if local(el.tag) == "messageFlow"]
        self.check_unique_ids()

        all_scopes = [scope for process in processes
                      for scope in _scope_tree(process)]
        scope_by_id = {scope.id: scope for scope in all_scopes if scope.id}
        all_nodes = {
            node_id: node
            for scope in all_scopes
            for node_id, node in _direct_scope_items(scope).nodes.items()
        }
        self.check_message_refs(all_nodes)
        self.check_called_elements()
        for process in processes:
            process_scopes = [scope for scope in all_scopes
                              if scope.process is process]
            top = next(scope for scope in process_scopes
                       if scope.element is process)
            self.check_processes(process_scopes, all_nodes)
            self.check_di(
                process_scopes, scope_by_id, participants, msg_flows,
                collab,
            )
            self.check_process_ref(collab, process)

            self._report_process_summary(_direct_scope_items(top))

        return self.report()

    def _report_process_summary(self, top_items: ScopeItems) -> None:
        logger.info(f"{self.path.name}: {len(top_items.nodes)} flow nodes, "
                    f"{len(top_items.flows)} sequence flows, "
                    f"{len(top_items.annotations)} annotations, "
                    f"{self.checks} assertions")

    def check_unique_ids(self) -> None:
        ids = [el.get("id") for el in self.root.iter() if el.get("id")]
        dupes = [i for i, count in Counter(ids).items() if count > 1]
        self.check(not dupes, f"duplicate ids: {dupes[:5]}")

    def check_processes(
        self,
        scopes: list[ScopeInfo],
        all_nodes: dict[str, ET.Element],
    ) -> None:
        owner_by_node = {
            node_id: scope.id
            for scope in scopes
            for node_id in _direct_scope_items(scope).nodes
        }
        for scope in scopes:
            items = _direct_scope_items(scope)
            self.check_flow_refs(
                items.nodes, items.flows, all_nodes, owner_by_node,
                items.annotations, items.associations,
            )
            self.check_connectivity(scope, items.nodes, items.flows)
            self.check_lanes(scope, items.nodes)
            self.check_gateways(items.nodes, items.flows)
            self.check_links(scope, items.nodes)

    def check_message_refs(self, all_nodes: dict[str, ET.Element]) -> None:
        for message in [el for el in self.root.iter()
                        if local(el.tag) == "messageFlow"]:
            for attr in ("sourceRef", "targetRef"):
                ref = message.get(attr)
                self.check(
                    ref in all_nodes or self._participant_exists(ref),
                    f"messageFlow {message.get('id')} {attr}={ref} "
                    "does not resolve",
                )

    def check_called_elements(self) -> None:
        for process in self.root:
            if local(process.tag) != "process":
                continue
            for element in process.iter():
                if local(element.tag) != "callActivity":
                    continue
                target = element.get("calledElement")
                self.check(
                    target in self.bundle_process_ids,
                    f"callActivity {element.get('id')} calledElement={target} "
                    "does not resolve to a process in the bundle",
                )

    def check_flow_refs(
        self,
        nodes: dict[str, ET.Element],
        flows: list[ET.Element],
        all_nodes: dict[str, ET.Element],
        owner_by_node: dict[str, str],
        annotations: set[str],
        associations: list[ET.Element],
    ) -> None:
        for flow in flows:
            for attr in ("sourceRef", "targetRef"):
                ref = flow.get(attr)
                if ref not in nodes and ref in all_nodes:
                    self.check(
                        False,
                        f"sequenceFlow {flow.get('id')} crosses scope boundary "
                        f"via {attr}={ref}",
                    )
                else:
                    self.check(
                        ref in nodes,
                        f"sequenceFlow {flow.get('id')} {attr}={ref} "
                        "does not resolve to a flow node",
                    )
        for association in associations:
            self.check(
                association.get("sourceRef") in nodes,
                f"association {association.get('id')} sourceRef does not "
                "resolve to a flow node",
            )
            self.check(
                association.get("targetRef") in annotations,
                f"association {association.get('id')} targetRef does not "
                "resolve to a text annotation",
            )

    def _participant_exists(self, participant_id: str | None) -> bool:
        return any(el.get("id") == participant_id
                   for el in (self.collab if self.collab is not None else [])
                   if local(el.tag) == "participant")

    def check_connectivity(
        self,
        scope: ScopeInfo,
        nodes: dict[str, ET.Element],
        flows: list[ET.Element],
    ) -> None:
        incoming = Counter(flow.get("targetRef") for flow in flows)
        outgoing = Counter(flow.get("sourceRef") for flow in flows)
        for node_id, element in nodes.items():
            self._check_node_connectivity(node_id, element, incoming, outgoing)
            self._check_declared_refs(node_id, element, flows)

        starts = [node_id for node_id, element in nodes.items()
                  if local(element.tag) == "startEvent"]
        self.check(len(starts) == 1,
                   f"expected exactly 1 start event, found {len(starts)}")
        self._check_reachability(nodes, flows, starts)

    def _check_node_connectivity(
        self,
        node_id: str,
        element: ET.Element,
        incoming: Counter,
        outgoing: Counter,
    ) -> None:
        tag = local(element.tag)
        link = _link_definition(element)
        if link is not None:
            is_throw = tag == "intermediateThrowEvent"
            self.check(
                incoming[node_id] > 0 if is_throw else incoming[node_id] == 0,
                f"{tag} {node_id} has invalid incoming sequence flow "
                "for a link event",
            )
            self.check(
                outgoing[node_id] == 0 if is_throw else outgoing[node_id] > 0,
                f"{tag} {node_id} has invalid outgoing sequence flow "
                "for a link event",
            )
        else:
            if tag != "startEvent":
                self.check(incoming[node_id] > 0,
                           f"{tag} {node_id} has no incoming sequence flow")
            else:
                self.check(incoming[node_id] == 0,
                           f"startEvent {node_id} must not have an incoming flow")
            if tag != "endEvent":
                self.check(outgoing[node_id] > 0,
                           f"{tag} {node_id} has no outgoing sequence flow")
            else:
                self.check(outgoing[node_id] == 0,
                           f"endEvent {node_id} must not have an outgoing flow")

    def _check_declared_refs(
        self,
        node_id: str,
        element: ET.Element,
        flows: list[ET.Element],
    ) -> None:
        declared_in = {child.text for child in element
                       if local(child.tag) == "incoming"}
        declared_out = {child.text for child in element
                        if local(child.tag) == "outgoing"}
        actual_in = {flow.get("id") for flow in flows
                     if flow.get("targetRef") == node_id}
        actual_out = {flow.get("id") for flow in flows
                      if flow.get("sourceRef") == node_id}
        self.check(declared_in == actual_in,
                   f"{node_id} <incoming> refs disagree with sequenceFlows")
        self.check(declared_out == actual_out,
                   f"{node_id} <outgoing> refs disagree with sequenceFlows")

    def _check_reachability(
        self,
        nodes: dict[str, ET.Element],
        flows: list[ET.Element],
        starts: list[str],
    ) -> None:
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
        for flow in flows:
            source, target = flow.get("sourceRef"), flow.get("targetRef")
            if source in adjacency and target in nodes:
                adjacency[source].append(target)

        links: dict[str, list[str]] = defaultdict(list)
        for node_id, element in nodes.items():
            definition = _link_definition(element)
            if definition is not None and definition.get("name"):
                links[definition.get("name")].append(node_id)
        for node_id, element in nodes.items():
            definition = _link_definition(element)
            if definition is None:
                continue
            name = definition.get("name")
            if name:
                paired = [candidate for candidate in links[name]
                          if _link_definition(nodes[candidate]) is not None
                          and local(nodes[candidate].tag) != local(element.tag)]
                adjacency[node_id].extend(paired)

        seen: set[str] = set(starts)
        stack = list(starts)
        while stack:
            current = stack.pop()
            for next_node in adjacency.get(current, []):
                if next_node not in seen:
                    seen.add(next_node)
                    stack.append(next_node)
        unreachable = sorted(set(nodes) - seen)
        self.check(not unreachable, f"unreachable nodes: {unreachable}")

    def check_lanes(self, scope: ScopeInfo, nodes: dict[str, ET.Element]) -> None:
        lane_set = next((child for child in scope.element
                         if local(child.tag) == "laneSet"), None)
        if lane_set is None:
            if scope.parent is None and scope.id not in self.called_process_ids:
                self.check(False, "process has no laneSet")
            return
        assigned: Counter = Counter()
        for lane in lane_set:
            for ref in lane:
                if local(ref.tag) == "flowNodeRef":
                    self.check(ref.text in nodes,
                               f"lane {lane.get('id')} references unknown node "
                               f"{ref.text}")
                    assigned[ref.text] += 1
        for node_id in nodes:
            self.check(assigned[node_id] == 1,
                       f"{node_id} appears in {assigned[node_id]} lanes, expected 1")

    def check_gateways(self, nodes, flows) -> None:
        for node_id, element in nodes.items():
            tag = local(element.tag)
            if tag not in GATEWAY_TAGS:
                continue
            outgoing = [flow for flow in flows
                        if flow.get("sourceRef") == node_id]
            if len(outgoing) < 2 or tag != "exclusiveGateway":
                continue
            for flow in outgoing:
                self.check(bool(flow.get("name")),
                           f"branch {flow.get('id')} out of {node_id} has no label")
            default = element.get("default")
            self.check(default is not None,
                       f"exclusiveGateway {node_id} splits without a default flow")
            self.check(default in {flow.get("id") for flow in outgoing},
                       f"exclusiveGateway {node_id} default={default} is not one "
                       "of its outgoing flows")
            for flow in outgoing:
                has_condition = any(local(child.tag) == "conditionExpression"
                                    for child in flow)
                if flow.get("id") == default:
                    self.check(not has_condition,
                               f"default flow {flow.get('id')} must not carry a "
                               "conditionExpression")
                else:
                    self.check(has_condition,
                               f"non-default branch {flow.get('id')} out of "
                               f"{node_id} has no conditionExpression")

    def check_links(self, scope: ScopeInfo, nodes: dict[str, ET.Element]) -> None:
        throws: defaultdict[str, list[str]] = defaultdict(list)
        catches: defaultdict[str, list[str]] = defaultdict(list)
        for node_id, element in nodes.items():
            definition = _link_definition(element)
            if definition is None:
                continue
            name = definition.get("name")
            if not name:
                self.check(False, f"link event {node_id} has no name")
            elif local(element.tag) == "intermediateThrowEvent":
                throws[name].append(node_id)
            else:
                catches[name].append(node_id)
        for name in sorted(set(throws) | set(catches)):
            self.check(
                len(throws[name]) == 1 and len(catches[name]) == 1,
                f"link {name} must have exactly 1 throw and 1 catch "
                f"within scope {scope.id}",
            )

    def check_di(
        self,
        scopes: list[ScopeInfo],
        scope_by_id: dict[str, ScopeInfo],
        participants: dict[str, ET.Element],
        msg_flows: list[ET.Element],
        collab: ET.Element | None,
    ) -> None:
        planes = [element for element in self.root.iter()
                  if local(element.tag) == "BPMNPlane"]
        by_scope: defaultdict[str, list[ET.Element]] = defaultdict(list)
        for plane in planes:
            owner = plane.get("bpmnElement")
            scope = scope_by_id.get(owner or "")
            if scope is None and collab is not None and owner == collab.get("id"):
                scope = next((candidate for candidate in scopes
                              if candidate.parent is None), None)
            self.check(scope is not None,
                       f"BPMNPlane {plane.get('id')} bpmnElement={owner} "
                       "does not resolve")
            if scope is not None:
                by_scope[scope.id].append(plane)

        for scope in scopes:
            scope_planes = by_scope[scope.id]
            expanded_child = False
            if scope.parent is not None:
                parent_planes = by_scope.get(scope.parent.id, [])
                expanded_child = (
                    not parent_planes
                    or self._expanded(scope, parent_planes[0])
                )
            expected_planes = 0 if expanded_child else 1
            self.check(len(scope_planes) == expected_planes,
                       f"scope {scope.id} has {len(scope_planes)} BPMNPlane(s), "
                       f"expected exactly {expected_planes}")
            for plane in scope_planes:
                self._check_plane(
                    plane, scope, scopes, participants, msg_flows, collab,
                )
        self._check_subprocess_planes(scopes, by_scope)

    def _expanded(self, subprocess: ScopeInfo, parent_plane: ET.Element) -> bool:
        shape = next((child for child in parent_plane
                      if local(child.tag) == "BPMNShape"
                      and child.get("bpmnElement") == subprocess.id), None)
        return shape is None or shape.get("isExpanded") != "false"

    def _visible_scope_items(self, scope: ScopeInfo, plane: ET.Element):
        items = _direct_scope_items(scope)
        visible_nodes = set(items.nodes)
        visible_flows = {flow.get("id") for flow in items.flows if flow.get("id")}
        visible_annotations = set(items.annotations)
        visible_associations = {association.get("id")
                                for association in items.associations
                                if association.get("id")}
        for child in scope.element:
            if local(child.tag) != "subProcess":
                continue
            child_scope = ScopeInfo(child, scope.process, scope)
            if self._expanded(child_scope, plane):
                nested = self._visible_scope_items(child_scope, plane)
                visible_nodes.update(nested[0])
                visible_flows.update(nested[1])
                visible_annotations.update(nested[2])
                visible_associations.update(nested[3])
        return (visible_nodes, visible_flows, visible_annotations,
                visible_associations)

    def _visible_lane_ids(self, scope: ScopeInfo, plane: ET.Element) -> set[str]:
        lane_set = next((child for child in scope.element
                         if local(child.tag) == "laneSet"), None)
        lane_ids = {lane.get("id") for lane in
                    (lane_set if lane_set is not None else [])
                    if lane.get("id")}
        for child in scope.element:
            if local(child.tag) != "subProcess":
                continue
            child_scope = ScopeInfo(child, scope.process, scope)
            if self._expanded(child_scope, plane):
                lane_ids.update(self._visible_lane_ids(child_scope, plane))
        return lane_ids

    def _check_plane(
        self,
        plane: ET.Element,
        scope: ScopeInfo,
        scopes: list[ScopeInfo],
        participants: dict[str, ET.Element],
        msg_flows: list[ET.Element],
        collab: ET.Element | None,
    ) -> None:
        nodes, flows, annotations, associations = self._visible_scope_items(scope, plane)
        lane_ids = self._visible_lane_ids(scope, plane)
        is_collaboration_plane = collab is not None and plane.get("bpmnElement") == collab.get("id")
        need_shape = set(nodes) | annotations | lane_ids
        if is_collaboration_plane:
            need_shape |= set(participants)
        need_edge = set(flows) | set(associations)
        if is_collaboration_plane:
            need_edge |= {flow.get("id") for flow in msg_flows if flow.get("id")}

        shaped = {child.get("bpmnElement") for child in plane
                  if local(child.tag) == "BPMNShape"}
        edged = {child.get("bpmnElement") for child in plane
                 if local(child.tag) == "BPMNEdge"}
        missing_shapes = sorted(need_shape - shaped)
        missing_edges = sorted(need_edge - edged)
        self.check(not missing_shapes, f"missing BPMNShape: {missing_shapes}")
        self.check(not missing_edges, f"missing BPMNEdge: {missing_edges}")

        known = need_shape | need_edge
        orphan_shapes = sorted(shaped - known)
        orphan_edges = sorted(edged - known)
        self.check(not orphan_shapes,
                   f"BPMNShape for unknown element: {orphan_shapes}")
        self.check(not orphan_edges,
                   f"BPMNEdge for unknown element: {orphan_edges}")

        for child in plane:
            kind = local(child.tag)
            if kind == "BPMNShape":
                bounds = _bounds(child)
                self.check(bounds is not None and bounds[2] > 0 and bounds[3] > 0,
                           f"shape {child.get('bpmnElement')} has no positive bounds")
            elif kind == "BPMNEdge":
                waypoints = [
                    (float(point.get("x")), float(point.get("y")))
                    for point in child if local(point.tag) == "waypoint"
                ]
                self.check(len(waypoints) >= 2,
                           f"edge {child.get('bpmnElement')} has "
                           f"{len(waypoints)} waypoints, needs at least 2")

        boxes: dict[str, Bounds] = {}
        labels: dict[str, Bounds] = {}
        edges: dict[str, list[tuple[float, float]]] = {}
        drawn = set(nodes) | annotations
        for child in plane:
            ref = child.get("bpmnElement")
            if local(child.tag) == "BPMNShape" and ref in drawn:
                bounds = _bounds(child)
                if bounds is not None:
                    boxes[ref] = bounds
            label = child.find(f"{BPMNDI}BPMNLabel/{DC}Bounds")
            if label is not None and ref:
                bounds = _bounds(label)
                if bounds is not None:
                    labels[ref + " label"] = bounds
            if local(child.tag) == "BPMNEdge" and ref:
                edges[ref] = [
                    (float(point.get("x")), float(point.get("y")))
                    for point in child if local(point.tag) == "waypoint"
                ]
        report = check_geometry(boxes, labels, edges)
        self.checks += report.checks
        self.errors.extend(format_finding(finding) for finding in report.findings)

    def _check_subprocess_planes(
        self,
        scopes: list[ScopeInfo],
        by_scope: dict[str, list[ET.Element]],
    ) -> None:
        for scope in scopes:
            for child in scope.element:
                if local(child.tag) != "subProcess" or not child.get("id"):
                    continue
                child_scope = next(candidate for candidate in scopes
                                   if candidate.element is child)
                parent_planes = by_scope.get(scope.id, [])
                parent_plane = parent_planes[0] if parent_planes else None
                expanded = parent_plane is None or self._expanded(child_scope, parent_plane)
                child_planes = by_scope.get(child_scope.id, [])
                if expanded:
                    self.check(not child_planes,
                               f"expanded subprocess {child_scope.id} must not "
                               "have a child BPMNPlane")
                else:
                    self.check(len(child_planes) == 1,
                               f"collapsed subprocess {child_scope.id} must "
                               "have exactly one child BPMNPlane")

    def check_process_ref(
        self,
        collab: ET.Element | None,
        process: ET.Element,
    ) -> None:
        process_id = process.get("id")
        if process_id in self.called_process_ids:
            return
        refs = [participant.get("processRef") for participant in
                (collab if collab is not None else [])
                if local(participant.tag) == "participant"
                and participant.get("processRef")]
        self.check(process_id in refs, "no participant references the process")

    def report(self) -> bool:
        if self.errors:
            logger.info(f"\nFAILED with {len(self.errors)} error(s):")
            for error in self.errors:
                logger.info(f"  - {error}")
            return False
        logger.info("all checks passed")
        return True


def validate_bundle(paths: list[Path]) -> bool:
    """Validate all documents together so cross-file calls can resolve."""

    process_ids: set[str] = set()
    called_ids: set[str] = set()
    for path in paths:
        root = ET.parse(path).getroot()
        process_ids.update(
            element.get("id") for element in root
            if local(element.tag) == "process" and element.get("id")
        )
        called_ids.update(
            element.get("calledElement") for element in root.iter()
            if local(element.tag) == "callActivity"
            and element.get("calledElement")
        )

    valid = True
    for path in paths:
        validator = Validator(
            path,
            bundle_process_ids=process_ids,
            called_process_ids=called_ids,
        )
        valid = validator.run() and valid
    return valid


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        logger.info("usage: validate_bpmn.py <file.bpmn> [<file.bpmn> ...]")
        return 2
    paths = [Path(arg) for arg in args]
    missing = [path for path in paths if not path.exists()]
    if missing:
        for path in missing:
            logger.info(f"no such file: {path}")
        return 2
    return 0 if validate_bundle(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
