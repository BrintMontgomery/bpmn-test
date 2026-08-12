
# SOP to BPMN Pipeline

Convert Standard Operating Procedure (SOP) Markdown documents into validated, auto-laid-out BPMN 2.0 diagrams — and back again.

## Desktop UI

For a guided local workflow, run:

```bash
py src/sop_to_bpmn_ui.py
```

## What It Does

This project implements a deterministic pipeline that reads a strictly-formatted SOP Markdown file, models its workflow as an intermediate JSON representation, and emits a production-ready `.bpmn` file (plus optional Mermaid preview). The key stages are:

1. **Structural extraction** — A regex-based extractor pulls actors, main-path steps, option branches, and inline notes from the Markdown template into inspectable JSON. No modeling judgment is applied here; it is purely mechanical.

2. **Semantic modeling (LLM-assisted)** — A provider-neutral prompt converts the extracted JSON into a versioned Intermediate Representation (IR) that encodes lanes, phases, gateways, task types, external participants, message flows, and decomposition policy. The IR is validated against a JSON Schema before it ever reaches the layout engine, so malformed output is caught at load time, not after rendering.

3. **Auto layout** — A shared layout engine computes column placement via longest-path topology, enforces authored phase order as a hard monotonic bound, derives sub-rows from branch-nesting depth, and uses conflict-graph coloring to keep overlapping option branches on separate rows. Collisions are resolved by construction; a bounded deterministic nudge loop exists only as a fallback.

4. **BPMN emission** — The engine emits standard BPMN 2.0 XML with full DI geometry. It supports:
   - Lanes, pools, and external participants with message flows
   - Exclusive and parallel gateways with default-path markers
   - Timer and message catch/throw events
   - Collapsed subprocesses with child lane sets and independent coordinate planes
   - Call activities for genuinely reusable procedures
   - Link throw/catch events for off-page connectors
   - Text annotations with automatic association edges

5. **Decomposition** — Large SOPs can be split automatically across multiple diagrams using collapsed subprocesses (default) or call activities (for cross-SOP reuse). Splits are triggered by configurable thresholds (node count, column count, pool width) and are always opt-in per process.

6. **Validation** — A strict validator checks every emitted file (and the whole bundle) for:
   - One start event per scope and reachability from it
   - Scope-local geometry with no cross-plane overlap
   - Exclusive gateway default-branch invariants
   - Link event 1:1 pairing
   - Subprocess DI consistency (collapsed vs. expanded)
   - No sequence flows crossing scope boundaries
   - Called-process resolution across the bundle

   Before any BPMN output is staged, the build also preflights every process
   scope through the layout engine. Layout-phase errors are rejected by
   default. The CLI and desktop UI provide an explicit build-only repair mode
   (`--repair-layout`) that flattens incompatible authored phases in memory;
   the source IR is never rewritten.

7. **Preview** — A self-contained HTML preview embeds the BPMN into a bpmn-js viewer with drill-down breadcrumbs, a document switcher for multi-file bundles, and dynamic download links.

## Markdown Authoring Convention

SOPs must follow a stable template:

```markdown
# Process Title

## Actors
* Actor One  
* Actor Two  

## Context
...

## Preconditions
* ...

## Outcome
...

## Main Path
1. **Actor** performs a step.  
2. **Actor** performs the next step.  

## Options from main path
### Option A — Title
Trigger: ...

1. Step text.  
2. Branching text.  

## Notes
\[a\] Note text.  
\[ end \]
```

See [the Markdown authoring guide](docs/MARKDOWN_AUTHORING.md) for the full specification.

## Repository Layout

```
src/        Pipeline, validation, layout, and preview source code
tests/      Unit and regression tests
docs/       Authoring guides, plans, and design notes
examples/   Sample SOP inputs, reviewed IR, and generated BPMN artifacts
assets/     Vendored browser assets used by the HTML preview
scripts/    Repository maintenance commands
```

## Output

| Input | Output |
|-------|--------|
| `examples/ir/OFC-001.ir.json` | `examples/bpmn/OFC-001.bpmn` |
| `examples/ir/OFC-004.ir.json` | `examples/bpmn/OFC-004.bpmn` |
| Validated IR JSON | `.bpmn` bundle (+ optional separate called-process files) |

## Architecture

```
markdown/ ──► markdown_extractor.py ──► structural JSON
                                                  │
                                                  ▼
                                        semantic_handoff.py
                                        (LLM + IR schema)
                                                  │
                                                  ▼
                                                ir.py
                                          (validated ProcessModel)
                                                  │
                                                  ▼
                                          bpmn_engine.py
                                          + decomposition.py
                                                  │
                                                  ▼
                                          .bpmn + .mmd
                                          ─────────────
                                          validate_bpmn.py
                                          build_preview.py
```

## Key Properties

- **Deterministic** — The same IR always produces the same diagram, making golden-file regression testing viable.
- **Collision-free by construction** — Layout is designed to avoid overlaps rather than patching them afterward.
- **Hierarchical** — Collapsed subprocesses render as drill-down planes inside a single `.bpmn` file, with proper lane inheritance at each level.
- **Separation of concerns** — Markdown parsing, semantic modeling, layout, and emission are independent stages. The IR is a reviewable, diffable artifact that can be committed to version control.

## Requirements

- Python 3.9+
- Standard library only (no `pip install` required for the core pipeline)
- Tk 8.6 (included with the installed Windows Python) for the optional desktop UI



Select an SOP Markdown file and validate its template. The app either validates
an adjacent reviewed `.ir.json` file or helps you create one by copying or
saving the generated semantic prompt and accepting the returned JSON. It then
builds validated BPMN files beside the Markdown source, reports the number
created, and opens the output folder. Each BPMN file uses the Markdown
basename with a `.bpmn` extension; bundles use `_0`, `_1`, and later suffixes
when more than one file is emitted. No network access or additional package is
required.

Run the regression suite with:

```bash
python -m unittest discover -s tests -t .
```

## Command-line / Developer Workflow

The desktop UI above is the recommended path for guided local use. These
commands are optional for automation, troubleshooting, and working with
individual pipeline stages.

```bash
# Extract and validate an SOP Markdown file
python src/markdown_extractor.py "examples/markdown/OFC-004 — Case Manager Intakes Consumer.md"

# After semantic modeling produces an IR JSON, emit BPMN
python src/ir_to_bpmn.py examples/ir/OFC-004.ir.json

# Explicitly repair incompatible authored phase layout in memory
python src/ir_to_bpmn.py examples/ir/OFC-004.ir.json --repair-layout

# Validate the emitted bundle
python src/validate_bpmn.py examples/bpmn/OFC-004.bpmn

# Generate an interactive HTML preview
python src/build_preview.py
```
