"""Strict structural extraction for the SOP Markdown format.

This module deliberately stops before BPMN modeling.  It records the facts
present in the document (including line numbers and inline note references)
so a later semantic step can make and review the modeling decisions.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class MarkdownExtractionError(ValueError):
    """Raised when an SOP does not follow the supported Markdown contract."""

    def __init__(self, message: str, *, line: int | None = None) -> None:
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(prefix + message)


@dataclass(frozen=True)
class Actor:
    name: str
    line: int


@dataclass(frozen=True)
class InlineNoteReference:
    key: str
    section: str
    line: int
    item: int


@dataclass(frozen=True)
class Step:
    number: int
    text: str
    line: int
    bold_actors: tuple[str, ...] = ()
    note_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Option:
    key: str
    title: str
    trigger: str
    steps: tuple[Step, ...]
    line: int


@dataclass(frozen=True)
class Note:
    key: str
    text: str
    line: int


@dataclass(frozen=True)
class Metadata:
    context: tuple[str, ...]
    preconditions: tuple[str, ...]
    outcome: tuple[str, ...]
    version: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedSOP:
    """The deterministic, JSON-serializable structural representation."""

    source_name: str | None
    metadata: Metadata
    actors: tuple[Actor, ...]
    main_path: tuple[Step, ...]
    options: tuple[Option, ...]
    notes: tuple[Note, ...]
    inline_references: tuple[InlineNoteReference, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""

        result = asdict(self)
        result["actors"] = [asdict(actor) for actor in self.actors]
        result["main_path"] = [_step_dict(step) for step in self.main_path]
        result["options"] = [
            {
                "key": option.key,
                "title": option.title,
                "trigger": option.trigger,
                "line": option.line,
                "steps": [_step_dict(step) for step in option.steps],
            }
            for option in self.options
        ]
        result["notes"] = [asdict(note) for note in self.notes]
        result["inline_references"] = [
            asdict(reference) for reference in self.inline_references
        ]
        result["metadata"] = {
            "context": list(self.metadata.context),
            "preconditions": list(self.metadata.preconditions),
            "outcome": list(self.metadata.outcome),
            "version": list(self.metadata.version),
        }
        return result


def _step_dict(step: Step) -> dict[str, Any]:
    return {
        "number": step.number,
        "text": step.text,
        "line": step.line,
        "bold_actors": list(step.bold_actors),
        "note_refs": list(step.note_refs),
    }


HEADING_RE = re.compile(r"^##\s+(.+?)\s*:?[ \t]*$")
OPTION_RE = re.compile(
    r"^###\s+Option\s+([A-Za-z])\s+(?:—|–|-)\s+(.+?)[ \t]*$"
)
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+?)\s*$")
ACTOR_RE = re.compile(r"^\*\s+(.+?)\s*$")
BOLD_ACTOR_RE = re.compile(r"\*\*(.+?)\*\*")
NOTE_MARKER_RE = re.compile(
    r"^\\?\[\s*([A-Za-z][A-Za-z0-9_-]*)\s*\\?\]\s*(.*)$"
)
NOTE_SENTINEL_RE = re.compile(r"^\\?\[\s*end\s*\\?\]\s*$", re.I)
NOTE_REF_RE = re.compile(
    r"\\?\[\s*([A-Za-z][A-Za-z0-9_-]*)\s*\\?\]"
)

EXPECTED_SECTIONS = (
    "Actors",
    "Context",
    "Preconditions",
    "Outcome",
    "Main Path",
    "Options from main path",
    "Notes",
)


def _clean_line(line: str) -> str:
    """Remove Markdown hard-break whitespace before structural matching."""

    return line.rstrip()


def _section_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().rstrip(":"))


def _paragraphs(lines: list[tuple[int, str]], section: str) -> tuple[str, ...]:
    paragraphs: list[str] = []
    current: list[str] = []
    # Unlike the other section parsers, a paragraph spans lines, so this one
    # cannot attribute a failure to a single line number.
    for _, raw in lines:
        text = _clean_line(raw).strip()
        if text:
            current.append(text)
        elif current:
            paragraphs.append("\n".join(current))
            current = []
    if current:
        paragraphs.append("\n".join(current))
    if not paragraphs:
        raise MarkdownExtractionError(f"{section} section must not be empty")
    return tuple(paragraphs)


def _bullets(lines: list[tuple[int, str]], section: str) -> tuple[str, ...]:
    values: list[str] = []
    for line_number, raw in lines:
        text = _clean_line(raw).strip()
        if not text:
            continue
        match = ACTOR_RE.fullmatch(text)
        if not match:
            raise MarkdownExtractionError(
                f"{section} entries must be '*' bullets", line=line_number
            )
        values.append(match.group(1).strip())
    if not values:
        raise MarkdownExtractionError(f"{section} section must not be empty")
    return tuple(values)


def _find_sections(lines: list[str]) -> dict[str, tuple[int, int]]:
    headings: list[tuple[str, int]] = []
    for index, raw in enumerate(lines):
        match = HEADING_RE.fullmatch(_clean_line(raw).strip())
        if match:
            headings.append((_section_name(match.group(1)), index))

    positions: dict[str, int] = {}
    for name, index in headings:
        if name in EXPECTED_SECTIONS:
            if name in positions:
                raise MarkdownExtractionError(
                    f"duplicate section {name!r}", line=index + 1
                )
            positions[name] = index

    missing = [name for name in EXPECTED_SECTIONS if name not in positions]
    if missing:
        raise MarkdownExtractionError(
            "missing required section(s): " + ", ".join(missing)
        )

    ordered = [positions[name] for name in EXPECTED_SECTIONS]
    if ordered != sorted(ordered):
        raise MarkdownExtractionError("required sections are out of order")

    return {
        name: (positions[name], positions[next_name] if next_name else len(lines))
        for name, next_name in zip(
            EXPECTED_SECTIONS,
            (*EXPECTED_SECTIONS[1:], None),
        )
    }


def _section_lines(
    lines: list[str], sections: dict[str, tuple[int, int]], name: str
) -> list[tuple[int, str]]:
    start, end = sections[name]
    return [(index + 1, lines[index]) for index in range(start + 1, end)]


def _version_marker_index(
    lines: list[str], outcome_start: int, main_start: int
) -> int:
    """Locate the ``Version`` marker that splits the Outcome section."""

    marker_index: int | None = None
    for index in range(outcome_start, main_start):
        if _clean_line(lines[index]).strip().rstrip(":") == "Version":
            if marker_index is not None:
                raise MarkdownExtractionError("duplicate Version marker", line=index + 1)
            marker_index = index
    if marker_index is None:
        raise MarkdownExtractionError("missing Version marker")
    return marker_index


def _version_lines(
    lines: list[str], outcome_start: int, main_start: int
) -> list[tuple[int, str]]:
    marker_index = _version_marker_index(lines, outcome_start, main_start)
    return [
        (index + 1, lines[index])
        for index in range(marker_index + 1, main_start)
    ]


def _outcome_lines(
    lines: list[str], outcome_start: int, main_start: int
) -> list[tuple[int, str]]:
    marker_index = _version_marker_index(lines, outcome_start, main_start)
    return [
        (index + 1, lines[index])
        for index in range(outcome_start, marker_index)
    ]


def _numbered_steps(
    lines: list[tuple[int, str]], section: str, *, require_nonempty: bool = True
) -> tuple[Step, ...]:
    steps: list[Step] = []
    expected = 1
    for line_number, raw in lines:
        text = _clean_line(raw).strip()
        if not text:
            continue
        match = NUMBERED_RE.fullmatch(text)
        if not match:
            raise MarkdownExtractionError(
                f"{section} entries must be sequential numbered steps",
                line=line_number,
            )
        number = int(match.group(1))
        if number != expected:
            raise MarkdownExtractionError(
                f"{section} step numbering expected {expected}, got {number}",
                line=line_number,
            )
        step_text = match.group(2).strip()
        steps.append(
            Step(
                number=number,
                text=step_text,
                line=line_number,
                bold_actors=tuple(
                    actor.strip() for actor in BOLD_ACTOR_RE.findall(step_text)
                ),
                note_refs=tuple(
                    reference.group(1).lower()
                    for reference in NOTE_REF_RE.finditer(step_text)
                ),
            )
        )
        expected += 1
    if require_nonempty and not steps:
        raise MarkdownExtractionError(f"{section} section must contain steps")
    return tuple(steps)


def _parse_options(lines: list[str], start: int, end: int) -> tuple[Option, ...]:
    options: list[Option] = []
    seen: set[str] = set()
    index = start + 1
    while index < end:
        raw = _clean_line(lines[index]).strip()
        if not raw:
            index += 1
            continue
        match = OPTION_RE.fullmatch(raw)
        if not match:
            raise MarkdownExtractionError(
                "expected an Option heading", line=index + 1
            )
        key = match.group(1).upper()
        if key in seen:
            raise MarkdownExtractionError(
                f"duplicate option key {key!r}", line=index + 1
            )
        seen.add(key)
        title = match.group(2).strip()
        option_line = index + 1
        index += 1

        while index < end and not _clean_line(lines[index]).strip():
            index += 1
        if index >= end:
            raise MarkdownExtractionError("option is missing its Trigger line", line=option_line)
        trigger_match = re.fullmatch(r"Trigger:\s+(.+?)\s*", _clean_line(lines[index]).strip())
        if not trigger_match:
            raise MarkdownExtractionError(
                "option must be followed by a Trigger line", line=index + 1
            )
        trigger = trigger_match.group(1).strip()
        index += 1

        body_start = index
        while index < end:
            candidate = _clean_line(lines[index]).strip()
            if OPTION_RE.fullmatch(candidate):
                break
            index += 1
        steps = _numbered_steps(
            [(line + 1, lines[line]) for line in range(body_start, index)],
            f"Option {key}",
        )
        options.append(Option(key, title, trigger, steps, option_line))
    if not options:
        raise MarkdownExtractionError("Options from main path section must contain options")
    return tuple(options)


def _parse_notes(lines: list[str], start: int, end: int) -> tuple[Note, ...]:
    notes: list[Note] = []
    seen: set[str] = set()
    current_key: str | None = None
    current_line: int | None = None
    current_text: list[str] = []
    sentinel_line: int | None = None

    def finish() -> None:
        if current_key is not None and current_line is not None:
            text = "\n".join(current_text).strip()
            if not text:
                raise MarkdownExtractionError(
                    f"note {current_key!r} must contain text", line=current_line
                )
            notes.append(Note(current_key, text, current_line))

    for index in range(start + 1, end):
        line_number = index + 1
        raw = _clean_line(lines[index])
        stripped = raw.strip()
        if not stripped:
            if current_key is not None and current_text and current_text[-1] != "":
                current_text.append("")
            continue
        if NOTE_SENTINEL_RE.fullmatch(stripped):
            finish()
            current_key = None
            current_text = []
            sentinel_line = line_number
            for trailing_index in range(index + 1, end):
                if _clean_line(lines[trailing_index]).strip():
                    raise MarkdownExtractionError(
                        "content is not allowed after the Notes end sentinel",
                        line=trailing_index + 1,
                    )
            break
        marker = NOTE_MARKER_RE.fullmatch(stripped)
        if marker:
            finish()
            key = marker.group(1).lower()
            if key in seen:
                raise MarkdownExtractionError(
                    f"duplicate note key {key!r}", line=line_number
                )
            seen.add(key)
            current_key = key
            current_line = line_number
            current_text = [marker.group(2).strip()]
            continue
        if current_key is None:
            raise MarkdownExtractionError(
                "note entries must begin with [key] markers", line=line_number
            )
        current_text.append(stripped)
    else:
        raise MarkdownExtractionError("missing Notes end sentinel")

    if sentinel_line is None:
        raise MarkdownExtractionError("missing Notes end sentinel")
    if not notes:
        raise MarkdownExtractionError("Notes section must contain notes", line=sentinel_line)
    return tuple(notes)


def _read_source(source: str | Path) -> tuple[str, str | None]:
    if isinstance(source, Path):
        try:
            return source.read_text(encoding="utf-8"), source.name
        except (OSError, UnicodeDecodeError) as exc:
            raise MarkdownExtractionError(f"could not read Markdown source: {exc}") from exc
    if not isinstance(source, str):
        raise TypeError("source must be Markdown text, a string path, or a Path")
    if "\n" in source or "\r" in source:
        return source, None
    path = Path(source)
    try:
        return path.read_text(encoding="utf-8"), path.name
    except (OSError, UnicodeDecodeError) as exc:
        raise MarkdownExtractionError(f"could not read Markdown source: {exc}") from exc


def extract_markdown(source: str | Path) -> ExtractedSOP:
    """Extract a supported SOP from Markdown text or a UTF-8 file path."""

    text, source_name = _read_source(source)
    lines = text.splitlines()
    if not lines:
        raise MarkdownExtractionError("Markdown source is empty")
    sections = _find_sections(lines)

    actor_lines = _section_lines(lines, sections, "Actors")
    # Call _bullets first for its non-bullet and empty-section errors; it
    # discards the line numbers, so the actors are matched again here.
    _bullets(actor_lines, "Actors")
    actors = tuple(
        Actor(match.group(1).strip(), line_number)
        for line_number, raw in actor_lines
        if (match := ACTOR_RE.fullmatch(_clean_line(raw).strip()))
    )

    main_start, _ = sections["Main Path"]
    version = _bullets(
        _version_lines(lines, sections["Outcome"][0] + 1, main_start), "Version"
    )
    main_path = _numbered_steps(
        _section_lines(lines, sections, "Main Path"), "Main Path"
    )
    options = _parse_options(
        lines, sections["Options from main path"][0], sections["Options from main path"][1]
    )
    notes = _parse_notes(lines, sections["Notes"][0], sections["Notes"][1])

    references: list[InlineNoteReference] = []
    for step in main_path:
        for key in step.note_refs:
            references.append(InlineNoteReference(key, "main_path", step.line, step.number))
    for option in options:
        for step in option.steps:
            for key in step.note_refs:
                references.append(
                    InlineNoteReference(key, f"option_{option.key}", step.line, step.number)
                )
    note_keys = {note.key for note in notes}
    for reference in references:
        if reference.key not in note_keys:
            raise MarkdownExtractionError(
                f"inline note reference {reference.key!r} has no Notes entry",
                line=reference.line,
            )

    return ExtractedSOP(
        source_name=source_name,
        metadata=Metadata(
            context=_paragraphs(_section_lines(lines, sections, "Context"), "Context"),
            preconditions=_bullets(
                _section_lines(lines, sections, "Preconditions"), "Preconditions"
            ),
            outcome=_paragraphs(
                _outcome_lines(lines, sections["Outcome"][0] + 1, main_start),
                "Outcome",
            ),
            version=version,
        ),
        actors=actors,
        main_path=main_path,
        options=options,
        notes=notes,
        inline_references=tuple(references),
    )


def write_extraction(extraction: ExtractedSOP, destination: str | Path) -> Path:
    """Write an extraction as deterministic, human-readable UTF-8 JSON."""

    path = Path(destination)
    path.write_text(
        json.dumps(extraction.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


__all__ = [
    "Actor",
    "ExtractedSOP",
    "InlineNoteReference",
    "MarkdownExtractionError",
    "Metadata",
    "Note",
    "Option",
    "Step",
    "extract_markdown",
    "write_extraction",
]
