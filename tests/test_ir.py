from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import bpmn_engine as engine
from ir import (
    IR_SCHEMA_PATH,
    IRValidationError,
    _item_object,
    _optional_array,
    _positive_int,
    _validate_required_array,
    dumps_ir_document,
    load_bundle,
    load_ir,
    validate_ir,
)
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

    def test_annotation_above_accepts_lane_ids_only(self) -> None:
        invalid = self.document()
        invalid["ann_above"] = ["Source: process.md"]
        self.assert_invalid(invalid, r"ann_above\[0\].*unknown lane")

    def test_document_manifest_rejects_source_and_unaddressed_documents(self) -> None:
        source_document = self.document()
        source_document["documents"] = [{
            "id": "Process_IRTest",
            "file": "process.md",
            "role": "main",
        }]
        with self.assertRaisesRegex(IRValidationError, r"documents: output file.*\.bpmn suffix"):
            load_bundle([source_document])

        unknown = self.document()
        unknown["documents"] = [{
            "id": "doc_source",
            "file": "main.bpmn",
            "role": "main",
        }]
        with self.assertRaisesRegex(IRValidationError, r"documents: unknown process document"):
            load_bundle([unknown])

        unaddressed = self.document()
        unaddressed["documents"] = [{
            "id": "Process_IRTest",
            "file": "main.bpmn",
            "role": "main",
        }]
        global_model = copy.deepcopy(self.document())
        global_model["process_id"] = "Process_Global"
        with self.assertRaisesRegex(IRValidationError, r"documents: unaddressed process id"):
            load_bundle([unaddressed, global_model])

    def test_document_manifest_rejects_duplicate_outputs_and_bad_roles(self) -> None:
        main = self.document()
        main["documents"] = [
            {"id": "Process_IRTest", "file": "same.bpmn", "role": "main"},
            {"id": "Process_Global", "file": "same.bpmn", "role": "global"},
        ]
        global_model = copy.deepcopy(self.document())
        global_model["process_id"] = "Process_Global"
        with self.assertRaisesRegex(IRValidationError, r"duplicate BPMN output filename"):
            load_bundle([main, global_model])

        wrong_role = copy.deepcopy(main)
        wrong_role["documents"] = [
            {"id": "Process_IRTest", "file": "main.bpmn", "role": "global"},
            {"id": "Process_Global", "file": "global.bpmn", "role": "main"},
        ]
        with self.assertRaisesRegex(IRValidationError, r"main document must address"):
            load_bundle([wrong_role, global_model])

    def test_document_manifest_accepts_valid_single_and_multi_process_outputs(self) -> None:
        single = self.document()
        single["documents"] = [{
            "id": "Process_IRTest",
            "file": "main.bpmn",
            "role": "main",
        }]
        self.assertEqual("main.bpmn", load_bundle([single]).documents[0].file)

        main = copy.deepcopy(single)
        main["documents"] = [
            {"id": "Process_IRTest", "file": "main.bpmn", "role": "main"},
            {"id": "Process_Global", "file": "global.bpmn", "role": "global"},
        ]
        global_model = copy.deepcopy(self.document())
        global_model["process_id"] = "Process_Global"
        bundle = load_bundle([main, global_model])
        self.assertEqual(("main.bpmn", "global.bpmn"), tuple(
            document.file for document in bundle.documents
        ))

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


class ValidationHelperTests(unittest.TestCase):
    """Direct coverage for the small scaffolding helpers _validate_and_normalize
    delegates to, extracted to remove duplication across the section validators.
    """

    def test_positive_int_accepts_positive_integers_only(self) -> None:
        self.assertEqual(3, _positive_int(3, "field"))
        with self.assertRaisesRegex(IRValidationError, "must be a positive integer"):
            _positive_int(0, "field")
        with self.assertRaisesRegex(IRValidationError, "must be a positive integer"):
            _positive_int(-1, "field")
        with self.assertRaisesRegex(IRValidationError, "must be a positive integer"):
            _positive_int(True, "field")  # bool is an int subclass
        with self.assertRaisesRegex(IRValidationError, "must be a positive integer"):
            _positive_int(1.5, "field")

    def test_optional_array_defaults_to_empty_list(self) -> None:
        self.assertEqual([], _optional_array({}, "items", "items"))
        self.assertEqual([1, 2], _optional_array({"items": [1, 2]}, "items", "items"))
        with self.assertRaisesRegex(IRValidationError, "expected an array"):
            _optional_array({"items": {}}, "items", "items")

    def test_validate_required_array_rejects_empty(self) -> None:
        with self.assertRaisesRegex(
            IRValidationError, "must contain at least one lane"
        ):
            _validate_required_array({"lanes": []}, "lanes", "lanes", item_name="lane")
        self.assertEqual(
            [1], _validate_required_array({"lanes": [1]}, "lanes", "lanes", item_name="lane")
        )

    def test_item_object_checks_keys_and_required_fields(self) -> None:
        item, path = _item_object(
            {"id": "x"}, 0, "lanes", allowed={"id", "name"}, required={"id"}
        )
        self.assertEqual({"id": "x"}, item)
        self.assertEqual("lanes[0]", path)
        with self.assertRaisesRegex(IRValidationError, "unknown field"):
            _item_object({"id": "x", "bogus": 1}, 0, "lanes", allowed={"id"}, required={"id"})
        with self.assertRaisesRegex(IRValidationError, "missing required field"):
            _item_object({}, 0, "lanes", allowed={"id"}, required={"id"})


class DumpsIRDocumentTests(unittest.TestCase):
    def test_output_is_sorted_and_newline_terminated(self) -> None:
        text = dumps_ir_document({"b": 1, "a": 2})
        self.assertTrue(text.endswith("\n"))
        self.assertLess(text.index('"a"'), text.index('"b"'))
        self.assertEqual({"b": 1, "a": 2}, json.loads(text))


if __name__ == "__main__":
    unittest.main()
