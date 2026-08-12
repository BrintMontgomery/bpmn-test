from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ir import IRValidationError
from markdown_extractor import MarkdownExtractionError, extract_markdown, write_extraction
from semantic_handoff import (
    SemanticHandoffError,
    build_semantic_prompt,
    parse_semantic_response,
    validate_semantic_response,
)
from project_paths import EXAMPLE_MARKDOWN_DIR


SOURCE = next(EXAMPLE_MARKDOWN_DIR.glob("OFC-004*.md"))


class MarkdownExtractorTests(unittest.TestCase):
    def test_extracts_ofc004_structure_and_references(self) -> None:
        extraction = extract_markdown(SOURCE)

        self.assertEqual(7, len(extraction.actors))
        self.assertEqual("Case Manager", extraction.actors[0].name)
        self.assertEqual(16, len(extraction.main_path))
        self.assertEqual(("Case Manager", "Prospective Treatment Advocate"),
                         extraction.main_path[7].bold_actors)
        self.assertEqual(6, len(extraction.options))
        self.assertEqual("Consumer Requests an Additional Contact",
                         extraction.options[0].title)
        self.assertIn("another person", extraction.options[0].trigger)
        self.assertEqual(5, len(extraction.notes))
        self.assertEqual(
            ["a", "b", "c"],
            [reference.key for reference in extraction.inline_references[:3]],
        )
        self.assertEqual(7, len(extraction.inline_references))
        self.assertEqual((), extraction.options[0].steps[0].bold_actors)
        self.assertIn("If the Prospective Contact agrees", extraction.options[0].steps[3].text)
        self.assertEqual(("a",), extraction.options[1].steps[2].note_refs)

    def test_text_input_and_json_output_are_deterministic(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        first = extract_markdown(source)
        second = extract_markdown(source)
        self.assertEqual(first.to_dict(), second.to_dict())

        with TemporaryDirectory() as directory:
            path = write_extraction(first, Path(directory) / "OFC-004.structural.json")
            decoded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(first.to_dict(), decoded)

    def test_bare_note_markers_and_hard_breaks_are_supported(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        source = source.replace(r"\[a\]", "[a]")
        source = source.replace(r"\[ end \]", "[ end ]")
        extraction = extract_markdown(source)
        self.assertEqual("a", extraction.main_path[2].note_refs[0])

    def assert_invalid(self, source: str, message: str) -> None:
        with self.assertRaisesRegex(MarkdownExtractionError, message):
            extract_markdown(source)

    def test_malformed_structure_fails_with_actionable_errors(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assert_invalid(source.replace("## Notes", "## Annotations"), "missing required")
        self.assert_invalid(source.replace("16. **Case Manager**", "18. **Case Manager**"),
                            r"Main Path step numbering")
        self.assert_invalid(source.replace("Trigger: The Consumer requests", "Condition: The Consumer requests"),
                            "Trigger line")
        self.assert_invalid(source.replace("### Option B", "### Option A"), "duplicate option")
        self.assert_invalid(source.replace(r"\[ end \]", ""), "end sentinel")
        self.assert_invalid(source.replace(r"\[a\] Protective orders", "unknown text"),
                            "note entries must begin")

    def test_unknown_inline_note_reference_is_rejected(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        source = source.replace("begins the Elopement Form", r"begins the Elopement Form \[z\]")
        with self.assertRaisesRegex(MarkdownExtractionError, "no Notes entry"):
            extract_markdown(source)


class SemanticHandoffTests(unittest.TestCase):
    def test_prompt_contains_structural_json_schema_and_rules(self) -> None:
        extraction = extract_markdown(SOURCE)
        prompt = build_semantic_prompt(extraction)
        self.assertIn('"main_path"', prompt)
        self.assertIn('"schema_version"', prompt)
        self.assertIn("first bold actor", prompt)
        self.assertIn("internal gateway", prompt)
        self.assertIn("lane IDs", prompt)
        self.assertIn("generated BPMN output manifest", prompt)
        self.assertIn("decomposition", prompt)
        self.assertIn("global layout constraint", prompt)

    def valid_ir(self) -> dict:
        return {
            "schema_version": 1,
            "process_id": "Process_Handoff",
            "participant_name": "Handoff Test",
            "process_doc": "",
            "lanes": [{"id": "A", "name": "Actor A"}],
            "phases": [{"id": "P0", "name": "Start"}],
            "nodes": [
                {"id": "Start", "kind": "start_message", "lane": "A", "phase": "P0", "name": "Start"},
                {"id": "End", "kind": "end", "lane": "A", "phase": "P0", "name": "End"},
            ],
            "edges": [{"source": "Start", "target": "End"}],
        }

    def test_response_parsing_and_ir_validation(self) -> None:
        document = self.valid_ir()
        response = "```json\n" + json.dumps(document) + "\n```"
        self.assertEqual(document, parse_semantic_response(response))
        self.assertEqual("Process_Handoff", validate_semantic_response(response).process_id)

    def test_response_errors_use_json_and_ir_contracts(self) -> None:
        with self.assertRaisesRegex(SemanticHandoffError, "not valid JSON"):
            parse_semantic_response("not JSON")
        with self.assertRaisesRegex(SemanticHandoffError, "JSON object"):
            parse_semantic_response("[]")

        invalid_kind = self.valid_ir()
        invalid_kind["nodes"][0]["kind"] = "not_a_kind"
        with self.assertRaisesRegex(IRValidationError, "must be one of"):
            validate_semantic_response(invalid_kind)

        invalid_lane = copy.deepcopy(self.valid_ir())
        invalid_lane["nodes"][1]["lane"] = "Missing"
        with self.assertRaisesRegex(IRValidationError, "unknown lane"):
            validate_semantic_response(invalid_lane)

        invalid_gateway = copy.deepcopy(self.valid_ir())
        invalid_gateway["nodes"].insert(1, {
            "id": "Gateway", "kind": "gateway_x", "lane": "A",
            "phase": "P0", "name": "Choose",
        })
        invalid_gateway["edges"] = [
            {"source": "Start", "target": "Gateway"},
            {"source": "Gateway", "target": "End", "condition": "Yes"},
            {"source": "Gateway", "target": "Start", "condition": "No"},
        ]
        with self.assertRaisesRegex(IRValidationError, "exactly one"):
            validate_semantic_response(invalid_gateway)


if __name__ == "__main__":
    unittest.main()
