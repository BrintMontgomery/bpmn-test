# Dev Plan: Clean Error Contracts for the Three Deferred Parse-Failure Findings
*Malformed or unreadable input — corrupt BPMN XML reached through the publish path, corrupt BPMN
XML given directly to the validator CLI, and non-UTF-8 Markdown — now fails through each module's
existing clean-error contract instead of escaping as an uncaught traceback.*

## Why this plan

A recent "Robust" refactor pass over `src/*.py` (commit `a6c7091`, "completed full refactoring")
deliberately did not fix three genuine error-handling gaps it found, listing them instead under
`## 6. Findings — flagged, NOT fixed in this pass` in
`C:\Users\brint\.claude\plans\role-you-are-rustling-candy.md`, per that plan's own "Separate
Concerns" rule: a structural cleanup pass should not silently change what a caller observes for
real (if rare) inputs. All three are still present in the current tree. This plan implements those
three follow-ups, and only those three — no other behavior, layout, or output changes.

### Root cause (verified against the code)

1. **`ir_to_bpmn.py:publish_bundle` lets a validator crash escape its own error contract.**
   `publish_bundle` (`src/ir_to_bpmn.py:150-174`) wraps `write_prepared_bundle` in
   `except (OSError, ValueError)` (157-159) but calls `validate_bundle(staged_paths)` immediately
   after at line 163 with no `try` around it at all. `validate_bundle` (`src/validate_bpmn.py:673-698`)
   and the `Validator` it constructs both call `ET.parse()` directly, which raises
   `xml.etree.ElementTree.ParseError` — not an `OSError`/`ValueError` — on malformed XML. That
   exception type is absent from `error_types=(CLIError,)` at `ir_to_bpmn.py:237` (the CLI's
   `run_cli` wiring) and from `except ir_to_bpmn.CLIError` at `sop_to_bpmn_ui.py:185` (the desktop
   UI's wiring), so both the CLI and the UI would show a raw traceback instead of a clean error.
2. **The same class of bug lives directly in `validate_bpmn.py`, in three places.**
   `Validator.__init__` (`src/validate_bpmn.py:120`, `self.root = ET.parse(self.path).getroot()`)
   and `validate_bundle`'s own first pass (`src/validate_bpmn.py:679`,
   `root = ET.parse(path).getroot()`) both parse unguarded. `main()`
   (`src/validate_bpmn.py:701-712`) already pre-checks argv for missing files (707-711, clean exit
   2) but has no equivalent check for malformed XML, so
   `python src/validate_bpmn.py <corrupt-file.bpmn>` reaches `validate_bundle` → `ET.parse` and
   crashes with a raw traceback instead of the clean exit-2 path the missing-file case already
   gets. The third unguarded call, `ir_to_bpmn.py:89` (`_plane_node_counts`), is the same bug
   reused, and is covered by item 1 above.
3. **`markdown_extractor.py:_read_source` only catches `OSError`.**
   Both branches (`src/markdown_extractor.py:433-447`) call `Path.read_text(encoding="utf-8")`
   (436, 445) inside `except OSError as exc:`. `read_text` raises `UnicodeDecodeError` — a
   `ValueError` subclass, not an `OSError` — when the file isn't valid UTF-8, so a non-UTF-8 source
   escapes uncaught instead of becoming this module's own `MarkdownExtractionError`, unlike every
   other parse failure in the module.

### Design rationale

**Chosen approach: translate each raw exception at the nearest boundary that already promises a
clean error contract, using the exact idiom already established in this codebase** — a `ValueError`
subclass per module (`CLIError` in `ir_to_bpmn.py`, `MarkdownExtractionError` in
`markdown_extractor.py`). `validate_bpmn.py` has no exception class of its own today (its contract
is return-value/exit-code based); this plan adds one (`BpmnParseError`) as one more instance of the
same established pattern, not a new mechanism.

Alternatives considered and rejected:

* **One shared "parse and wrap" helper used by all three modules.** The source plan's own Group 1
  explicitly warned against over-generalizing validation helpers — a shared duplicate-id checker
  would have lost `_validate_message_flows`'s bespoke error text. The same risk applies here: each
  module's error message is already worded for its own callers (`"could not read Markdown
  source: …"` vs. `"could not parse …"`). Three small, independent, boundary-local fixes are safer
  than one shared utility that would need to satisfy three different message shapes.
