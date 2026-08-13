from __future__ import annotations

import copy
import io
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ir_to_bpmn
import sop_to_bpmn
import sop_to_ir
from project_paths import EXAMPLE_MARKDOWN_DIR


SOURCE = next(EXAMPLE_MARKDOWN_DIR.glob("OFC-004*.md"))
TRV_SOURCE = next(EXAMPLE_MARKDOWN_DIR.glob("TRV-001*.md"))
TRV_RESPONSE = Path(__file__).with_name("fixtures") / "trv-001-semantic-response.json"


def source_without_inline_notes() -> str:
    """Keep the required Notes section while removing only inline markers.

    Generic CLI fixtures intentionally model a two-node process; use this
    variant so source-aware note attachment validation is not bypassed.
    """
    before_notes, marker, notes = SOURCE.read_text(encoding="utf-8").partition("## Notes")
    return re.sub(r"\\\[[A-Za-z0-9_-]+\\\]", "", before_notes) + marker + notes


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


def phase_order_invalid_ir() -> dict:
    document = valid_ir("Process_PhaseOrder")
    document["phases"] = [
        {"id": "P0", "name": "Main"},
        {"id": "P1", "name": "Exception"},
    ]
    document["nodes"] = [
        {"id": "Start", "kind": "start_message", "lane": "A", "phase": "P0", "name": "Start"},
        {"id": "Main1", "kind": "task", "lane": "A", "phase": "P0", "name": "Main 1"},
        {"id": "Main2", "kind": "task", "lane": "A", "phase": "P0", "name": "Main 2"},
        {"id": "Option", "kind": "task", "lane": "A", "phase": "P1", "name": "Exception"},
        {"id": "End", "kind": "end", "lane": "A", "phase": "P1", "name": "End"},
    ]
    document["edges"] = [
        {"source": "Start", "target": "Main1"},
        {"source": "Main1", "target": "Main2"},
        {"source": "Main2", "target": "End"},
        {"source": "Start", "target": "Option"},
        {"source": "Option", "target": "End"},
    ]
    return document


