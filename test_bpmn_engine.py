"""Unit and regression coverage for the shared BPMN engine."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from dataclasses import fields, replace
from pathlib import Path
from tempfile import TemporaryDirectory

import bpmn_engine as engine
from validate_bpmn import Validator


BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"


class EngineTests(unittest.TestCase):
    def make_model(self) -> engine.ProcessModel:
        lanes = [("Lane_A", "Actor A"), ("Lane_B", "Actor B")]
        nodes = [
            engine.Node(
                "Start_Custom", "start_message", "Lane_A",
                "Custom start", "P0", doc=["Start documentation."],
            ),
            engine.Node(
                "Gateway_Custom", "gateway_x", "Lane_A",
                "Continue?", "P0",
            ),
            engine.Node(
                "Task_Default", "task", "Lane_A",
                "Default task", "P0", ttype="user",
                note="A regression note.",
            ),
            engine.Node(
                "Task_Conditional", "task", "Lane_B",
                "Conditional task", "P0",
            ),
            engine.Node(
                "End_Custom", "end", "Lane_A",
                "Finished", "P0",
            ),
        ]
        edges = [
            engine.Edge("Start_Custom", "Gateway_Custom"),
            engine.Edge("Gateway_Custom", "Task_Default"),
            engine.Edge(
                "Gateway_Custom", "Task_Conditional", "Yes",
                "The condition is true",
            ),
            engine.Edge("Task_Default", "End_Custom"),
            engine.Edge("Task_Conditional", "End_Custom", loop=True),
        ]
        return engine.ProcessModel(
            lanes=lanes,
            phases=[("P0", "Trigger")],
            nodes=nodes,
            edges=edges,
            process_id="Process_Custom",
            participant_name="Custom Participant",
            process_doc="Custom process documentation.",
            process_name="Custom Process",
            participant_id="Participant_Custom",
            collaboration_id="Collaboration_Custom",
            definitions_id="Definitions_Custom",
            exporter="test_bpmn_engine.py",
            ann_above={"Lane_A"},
            lane_classes={"Lane_A": "a", "Lane_B": "b"},
            mermaid_class_defs=[
                "  classDef a fill:#ffffff,stroke:#000000,color:#000000;",
                "  classDef b fill:#eeeeee,stroke:#111111,color:#111111;",
            ],
            external_pools=[engine.ExternalPool(
                id="Participant_External",
                name="External Actor",
                anchor="Start_Custom",
                width=100,
                height=20,
                gap_above=10,
                mermaid_id="EXT",
            )],
            message_flows=[engine.MessageFlow(
                id="MessageFlow_Custom",
                source="Participant_External",
                target="Start_Custom",
                name="Custom message",
            )],
        )

    def build(self) -> tuple[engine.ProcessModel, engine.Scope, engine.Layout,
                               ET.Element]:
        model = self.make_model()
        scope = engine.Scope.top_level(model)
        layout = engine.compute_layout(model, scope)
        return model, scope, layout, engine.build_xml(model, layout, scope)

    def test_layout_and_routing_are_scope_and_model_driven(self) -> None:
        model, scope, layout, _ = self.build()

        self.assertIn("Start_Custom", layout.bounds)
        self.assertIn("Task_Default", layout.ann_bounds)
        self.assertLess(
            layout.ann_bounds["Task_Default"][1],
            layout.bounds["Task_Default"][1],
        )

        cross_lane = model.edges[2]
        points = engine.edge_waypoints(model, cross_lane, layout)
        self.assertEqual(4, len(points))
        self.assertEqual(
            (30, 18),
            engine.edge_label_bounds(model, cross_lane, points, layout)[2:],
        )

        loop = model.edges[-1]
        self.assertEqual(4, len(engine.edge_waypoints(model, loop, layout)))
        self.assertEqual(50, engine.annotation_height("short note"))
        self.assertEqual(scope.id, model.process_id)

    def test_auto_columns_subrows_and_loop_ignoring(self) -> None:
        model, _, layout, _ = self.build()
        placements = layout.placements

        self.assertEqual(0, placements["Start_Custom"].col)
        self.assertEqual(1, placements["Gateway_Custom"].col)
        self.assertEqual(2, placements["Task_Default"].col)
        self.assertEqual(2, placements["Task_Conditional"].col)
        self.assertEqual(3, placements["End_Custom"].col)
        self.assertEqual(0, placements["Task_Default"].subrow)
        self.assertEqual(1, placements["Task_Conditional"].subrow)
        self.assertEqual(0, placements["Task_Conditional"].col - 2)
        self.assertEqual(4, len(engine.edge_waypoints(model, model.edges[-1], layout)))

    def test_phase_order_allows_compact_same_column_and_rejects_backtracking(self) -> None:
        def graph_model(nodes, edges, phases):
            return replace(
                self.make_model(),
                nodes=nodes,
                edges=edges,
                phases=phases,
                external_pools=[],
                message_flows=[],
            )

        compact = graph_model(
            [
                engine.Node("Start", "start_message", "Lane_A", "Start", "P0"),
                engine.Node("Split", "gateway_p", "Lane_A", "Split", "P0"),
                engine.Node("Early", "task", "Lane_A", "Early", "P1"),
                engine.Node("Late", "task", "Lane_B", "Late", "P2"),
                engine.Node("End", "end", "Lane_A", "End", "P2"),
            ],
            [
                engine.Edge("Start", "Split"),
                engine.Edge("Split", "Early"),
                engine.Edge("Split", "Late"),
                engine.Edge("Early", "End"),
                engine.Edge("Late", "End"),
            ],
            [("P0", "Trigger"), ("P1", "Early"), ("P2", "Late")],
        )
        compact_layout = engine.compute_layout(
            compact, engine.Scope.top_level(compact)
        )
        self.assertEqual(
            compact_layout.placements["Early"].col,
            compact_layout.placements["Late"].col,
        )

        invalid = graph_model(
            [
                engine.Node("Start", "start_message", "Lane_A", "Start", "P0"),
                engine.Node("Late", "task", "Lane_A", "Late", "P2"),
                engine.Node("Early", "task", "Lane_A", "Early", "P1"),
                engine.Node("End", "end", "Lane_A", "End", "P2"),
            ],
            [
                engine.Edge("Start", "Late"),
                engine.Edge("Late", "Early"),
                engine.Edge("Early", "End"),
            ],
            [("P0", "Trigger"), ("P1", "Early"), ("P2", "Late")],
        )
        with self.assertRaisesRegex(engine.LayoutError, "later phase"):
            engine.compute_layout(invalid, engine.Scope.top_level(invalid))

    def test_scope_layout_restarts_from_scope_start(self) -> None:
        model = self.make_model()
        scope = engine.Scope(
            id="NestedScope",
            node_ids=("Start_Custom", "Gateway_Custom", "Task_Default", "End_Custom"),
            lane_ids=("Lane_A",),
            include_pool=False,
        )
        nested = engine.compute_layout(model, scope)
        self.assertEqual(0, nested.placements["Start_Custom"].col)
        self.assertEqual(1, nested.placements["Gateway_Custom"].col)
        self.assertEqual(2, nested.placements["Task_Default"].col)
        self.assertEqual(3, nested.placements["End_Custom"].col)
        self.assertIsNone(nested.pool)

    def test_layout_is_deterministic_and_geometry_clean(self) -> None:
        model, scope, first, _ = self.build()
        second = engine.compute_layout(model, scope)

        self.assertEqual(first.placements, second.placements)
        self.assertEqual(first.bounds, second.bounds)
        self.assertEqual([], engine.layout_findings(model, scope, first))
        self.assertEqual(
            ET.tostring(engine.build_xml(model, first, scope)),
            ET.tostring(engine.build_xml(model, second, scope)),
        )

    def test_unresolved_collision_is_reported(self) -> None:
        model = self.make_model()
        scope = engine.Scope.top_level(model)
        original_findings = engine.layout_findings
        engine.layout_findings = lambda *_args: [
            engine.GeometryFinding("test collision", "Task_Default", "Task_Conditional")
        ]
        try:
            with self.assertRaisesRegex(engine.LayoutError, "Task_Default"):
                engine.compute_layout(model, scope)
        finally:
            engine.layout_findings = original_findings

    def test_node_has_no_manual_coordinate_fields(self) -> None:
        names = {field.name for field in fields(engine.Node)}
        self.assertNotIn("col", names)
        self.assertNotIn("subrow", names)

    def test_nested_and_parallel_branches_get_stable_rows(self) -> None:
        import generate_bpmn_ofc004
        import ofc001_model

        ofc001_layout = engine.compute_layout(
            ofc001_model.MODEL,
            engine.Scope.top_level(ofc001_model.MODEL),
        )
        self.assertEqual(
            1, ofc001_layout.placements["Task_RecordBehavioralInfo"].subrow
        )
        self.assertEqual(
            2, ofc001_layout.placements["Task_AdjustPrecautions"].subrow
        )
        self.assertEqual(
            0, ofc001_layout.placements["Task_LiceTreatment"].subrow
        )
        self.assertEqual(
            0, ofc001_layout.placements["Task_RecordIntakeNeeds"].subrow
        )

        ofc004_layout = engine.compute_layout(
            generate_bpmn_ofc004.MODEL,
            engine.Scope.top_level(generate_bpmn_ofc004.MODEL),
        )
        self.assertGreater(
            ofc004_layout.placements["Task_InformConsumerDeclined"].subrow,
            ofc004_layout.placements["Task_InformFloorStaffNewContact"].subrow,
        )

    def test_current_processes_generate_valid_bpmn(self) -> None:
        import ofc001_model
        import generate_bpmn_ofc004

        with TemporaryDirectory() as temp_dir:
            for model, filename in (
                (ofc001_model.MODEL, "OFC-001.bpmn"),
                (generate_bpmn_ofc004.MODEL, "OFC-004.bpmn"),
            ):
                path = Path(temp_dir) / filename
                scope = engine.Scope.top_level(model)
                engine.write_bpmn(path, model, engine.compute_layout(model, scope), scope)
                self.assertTrue(Validator(path).run())

    def test_element_tags_and_xml_content(self) -> None:
        model, _, _, definitions = self.build()
        process = definitions.find(f"{BPMN}process")
        self.assertIsNotNone(process)
        assert process is not None

        self.assertEqual("Process_Custom", process.attrib["id"])
        self.assertIn("Custom process documentation.",
                      process.findtext(f"{BPMN}documentation"))

        gateway = process.find(f"{BPMN}exclusiveGateway")
        self.assertIsNotNone(gateway)
        assert gateway is not None
        self.assertEqual(
            "Flow_Gateway_Custom__Task_Default",
            gateway.attrib["default"],
        )

        self.assertEqual(
            "userTask",
            engine.element_tag(model.nodes[2]),
        )
        self.assertEqual("startEvent", engine.element_tag(model.nodes[0]))
        self.assertEqual("endEvent", engine.element_tag(model.nodes[4]))
        self.assertIsNotNone(process.find(f"{BPMN}textAnnotation"))
        self.assertIsNotNone(process.find(
            f"{BPMN}startEvent/{BPMN}messageEventDefinition"
        ))

    def test_external_pool_and_message_flow_are_first_class_inputs(self) -> None:
        _, _, _, definitions = self.build()
        collaboration = definitions.find(f"{BPMN}collaboration")
        self.assertIsNotNone(collaboration)
        assert collaboration is not None

        self.assertIsNotNone(collaboration.find(
            f"{BPMN}participant[@id='Participant_External']"
        ))
        self.assertIsNotNone(collaboration.find(
            f"{BPMN}messageFlow[@id='MessageFlow_Custom']"
        ))

        plane = definitions.find(f"{BPMNDI}BPMNDiagram/{BPMNDI}BPMNPlane")
        self.assertIsNotNone(plane)
        assert plane is not None
        self.assertIsNotNone(plane.find(
            f"{BPMNDI}BPMNShape[@bpmnElement='Participant_External']"
        ))
        self.assertIsNotNone(plane.find(
            f"{BPMNDI}BPMNEdge[@bpmnElement='MessageFlow_Custom']"
        ))

    def test_mermaid_uses_model_lanes_phases_and_external_flow(self) -> None:
        model, scope, _, _ = self.build()
        mermaid = engine.build_mermaid(model, scope)

        self.assertIn('subgraph P0["Trigger"]', mermaid)
        self.assertIn("EXT([External Actor]):::ext", mermaid)
        self.assertIn("EXT -. Custom message .-> Start_Custom", mermaid)
        self.assertIn(
            "class Start_Custom,Gateway_Custom,Task_Default,End_Custom a;",
            mermaid,
        )
        self.assertIn("classDef b fill:#eeeeee", mermaid)



class PreviewTests(unittest.TestCase):
    def test_preview_consumes_model_bundle_and_options(self) -> None:
        import build_preview
        import ofc001_model

        self.assertIs(build_preview.DEFAULT_MODEL, ofc001_model.MODEL)
        self.assertEqual(66, len(build_preview.DEFAULT_MODEL.nodes))
        self.assertEqual(5, len(build_preview.DEFAULT_MODEL.options))
        self.assertEqual(12, len(build_preview.phase_summary()))
        self.assertFalse(hasattr(build_preview, "OPTIONS"))

        html = build_preview.build()
        for option in ofc001_model.MODEL.options:
            self.assertIn(option.title, html)
            self.assertIn(option.gateway, html)
            self.assertIn(option.effect, html)

        self.assertIn("Security Intakes Consumer", html)
        self.assertIn("bjs-breadcrumbs", html)
        self.assertIn(".doc-viewer {", html)
        self.assertIn("click a collapsed subprocess to drill down", html)

    def test_preview_supports_multiple_documents_and_dynamic_downloads(self) -> None:
        import build_preview
        import ofc001_model

        xml = (build_preview.HERE / "OFC-001.bpmn").read_text(encoding="utf-8")
        bundle = build_preview.PreviewBundle((
            build_preview.PreviewDocument(
                id="main-process",
                filename="main-process.bpmn",
                model=ofc001_model.MODEL,
                xml=xml,
                label="Main process",
            ),
            build_preview.PreviewDocument(
                id="called-process",
                filename="called-process.bpmn",
                model=ofc001_model.MODEL,
                xml=xml,
                label="Called process",
            ),
        ))

        html = build_preview.build(bundle)

        self.assertIn('data-document-tab="main-process"', html)
        self.assertIn('data-document-tab="called-process"', html)
        self.assertIn('id="canvas-main-process"', html)
        self.assertIn('id="canvas-called-process"', html)
        self.assertIn('download="main-process.bpmn"', html)
        self.assertIn('called-process.bpmn', html)
        self.assertNotIn('download="OFC-001.bpmn"', html)
        self.assertIn("var documents =", html)
        self.assertIn("selectDocument", html)

    def test_preview_bundle_rejects_duplicate_or_unknown_documents(self) -> None:
        import build_preview
        import ofc001_model

        document = build_preview.PreviewDocument(
            id="same",
            filename="same.bpmn",
            model=ofc001_model.MODEL,
            xml="<xml />",
        )
        with self.assertRaises(ValueError):
            build_preview.PreviewBundle((document, document))
        with self.assertRaises(ValueError):
            build_preview.PreviewBundle((document,), primary_id="missing")


if __name__ == "__main__":
    unittest.main()