* **Catching broadly (`except Exception`) at each site.** Would also swallow genuine bugs (e.g. an
  `AttributeError` from a real defect) and misreport them as a clean input error. Catch only the
  exact exception type each finding names: `ET.ParseError` or `UnicodeDecodeError`.
* **Soft-failing inside `Validator` itself** (stuff a parse failure into `self.errors` and return
  `False` from `run()`, treating "not well-formed XML" as just another validation finding).
  Rejected because `Validator.__init__` calls `ET.parse` at line 120, *before* `self.errors` is
  initialized at line 121 — soft-failing would require threading a half-constructed,
  always-fails instance through every downstream method (`run()`, every `check_*`) for one rare
  input case. Raising immediately from `__init__` is a smaller, safer change.

## Cross-Phase Engineering Contract

* Every phase in this plan changes only exception handling on malformed/unreadable input — never
  validation logic, layout, or emitted BPMN/IR/Markdown-extraction output. No golden-file or byte-
  output diff is expected from any phase here.
* Every new or widened `except` clause raises a `ValueError` subclass matching this codebase's
  existing per-module convention, built as `raise NewError(f"...: {exc}") from exc` so the original
  exception survives in `__cause__`.
* Do not widen any `except` clause beyond the exact exception type named in the corresponding
  finding above. Broadening scope beyond that is explicitly deferred (see the closing section).
* A phase is not complete until its new/extended `except` clause is covered by a test that
  triggers the real underlying stdlib exception against a real fixture on disk (actual malformed
  XML, an actual non-UTF-8-encoded file) — not a mocked exception — and the full `pytest` suite
  passes with no drop in pass count versus the start of that phase.

---

## [x] Phase 1: `markdown_extractor.py` — catch non-UTF-8 source files
*Widen `_read_source`'s exception handling so a non-UTF-8 Markdown file raises this module's own
`MarkdownExtractionError` instead of an uncaught `UnicodeDecodeError`. Complexity of coding: Low.*

### 1. Objectives & Scope
* **In scope:** catch `UnicodeDecodeError` alongside `OSError` in both branches of `_read_source`
  (`src/markdown_extractor.py:435-438` and `443-447`), raising the existing
  `MarkdownExtractionError` with a matching message in each case.
* **In scope:** one new regression test proving the fix against a real non-UTF-8 file.
* **Out of scope:** any other error path in `markdown_extractor.py`; the structural extraction
  logic (Actors/Main Path/Options/Notes parsing); the extracted JSON shape; merging the two
  `_read_source` branches (they stay independently duplicated, matching this file's existing
  style).

### 2. Implementation Checklist
- [x] **Task 1:** Widen `except OSError as exc:` at `markdown_extractor.py:437` (the `Path`-input
  branch) to `except (OSError, UnicodeDecodeError) as exc:`; keep the existing
  `raise MarkdownExtractionError(f"could not read Markdown source: {exc}") from exc` body
  unchanged.
- [x] **Task 2:** Apply the identical change to the string-input branch's `except OSError as exc:`
  at `markdown_extractor.py:446`.
- [x] **Task 3:** Add a regression test that writes a file containing bytes that are not valid
  UTF-8 (e.g. a bare `0xFF` byte) and asserts `extract_markdown(path)` raises
  `MarkdownExtractionError` with `"could not read Markdown source"` in the message.

### Implementation Notes
* `Path.read_text(encoding="utf-8")` raises `UnicodeDecodeError` for invalid UTF-8 bytes;
  `UnicodeDecodeError` subclasses `ValueError`, not `OSError` — that mismatch is exactly why
  today's `except OSError` misses it.
* Both call sites share the identical fix; keep the two `except` clauses textually parallel, only
  differing in which `read_text()` call they wrap — this mirrors how the rest of `_read_source`
  already keeps its two branches independently written rather than merged.
* No change to `extract_markdown` (`markdown_extractor.py:450`) or anything downstream — it already
  calls `_read_source` once and propagates whatever it raises.

### Phase 1 Handoff
`markdown_extractor.py` now raises `MarkdownExtractionError` for every documented failure mode of
`_read_source` (`OSError` and `UnicodeDecodeError`). Any existing caller that already catches
`MarkdownExtractionError` (`sop_to_ir.py`, `sop_to_bpmn_ui.py`) is covered automatically with no
changes on its side. Phases 2 and 3 do not depend on this phase and may run before or after it;
this plan sequences it first only because it is the smallest, fully independent change.