class SopToIRTests(unittest.TestCase):
    def test_trv_note_keys_are_resolved_and_attached_exactly_once(self) -> None:
        response = json.loads(TRV_RESPONSE.read_text(encoding="utf-8"))
        extraction = sop_to_ir.extract_markdown(TRV_SOURCE)
        expected_note = extraction.notes[0].text
        with TemporaryDirectory() as directory:
            root = Path(directory)
            response_path = root / "trv-response.json"
            response_path.write_text(json.dumps(response), encoding="utf-8")
            output = sop_to_ir.run(
                TRV_SOURCE, output=root / "TRV-001.ir.json",
                response_file=str(response_path), prompt_stream=io.StringIO(),
            )
            document = json.loads(output.read_text(encoding="utf-8"))
        verification = next(node for node in document["nodes"]
                            if node["id"] == "task_verify_approval")
        self.assertEqual(expected_note, verification["note"])

    def test_trv_note_attachment_guards_reject_missing_duplicate_and_unknown_notes(self) -> None:
        extraction = sop_to_ir.extract_markdown(TRV_SOURCE)
        response = json.loads(TRV_RESPONSE.read_text(encoding="utf-8"))
        cases = []
        missing = copy.deepcopy(response)
        next(node for node in missing["nodes"] if node["id"] == "task_verify_approval").pop("note")
        cases.append((missing, "missing note attachment"))
        unknown = copy.deepcopy(response)
        next(node for node in unknown["nodes"] if node["id"] == "task_verify_approval")["note"] = "z"
        cases.append((unknown, "does not resolve"))
        duplicate = copy.deepcopy(response)
        next(node for node in duplicate["nodes"] if node["id"] == "end_approval_confirmed")["note"] = "a"
        cases.append((duplicate, "duplicate or misplaced"))
        for document, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(sop_to_ir.CLIError, message):
                    sop_to_ir._resolve_source_notes(document, extraction)

    def test_response_file_is_validated_before_deterministic_write(self) -> None:
        document = valid_ir()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Process.md"
            source.write_text(source_without_inline_notes(), encoding="utf-8")
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
            source.write_text(source_without_inline_notes(), encoding="utf-8")
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
            source.write_text(source_without_inline_notes(), encoding="utf-8")
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
            source.write_text(source_without_inline_notes(), encoding="utf-8")
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

    def test_trv_pipeline_normalizes_labels_and_annotation_placement_without_rewriting_ir(self) -> None:
        response = json.loads(TRV_RESPONSE.read_text(encoding="utf-8"))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            response_path = root / "trv-response.json"
            response_path.write_text(json.dumps(response), encoding="utf-8")
            ir_path = sop_to_ir.run(
                TRV_SOURCE, output=root / "TRV-001.ir.json",
                response_file=str(response_path), prompt_stream=io.StringIO(),
            )
            original_ir = ir_path.read_bytes()
            _bundle, prepared = ir_to_bpmn.preflight([ir_path])
            model = prepared.bundle.main
            self.assertEqual({"lane_travel_approver"}, model.ann_above)
            labels = {
                edge.target: edge.label for edge in model.edges
                if edge.source == "gateway_approval_button_displayed"
            }
            self.assertEqual("Approval button is displayed", labels["task_select_approval"])
            self.assertEqual("Otherwise", labels["task_open_worklist"])
            self.assertTrue(any("labeled" in repair for repair in prepared.repairs))
            self.assertTrue(any("annotation bands" in repair for repair in prepared.repairs))
            paths = ir_to_bpmn.run([ir_path], output_dir=root / "out")
            self.assertEqual(original_ir, ir_path.read_bytes())
            self.assertTrue(paths[0].exists())

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

    def test_source_basename_numbers_multiple_outputs(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            documents = [
                {"id": "Process_Main", "file": "reviewed-main.bpmn", "role": "main"},
                {"id": "Process_Global", "file": "reviewed-global.bpmn", "role": "global"},
            ]
            main = self.write_ir(
                root, "main.ir.json",
                valid_ir("Process_Main", documents=documents, call_target="Process_Global"),
            )
            global_ir = self.write_ir(root, "global.ir.json", valid_ir("Process_Global"))

            with redirect_stdout(io.StringIO()):
                paths = ir_to_bpmn.run(
                    [main, global_ir],
                    output_dir=root / "out",
                    output_basename="Case Manager.v2 (Draft)",
                )

            self.assertEqual(
                ["Case Manager.v2 (Draft)_0.bpmn", "Case Manager.v2 (Draft)_1.bpmn"],
                [path.name for path in paths],
            )
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

    def test_publish_bundle_wraps_validator_parse_error_as_cli_error(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ir_path = self.write_ir(root, "Process.ir.json", valid_ir())
            _bundle, prepared = ir_to_bpmn.preflight([ir_path])
            parse_error = ir_to_bpmn.BpmnParseError("could not parse staged BPMN")

            with patch.object(ir_to_bpmn, "validate_bundle", side_effect=parse_error):
                with self.assertRaises(ir_to_bpmn.CLIError) as raised:
                    ir_to_bpmn.publish_bundle(root, prepared)

            self.assertNotIsInstance(raised.exception, ir_to_bpmn.BpmnParseError)
            self.assertIs(raised.exception.__cause__, parse_error)
            self.assertIn("could not parse staged BPMN", str(raised.exception))

    def test_plane_node_counts_rejects_malformed_xml(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.bpmn"
            path.write_text("<definitions>", encoding="utf-8")

            with self.assertRaises(ir_to_bpmn.CLIError) as raised:
                ir_to_bpmn._plane_node_counts(path)

            self.assertIn(str(path), str(raised.exception))
            self.assertIsInstance(raised.exception.__cause__, ET.ParseError)

    def test_buildability_preflight_rejects_phase_backtracking_before_output(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ir_path = self.write_ir(root, "PhaseOrder.ir.json", phase_order_invalid_ir())
            output_dir = root / "out"
            with self.assertRaisesRegex(
                ir_to_bpmn.CLIError,
                r"phase P1 places Option.*left of an earlier phase ending at column",
            ):
                ir_to_bpmn.run([ir_path], output_dir=output_dir)
            self.assertFalse(output_dir.exists())

    def test_repair_layout_is_build_only_and_preserves_source_ir(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            document = phase_order_invalid_ir()
            ir_path = self.write_ir(root, "PhaseOrder.ir.json", document)
            original = ir_path.read_bytes()
            output = io.StringIO()
            with redirect_stdout(output):
                paths = ir_to_bpmn.run(
                    [ir_path], output_dir=root / "out", repair_layout=True
                )
            self.assertTrue(paths[0].exists())
            self.assertEqual(original, ir_path.read_bytes())
            self.assertIn("layout repair", output.getvalue())


class ConvenienceWrapperTests(unittest.TestCase):
    def test_existing_ir_skips_semantic_stage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Case Manager.v2 (Draft).md"
            ir_path = root / "NotNeeded.ir.json"
            ir_path.write_text(json.dumps(valid_ir()), encoding="utf-8")
            with patch.object(sop_to_bpmn.sop_to_ir, "run") as semantic_run:
                with redirect_stdout(io.StringIO()):
                    paths = sop_to_bpmn.run(source, ir_output=ir_path)
            semantic_run.assert_not_called()
            self.assertEqual([root / "Case Manager.v2 (Draft).bpmn"], paths)

    def test_missing_ir_requires_a_response_and_then_runs_both_stages(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Process.md"
            source.write_text(source_without_inline_notes(), encoding="utf-8")
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
