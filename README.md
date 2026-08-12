
# SOP to BPMN Pipeline

Convert Standard Operating Procedure (SOP) Markdown documents into validated, auto-laid-out BPMN 2.0 diagrams — and back again.

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

See [MARKDOWN_AUTHORING.md](MARKDOWN_AUTHORING.md) for the full specification.

## Output

| Input | Output |
|-------|--------|
| `OFC-004 — Case Manager Intakes Consumer.md` | `OFC-004.bpmn`, `OFC-004.mmd` |
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

## Example

```bash
# Extract and validate an SOP Markdown file
python markdown_extractor.py "OFC-004 — Case Manager Intakes Consumer.md"

# After semantic modeling produces an IR JSON, emit BPMN
python ir_to_bpmn.py OFC-004.ir.json

# Validate the emitted bundle
python validate_bpmn.py OFC-004.bpmn

# Generate an interactive HTML preview
python build_preview.py
```
