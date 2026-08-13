"""Convert an SOP Markdown document into a reviewed IR JSON artifact.

The semantic-model provider is deliberately outside this module.  A caller
supplies its JSON response through a file or stdin after using the generated
prompt with the provider of their choice.
"""

from __future__ import annotations

import argparse
import copy
import logging
import sys
from pathlib import Path
from typing import Any, TextIO

from cli_support import run_cli
from ir import dumps_ir_document, load_bundle
from logging_setup import configure
from markdown_extractor import ExtractedSOP, extract_markdown
from semantic_handoff import build_semantic_prompt, parse_semantic_response

configure()
logger = logging.getLogger(__name__)


class CLIError(ValueError):
    """Raised for an actionable command-line workflow error."""


def default_ir_path(source: Path) -> Path:
    """Return the adjacent IR filename for a Markdown source."""

    return source.with_suffix(".ir.json")


def _read_response(response_file: str, *, input_stream: TextIO | None) -> str:
    if response_file == "-":
        stream = input_stream if input_stream is not None else sys.stdin
        return stream.read()
    try:
        return Path(response_file).read_text(encoding="utf-8")
    except OSError as exc:
        raise CLIError(f"could not read semantic response {response_file!r}: {exc}") from exc


def _emit_prompt(
    prompt: str,
    *,
    prompt_file: str | Path | None,
    prompt_stream: TextIO | None,
) -> None:
    if prompt_file is not None:
        prompt_path = Path(prompt_file)
        try:
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"could not write prompt {str(prompt_path)!r}: {exc}") from exc
    else:
        (prompt_stream if prompt_stream is not None else sys.stderr).write(prompt + "\n")


def _resolve_source_notes(
    document: dict[str, Any], extraction: ExtractedSOP,
) -> dict[str, Any]:
    """Resolve and validate note attachments against the extracted SOP.

    Semantic responses historically used a note key such as ``"a"`` even
    though the IR's ``note`` field is the rendered annotation text.  Accept
    that narrow legacy form, normalize it to the source text, and reject any
    response that loses, duplicates, or invents an inline-note attachment.
    """
    normalized = copy.deepcopy(document)
    note_text = {note.key: note.text for note in extraction.notes}
    keys_by_text: dict[str, list[str]] = {}
    for key, text in note_text.items():
        keys_by_text.setdefault(text, []).append(key)
    expected = [reference.key for reference in extraction.inline_references]
    attached: list[str] = []

    for index, node in enumerate(normalized.get("nodes", [])):
        if not isinstance(node, dict) or "note" not in node:
            continue
        value = node["note"]
        if not isinstance(value, str) or not value.strip():
            raise CLIError(f"nodes[{index}].note must be a non-empty string")
        if value in note_text:
            key = value
            node["note"] = note_text[key]
        else:
            matches = keys_by_text.get(value, [])
            if len(matches) != 1:
                raise CLIError(
                    f"nodes[{index}].note does not resolve to an extracted Notes entry"
                )
            key = matches[0]
        attached.append(key)

    missing = sorted(set(expected) - set(attached))
    unexpected = sorted(set(attached) - set(expected))
    duplicate = sorted(
        key for key in set(attached)
        if attached.count(key) != expected.count(key)
    )
    if missing or unexpected or duplicate:
        details: list[str] = []
        if missing:
            details.append(f"missing note attachment(s): {missing}")
        if unexpected:
            details.append(f"unexpected note attachment(s): {unexpected}")
        if duplicate:
            details.append(f"duplicate or misplaced note attachment(s): {duplicate}")
        raise CLIError("; ".join(details))
    return normalized


def _resolve_document(
    response_file: str | None,
    *,
    extraction: ExtractedSOP,
    input_stream: TextIO | None,
) -> dict[str, Any]:
    if response_file is None:
        raise CLIError(
            "a semantic response is required; use --response-file PATH or "
            "--response-file - for stdin"
        )
    response = _read_response(response_file, input_stream=input_stream)
    try:
        document = _resolve_source_notes(parse_semantic_response(response), extraction)
        load_bundle([document])
    except (OSError, TypeError, ValueError) as exc:
        raise CLIError(f"semantic response failed IR validation: {exc}") from exc
    return document


def _write_ir_document(document: dict[str, Any], output_path: Path) -> None:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(dumps_ir_document(document), encoding="utf-8")
    except OSError as exc:
        raise CLIError(f"could not write IR {str(output_path)!r}: {exc}") from exc


def run(
    source: str | Path,
    *,
    output: str | Path | None = None,
    response_file: str | None = None,
    prompt_file: str | Path | None = None,
    input_stream: TextIO | None = None,
    prompt_stream: TextIO | None = None,
) -> Path:
    """Extract, validate, and write one IR document.

    ``response_file`` is either a UTF-8 filename or ``-`` for stdin.  The
    prompt is written to ``prompt_file`` when supplied, otherwise to stderr.
    Validation completes before the output file is created or replaced.
    """

    source_path = Path(source)
    try:
        extraction = extract_markdown(source_path)
        prompt = build_semantic_prompt(extraction)
    except (OSError, ValueError) as exc:
        raise CLIError(str(exc)) from exc

    _emit_prompt(prompt, prompt_file=prompt_file, prompt_stream=prompt_stream)
    document = _resolve_document(
        response_file, extraction=extraction, input_stream=input_stream
    )

    output_path = Path(output) if output is not None else default_ir_path(source_path)
    _write_ir_document(document, output_path)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert SOP Markdown into a validated BPMN IR JSON artifact."
    )
    parser.add_argument("source", type=Path, help="SOP Markdown source")
    parser.add_argument(
        "--response-file",
        metavar="PATH",
        help="semantic-model JSON response, or '-' to read it from stdin",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="optional path for the generated provider-neutral prompt",
    )
    parser.add_argument("-o", "--output", type=Path, help="IR output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run_cli(
        argv,
        parser_factory=build_parser,
        action=lambda args: run(
            args.source,
            output=args.output,
            response_file=args.response_file,
            prompt_file=args.prompt_file,
        ),
        error_types=(CLIError,),
        logger=logger,
        on_success=lambda output: logger.info(f"wrote {output}"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
