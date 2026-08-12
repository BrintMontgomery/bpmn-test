"""Structural validation for a generated BPMN 2.0 file.

Checks referential integrity and the invariants a BPMN modeller will
complain about, without needing a BPMN toolchain installed.

    py validate_bpmn.py OFC-001.bpmn
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"

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


class Validator:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.root = ET.parse(path).getroot()
        self.errors: list[str] = []
        self.checks = 0

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def check(self, condition: bool, msg: str) -> None:
        self.checks += 1
        if not condition:
            self.fail(msg)

    # ------------------------------------------------------------------
    def run(self) -> bool:
        proc = self.root.find(f"{BPMN}process")
        collab = self.root.find(f"{BPMN}collaboration")
        if proc is None or collab is None:
            self.fail("missing bpmn:process or bpmn:collaboration")
            return self.report()

        nodes = {el.get("id"): el for el in proc
                 if local(el.tag) in FLOW_NODE_TAGS}
        flows = [el for el in proc if local(el.tag) == "sequenceFlow"]
        annotations = {el.get("id") for el in proc
                       if local(el.tag) == "textAnnotation"}
        associations = [el for el in proc if local(el.tag) == "association"]
        msg_flows = [el for el in collab if local(el.tag) == "messageFlow"]
        participants = {el.get("id"): el for el in collab
                        if local(el.tag) == "participant"}

        self.check_unique_ids()
        self.check_flow_refs(nodes, flows, participants, msg_flows,
                             annotations, associations)
        self.check_connectivity(nodes, flows)
        self.check_lanes(proc, nodes)
        self.check_gateways(nodes, flows)
        self.check_di(nodes, flows, annotations, associations, msg_flows,
                      participants, proc)
        self.check_geometry(nodes, annotations)
        self.check_process_ref(collab, proc)

        print(f"{self.path.name}: {len(nodes)} flow nodes, {len(flows)} "
              f"sequence flows, {len(annotations)} annotations, "
              f"{self.checks} assertions")
        return self.report()

    # ------------------------------------------------------------------
    def check_unique_ids(self) -> None:
        ids = [el.get("id") for el in self.root.iter() if el.get("id")]
        dupes = [i for i, c in Counter(ids).items() if c > 1]
        self.check(not dupes, f"duplicate ids: {dupes[:5]}")

    def check_flow_refs(self, nodes, flows, participants, msg_flows,
                        annotations, associations) -> None:
        for f in flows:
            for attr in ("sourceRef", "targetRef"):
                ref = f.get(attr)
                self.check(ref in nodes,
                           f"sequenceFlow {f.get('id')} {attr}={ref} "
                           f"does not resolve to a flow node")
        for mf in msg_flows:
            for attr in ("sourceRef", "targetRef"):
                ref = mf.get(attr)
                self.check(ref in nodes or ref in participants,
                           f"messageFlow {mf.get('id')} {attr}={ref} "
                           f"does not resolve")
        for a in associations:
            self.check(a.get("sourceRef") in nodes,
                       f"association {a.get('id')} sourceRef does not "
                       f"resolve to a flow node")
            self.check(a.get("targetRef") in annotations,
                       f"association {a.get('id')} targetRef does not "
                       f"resolve to a text annotation")

    def check_connectivity(self, nodes, flows) -> None:
        incoming = Counter(f.get("targetRef") for f in flows)
        outgoing = Counter(f.get("sourceRef") for f in flows)
        for nid, el in nodes.items():
            tag = local(el.tag)
            if tag != "startEvent":
                self.check(incoming[nid] > 0,
                           f"{tag} {nid} has no incoming sequence flow")
            else:
                self.check(incoming[nid] == 0,
                           f"startEvent {nid} must not have an incoming flow")
            if tag != "endEvent":
                self.check(outgoing[nid] > 0,
                           f"{tag} {nid} has no outgoing sequence flow")
            else:
                self.check(outgoing[nid] == 0,
                           f"endEvent {nid} must not have an outgoing flow")

            # The <incoming>/<outgoing> child references must match the flows.
            declared_in = {c.text for c in el if local(c.tag) == "incoming"}
            declared_out = {c.text for c in el if local(c.tag) == "outgoing"}
            actual_in = {f.get("id") for f in flows
                         if f.get("targetRef") == nid}
            actual_out = {f.get("id") for f in flows
                          if f.get("sourceRef") == nid}
            self.check(declared_in == actual_in,
                       f"{nid} <incoming> refs disagree with sequenceFlows")
            self.check(declared_out == actual_out,
                       f"{nid} <outgoing> refs disagree with sequenceFlows")

        # Every node must be reachable from the start event.
        starts = [n for n, el in nodes.items()
                  if local(el.tag) == "startEvent"]
        self.check(len(starts) == 1, f"expected exactly 1 start event, "
                                     f"found {len(starts)}")
        adjacency: dict[str, list[str]] = {n: [] for n in nodes}
        for f in flows:
            if f.get("sourceRef") in adjacency:
                adjacency[f.get("sourceRef")].append(f.get("targetRef"))
        seen, stack = set(starts), list(starts)
        while stack:
            cur = stack.pop()
            for nxt in adjacency.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        unreachable = sorted(set(nodes) - seen)
        self.check(not unreachable, f"unreachable nodes: {unreachable}")

    def check_lanes(self, proc, nodes) -> None:
        lane_set = proc.find(f"{BPMN}laneSet")
        self.check(lane_set is not None, "process has no laneSet")
        if lane_set is None:
            return
        assigned: Counter = Counter()
        for lane in lane_set:
            for ref in lane:
                if local(ref.tag) == "flowNodeRef":
                    self.check(ref.text in nodes,
                               f"lane {lane.get('id')} references unknown "
                               f"node {ref.text}")
                    assigned[ref.text] += 1
        for nid in nodes:
            self.check(assigned[nid] == 1,
                       f"{nid} appears in {assigned[nid]} lanes, expected 1")

    def check_gateways(self, nodes, flows) -> None:
        for nid, el in nodes.items():
            tag = local(el.tag)
            if tag not in GATEWAY_TAGS:
                continue
            outs = [f for f in flows if f.get("sourceRef") == nid]
            if len(outs) < 2:
                continue
            if tag != "exclusiveGateway":
                continue
            for f in outs:
                self.check(bool(f.get("name")),
                           f"branch {f.get('id')} out of {nid} has no label")
            default = el.get("default")
            self.check(default is not None,
                       f"exclusiveGateway {nid} splits without a default flow")
            self.check(default in {f.get("id") for f in outs},
                       f"exclusiveGateway {nid} default={default} is not one "
                       f"of its outgoing flows")
            for f in outs:
                has_cond = any(local(c.tag) == "conditionExpression"
                               for c in f)
                if f.get("id") == default:
                    self.check(not has_cond,
                               f"default flow {f.get('id')} must not carry a "
                               f"conditionExpression")
                else:
                    self.check(has_cond,
                               f"non-default branch {f.get('id')} out of "
                               f"{nid} has no conditionExpression")

    def check_di(self, nodes, flows, annotations, associations, msg_flows,
                 participants, proc) -> None:
        plane = self.root.find(f"{BPMNDI}BPMNDiagram/{BPMNDI}BPMNPlane")
        self.check(plane is not None, "no BPMNPlane")
        if plane is None:
            return
        shaped = {el.get("bpmnElement") for el in plane
                  if local(el.tag) == "BPMNShape"}
        edged = {el.get("bpmnElement") for el in plane
                 if local(el.tag) == "BPMNEdge"}

        lane_set = proc.find(f"{BPMN}laneSet")
        lane_ids = {lane.get("id") for lane in lane_set} if lane_set is not None else set()

        need_shape = set(nodes) | annotations | set(participants) | lane_ids
        need_edge = ({f.get("id") for f in flows}
                     | {a.get("id") for a in associations}
                     | {m.get("id") for m in msg_flows})

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

        for el in plane:
            if local(el.tag) == "BPMNShape":
                b = el.find(f"{{http://www.omg.org/spec/DD/20100524/DC}}Bounds")
                self.check(b is not None and float(b.get("width", 0)) > 0
                           and float(b.get("height", 0)) > 0,
                           f"shape {el.get('bpmnElement')} has no positive "
                           f"bounds")
            else:
                wps = [c for c in el if local(c.tag) == "waypoint"]
                self.check(len(wps) >= 2,
                           f"edge {el.get('bpmnElement')} has "
                           f"{len(wps)} waypoints, needs at least 2")

    def check_geometry(self, nodes, annotations) -> None:
        """No shape may overlap another, and no connector may run through
        a shape it is not attached to. A modeller will render either, but
        both make the diagram unreadable."""
        plane = self.root.find(f"{BPMNDI}BPMNDiagram/{BPMNDI}BPMNPlane")
        if plane is None:
            return
        dc = "{http://www.omg.org/spec/DD/20100524/DC}Bounds"
        drawn = set(nodes) | set(annotations)

        def bounds_of(el):
            b = el.find(dc)
            return (float(b.get("x")), float(b.get("y")),
                    float(b.get("width")), float(b.get("height")))

        boxes: dict[str, tuple[float, ...]] = {}
        labels: dict[str, tuple[float, ...]] = {}
        for el in plane:
            ref = el.get("bpmnElement")
            kind = local(el.tag)
            if kind == "BPMNShape" and ref in drawn:
                boxes[ref] = bounds_of(el)
            # An explicit label box is as much an obstacle as the shape.
            lbl = el.find(f"{BPMNDI}BPMNLabel/{dc}")
            if lbl is not None and ref:
                labels[ref + " label"] = (
                    float(lbl.get("x")), float(lbl.get("y")),
                    float(lbl.get("width")), float(lbl.get("height")))

        items = sorted(boxes.items())
        for i, (aid, a) in enumerate(items):
            for bid, b in items[i + 1:]:
                overlap = (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                           and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])
                self.check(not overlap, f"shapes {aid} and {bid} overlap")

        obstacles = dict(boxes)
        obstacles.update(labels)

        pad = 4.0
        for el in plane:
            if local(el.tag) != "BPMNEdge":
                continue
            ref = el.get("bpmnElement") or ""
            pts = [(float(w.get("x")), float(w.get("y")))
                   for w in el if local(w.tag) == "waypoint"]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                lo_x, hi_x = min(x1, x2), max(x1, x2)
                lo_y, hi_y = min(y1, y2), max(y1, y2)
                for nid, (bx, by, bw, bh) in obstacles.items():
                    if nid.split(" label")[0] in ref:
                        continue    # attached to this shape, or its own label
                    if (lo_x < bx + bw - pad and bx + pad < hi_x
                            and lo_y < by + bh - pad and by + pad < hi_y):
                        self.fail(f"edge {ref} passes through {nid}")
                    self.checks += 1

        # Labels must not land on a shape or on another label.
        for lid, (lx, ly, lw, lh) in sorted(labels.items()):
            owner = lid.split(" label")[0]
            for oid, (bx, by, bw, bh) in sorted(obstacles.items()):
                if oid == lid or oid.split(" label")[0] == owner:
                    continue
                self.checks += 1
                if (lx < bx + bw - pad and bx + pad < lx + lw
                        and ly < by + bh - pad and by + pad < ly + lh):
                    self.fail(f"{lid} overlaps {oid}")

    def check_process_ref(self, collab, proc) -> None:
        refs = [p.get("processRef") for p in collab
                if local(p.tag) == "participant" and p.get("processRef")]
        self.check(proc.get("id") in refs,
                   "no participant references the process")

    def report(self) -> bool:
        if self.errors:
            print(f"\nFAILED with {len(self.errors)} error(s):")
            for e in self.errors:
                print(f"  - {e}")
            return False
        print("all checks passed")
        return True


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "OFC-001.bpmn")
    if not path.exists():
        print(f"no such file: {path}")
        return 2
    return 0 if Validator(path).run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
