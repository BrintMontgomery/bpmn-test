"""Emit and validate BPMN documents from one or more IR JSON files."""

from __future__ import annotations

import argparse
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from bpmn_engine import DocumentSpec, ProcessBundle, write_bundle
from ir import IRValidationError, load_bundle
from validate_bpmn import FLOW_NODE_TAGS, local, validate_bundle


class CLIError(ValueError):
    """Raised for an actionable command-line workflow error."""


def default_bpmn_name(ir_path: Path) -> str:
    """Return the BPMN name implied by an IR filename."""

    name = ir_path.name
    stem = name[:-len(".ir.json")] if name.endswith(".ir.json") else ir_path.stem
    return f"{stem}.bpmn"


def _default_documents(ir_paths: list[Path], bundle: ProcessBundle) -> ProcessBundle:
    """Fill in output names without overriding reviewed document metadata."""

    models_by_id = {model.process_id: model for model in bundle.models}
    # load_bundle supplies process-id filenames when the IR omitted
    # ``documents``. Those are loader fallbacks, not reviewed metadata, so
    # replace them with the CLI's input-stem policy.
    specs = list(bundle.documents) if bundle.models[0].documents else []
    known_ids = {spec.id for spec in specs}
    for index, (ir_path, model) in enumerate(zip(ir_paths, bundle.models)):
        if model.process_id in known_ids:
            continue
        specs.append(
            DocumentSpec(
                model.process_id,
                default_bpmn_name(ir_path),
                "main" if index == 0 else "global",
            )
        )
        known_ids.add(model.process_id)
    if len(specs) != len(models_by_id):
        raise CLIError("IR bundle contains duplicate or unaddressed process documents")
    filenames = [spec.file for spec in specs]
    if len(filenames) != len(set(filenames)):
        raise CLIError("IR bundle contains duplicate BPMN output filenames")
    return ProcessBundle(bundle.models, tuple(specs))


def _plane_node_counts(path: Path) -> list[tuple[str, int]]:
    root = ET.parse(path).getroot()
    flow_node_ids = {
        element.get("id")
        for process in root
        if local(process.tag) == "process"
        for element in process.iter()
        if local(element.tag) in FLOW_NODE_TAGS and element.get("id")
    }
    counts: list[tuple[str, int]] = []
    for plane in root.iter():
        if local(plane.tag) != "BPMNPlane":
            continue
        plane_id = plane.get("id") or plane.get("bpmnElement") or "<unnamed>"
        count = sum(
            1
            for shape in plane
            if local(shape.tag) == "BPMNShape"
            and shape.get("bpmnElement") in flow_node_ids
        )
        counts.append((plane_id, count))
    return counts


def planned_output_paths(
    ir_files: list[str | Path], *, output_dir: str | Path | None = None,
) -> list[Path]:
    """Return the BPMN paths that :func:`run` would publish.

    This is useful to interactive callers that need to obtain overwrite
    consent before generating a bundle.  It validates the IR bundle but does
    not create directories or write output files.
    """

    if not ir_files:
        raise CLIError("at least one IR file is required")
    ir_paths = [Path(path) for path in ir_files]
    try:
        bundle = _default_documents(ir_paths, load_bundle(ir_paths))
    except (OSError, IRValidationError, ValueError) as exc:
        raise CLIError(str(exc)) from exc
    directory = Path(output_dir) if output_dir is not None else ir_paths[0].parent
    return [directory / document.file for document in bundle.documents]


def run(
    ir_files: list[str | Path],
    *,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """Emit and validate a complete BPMN bundle, returning emitted paths."""

    if not ir_files:
        raise CLIError("at least one IR file is required")
    ir_paths = [Path(path) for path in ir_files]
    try:
        bundle = _default_documents(ir_paths, load_bundle(ir_paths))
        directory = Path(output_dir) if output_dir is not None else ir_paths[0].parent
        directory.mkdir(parents=True, exist_ok=True)
    except (OSError, IRValidationError, ValueError) as exc:
        raise CLIError(str(exc)) from exc

    # Build in a private directory so an invalid bundle is never published.
    with tempfile.TemporaryDirectory(prefix=".bpmn-stage-", dir=directory) as staged_name:
        staged_directory = Path(staged_name)
        try:
            staged_paths = write_bundle(staged_directory, bundle)
        except (OSError, ValueError) as exc:
            raise CLIError(str(exc)) from exc

        # validate_bundle constructs Validator once per emitted file and
        # supplies the complete process-id set for cross-document checks.
        if not validate_bundle(staged_paths):
            raise CLIError(
                "BPMN bundle validation failed; no successful output was reported"
            )

        paths = []
        for staged_path in staged_paths:
            final_path = directory / staged_path.relative_to(staged_directory)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.replace(final_path)
            paths.append(final_path)

    for path in paths:
        counts = ", ".join(
            f"{plane_id}: {count} flow nodes"
            for plane_id, count in _plane_node_counts(path)
        )
        print(f"wrote {path}: {counts or 'no BPMN planes'}")
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit and validate BPMN from one or more IR JSON files."
    )
    parser.add_argument("ir_files", nargs="+", type=Path, help="main IR followed by bundle IR files")
    parser.add_argument("-o", "--output-dir", type=Path, help="BPMN output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(args.ir_files, output_dir=args.output_dir)
    except CLIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
