from __future__ import annotations

import contextlib
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from geometry import GeometryFinding, check_geometry, format_finding, strip_label_suffix
from validate_bpmn import BpmnParseError, Validator, main, validate_bundle

BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"
DC = "{http://www.omg.org/spec/DD/20100524/DC}"
DI = "{http://www.omg.org/spec/DD/20100524/DI}"


def q(namespace: str, tag: str) -> str:
    return namespace + tag


def shape(plane: ET.Element, element_id: str, x: float, y: float,
          width: float = 80, height: float = 40, expanded: str | None = None) -> None:
    attrs = {"id": f"Shape_{element_id}", "bpmnElement": element_id}
    if expanded is not None:
        attrs["isExpanded"] = expanded
    item = ET.SubElement(plane, q(BPMNDI, "BPMNShape"), attrs)
    ET.SubElement(item, q(DC, "Bounds"), {
        "x": str(x), "y": str(y), "width": str(width), "height": str(height),
    })


def edge(plane: ET.Element, element_id: str, *points: tuple[float, float]) -> None:
    item = ET.SubElement(plane, q(BPMNDI, "BPMNEdge"), {
        "id": f"Edge_{element_id}", "bpmnElement": element_id,
    })
    for x, y in points:
        ET.SubElement(item, q(DI, "waypoint"), {"x": str(x), "y": str(y)})


def flow(process: ET.Element, flow_id: str, source: str, target: str) -> None:
    ET.SubElement(process, q(BPMN, "sequenceFlow"), {
        "id": flow_id, "sourceRef": source, "targetRef": target,
    })
    for node in process:
        if node.get("id") == source:
            ET.SubElement(node, q(BPMN, "outgoing")).text = flow_id
        if node.get("id") == target:
            ET.SubElement(node, q(BPMN, "incoming")).text = flow_id


def node(process: ET.Element, tag: str, node_id: str, **attrs) -> ET.Element:
    attrs = {"id": node_id, "name": node_id, **attrs}
    return ET.SubElement(process, q(BPMN, tag), attrs)


def lane_set(process: ET.Element, lane_id: str, node_ids: list[str]) -> None:
    lanes = ET.SubElement(process, q(BPMN, "laneSet"), {"id": f"LaneSet_{lane_id}"})
    lane = ET.SubElement(lanes, q(BPMN, "lane"), {"id": lane_id, "name": lane_id})
    for node_id in node_ids:
        ET.SubElement(lane, q(BPMN, "flowNodeRef")).text = node_id


def simple_document(
    process_id: str = "Process_Main",
    *,
    include_collaboration: bool = True,
    include_lane_set: bool = True,
    call_target: str | None = None,
) -> ET.Element:
    definitions = ET.Element(q(BPMN, "definitions"), {"id": "Definitions"})
    process = ET.SubElement(definitions, q(BPMN, "process"), {"id": process_id})
    start = node(process, "startEvent", "Start")
    if call_target is None:
        middle = node(process, "task", "Task")
    else:
        middle = node(process, "callActivity", "Call", calledElement=call_target)
    end = node(process, "endEvent", "End")
    flow(process, "Flow_Start_Task", start.get("id"), middle.get("id"))
    flow(process, "Flow_Task_End", middle.get("id"), end.get("id"))
    if include_lane_set:
        lane_set(process, "Lane_Main", ["Start", middle.get("id"), "End"])

    collab = None
    if include_collaboration:
        collab = ET.SubElement(definitions, q(BPMN, "collaboration"), {"id": "Collab"})
        ET.SubElement(collab, q(BPMN, "participant"), {
            "id": "Participant_Main", "processRef": process_id,
        })

    diagram = ET.SubElement(definitions, q(BPMNDI, "BPMNDiagram"), {"id": "Diagram"})
    plane_owner = collab.get("id") if collab is not None else process_id
    plane = ET.SubElement(diagram, q(BPMNDI, "BPMNPlane"), {
        "id": "Plane", "bpmnElement": plane_owner,
    })
    if include_collaboration:
        shape(plane, "Participant_Main", 0, 0, 500, 300)
    if include_lane_set:
        shape(plane, "Lane_Main", 20, 20, 470, 260)
    shape(plane, "Start", 60, 100, 36, 36)
    shape(plane, middle.get("id"), 220, 80, 100, 80)
    shape(plane, "End", 420, 100, 36, 36)
    edge(plane, "Flow_Start_Task", (96, 118), (220, 120))
    edge(plane, "Flow_Task_End", (320, 120), (420, 118))
    return definitions