### 3. Testing & Verification
* **Test Location:** `tests/test_markdown_to_ir.py`
* **Unit Tests to Write:**
    * [x] `test_extract_markdown_rejects_non_utf8_source`: writes invalid UTF-8 bytes to a temp
      `.md` file and asserts `MarkdownExtractionError` is raised, not `UnicodeDecodeError`.
* **Integration/Regression Tests to Run:**
    * [x] `pytest` (full suite; confirm the pass count does not drop)
* **Acceptance Criteria:** `extract_markdown()` given a non-UTF-8 file raises
  `MarkdownExtractionError`; every previously passing test still passes.

---

## [ ] Phase 2: `validate_bpmn.py` — guard malformed-XML parsing at its source
*Introduce `BpmnParseError` and raise it from the two unguarded `ET.parse()` call sites inside
`validate_bpmn.py`, then give `main()` the same clean exit-2 path it already has for missing files.
Complexity of coding: Low.*

### 1. Objectives & Scope
* **In scope:** add `class BpmnParseError(ValueError)` to `validate_bpmn.py`.
* **In scope:** guard `Validator.__init__`'s `ET.parse(self.path)` at `validate_bpmn.py:120`.
* **In scope:** guard `validate_bundle`'s own `ET.parse(path)` at `validate_bpmn.py:679`.
* **In scope:** extend `main()` (`validate_bpmn.py:701-712`) with a `BpmnParseError` → exit-2 path,
  parallel to its existing missing-file → exit-2 path (707-711).
* **Out of scope:** any validation *check* method (`check_*`), `report()`'s output format, or
  `ir_to_bpmn.py`'s `_plane_node_counts` (that call site is Phase 3). `Validator`'s public
  constructor signature and `validate_bundle`'s `bool` return type are unchanged for well-formed
  input — this phase only changes behavior for malformed XML.

### 2. Implementation Checklist
- [ ] **Task 1:** Define `class BpmnParseError(ValueError): """Raised when a BPMN file is not
  well-formed XML."""` near the top of `validate_bpmn.py`, alongside the other module-level
  constants and above `class Validator`.
- [ ] **Task 2:** Wrap `validate_bpmn.py:120` in
  `try/except ET.ParseError as exc: raise BpmnParseError(f"could not parse {self.path}: {exc}") from exc`.
- [ ] **Task 3:** Wrap `validate_bpmn.py:679` the same way, using that loop's own `path` variable
  in the message.
- [ ] **Task 4:** In `main()`, wrap the existing `return 0 if validate_bundle(paths) else 1`
  (`validate_bpmn.py:712`) in
  `try/except BpmnParseError as exc: logger.info(str(exc)); return 2`.
- [ ] **Task 5:** Add the three regression tests listed under Testing & Verification below.

### Implementation Notes
* `main()` already distinguishes "bad input" (exit 2: no args, missing file) from "ran cleanly but
  found problems" (exit 1: `validate_bundle` returned `False`) from "success" (exit 0). Malformed
  XML is a third case of "bad input," so it gets the same exit-2 treatment as the missing-file
  check immediately above it — do not make it exit 1, which means "well-formed BPMN, but invalid."
* `Validator.__init__` raising immediately means the object is never constructed for malformed
  input, so nothing downstream needs to handle a half-initialized instance (see Design rationale
  for why a soft-fail-into-`self.errors` approach was rejected).
* `validate_bundle`'s first loop (676-688, gathering `process_ids`/`called_ids` across the whole
  bundle) parses each path independently of the `Validator` construction in its second loop
  (690-698) — these are two genuinely separate `ET.parse` call sites today, and both need their own
  guard; fixing only one leaves the other raising raw `ET.ParseError`.
* `tests/test_validate_bpmn.py:259-261` already exercises `validate_bundle` returning `False` for
  a *semantically* missing called process (a file that parses fine but references an unresolvable
  `calledElement`, written via `self.write(...)`, not an actually-missing file) — that must keep
  returning `False`, not raise. Do not conflate that case with this phase's malformed-XML case.
