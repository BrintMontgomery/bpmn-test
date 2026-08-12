from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import bpmn_engine as engine
from ir import IR_SCHEMA_PATH, IRValidationError, load_ir, validate_ir
from validate_bpmn import Validator


class IRTests(unittest.TestCase):
    def document(self) -> dict:
        return {
            "schema_version": 1,
            "process_id": "Process_IRTest",
            "participant_name": "IR Test Process",
            "process_doc": "A process loaded from JSON.",
            "process_name": "IR Test",
            "lanes": [
                {"id": "Lane_A", "name": "Actor A", "ann_above": True},
                {"id": "Lane_B", "name": "Actor B"},
            ],
            "phases": [
                {"id": "P0", "name": "Trigger"},
                {"id": "P1", "name": "Work"},
            ],
            "nodes": [
                {
                    "id": "Start",
                    "kind": "start_message",
                    "lane": "Lane_A",
                    "phase": "P0",
                    "name": "Start",
                    "doc": ["Start documentation."],
                    "parent": None,
                },
                {
                    "id": "Gateway",
                    "kind": "gateway_x",
                    "lane": "Lane_A",
                    "phase": "P0",
                    "name": "Continue?",
                    "parent": None,
                },
                {
                    "id": "Default",
                    "kind": "task",
                    "lane": "Lane_A",
                    "phase": "P1",
                    "name": "Default task",
                    "ttype": "user",
                    "note": "A regression note.",
                    "parent": "Gateway",
                },
                {
                    "id": "Conditional",
                    "kind": "task",
                    "lane": "Lane_B",
                    "phase": "P1",
                    "name": "Conditional task",
                    "ttype": "manual",
                },
                {
                    "id": "End",
                    "kind": "end",
                    "lane": "Lane_A",
                    "phase": "P1",
                    "name": "Finished",
                },
            ],
            "edges": [
                {"source": "Start", "target": "Gateway"},
                {"source": "Gateway", "target": "Default", "label": "No"},
                {
                    "source": "Gateway",
                    "target": "Conditional",
                    "label": "Yes",
                    "condition": "The condition is true",
                },
                {"source": "Default", "target": "End"},
                {"source": "Conditional", "target": "End"},
            ],
            "external_pools": [
                {
                    "id": "Participant_External",
                    "name": "External Actor",
                    "anchor": "Start",
                    "width": 100,
                    "height": 20,
                    "gap_above": 10,
                    "mermaid_id": "EXT",
                }
            ],
            "message_flows": [
                {
                    "source": "Participant_External",
                    "target": "Start",
                    "name": "Start message",
                }
            ],
        }

    def assert_invalid(self, document: dict, message: str) -> None:
        with self.assertRaisesRegex(IRValidationError, message):
            validate_ir(document)

    def test_schema_is_versioned_and_matches_loader_contract(self) -> None:
        schema = json.loads(IR_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(1, schema["properties"]["schema_version"]["const"])
        non_task_kinds = schema["$defs"]["node"]["oneOf"][1]["properties"]["kind"]["enum"]
        self.assertIn("gateway_x", non_task_kinds)
        validate_ir(self.document())

    def test_load_mapping_and_path_with_deterministic_defaults(self) -> None:
        document = self.document()
        first = load_ir(document)
        self.assertEqual({"Lane_A"}, first.ann_above)
        self.assertEqual("Gateway", first.nodes[2].parent)
        self.assertEqual("Participant_IRTest", first.participant_id)
        self.assertEqual("MessageFlow_Participant_External__Start", first.message_flows[0].id)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "process.ir.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            second = load_ir(path)
        self.assertEqual(first, second)

    def test_invalid_vocabularies_and_shapes_fail_before_layout(self) -> None:
        invalid_kind = self.document()
        invalid_kind["nodes"][1]["kind"] = "gateway_typo"
        self.assert_invalid(invalid_kind, r"nodes\[1\]\.kind.*must be one of")

        invalid_type = self.document()
        invalid_type["nodes"][1]["ttype"] = "user"
        self.assert_invalid(invalid_type, r"nodes\[1\]\.ttype.*only valid")

        missing_type = self.document()
        del missing_type["nodes"][2]["ttype"]
        self.assertEqual("manual", load_ir(missing_type).nodes[2].ttype)

        duplicate = self.document()
        duplicate["nodes"][4]["id"] = "Start"
        self.assert_invalid(duplicate, r"nodes\[4\].*duplicate id")

        unknown_edge = self.document()
        unknown_edge["edges"][0]["target"] = "Missing"
        self.assert_invalid(unknown_edge, r"edges\[0\]\.target.*unknown node")

    def test_hierarchy_references_and_cycles_are_checked(self) -> None:
        unknown_parent = self.document()
        unknown_parent["nodes"][2]["parent"] = "Missing"
        self.assert_invalid(unknown_parent, r"nodes\[2\]\.parent.*unknown parent")

        cycle = self.document()
        cycle["nodes"][2]["parent"] = "Conditional"
        cycle["nodes"][3]["parent"] = "Default"
        self.assert_invalid(cycle, r"nodes\.parent.*contains a cycle")

    def test_gateway_default_invariant_is_checked(self) -> None:
        no_default = self.document()
        no_default["edges"][1]["condition"] = "No condition was supplied"
        self.assert_invalid(no_default, r"exclusive gateway must have exactly one")

        two_defaults = self.document()
        two_defaults["edges"][2].pop("condition")
        self.assert_invalid(two_defaults, r"exclusive gateway must have exactly one")

    def test_loaded_ir_reaches_layout_xml_and_validator(self) -> None:
        model = load_ir(self.document())
        scope = engine.Scope.top_level(model)
        first_layout = engine.compute_layout(model, scope)
        second_layout = engine.compute_layout(load_ir(self.document()), scope)
        self.assertEqual(first_layout.placements, second_layout.placements)
        self.assertEqual([], engine.layout_findings(model, scope, first_layout))

        with TemporaryDirectory() as directory:
            path = Path(directory) / "process.bpmn"
            engine.write_bpmn(path, model, first_layout, scope)
            self.assertTrue(Validator(path).run())


if __name__ == "__main__":
    unittest.main()