def add_nested_subprocess(collapsed: bool) -> ET.Element:
    definitions = simple_document()
    process = definitions.find(q(BPMN, "process"))
    assert process is not None
    subprocess = node(process, "subProcess", "SubProcess")
    # Replace the simple task with the subprocess in the existing flow refs.
    for element in process.iter():
        if element.get("sourceRef") == "Task":
            element.set("sourceRef", "SubProcess")
        if element.get("targetRef") == "Task":
            element.set("targetRef", "SubProcess")
        if element.text == "Task":
            element.text = "SubProcess"
    for ref in process.iter(q(BPMN, "flowNodeRef")):
        if ref.text == "Task":
            ref.text = "SubProcess"
    task = next(element for element in list(process) if element.get("id") == "Task")
    process.remove(task)
    for top_flow in process:
        if top_flow.get("sourceRef") == "SubProcess":
            ET.SubElement(subprocess, q(BPMN, "outgoing")).text = top_flow.get("id")
        if top_flow.get("targetRef") == "SubProcess":
            ET.SubElement(subprocess, q(BPMN, "incoming")).text = top_flow.get("id")

    start = node(subprocess, "startEvent", "Child_Start")
    child_task = node(subprocess, "task", "Child_Task")
    end = node(subprocess, "endEvent", "Child_End")
    flow(subprocess, "Child_Flow_1", "Child_Start", "Child_Task")
    flow(subprocess, "Child_Flow_2", "Child_Task", "Child_End")
    lane_set(subprocess, "Lane_Child", ["Child_Start", "Child_Task", "Child_End"])

    diagram = definitions.find(q(BPMNDI, "BPMNDiagram"))
    assert diagram is not None
    parent_plane = diagram.find(q(BPMNDI, "BPMNPlane"))
    assert parent_plane is not None
    shape(parent_plane, "SubProcess", 220, 80, 100, 80,
          expanded="false" if collapsed else "true")
    # The original simple fixture has the Task shape and edge; remove them.
    for child in list(parent_plane):
        if child.get("bpmnElement") in {"Task", "Shape_Task", "Flow_Start_Task", "Flow_Task_End"}:
            parent_plane.remove(child)
    edge(parent_plane, "Flow_Start_Task", (96, 118), (220, 120))
    edge(parent_plane, "Flow_Task_End", (320, 120), (420, 118))
    if collapsed:
        child_plane = ET.SubElement(diagram, q(BPMNDI, "BPMNPlane"), {
            "id": "Child_Plane", "bpmnElement": "SubProcess",
        })
        shape(child_plane, "Lane_Child", 20, 20, 470, 260)
        shape(child_plane, "Child_Start", 60, 100, 36, 36)
        shape(child_plane, "Child_Task", 220, 80, 100, 80)
        shape(child_plane, "Child_End", 420, 100, 36, 36)
        edge(child_plane, "Child_Flow_1", (96, 118), (220, 120))
        edge(child_plane, "Child_Flow_2", (320, 120), (420, 118))
    else:
        shape(parent_plane, "Lane_Child", 20, 320, 470, 260)
        shape(parent_plane, "Child_Start", 60, 400, 36, 36)
        shape(parent_plane, "Child_Task", 220, 380, 100, 80)
        shape(parent_plane, "Child_End", 420, 400, 36, 36)
        edge(parent_plane, "Child_Flow_1", (96, 418), (220, 420))
        edge(parent_plane, "Child_Flow_2", (320, 420), (420, 418))
    return definitions


