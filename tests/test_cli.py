from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ir_to_bpmn
import sop_to_bpmn
import sop_to_ir
from project_paths import EXAMPLE_MARKDOWN_DIR


SOURCE = next(EXAMPLE_MARKDOWN_DIR.glob("OFC-004*.md"))


def valid_ir(
    process_id: str = "Process_CLI",
    *,
    documents: list[dict[str, str]] | None = None,
    call_target: str | None = None,
) -> dict:
    nodes = [
        {"id": "Start", "kind": "start_message", "lane": "A", "phase": "P0", "name": "Start"},
        {"id": "End", "kind": "end", "lane": "A", "phase": "P0", "name": "End"},
    ]
    edges = [{"source": "Start", "target": "End"}]
    if call_target is not None:
        nodes.insert(1, {
            "id": "Call", "kind": "call_activity", "lane": "A",
            "phase": "P0", "name": "Call global", "called_element": call_target,
        })
        edges = [
            {"source": "Start", "target": "Call"},
            {"source": "Call", "target": "End"},
        ]
    document = {
        "schema_version": 1,
        "process_id": process_id,
        "participant_name": process_id,
        "process_doc": "CLI test process",
        "lanes": [{"id": "A", "name": "Actor A"}],
        "phases": [{"id": "P0", "name": "Start"}],
        "nodes": nodes,
        "edges": edges,
    }
    if documents is not None:
        document["documents"] = documents
    return document


class SopToIRTests(unittest.TestCase):
    def test_response_file_is_validated_before_deterministic_write(self) -> None:
        document = valid_ir()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Process.md"
            source.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
            response = root / "model.json"
            response.write_text(json.dumps(document), encoding="utf-8")
            prompt = io.StringIO()

            output = sop_to_ir.run(
                source,
                response_file=str(response),
                prompt_stream=prompt,
            )

            self.assertEqual(root / "Process.ir.json", output)
            self.assertEqual(document, json.loads(output.read_text(encoding="utf-8")))
            self.assertIn("Structural extraction", prompt.getvalue())

    def test_stdin_response_and_invalid_response_do_not_create_output(self) -> None:
        document = valid_ir()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Process.md"
            source.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
            output = root / "result.ir.json"
            sop_to_ir.run(
                source,
                output=output,
                response_file="-",
                input_stream=io.StringIO("```json\n" + json.dumps(document) + "\n```"),
                prompt_stream=io.StringIO(),
            )
            self.assertTrue(output.exists())

            invalid_output = root / "invalid.ir.json"
            with self.assertRaises(sop_to_ir.CLIError):
                sop_to_ir.run(
                    source,
                    output=invalid_output,
                    response_file="-",
                    input_stream=io.StringIO("not JSON"),
                    prompt_stream=io.StringIO(),
                )
            self.assertFalse(invalid_output.exists())

    def test_invalid_document_manifest_does_not_create_output(self) -> None:
        document = valid_ir()
        document["documents"] = [{
            "id": document["process_id"],
            "file": "source.md",
            "role": "main",
        }]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Process.md"
            source.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
            response = root / "model.json"
            response.write_text(json.dumps(document), encoding="utf-8")
            output = root / "invalid.ir.json"

            with self.assertRaisesRegex(sop_to_ir.CLIError, r"\.bpmn suffix"):
                sop_to_ir.run(
                    source,
                    output=output,
                    response_file=str(response),
                    prompt_stream=io.StringIO(),
                )
            self.assertFalse(output.exists())

    def test_main_uses_explicit_argv_instead_of_sys_argv(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Process.md"
            source.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
            response = root / "model.json"
            response.write_text(json.dumps(valid_ir()), encoding="utf-8")
            with patch.object(sys, "argv", ["unexpected", "arguments"]):
                status = sop_to_ir.main([
                    str(source), "--response-file", str(response),
                    "--prompt-file", str(root / "prompt.txt"),
                ])
            self.assertEqual(0, status)


class IRToBPMNTests(unittest.TestCase):
    def write_ir(self, directory: Path, filename: str, document: dict) -> Path:
        path = directory / filename
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_input_stem_output_and_plane_counts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ir_path = self.write_ir(root, "Process.ir.json", valid_ir())
            output = io.StringIO()
            with redirect_stdout(output):
                paths = ir_to_bpmn.run([ir_path])
            self.assertEqual([root / "Process.bpmn"], paths)
            self.assertIn("BPMNPlane_CLI", output.getvalue())
            self.assertIn("2 flow nodes", output.getvalue())

    def test_explicit_multi_document_bundle_is_emitted_and_validated(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            documents = [
                {"id": "Process_Main", "file": "main.bpmn", "role": "main"},
                {"id": "Process_Global", "file": "global.bpmn", "role": "global"},
            ]
            main = self.write_ir(
                root, "main.ir.json",
                valid_ir("Process_Main", documents=documents, call_target="Process_Global"),
            )
            global_ir = self.write_ir(root, "global.ir.json", valid_ir("Process_Global"))
            with redirect_stdout(io.StringIO()):
                paths = ir_to_bpmn.run([main, global_ir], output_dir=root / "out")
            self.assertEqual(["main.bpmn", "global.bpmn"], [path.name for path in paths])
            self.assertTrue(all(path.exists() for path in paths))

    def test_validation_failure_returns_cli_error_without_success_message(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ir_path = self.write_ir(root, "Process.ir.json", valid_ir())
            output = io.StringIO()
            with patch.object(ir_to_bpmn, "validate_bundle", return_value=False):
                with redirect_stdout(output):
                    with self.assertRaisesRegex(ir_to_bpmn.CLIError, "validation failed"):
                        ir_to_bpmn.run([ir_path])
            self.assertNotIn("wrote", output.getvalue())
            self.assertFalse((root / "Process.bpmn").exists())


class ConvenienceWrapperTests(unittest.TestCase):
    def test_existing_ir_skips_semantic_stage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "NotNeeded.md"
            ir_path = root / "NotNeeded.ir.json"
            ir_path.write_text(json.dumps(valid_ir()), encoding="utf-8")
            with patch.object(sop_to_bpmn.sop_to_ir, "run") as semantic_run:
                with redirect_stdout(io.StringIO()):
                    paths = sop_to_bpmn.run(source)
            semantic_run.assert_not_called()
            self.assertEqual([root / "NotNeeded.bpmn"], paths)

    def test_missing_ir_requires_a_response_and_then_runs_both_stages(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Process.md"
            source.write_text(SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
            response = root / "model.json"
            response.write_text(json.dumps(valid_ir()), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = sop_to_bpmn.main([
                    str(source), "--response-file", str(response),
                    "--prompt-file", str(root / "prompt.txt"),
                ])
            self.assertEqual(0, status)
            self.assertTrue((root / "Process.ir.json").exists())
            self.assertTrue((root / "Process.bpmn").exists())


if __name__ == "__main__":
    unittest.main()