* `logger.info(str(exc))` on the new exit-2 path mirrors the existing missing-file lines' use of
  `logger.info` rather than `.error` — confirmed load-bearing by
  `tests/test_validate_bpmn.py:289-294`'s `redirect_stdout`-based assertion on `main([])`'s usage
  message. Keep the malformed-XML message on the same stdout stream for consistency.

### Phase 2 Handoff
`validate_bpmn.py` now exposes `BpmnParseError` as its documented exception for "not well-formed
XML," raised from both `Validator.__init__` and `validate_bundle`, with its own CLI (`main()`)
already translating that into a clean exit-2 message. Phase 3 imports `BpmnParseError` from this
module and translates it into `ir_to_bpmn.py`'s own `CLIError` contract at the one call site that
currently lets it escape unguarded.

### 3. Testing & Verification
* **Test Location:** `tests/test_validate_bpmn.py`
* **Unit Tests to Write:**
    * [ ] `test_validator_rejects_malformed_xml`: construct `Validator` directly on a file
      containing not-well-formed XML (e.g. an unclosed tag) and assert `BpmnParseError` is raised.
    * [ ] `test_validate_bundle_rejects_malformed_xml`: call `validate_bundle([...])` with one
      well-formed and one malformed path and assert `BpmnParseError` is raised (not a raw
      `ET.ParseError`, and not a silent `False`).
    * [ ] `test_main_reports_malformed_xml_cleanly`: call `main([str(corrupt_path)])` under
      `contextlib.redirect_stdout`, following the existing `test_main_requires_paths` pattern
      (`tests/test_validate_bpmn.py:289-294`); assert the return value is `2` and the captured
      output identifies the file.
* **Integration/Regression Tests to Run:**
    * [ ] `pytest` (full suite)
    * [ ] `python scripts/check_golden.py` (must stay unchanged — this phase only touches invalid-
      input paths)
* **Acceptance Criteria:** all three new tests pass; `python src/validate_bpmn.py <corrupt-file.bpmn>`
  exits 2 with a clean message instead of a traceback; no previously-passing test regresses.

---

## [ ] Phase 3: `ir_to_bpmn.py` — close the publish-path and plane-count gaps
*Catch `BpmnParseError`/`ET.ParseError` at the two unguarded call sites inside `ir_to_bpmn.py` and
translate both into this module's own `CLIError`, so the CLI and the desktop UI both already handle
them for free. Complexity of coding: Low. Depends on Phase 2 (`BpmnParseError`).*

### 1. Objectives & Scope
* **In scope:** import `BpmnParseError` from `validate_bpmn` alongside the existing
  `FLOW_NODE_TAGS, local, validate_bundle` import at `ir_to_bpmn.py:16`.
* **In scope:** guard the `validate_bundle(staged_paths)` call inside `publish_bundle`
  (`ir_to_bpmn.py:163`), translating `BpmnParseError` into `CLIError`.
* **In scope:** guard `_plane_node_counts`'s own `ET.parse(path)` call (`ir_to_bpmn.py:89`),
  translating `ET.ParseError` into `CLIError`.
* **Out of scope:** `preflight`, `run`, or any of the existing `(OSError, IRValidationError,
  ValueError)` catches elsewhere in this file — those already have working contracts for their own
  inputs. No changes to `sop_to_bpmn_ui.py`: it already catches `ir_to_bpmn.CLIError` around both
  `publish_bundle` and `report_published` (`sop_to_bpmn_ui.py:182-186`), so it picks up this fix
  automatically once `ir_to_bpmn.py` raises `CLIError` instead of letting the parse error escape.

### 2. Implementation Checklist
- [ ] **Task 1:** Change the import at `ir_to_bpmn.py:16` to
  `from validate_bpmn import BpmnParseError, FLOW_NODE_TAGS, local, validate_bundle`.
- [ ] **Task 2:** In `publish_bundle` (`ir_to_bpmn.py:150-174`), wrap the
  `if not validate_bundle(staged_paths):` check (163) so a `BpmnParseError` raised out of
  `validate_bundle` is caught and re-raised as `raise CLIError(str(exc)) from exc`, consistent with
  the `write_prepared_bundle` catch immediately above it (157-159).
- [ ] **Task 3:** In `_plane_node_counts` (`ir_to_bpmn.py:88-109`), wrap
  `root = ET.parse(path).getroot()` (89) in
  `try/except ET.ParseError as exc: raise CLIError(f"could not parse {path}: {exc}") from exc`.
