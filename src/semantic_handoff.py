"""Provider-neutral handoff from extracted SOP structure to IR modeling."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bpmn_engine import ProcessModel
from ir import IR_SCHEMA_PATH, load_ir
from markdown_extractor import ExtractedSOP


class SemanticHandoffError(ValueError):
    """Raised when a semantic-model response is not a JSON object."""


MODELING_RULES = """Modeling rules:
1. The first bold actor on a main-path step is the owning lane candidate.
2. Later bold actors are counterparties unless the semantic model explicitly
   gives them a separate task and lane handoff.
3. Each option has an entry gateway in the main path; conditional branches
   inside an option require their own internal gateway in that option.
4. Every extracted inline note reference must attach exactly once to the
   modeled task or event that carries it. Set that node's `note` to the full
   text of the matching extracted Notes entry, never merely its key.
5. Decomposition proposals must include a one-line rationale for every split.
6. `ann_above`, when present, is an array of lane IDs from `lanes`; never put
   source filenames, version text, lane names, or other prose there. Omit it
   or use an empty array when no lane annotation placement is specified.
7. `documents`, when present, is the generated BPMN output manifest, not a
   list of source Markdown documents. For one process, omit it or use exactly
   `{\"id\": <process_id>, \"file\": <name ending in .bpmn>, \"role\": \"main\"}`.
   For a bundle, include exactly one entry per process ID, with one `main`
   entry and `global` entries for the other process IDs.
8. Every branching `gateway_x` must have exactly one outgoing edge whose
   `condition` is omitted or an empty string; every other outgoing edge must
   have a non-empty condition.
9. Phase order is a global layout constraint: a later phase cannot contain a
   branch node whose path begins before an earlier phase finishes. Branching
   options should share the enclosing phase unless they are decomposed into a
   separate BPMN scope. Do not assign exception branches to later phases when
   they rejoin or loop back into an earlier main-path step.
10. Give every outgoing edge of a branching `gateway_x` a non-empty `label`.
    Use the branch condition as the label when it is concise; use `Otherwise`
    for its default branch when no more specific evidence is available.
11. Return one JSON object conforming to the supplied IR schema. Do not return
   Markdown, commentary, or a second representation of the IR.
"""


def _extraction_dict(extraction: ExtractedSOP | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(extraction, ExtractedSOP):
        return extraction.to_dict()
    if isinstance(extraction, Mapping):
        return dict(extraction)
    raise TypeError("extraction must be an ExtractedSOP or mapping")


def _read_schema(schema_path: str | Path) -> str:
    try:
        return Path(schema_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SemanticHandoffError(f"could not read IR schema: {exc}") from exc


def _format_semantic_prompt(extraction_dict: dict[str, Any], schema: str) -> str:
    """Assemble the complete prompt text; no I/O."""
    structural_json = json.dumps(extraction_dict, ensure_ascii=False, indent=2)
    return (
        "Convert the structurally extracted SOP below into the version-1 BPMN "
        "intermediate representation. Use only evidence in the extraction and "
        "make uncertain modeling judgments explicit in the IR documentation.\n\n"
        + MODELING_RULES
        + "\n\nStructural extraction:\n```json\n"
        + structural_json
        + "\n```\n\nIR JSON Schema:\n```json\n"
        + schema
        + "\n```\n"
    )


def build_semantic_prompt(
    extraction: ExtractedSOP | Mapping[str, Any],
    *,
    schema_path: str | Path = IR_SCHEMA_PATH,
) -> str:
    """Build a complete prompt without making a provider or network call."""

    schema = _read_schema(schema_path)
    return _format_semantic_prompt(_extraction_dict(extraction), schema)


def parse_semantic_response(response: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    """Parse a JSON object returned by a semantic model.

    A single JSON code fence is accepted because it is a common transport
    wrapper from LLMs; no prose or heuristic extraction is accepted.
    """

    if isinstance(response, Mapping):
        return dict(response)
    if isinstance(response, bytes):
        try:
            response = response.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SemanticHandoffError("semantic response is not UTF-8") from exc
    if not isinstance(response, str):
        raise TypeError("response must be JSON text, bytes, or a mapping")
    text = response.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) < 3:
            raise SemanticHandoffError("semantic response code fence is empty")
        language = lines[0].strip()[3:].strip().lower()
        if language not in {"", "json"}:
            raise SemanticHandoffError("semantic response must use a JSON code fence")
        text = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SemanticHandoffError(
            f"semantic response is not valid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise SemanticHandoffError("semantic response must be a JSON object")
    return value


def validate_semantic_response(
    response: str | bytes | Mapping[str, Any],
) -> ProcessModel:
    """Parse and validate a semantic response using the established IR loader.

    An invalid document raises :class:`IRValidationError` from ``load_ir``.
    """

    return load_ir(parse_semantic_response(response))


__all__ = [
    "MODELING_RULES",
    "SemanticHandoffError",
    "build_semantic_prompt",
    "parse_semantic_response",
    "validate_semantic_response",
]
