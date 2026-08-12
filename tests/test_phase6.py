"""Phase 6 migration and decomposition regression coverage."""

from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import bpmn_engine as engine
import ir_to_bpmn
from decomposition import decompose_model
from ir import load_ir
from project_paths import EXAMPLE_BPMN_DIR, EXAMPLE_IR_DIR
from validate_bpmn import Validator


ROOT = EXAMPLE_IR_DIR
IR_FILES = (ROOT / "OFC-001.ir.json", ROOT / "OFC-004.ir.json")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def element_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def bpmn_semantics(path: Path) -> dict[str, object]:
    """Extract semantic BPMN content while deliberately ignoring DI."""

    root = ET.parse(path).getroot()
    processes = [element for element in root if local(element.tag) == "process"]
    flow_node_tags = {
        "task", "exclusiveGateway", "parallelGateway", "startEvent",
        "intermediateCatchEvent", "endEvent", "subProcess", "callActivity",
        "throwEvent",
    }
    nodes: dict[str, tuple[object, ...]] = {}
    lanes: dict[str, str] = {}
    annotations: dict[str, str] = {}
    associations: dict[str, str] = {}
    edges: set[tuple[object, ...]] = set()

    for process in processes:
        for element in process:
            tag = local(element.tag)
            if tag in flow_node_tags:
                docs = tuple(
                    element_text(child)
                    for child in element
                    if local(child.tag) == "documentation"
                )
                nodes[element.get("id", "")] = (
                    tag, element.get("name", ""), docs,
                )
            elif tag == "sequenceFlow":
                condition = tuple(
                    element_text(child)
                    for child in element
                    if local(child.tag) == "conditionExpression"
                )
                edges.add((
                    element.get("sourceRef"), element.get("targetRef"),
                    element.get("name", ""), condition,
                ))
            elif tag == "textAnnotation":
                text = next(
                    (child for child in element if local(child.tag) == "text"),
                    None,
                )
                annotations[element.get("id", "")] = element_text(text) if text is not None else ""
            elif tag == "association":
                associations[element.get("sourceRef", "")] = element.get("targetRef", "")
        for lane in process.iter():
            if local(lane.tag) != "lane":
                continue
            for reference in lane:
                if local(reference.tag) == "flowNodeRef":
                    lanes[reference.text or ""] = lane.get("id", "")

    node_semantics = {
        node_id: value + (lanes.get(node_id, ""),)
        for node_id, value in nodes.items()
    }
    annotation_semantics = {
        source: annotations.get(target, "")
        for source, target in associations.items()
    }
    participants = {
        (element.get("id", ""), element.get("name", ""))
        for element in root.iter()
        if local(element.tag) == "participant"
    }
    message_flows = {
        (
            element.get("sourceRef", ""), element.get("targetRef", ""),
            element.get("name", ""),
        )
        for element in root.iter()
        if local(element.tag) == "messageFlow"
    }
    return {
        "nodes": node_semantics,
        "edges": edges,
        "annotations": annotation_semantics,
        "participants": participants,
        "message_flows": message_flows,
    }


class MigrationTests(unittest.TestCase):
    def test_ir_artifacts_are_valid_and_match_legacy_bpmn_semantics(self) -> None:
        for ir_path in IR_FILES:
            model = load_ir(ir_path)
            self.assertGreater(len(model.nodes), 0)
            self.assertGreater(len(model.edges), 0)

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            emitted = ir_to_bpmn.run(IR_FILES, output_dir=output_dir)
            self.assertEqual(
                {"OFC-001.bpmn", "OFC-004.bpmn"},
                {path.name for path in emitted},
            )
            for ir_path in IR_FILES:
                generated = output_dir / ir_path.name.replace(".ir.json", ".bpmn")
                legacy = EXAMPLE_BPMN_DIR / generated.name
                self.assertTrue(Validator(generated).run())
                self.assertEqual(
                    bpmn_semantics(legacy), bpmn_semantics(generated),
                    generated.name,
                )

    def test_ir_loop_metadata_is_preserved(self) -> None:
        expected = {
            "OFC-001.ir.json": {
                ("Gateway_CustodyDocsComplete", "Task_OfficerSignsAndCopies"),
                ("Gateway_BeaconVerified", "Task_ObserveSmartEntry"),
            },
            "OFC-004.ir.json": {
                ("Task_PeriodicFollowUp", "Task_ReviewTAFormWithConsumer"),
                ("Task_CommunicateChangeToFloorStaff", "Gateway_PostAdmissionChange"),
            },
        }
        for ir_path in IR_FILES:
            model = load_ir(ir_path)
            actual = {
                (edge.source, edge.target)
                for edge in model.edges
                if edge.loop
            }
            self.assertEqual(expected[ir_path.name], actual)

    def test_ofc001_decomposition_is_valid_deterministic_and_scope_local(self) -> None:
        model = load_ir(ROOT / "OFC-001.ir.json")
        requested = tuple(phase_id for phase_id, _ in model.phases)
        configured = replace(
            model,
            decomposition=replace(
                model.decomposition,
                mode="auto",
                collapse_phases=requested,
            ),
        )
        decomposed = decompose_model(configured)
        subprocesses = [
            node.id for node in decomposed.nodes if node.kind == "subprocess"
        ]
        self.assertEqual(
            [f"SubProcess_P{index}" for index in range(1, 11)], subprocesses,
        )
        self.assertIsNone(decomposed.by_id()["Event_DayOfAdmission"].parent)
        self.assertIsNone(decomposed.by_id()["EndEvent_Complete"].parent)

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for directory in (Path(first), Path(second)):
                scope = engine.Scope.top_level(decomposed)
                layout = engine.compute_layout(decomposed, scope)
                engine.write_bpmn(
                    directory / "OFC-001-decomposed.bpmn",
                    decomposed,
                    layout,
                    scope,
                )
            first_path = Path(first) / "OFC-001-decomposed.bpmn"
            second_path = Path(second) / "OFC-001-decomposed.bpmn"
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertTrue(Validator(first_path).run())
            root = ET.parse(first_path).getroot()
            self.assertEqual(11, sum(1 for e in root.iter() if local(e.tag) == "BPMNPlane"))

    def test_migrated_output_can_be_loaded_by_preview_renderer(self) -> None:
        import build_preview
        import ofc001_model

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            ir_to_bpmn.run([ROOT / "OFC-001.ir.json"], output_dir=output_dir)
            xml = (output_dir / "OFC-001.bpmn").read_text(encoding="utf-8")
            bundle = build_preview.PreviewBundle((
                build_preview.PreviewDocument(
                    id="ofc001-migrated",
                    filename="OFC-001.bpmn",
                    model=ofc001_model.MODEL,
                    xml=xml,
                ),
            ))
            html = build_preview.build(bundle)
            self.assertIn("OFC-001.bpmn", html)
            self.assertIn("bjs-breadcrumbs", html)


if __name__ == "__main__":
    unittest.main()
