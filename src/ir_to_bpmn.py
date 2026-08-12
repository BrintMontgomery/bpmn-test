"""Emit and validate BPMN documents from one or more IR JSON files."""

from __future__ import annotations

import argparse
import logging
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from bpmn_engine import DocumentSpec, ProcessBundle
from cli_support import run_cli
from decomposition import PreparedBundle, prepare_bundle_for_build, write_prepared_bundle
from ir import IRValidationError, load_bundle, validate_document_manifest
from logging_setup import configure
from validate_bpmn import FLOW_NODE_TAGS, local, validate_bundle

configure()
logger = logging.getLogger(__name__)


class CLIError(ValueError):
    """Raised for an actionable command-line workflow error."""


def default_bpmn_name(ir_path: Path) -> str:
    """Return the BPMN name implied by an IR filename."""

    name = ir_path.name
    stem = name[:-len(".ir.json")] if name.endswith(".ir.json") else ir_path.stem
    return f"{stem}.bpmn"


def _ir_paths(ir_files: list[str | Path]) -> list[Path]:
    """Require at least one IR input and return the inputs as paths."""

    if not ir_files:
        raise CLIError("at least one IR file is required")
    return [Path(path) for path in ir_files]


def _source_bpmn_names(basename: str, count: int) -> list[str]:
    """Return BPMN filenames derived from a source basename."""

    if count == 1:
        return [f"{basename}.bpmn"]
    return [f"{basename}_{index}.bpmn" for index in range(count)]


def _default_documents(
    ir_paths: list[Path], bundle: ProcessBundle, *, output_basename: str | None = None,
) -> ProcessBundle:
    """Fill in output names without overriding reviewed document metadata."""

    if len(ir_paths) != len(bundle.models):
        raise CLIError(
            "IR bundle input count does not match the number of loaded processes"
        )
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
    if output_basename is not None:
        names = _source_bpmn_names(output_basename, len(specs))
        specs = [
            DocumentSpec(spec.id, name, spec.role)
            for spec, name in zip(specs, names)
        ]
    try:
        validated = validate_document_manifest(bundle.models, specs)
    except IRValidationError as exc:
        raise CLIError(str(exc)) from exc
    return ProcessBundle(bundle.models, validated)


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


def preflight(
    ir_files: list[str | Path], *, repair_layout: bool = False,
    output_basename: str | None = None,
) -> tuple[ProcessBundle, PreparedBundle]:
    """Load, normalize, decompose, and layout a complete BPMN bundle."""

    ir_paths = _ir_paths(ir_files)
    try:
        bundle = _default_documents(
            ir_paths, load_bundle(ir_paths), output_basename=output_basename
        )
        prepared = prepare_bundle_for_build(bundle, repair_layout=repair_layout)
    except (OSError, IRValidationError, ValueError) as exc:
        raise CLIError(str(exc)) from exc
    return bundle, prepared


def planned_output_paths(
    ir_files: list[str | Path], *, output_dir: str | Path | None = None,
    repair_layout: bool = False, output_basename: str | None = None,
) -> list[Path]:
    """Return the BPMN paths that :func:`run` would publish.

    This is useful to interactive callers that need to obtain overwrite
    consent before generating a bundle.  It validates the IR bundle but does
    not create directories or write output files.
    """

    ir_paths = _ir_paths(ir_files)
    bundle, _prepared = preflight(
        ir_paths,
        repair_layout=repair_layout,
        output_basename=output_basename,
    )
    directory = Path(output_dir) if output_dir is not None else ir_paths[0].parent
    return [directory / document.file for document in bundle.documents]


def publish_bundle(directory: Path, prepared: PreparedBundle) -> list[Path]:
    """Stage, validate, and atomically publish an already-preflighted bundle."""

    # Build in a private directory so an invalid bundle is never published.
    with tempfile.TemporaryDirectory(prefix=".bpmn-stage-", dir=directory) as staged_name:
        staged_directory = Path(staged_name)
        try:
            staged_paths = write_prepared_bundle(staged_directory, prepared)
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
    return paths


def report_published(prepared: PreparedBundle, paths: list[Path]) -> None:
    """Log the console lines describing one successful publish."""

    for repair in prepared.repairs:
        logger.info(f"layout repair: {repair}")
    for path in paths:
        counts = ", ".join(
            f"{plane_id}: {count} flow nodes"
            for plane_id, count in _plane_node_counts(path)
        )
        logger.info(f"wrote {path}: {counts or 'no BPMN planes'}")


def run(
    ir_files: list[str | Path],
    *,
    output_dir: str | Path | None = None,
    repair_layout: bool = False, output_basename: str | None = None,
) -> list[Path]:
    """Emit and validate a complete BPMN bundle, returning emitted paths."""

    ir_paths = _ir_paths(ir_files)
    try:
        _bundle, prepared = preflight(
            ir_paths,
            repair_layout=repair_layout,
            output_basename=output_basename,
        )
        directory = Path(output_dir) if output_dir is not None else ir_paths[0].parent
        directory.mkdir(parents=True, exist_ok=True)
    except (OSError, IRValidationError, ValueError) as exc:
        raise CLIError(str(exc)) from exc

    paths = publish_bundle(directory, prepared)
    report_published(prepared, paths)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit and validate BPMN from one or more IR JSON files."
    )
    parser.add_argument("ir_files", nargs="+", type=Path, help="main IR followed by bundle IR files")
    parser.add_argument("-o", "--output-dir", type=Path, help="BPMN output directory")
    parser.add_argument(
        "--repair-layout", action="store_true",
        help="flatten incompatible authored phases in memory for this build",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_cli(
        argv,
        parser_factory=build_parser,
        action=lambda args: run(
            args.ir_files,
            output_dir=args.output_dir,
            repair_layout=args.repair_layout,
        ),
        error_types=(CLIError,),
        logger=logger,
    )


if __name__ == "__main__":
    raise SystemExit(main())