class ValidatorTests(unittest.TestCase):
    def write(self, directory: str, name: str, definitions: ET.Element) -> Path:
        path = Path(directory) / name
        path.write_bytes(ET.tostring(definitions, encoding="utf-8"))
        return path

    def test_geometry_findings_are_structured_and_format_compatibly(self) -> None:
        report = check_geometry(
            {"A": (0, 0, 20, 20), "B": (10, 10, 20, 20)},
            {},
            {},
        )
        self.assertEqual(1, len(report.findings))
        finding = report.findings[0]
        self.assertIsInstance(finding, GeometryFinding)
        self.assertEqual((0, 0, 20, 20), finding.first_bounds)
        self.assertEqual("shapes A and B overlap", format_finding(finding))

    def test_collapsed_and_expanded_subprocess_scopes_validate(self) -> None:
        with TemporaryDirectory() as directory:
            for collapsed in (True, False):
                path = self.write(directory, f"subprocess-{collapsed}.bpmn",
                                  add_nested_subprocess(collapsed))
                validator = Validator(path)
                self.assertTrue(validator.run())

    def test_link_events_pair_and_participate_in_reachability(self) -> None:
        definitions = simple_document()
        process = definitions.find(q(BPMN, "process"))
        assert process is not None
        task = process.find(q(BPMN, "task"))
        assert task is not None
        process.remove(task)
        throw = node(process, "intermediateThrowEvent", "Link_Throw")
        catch = node(process, "intermediateCatchEvent", "Link_Catch")
        for event in (throw, catch):
            definition = ET.SubElement(event, q(BPMN, "linkEventDefinition"),
                                       {"name": "Continue"})
        ET.SubElement(throw, q(BPMN, "incoming")).text = "Flow_Start_Task"
        for element in process.iter():
            if element.get("targetRef") == "Task":
                element.set("targetRef", "Link_Throw")
            if element.text == "Task":
                element.text = "Link_Throw"
        old_flow = next(flow for flow in process
                        if flow.get("id") == "Flow_Task_End")
        process.remove(old_flow)
        end_incoming = process.find(f"{BPMN}endEvent/{BPMN}incoming")
        assert end_incoming is not None
        end_incoming.text = "Flow_Link_Catch_End"
        flow(process, "Flow_Link_Catch_End", "Link_Catch", "End")
        lane = process.find(f"{BPMN}laneSet/{BPMN}lane")
        assert lane is not None
        for ref in list(lane):
            if ref.text == "Task":
                ref.text = "Link_Throw"
        lane.append(ET.Element(q(BPMN, "flowNodeRef")))
        lane[-1].text = "Link_Catch"
        plane = definitions.find(f"{BPMNDI}BPMNDiagram/{BPMNDI}BPMNPlane")
        assert plane is not None
        for child in list(plane):
            if child.get("bpmnElement") in {"Task", "Flow_Task_End"}:
                plane.remove(child)
        shape(plane, "Link_Throw", 220, 80, 36, 36)
        shape(plane, "Link_Catch", 320, 80, 36, 36)
        edge(plane, "Flow_Link_Catch_End", (356, 98), (420, 118))
        with TemporaryDirectory() as directory:
            path = self.write(directory, "links.bpmn", definitions)
            self.assertTrue(Validator(path).run())

            catch_def = catch.find(q(BPMN, "linkEventDefinition"))
            assert catch_def is not None
            catch_def.set("name", "Other")
            path.write_bytes(ET.tostring(definitions, encoding="utf-8"))
            validator = Validator(path)
            self.assertFalse(validator.run())
            self.assertTrue(any("link Continue" in error for error in validator.errors))

    def test_bundle_resolves_called_process_and_allows_global_process_without_pool(self) -> None:
        with TemporaryDirectory() as directory:
            main_path = self.write(directory, "main.bpmn",
                                   simple_document(call_target="Process_Global"))
            global_path = self.write(directory, "global.bpmn", simple_document(
                "Process_Global", include_collaboration=False,
                include_lane_set=False,
            ))
            self.assertTrue(validate_bundle([main_path, global_path]))
            missing = self.write(directory, "missing.bpmn",
                                  simple_document(call_target="Process_Missing"))
            self.assertFalse(validate_bundle([missing]))

    def test_validator_rejects_malformed_xml(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.bpmn"
            path.write_text("<definitions>", encoding="utf-8")

            with self.assertRaises(BpmnParseError) as raised:
                Validator(path)

            self.assertIn(str(path), str(raised.exception))
            self.assertIsInstance(raised.exception.__cause__, ET.ParseError)

    def test_validate_bundle_rejects_malformed_xml(self) -> None:
        with TemporaryDirectory() as directory:
            valid_path = self.write(directory, "valid.bpmn", simple_document())
            malformed_path = Path(directory) / "malformed.bpmn"
            malformed_path.write_text("<definitions>", encoding="utf-8")

            with self.assertRaises(BpmnParseError) as raised:
                validate_bundle([valid_path, malformed_path])

            self.assertIn(str(malformed_path), str(raised.exception))
            self.assertIsInstance(raised.exception.__cause__, ET.ParseError)

    def test_scope_boundary_and_di_mismatch_are_rejected(self) -> None:
        definitions = add_nested_subprocess(True)
        process = definitions.find(q(BPMN, "process"))
        assert process is not None
        nested_flow = process.find(f"{BPMN}subProcess/{BPMN}sequenceFlow")
        assert nested_flow is not None
        nested_flow.set("sourceRef", "Start")
        with TemporaryDirectory() as directory:
            path = self.write(directory, "cross-scope.bpmn", definitions)
            validator = Validator(path)
            self.assertFalse(validator.run())
            self.assertTrue(any("crosses scope boundary" in error
                                for error in validator.errors))

            valid = add_nested_subprocess(True)
            diagram = valid.find(q(BPMNDI, "BPMNDiagram"))
            assert diagram is not None
            child_plane = next(plane for plane in diagram
                               if plane.get("bpmnElement") == "SubProcess")
            diagram.remove(child_plane)
            invalid_path = self.write(directory, "missing-plane.bpmn", valid)
            invalid = Validator(invalid_path)
            self.assertFalse(invalid.run())
            self.assertTrue(any("collapsed subprocess SubProcess" in error
                                for error in invalid.errors))

    def test_main_requires_paths(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main([])
        self.assertEqual(2, result)
        self.assertIn("usage:", output.getvalue())

    def test_main_reports_malformed_xml_cleanly(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.bpmn"
            path.write_text("<definitions>", encoding="utf-8")
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                result = main([str(path)])

            self.assertEqual(2, result)
            self.assertIn(str(path), output.getvalue())


class StripLabelSuffixTests(unittest.TestCase):
    def test_strips_the_label_suffix_when_present(self) -> None:
        self.assertEqual("Task_1", strip_label_suffix("Task_1 label"))

    def test_leaves_ids_without_a_label_suffix_unchanged(self) -> None:
        self.assertEqual("Task_1", strip_label_suffix("Task_1"))

    def test_only_strips_the_first_label_occurrence(self) -> None:
        self.assertEqual(
            "Flow_A__B", strip_label_suffix("Flow_A__B label")
        )


if __name__ == "__main__":
    unittest.main()
