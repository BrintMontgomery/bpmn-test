"""Convenience wrapper for the two-stage SOP-to-BPMN workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

import ir_to_bpmn
import sop_to_ir


def run(
    source: str | Path,
    *,
    ir_output: str | Path | None = None,
    output_dir: str | Path | None = None,
    response_file: str | None = None,
    prompt_file: str | Path | None = None,
    input_stream: TextIO | None = None,
    prompt_stream: TextIO | None = None,
    repair_layout: bool = False,
) -> list[Path]:
    """Use an existing adjacent IR or create one, then emit validated BPMN."""

    source_path = Path(source)
    ir_path = Path(ir_output) if ir_output is not None else sop_to_ir.default_ir_path(source_path)
    if not ir_path.exists():
        sop_to_ir.run(
            source_path,
            output=ir_path,
            response_file=response_file,
            prompt_file=prompt_file,
            input_stream=input_stream,
            prompt_stream=prompt_stream,
        )
    return ir_to_bpmn.run(
        [ir_path], output_dir=output_dir, repair_layout=repair_layout
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an SOP Markdown document into validated BPMN."
    )
    parser.add_argument("source", type=Path, help="SOP Markdown source")
    parser.add_argument(
        "--response-file",
        metavar="PATH",
        help="semantic-model JSON response, or '-' to read it from stdin",
    )
    parser.add_argument("--prompt-file", type=Path, help="optional semantic prompt path")
    parser.add_argument("--ir-output", type=Path, help="IR artifact path")
    parser.add_argument("-o", "--output-dir", type=Path, help="BPMN output directory")
    parser.add_argument(
        "--repair-layout", action="store_true",
        help="flatten incompatible authored phases in memory for this build",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        paths = run(
            args.source,
            ir_output=args.ir_output,
            output_dir=args.output_dir,
            response_file=args.response_file,
            prompt_file=args.prompt_file,
            repair_layout=args.repair_layout,
        )
    except (sop_to_ir.CLIError, ir_to_bpmn.CLIError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"validated {len(paths)} BPMN file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
