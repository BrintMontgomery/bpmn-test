from __future__ import annotations

import xml.etree.ElementTree as ET
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import bpmn_engine as engine
from decomposition import decompose_model, scopes_for
from ir import IRValidationError, load_bundle, load_ir, validate_ir
from validate_bpmn import Validator, validate_bundle


BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"


def model(config: engine.DecompositionConfig | None = None) -> engine.ProcessModel:
    return engine.ProcessModel(
        lanes=[("Lane_A", "Actor A"), ("Lane_B", "Actor B")],
        phases=[("P0", "Trigger"), ("P1", "Detailed work"), ("P2", "Finish")],
        nodes=[
            engine.Node("Start", "start_message", "Lane_A", "Start", "P0"),
            engine.Node("Work_A", "task", "Lane_A", "Work A", "P1"),
            engine.Node("Work_B", "task", "Lane_B", "Work B", "P1"),
            engine.Node("End", "end", "Lane_A", "End", "P2"),
        ],
        edges=[
            engine.Edge("Start", "Work_A"),
            engine.Edge("Work_A", "Work_B"),
            engine.Edge("Work_B", "End"),
        ],
        process_id="Process_Decomp",
        participant_name="Decomposition Test",
        process_doc="",
        process_name="Decomposition Test",
        participant_id="Participant_Decomp",
        collaboration_id="Collaboration_Decomp",
        definitions_id="Definitions_Decomp",
        exporter="test_decomposition.py",
        decomposition=config or engine.DecompositionConfig(),
    )