- [ ] **Task 4:** Add the two regression tests listed under Testing & Verification below.

### Implementation Notes
* `publish_bundle` and `report_published` are called from two places today: `run()`
  (`ir_to_bpmn.py:210-211`, wrapped only by `run_cli`'s `error_types=(CLIError,)` at line 237) and
  `sop_to_bpmn_ui.py`'s `build_bpmn` (183-185, wrapped by `except ir_to_bpmn.CLIError`). Neither
  wrapper catches a raw `ET.ParseError`/`BpmnParseError` today — fixing both call sites inside
  `ir_to_bpmn.py` itself, rather than at each of its two callers, is what makes both paths clean
  with one change, per this plan's Design rationale of translating at the nearest boundary that
  owns the contract.
* `_plane_node_counts` runs from `report_published` (177-187) only after `publish_bundle` has
  already atomically published the same files, so in normal operation the file it re-parses is one
  this program just wrote and validated moments earlier. This guard is defensive — matching the
  finding's explicit call-out of this site as unguarded — not a fix for a currently-reachable crash
  in the happy path.
* Since `write_prepared_bundle` always emits well-formed XML by construction, exercising the
  `publish_bundle` guard in a test means simulating a `BpmnParseError` from `validate_bundle`
  directly (e.g. monkeypatching `ir_to_bpmn.validate_bundle` for that one test) rather than staging
  genuinely malformed XML on disk — call this out in the test itself so it stays honest about what
  it does and does not exercise end-to-end. The `_plane_node_counts` test, by contrast, can and
  should use a real malformed file on disk, matching this plan's Cross-Phase Engineering Contract.
* Mirror the message shape already used in Phase 2 (`f"could not parse {path}: {exc}"`) so all
  three phases read consistently.

### Phase 3 Handoff
This is the final phase of this plan. Combined with Phases 1 and 2, every call site named in
`role-you-are-rustling-candy.md` §6 now raises its owning module's existing clean-error type
instead of an uncaught traceback, and both consumers of `ir_to_bpmn.py` (its own CLI and the
desktop UI) observe that through the contract each already has, with no further caller-side
changes needed. No later phase in this plan builds on this one.

### 3. Testing & Verification
* **Test Location:** `tests/test_cli.py` (covers `ir_to_bpmn.py`'s CLI/library functions)
* **Unit Tests to Write:**
    * [ ] `test_publish_bundle_wraps_validator_parse_error_as_cli_error`: with `validate_bundle`
      made to raise `BpmnParseError` for one call, call `publish_bundle` and assert `CLIError` is
      raised (not `BpmnParseError`).
    * [ ] `test_plane_node_counts_rejects_malformed_xml`: write a malformed `.bpmn` file directly
      to disk and call `ir_to_bpmn._plane_node_counts(path)`, asserting `CLIError` is raised.
* **Integration/Regression Tests to Run:**
    * [ ] `pytest` (full suite)
    * [ ] `python scripts/check_golden.py`
* **Acceptance Criteria:** both new tests pass; `pytest`'s full-suite pass count does not drop; no
  observable behavior change for well-formed input (golden check untouched); a malformed staged
  BPMN file surfaces as `WorkflowError` in the desktop UI and as a single `error: …` CLI line,
  never a traceback.

---

## Deferred Items And Explicit Non-Goals

* No change to validation logic, layout, or emitted BPMN/IR/Markdown-extraction output for
  well-formed input in any phase — this plan is pure error-path hardening.
* Broadening any `except` clause beyond the exact exception type named in the corresponding finding
  (e.g. a catch-all `except Exception`) is explicitly rejected; see Design rationale.
* `sop_to_ir.py`'s error handling needs no change — it already catches `MarkdownExtractionError`
  end-to-end and is covered automatically once Phase 1 lands.
* Auditing the rest of the codebase for other unguarded I/O beyond the three findings named in
  `role-you-are-rustling-candy.md` §6 is out of scope here; that would be a separate, freshly
  re-verified follow-up plan, not an extension of this one.
* No new CLI flags, no changes to `logging_setup.py` or `cli_support.py`, and no changes to the
  desktop UI (`sop_to_bpmn_ui.py`) — its existing `except ir_to_bpmn.CLIError` handling is exercised
  by this plan, not modified by it.
