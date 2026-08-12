from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ir_to_bpmn
from project_paths import EXAMPLE_MARKDOWN_DIR
from sop_to_bpmn_ui import (
    IRResponseValidationError,
    OverwriteRequired,
    SOPToBPMNApp,
    SOPToBPMNController,
    WorkflowError,
    build_ir_validation_feedback,
)


SOURCE = next(EXAMPLE_MARKDOWN_DIR.glob("OFC-004*.md"))


def valid_ir(process_id: str = "Process_UI") -> dict:
    return {
        "schema_version": 1,
        "process_id": process_id,
        "participant_name": "UI test process",
        "process_doc": "A UI test process.",
        "lanes": [{"id": "A", "name": "Actor A"}],
        "phases": [{"id": "P0", "name": "Start"}],
        "nodes": [
            {"id": "Start", "kind": "start_message", "lane": "A", "phase": "P0", "name": "Start"},
            {"id": "End", "kind": "end", "lane": "A", "phase": "P0", "name": "End"},
        ],
        "edges": [{"source": "Start", "target": "End"}],
    }


class SOPToBPMNControllerTests(unittest.TestCase):
    def make_source(self, directory: Path, name: str = "Process.md") -> Path:
        path = directory / name
        path.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        return path

    def test_prepare_source_generates_prompt_and_detects_existing_ir(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            controller = SOPToBPMNController()

            prepared = controller.prepare_source(source)

            self.assertFalse(prepared.has_existing_ir)
            self.assertEqual(source.with_suffix(".ir.json"), prepared.ir_path)
            self.assertIn("Structural extraction", prepared.prompt)

            prepared.ir_path.write_text(json.dumps(valid_ir()), encoding="utf-8")
            second = controller.prepare_source(source)
            self.assertTrue(second.has_existing_ir)

    def test_invalid_markdown_and_existing_ir_are_actionable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.md"
            invalid.write_text("# Not an SOP\n", encoding="utf-8")
            with self.assertRaisesRegex(WorkflowError, "required section"):
                SOPToBPMNController().prepare_source(invalid)

            source = self.make_source(root)
            source.with_suffix(".ir.json").write_text("not JSON", encoding="utf-8")
            controller = SOPToBPMNController()
            controller.prepare_source(source)
            with self.assertRaisesRegex(WorkflowError, "Existing IR is not valid"):
                controller.use_existing_ir()

    def test_existing_ir_can_be_validated_and_used(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            ir_path = source.with_suffix(".ir.json")
            ir_path.write_text(json.dumps(valid_ir()), encoding="utf-8")
            controller = SOPToBPMNController()
            controller.prepare_source(source)

            self.assertEqual(ir_path, controller.use_existing_ir())
            self.assertEqual(ir_path, controller.ir_path)

    def test_response_is_validated_before_save_and_requires_ir_consent(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            controller = SOPToBPMNController()
            controller.prepare_source(source)

            with self.assertRaisesRegex(WorkflowError, "not valid JSON"):
                controller.save_semantic_response("not JSON")
            self.assertFalse(source.with_suffix(".ir.json").exists())

            response = "```json\n" + json.dumps(valid_ir()) + "\n```"
            saved = controller.save_semantic_response(response)
            self.assertEqual(source.with_suffix(".ir.json"), saved)
            with self.assertRaises(OverwriteRequired):
                controller.save_semantic_response(json.dumps(valid_ir()))
            controller.save_semantic_response(json.dumps(valid_ir()), overwrite=True)

    def test_validation_feedback_preserves_error_and_raw_response(self) -> None:
        response = "```json\n{\"nodes\": [\n\tbroken\n]}\n```"
        error = IRResponseValidationError(
            "Semantic response failed IR validation: response is not valid JSON"
        )

        feedback = build_ir_validation_feedback(response, error)

        self.assertIn("Return only the corrected IR JSON object.", feedback)
        self.assertIn(str(error), feedback)
        self.assertIn(response, feedback)
        self.assertIn("--- BEGIN SUBMITTED RESPONSE ---", feedback)
        self.assertIn("--- END SUBMITTED RESPONSE ---", feedback)

    def test_invalid_semantic_response_raises_copyable_validation_error(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            controller = SOPToBPMNController()
            controller.prepare_source(source)

            with self.assertRaises(IRResponseValidationError) as context:
                controller.save_semantic_response("not JSON")

            feedback = build_ir_validation_feedback("not JSON", context.exception)
            self.assertIn("not JSON", feedback)
            self.assertIn("not valid JSON", feedback)
            self.assertFalse(source.with_suffix(".ir.json").exists())

    def test_valid_response_can_be_saved_after_invalid_response(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            controller = SOPToBPMNController()
            controller.prepare_source(source)

            with self.assertRaises(IRResponseValidationError):
                controller.save_semantic_response("not JSON")

            saved = controller.save_semantic_response(json.dumps(valid_ir()))

            self.assertEqual(source.with_suffix(".ir.json"), saved)

    def test_invalid_document_manifest_is_rejected_before_ir_write(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            controller = SOPToBPMNController()
            controller.prepare_source(source)
            invalid = valid_ir()
            invalid["documents"] = [{
                "id": invalid["process_id"],
                "file": source.name,
                "role": "main",
            }]

            with self.assertRaisesRegex(IRResponseValidationError, r"\.bpmn suffix"):
                controller.save_semantic_response(json.dumps(invalid))
            self.assertFalse(source.with_suffix(".ir.json").exists())

    def test_existing_ir_manifest_is_validated_before_use(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            ir_path = source.with_suffix(".ir.json")
            invalid = valid_ir()
            invalid["documents"] = [{
                "id": "wrong_process",
                "file": "main.bpmn",
                "role": "main",
            }]
            ir_path.write_text(json.dumps(invalid), encoding="utf-8")
            controller = SOPToBPMNController()
            controller.prepare_source(source)

            with self.assertRaisesRegex(WorkflowError, "unknown process document"):
                controller.use_existing_ir()

    def test_status_copy_preserves_exact_text_for_all_status_states(self) -> None:
        class FakeRoot:
            def __init__(self) -> None:
                self.clipboard = ""

            def clipboard_clear(self) -> None:
                self.clipboard = ""

            def clipboard_append(self, value: str) -> None:
                self.clipboard = value

        class FakeStatus:
            def __init__(self, value: str) -> None:
                self.value = value

            def get(self) -> str:
                return self.value

        for status in (
            "1. Select a Markdown SOP file.",
            "Working…",
            "Template validation failed: malformed SOP",
            "Built and validated 1 BPMN file.",
        ):
            app = object.__new__(SOPToBPMNApp)
            app.root = FakeRoot()
            app.status_var = FakeStatus(status)
            app._copy_status()
            self.assertEqual(status, app.root.clipboard)

    def test_builds_bpmn_beside_markdown_and_requires_output_consent(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            controller = SOPToBPMNController()
            controller.prepare_source(source)
            controller.save_semantic_response(json.dumps(valid_ir()))

            self.assertEqual([source.with_name("Process.bpmn")], controller.planned_outputs())
            with redirect_stdout(io.StringIO()):
                result = controller.build_bpmn()
            self.assertEqual((source.with_name("Process.bpmn"),), result.paths)
            self.assertTrue(result.paths[0].exists())
            with self.assertRaises(OverwriteRequired):
                controller.build_bpmn()

    def test_bundle_results_and_build_errors_are_returned_without_success(self) -> None:
        with TemporaryDirectory() as directory:
            source = self.make_source(Path(directory))
            controller = SOPToBPMNController()
            controller.prepare_source(source)
            controller.save_semantic_response(json.dumps(valid_ir()))
            outputs = [source.with_name("main.bpmn"), source.with_name("global.bpmn")]
            with patch.object(ir_to_bpmn, "planned_output_paths", return_value=outputs), \
                 patch.object(ir_to_bpmn, "run", return_value=outputs):
                self.assertEqual(tuple(outputs), controller.build_bpmn().paths)

            with patch.object(ir_to_bpmn, "run", side_effect=ir_to_bpmn.CLIError("validation failed")):
                with self.assertRaisesRegex(WorkflowError, "validation failed"):
                    controller.build_bpmn(overwrite=True)


if __name__ == "__main__":
    unittest.main()
