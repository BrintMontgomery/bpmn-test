"""Convert an SOP Markdown document into a reviewed IR JSON artifact.

The semantic-model provider is deliberately outside this module.  A caller
supplies its JSON response through a file or stdin after using the generated
prompt with the provider of their choice.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from ir import load_ir
from markdown_extractor import extract_markdown
from semantic_handoff import build_semantic_prompt, parse_semantic_response


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

    if prompt_file is not None:
        prompt_path = Path(prompt_file)
        try:
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt, encoding="utf-8")
        except OSError as exc:
            raise CLIError(f"could not write prompt {str(prompt_path)!r}: {exc}") from exc
    else:
        (prompt_stream if prompt_stream is not None else sys.stderr).write(prompt + "\n")

    if response_file is None:
        raise CLIError(
            "a semantic response is required; use --response-file PATH or "
            "--response-file - for stdin"
        )

    response = _read_response(response_file, input_stream=input_stream)
    try:
        document = parse_semantic_response(response)
        load_ir(document)
    except (OSError, TypeError, ValueError) as exc:
        raise CLIError(f"semantic response failed IR validation: {exc}") from exc

    output_path = Path(output) if output is not None else default_ir_path(source_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise CLIError(f"could not write IR {str(output_path)!r}: {exc}") from exc
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
    args = build_parser().parse_args(argv)
    try:
        output = run(
            args.source,
            output=args.output,
            response_file=args.response_file,
            prompt_file=args.prompt_file,
        )
    except CLIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