class DecompositionTests(unittest.TestCase):
    def test_phase_boundary_rewrite_and_child_plane_validate(self) -> None:
        decomposed = decompose_model(model(engine.DecompositionConfig(
            mode="auto", collapse_phases=("P1",),
        )))
        subprocess = next(node for node in decomposed.nodes
                          if node.kind == "subprocess")
        children = [node for node in decomposed.nodes
                    if node.parent == subprocess.id]
        self.assertEqual("Lane_A", subprocess.lane)
        self.assertEqual(4, len(children))
        self.assertIn(
            ("Start", subprocess.id),
            [(edge.source, edge.target) for edge in decomposed.edges],
        )
        self.assertIn(
            (subprocess.id, "End"),
            [(edge.source, edge.target) for edge in decomposed.edges],
        )

        scopes = scopes_for(decomposed)
        layouts = {scope.id: engine.compute_layout(decomposed, scope)
                   for scope in scopes}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "decomposed.bpmn"
            engine.write_bpmn(
                path, decomposed, layouts[scopes[0].id], scopes[0], layouts=layouts
            )
            root = ET.parse(path).getroot()
            planes = root.findall(f"{BPMNDI}BPMNDiagram/{BPMNDI}BPMNPlane")
            self.assertEqual(2, len(planes))
            shape = root.find(
                f"{BPMNDI}BPMNDiagram/{BPMNDI}BPMNPlane/"
                f"{BPMNDI}BPMNShape[@bpmnElement='{subprocess.id}']"
            )
            self.assertEqual("false", shape.get("isExpanded"))
            self.assertTrue(Validator(path).run())

    def test_auto_policy_is_deterministic_and_lane_fallback_is_safe(self) -> None:
        config = engine.DecompositionConfig(
            mode="auto", max_nodes_per_plane=3, max_columns=99,
            max_pool_width=99999,
        )
        first = decompose_model(model(config))
        second = decompose_model(model(config))
        self.assertEqual(first.nodes, second.nodes)
        self.assertEqual(first.edges, second.edges)

        no_split = decompose_model(model(engine.DecompositionConfig(
            mode="auto", collapse_phases=("P1",), max_lanes_per_collapsed_phase=1,
        )))
        self.assertFalse(any(node.kind == "subprocess" for node in no_split.nodes))

    def test_call_activity_bundle_and_cross_document_resolution(self) -> None:
        main = model()
        main.nodes[1] = engine.Node(
            "Call", "call_activity", "Lane_A", "Reusable work", "P1",
            called_element="Process_Global",
        )
        main.nodes = [
            main.nodes[0], main.nodes[1],
            engine.Node("End_Work", "end", "Lane_A", "End work", "P2"),
        ]
        main.edges = [engine.Edge("Start", "Call"), engine.Edge("Call", "End_Work")]
        global_model = model()
        global_model.process_id = "Process_Global"
        global_model.participant_id = "Participant_Global"
        global_model.collaboration_id = "Collaboration_Global"
        global_model.definitions_id = "Definitions_Global"
        global_model.process_name = "Global work"
        main.documents = (
            engine.DocumentSpec("Process_Decomp", "main.bpmn", "main"),
            engine.DocumentSpec("Process_Global", "global.bpmn", "global"),
        )
        bundle = engine.ProcessBundle([main, global_model], main.documents)
        with TemporaryDirectory() as directory:
            paths = engine.write_bundle(Path(directory), bundle)
            self.assertEqual(["main.bpmn", "global.bpmn"],
                             [path.name for path in paths])
            self.assertTrue(validate_bundle(paths))

    def test_link_events_emit_named_definitions_and_mermaid(self) -> None:
        linked = model()
        linked.nodes = [
            engine.Node("Start", "start_message", "Lane_A", "Start", "P0"),
            engine.Node("Throw", "link_throw", "Lane_A", "Continue", "P1", link_name="Continue"),
            engine.Node("Catch", "link_catch", "Lane_B", "Continue", "P1", link_name="Continue"),
            engine.Node("End", "end", "Lane_A", "End", "P2"),
        ]
        linked.edges = [
            engine.Edge("Start", "Throw"), engine.Edge("Catch", "End")
        ]
        scope = engine.Scope.top_level(linked)
        layout = engine.compute_layout(linked, scope)
        definitions = engine.build_xml(linked, layout, scope)
        self.assertIsNotNone(definitions.find(
            f".//{BPMN}linkEventDefinition[@name='Continue']"
        ))
        self.assertIn("Throw", engine.build_mermaid(linked, scope))

    def test_ir_contract_loads_decomposition_and_documents(self) -> None:
        document = {
            "schema_version": 1,
            "process_id": "Process_IR3b",
            "participant_name": "IR 3b",
            "process_doc": "",
            "lanes": [{"id": "A", "name": "A"}],
            "phases": [{"id": "P0", "name": "P0"}],
            "nodes": [{
                "id": "Start", "kind": "start_message", "lane": "A",
                "phase": "P0", "name": "Start", "parent": None,
            }],
            "edges": [],
            "documents": [{"id": "Process_IR3b", "file": "main.bpmn"}],
            "decomposition": {"mode": "auto", "collapse_phases": ["P0"]},
        }
        loaded = load_ir(document)
        self.assertEqual("auto", loaded.decomposition.mode)
        self.assertEqual("main.bpmn", loaded.documents[0].file)
        self.assertEqual(1, len(load_bundle([document]).models))

    def test_ir_accepts_new_node_kinds_and_rejects_misplaced_metadata(self) -> None:
        for kind, extra in (
            ("subprocess", {"collapsed": True}),
            ("call_activity", {"called_element": "Process_IR3b"}),
            ("link_throw", {"link_name": "Continue"}),
            ("link_catch", {"link_name": "Continue"}),
        ):
            candidate = {
                "schema_version": 1,
                "process_id": "Process_IR3b",
                "participant_name": "IR 3b",
                "process_doc": "",
                "lanes": [{"id": "A", "name": "A"}],
                "phases": [{"id": "P0", "name": "P0"}],
                "nodes": [{
                    "id": "Node", "kind": kind, "lane": "A",
                    "phase": "P0", "name": "Node", "parent": None,
                    **extra,
                }],
                "edges": [],
                "documents": [{"id": "Process_IR3b", "file": "main.bpmn"}],
            }
            validate_ir(candidate)

        invalid = {
            "schema_version": 1,
            "process_id": "Process_IR3b",
            "participant_name": "IR 3b",
            "process_doc": "",
            "lanes": [{"id": "A", "name": "A"}],
            "phases": [{"id": "P0", "name": "P0"}],
            "nodes": [{
                "id": "Node", "kind": "task", "lane": "A",
                "phase": "P0", "name": "Node", "collapsed": True,
            }],
            "edges": [],
        }
        with self.assertRaisesRegex(IRValidationError, "only valid for subprocess"):
            validate_ir(invalid)


if __name__ == "__main__":
    unittest.main()
