# Dev Plan — Generalize SOP → BPMN Generation

## Goal

Today, turning a markdown SOP (like `OFC-001 …md`, `OFC-004 …md`) into a `.bpmn`
file means hand-writing a new ~600–900 line Python script per process
(`generate_bpmn.py`, `generate_bpmn_ofc004.py`) that duplicates the entire
layout engine and only changes the `NODES`/`EDGES` model at the top. Building
OFC-004 this way took a full manual pass: read the markdown, design lanes/
phases/nodes/edges by hand, transcribe into dataclasses, then iterate against
`validate_bpmn.py` fixing column/subrow collisions one error at a time.

The target end state: drop a new SOP markdown file in, run one command, get a
validated `.bpmn` out — without hand-writing a new script or manually tuning
layout coordinates. When the process is too large for one readable sheet, the
same command decomposes it across sub-diagrams using standard BPMN
constructs rather than emitting one unreadable wall.

```
py sop_to_bpmn.py "OFC-00X — Some Process.md"   →   OFC-00X.bpmn (validated)
```

## Current State (verified against the code, not assumed)

- `generate_bpmn.py` (OFC-001) / `generate_bpmn_ofc004.py` (OFC-004) —
  self-contained: model data + layout engine + XML/DI emitter in one file.
- **The two engines are logically identical, but not equal in value.**
  Diffing `node_size` → `edge_label_bounds` in both files shows the only
  differences are deleted docstrings and comments: `generate_bpmn_ofc004.py`
  is a comment-stripped copy. Extraction must take
  **`generate_bpmn.py` as the base** — it carries the rationale ("why the
  corridor drops before the target", "why the SO annotation band goes
  above") that the OFC-004 copy threw away. That rationale is the expensive
  part; the code is the cheap part.
- **The emitters are *not* identical.** `generate_bpmn.py` additionally has:
  a second collapsed participant pool (`Participant_AdmissionsCoordinator`,
  hand-placed at `POOL_Y - AC_POOL_H - 110`), a `messageFlow` into the start
  event, `ANN_ABOVE = {SO}` (per-lane annotation band placement), and a
  whole Mermaid emitter (`build_mermaid`, ~70 lines) writing `OFC-001.mmd`.
  None of this exists in the OFC-004 file. Any shared engine must support
  all of it on day one or OFC-001 cannot be re-pointed at it.
- `build_preview.py` — **not mentioned in the original plan, and it is a
  hard dependency.** It does `import generate_bpmn as model` and reaches
  into module-level internals (`model.SO`, `model.LED`, …, `model.NODES`),
  plus a hand-written `OPTIONS` table keyed by gateway id. Retiring
  `generate_bpmn.py` breaks it.
- `validate_bpmn.py` — generic, takes any `.bpmn` path, exposes a
  `Validator` class plus `main()`. It parses a file from disk and reports
  failures as **free-text strings** in `self.errors`. `main()` still
  defaults to `OFC-001.bpmn` when given no argv.
- `OFC-004.bpmn` currently passes: 55 flow nodes, 63 sequence flows,
  6 annotations, 17,526 assertions, zero errors.
- **`OFC-001.md`, `OFC-001.bpmn`, and `OFC-001.mmd` are not in this
  directory.** Only the OFC-004 markdown and `.bpmn` are present. There is
  no baseline to diff OFC-001 against today.
- **This directory is not a git repository.** There is no undo.
- Column (`col`) and sub-row (`subrow`) placement is chosen **by hand** per
  node, and collisions are found and fixed **by hand**, one
  `validate_bpmn.py` run at a time.
- `Node.phase` is **dead data in the BPMN path.** It is consumed only by
  `build_mermaid()` in `generate_bpmn.py` (as subgraph grouping) and is
  referenced nowhere at all in `generate_bpmn_ofc004.py`. Nothing about
  phases reaches the `.bpmn` output today.

Facts that matter specifically for decomposition:

- **The engine is single-scope from top to bottom.** `build_xml` emits one
  `bpmn:process`, one `laneSet`, and one `BPMNPlane`; `compute_layout`
  assumes one global coordinate space with one pool and one lane stack.
  Nothing in it can express a second sheet.
- **`validate_bpmn.py` sees only the direct children of `bpmn:process`.**
  `nodes`, `flows`, `annotations`, and `associations` are all built with
  `for el in proc` — a flat iteration. Flow nodes nested inside a
  `subProcess` are invisible to every check. `check_di` likewise resolves
  `BPMNDiagram/BPMNPlane` to the **first** plane only.
- `subProcess` and `callActivity` are already in `FLOW_NODE_TAGS`, so the
  tag vocabulary needs no change — but the traversal does.
- **The vendored viewer already supports all three mechanisms.**
  `vendor/bpmn-navigated-viewer.production.min.js` is bpmn-js **v17.11.1**;
  it carries the drilldown module and `vendor/bpmn-js.css` defines
  `.bjs-breadcrumbs` and `.bjs-drilldown`. `SubProcess`, `CallActivity`,
  `LinkEventDefinition`, and `BPMNPlane` all appear in the bundle. So
  multi-plane drill-down works in the existing preview with no new vendor
  files — a real constraint removed.
- `build_preview.py` embeds exactly **one** BPMN string into one viewer,
  with the download link hardcoded to `OFC-001.bpmn`. Multi-*file* output
  needs a document switcher there; multi-*plane* output does not.

## Phase 0 — Make the refactor reversible (do this first) [x]

Everything below is a refactor whose success criterion is "the output didn't
change." That criterion is unenforceable right now.

1. [x] `git init`; commit the current tree as-is. Nothing else starts until
   this is done.
2. [x] Locate the OFC-001 source markdown and its generated `OFC-001.bpmn` /
   `OFC-001.mmd`, or regenerate them with `py generate_bpmn.py`. Commit the
   outputs as **golden files**.
3. [x] Confirm both goldens pass: `py validate_bpmn.py OFC-001.bpmn` and
   `py validate_bpmn.py OFC-004.bpmn`.
4. [x] Add a one-line regression check (`check_golden.py` or a `Makefile`
   target) that regenerates both diagrams and byte-diffs them against the
   goldens. This is the gate that every phase below runs against.
5. [x] Add `__pycache__/` to `.gitignore`.

## Phase 1 — Extract the shared engine [x]

Pull the layout algorithm and BPMN XML/DI emitter out of `generate_bpmn.py`
(the commented copy — see Current State) into `bpmn_engine.py`:

- [x] `Node` / `Edge` dataclasses (already process-agnostic)
- [x] `node_size()`, `annotation_height()`, `compute_layout()`,
  `corridor_offsets()`, `edge_waypoints()`, `event_label_bounds()`,
  `edge_label_bounds()`
- [x] `q()`, `element_tag()`, `flow_id()`, `add_doc()`, `build_xml()`,
  `write_bpmn()`
- [x] `build_mermaid()` and its helpers (`mermaid_label`, `wrap`,
  `mermaid_node`) — optional per caller, but it must move too, or OFC-001
  loses its preview and the "the two can never drift apart" guarantee in
  that file's own docstring.

- [x] Input becomes a plain data bundle: `lanes`, `phases`, `nodes`, `edges`,
`process_id`, `participant_name`, `process_doc` — no process-specific
constants baked in (today's `POOL_X`, `TASK_W`, etc. stay as engine
defaults, but lane lists / phase lists / the model itself move to the
caller).

Three things the original plan treated as out of scope but that Phase 1
cannot avoid, because `generate_bpmn.py` uses all three:

- [x] `ann_above` — the set of lanes whose annotation band sits above their
  tasks. Today a module constant; becomes a per-process input.
- [x] **External participants and message flows** — OFC-001's collapsed
  Admissions Coordinator pool and its message flow are currently hardcoded
  inside `build_xml`, including hand-computed geometry and a hand-placed
  label box. These must become first-class engine inputs
  (`external_pools`, `message_flows`), not a special case. This was listed
  as an Open Question; it is actually a Phase 1 blocker.
- [x] The Mermaid emitter, per above.

- [x] **Build for scopes now, even though Phase 1 emits only one.** Decomposition
(Phase 3b) needs `compute_layout()` and `build_xml()` to run once per
*scope* — the top-level process plus each collapsed subprocess plus each
separate called process — with each scope owning its own coordinate space,
its own column widths, and its own optional lane stack. Retrofitting that
after the fact means rewriting both functions, so give them a `scope`
parameter and a `Layout` result object in Phase 1 and call them with a
single scope. Keep pool/participant emission separate from process
emission: a called global process has no pool, and a subprocess plane has
no pool of its own.

- [x] **Exit criterion:** both generators re-pointed at the shared module, and
`check_golden.py` from Phase 0 reports byte-identical output for OFC-001
and OFC-004. Commit here. This is the last point where byte-identity is
achievable, so do not let it slip past.
- [x] Unit and regression tests cover the shared engine, external message
  flows, scope-aware layout, Mermaid output, and preview compatibility.

## Phase 1b — Unbreak `build_preview.py` [x]

- [x] `build_preview.py` consumes reusable process/model bundles instead of
  importing `generate_bpmn` and reading module-level process constants.
- [x] Move option metadata and process-specific preview copy into the model
  bundle so the renderer has no hand-written OFC-001 `OPTIONS` table.
- [x] Extract OFC-001 data into a dedicated provider while retaining
  `generate_bpmn.py` as a compatibility generator wrapper.
- [x] Support multiple emitted BPMN files with one lazily-created viewer per
  file, an accessible document switcher, and dynamic download filenames.
- [x] Enable the vendored bpmn-js v17.11.1 drill-down breadcrumbs without
  changing vendor files.
- [x] Add unit and regression coverage for model consumption, options,
  dynamic documents/downloads, and bundle validation.

## Phase 2 — Auto layout (remove hand-tuned columns/subrows) [x]

Manual `col`/`subrow` assignment is the main source of iteration pain (most
of the fix-up work on OFC-004 was nudging these numbers).

- [x] **Column** — longest-path distance from the start event via a topological
pass over `EDGES`, ignoring `loop=True` back-edges. Branch nodes on the
same logical step naturally land in the same column. Add one constraint the
original plan missed: **`phase` order is a hard monotonic bound on column
order.** Phases are already authored, already ordered, and are currently
dead data — this gives them a job, and it stops a long option branch from
dragging a late-phase node left of an early-phase one. If graph depth and
phase order disagree, that is a modeling error worth reporting, not
silently resolving.

- [x] **Subrow** — derived from branch nesting depth within a lane: the default
path stays on subrow 0; each nested `Yes`/option branch increments the
subrow for the duration of its branch, matching what was done by hand.

- [x] Both run **per scope**: a subprocess's children are laid out in their own
coordinate space, and depth/phase constraints restart at that scope's own
start event.

- [x] **Collision handling** — the original plan proposed a hill-climbing loop
that bumps a node's col/subrow by one whenever the validator complains.
Two problems with that as written:

- [x] `Validator` reports failures as **formatted strings** (`"shapes A and B
  overlap"`, `"edge X passes through Y"`), and it parses a file from disk.
  A repair loop cannot consume that. It needs structured findings
  (element ids, kind, offending geometry) from an in-memory model. See
  Phase 2b.
- [x] Nudging one node at a time against a global layout is a weak search: a
  col bump reshuffles every column width downstream, so each nudge
  invalidates the evidence that motivated it, and the loop can oscillate.

Prefer **collision-free by construction**, with the validator as a gate
rather than as the search oracle:

- [x] Assign subrows per lane by conflict-graph coloring over branch column
  spans (two branches that overlap in columns must not share a subrow).
  This is the rule that was being applied by hand anyway.
- [x] Reserve the routing corridor before the target column as layout-owned
  space, so `edge_waypoints`' dog-leg never has to be repaired after the
  fact.
- [x] Keep a *bounded, deterministic* nudge loop as a fallback only, with a
  fixed visitation order so the same input always produces the same
  output. Non-deterministic layout would make every golden diff unusable.
- [x] Surface any still-unresolved collision as a clear error naming the two
  elements — never emit a broken diagram.

- [x] **Watch the cost:** `check_geometry` is O(shapes × edge segments) and
already fires 17.5k assertions on a 55-node diagram. That is milliseconds
today, but a nudge loop that re-validates from disk on every attempt
multiplies it by the attempt count *and* by XML serialize/parse round
trips. Run the geometry pass in memory.

- [x] One caveat to state plainly: if the generator optimizes against the
validator, it inherits the validator's blind spots (axis-aligned boxes
only, `pad = 4.0`, no text-metric checks). Passing validation stops meaning
"looks right" and starts meaning "satisfies these checks." Keep a human
spot-check via `build_preview.py` in the loop at Phase 6.

- [x] Unit and regression coverage verifies automatic placement, phase
  constraints, scope-local layout, deterministic geometry, collision findings,
  and validation of both current processes.

## Phase 2b — Validator rework [x]

The original plan said `validate_bpmn.py` needs no changes. Between the
repair loop (Phase 2) and decomposition (Phase 3b), it needs a fair amount.
Do this before Phase 3b lands, or every sub-diagram ships unchecked.

- [x] **Structured findings.** Factor the geometry checks into a `geometry.py`
that returns records (element ids, kind, offending bounds) instead of
strings, and have `Validator` format those records into its existing
messages. CLI output stays byte-compatible; the repair loop gets something
it can act on.

- [x] **Multi-scope traversal.** Each of these was confirmed against the current
code, and each breaks the moment a subprocess or link event appears:

| Current behaviour | Breaks because | Fix |
| :--- | :--- | :--- |
| `nodes`/`flows`/`annotations`/`associations` built with a flat `for el in proc` | children nested in a `subProcess` are never seen | collect scopes recursively; run the node/flow checks once per scope |
| `check(len(starts) == 1)` | each embedded subprocess has its own start event | assert exactly one start **per scope** |
| reachability from the single start | subprocess children aren't reachable from the top-level start | run the reachability walk per scope, from that scope's start |
| `check_lanes` requires a `laneSet` on the process | subprocess planes and called global processes may legitimately have none | top-level requires a laneSet; nested scopes only validate one if present |
| `check_di` resolves `BPMNDiagram/BPMNPlane` (first match only) | a collapsed subprocess adds a second plane | iterate every plane; map each `bpmnElement` to its owning scope |
| `check_geometry` compares all shapes on one plane | planes are **independent coordinate spaces** — cross-plane comparison invents overlaps that don't exist | group shapes by plane, compare only within a plane |
| `check_connectivity` requires outgoing on every non-`endEvent` and incoming on every non-`startEvent` | a **link throw** event has incoming but no outgoing; a **link catch** has outgoing but no incoming — both are `intermediateThrow/CatchEvent`, already in `FLOW_NODE_TAGS`, so both hit the failing branch | exempt link events, and instead pair-check them (below) |
| `check_process_ref` requires a participant referencing the process | a called global process has no pool | require it for the top-level process only |

- [x] **New checks decomposition needs:**

- [x] every `callActivity`'s `calledElement` resolves to a process that exists
  in the bundle;
- [x] link throw/catch events pair **exactly 1:1 by name** within a scope — an
  unmatched throw is a dead end and an unmatched catch is unreachable, and
  neither is caught by any check today;
- [x] every collapsed subprocess (`isExpanded="false"` on its `BPMNShape`) has
  a matching child `BPMNPlane`, and an expanded one has its children on the
  parent plane instead — mismatch here is the single most common way a
  hand-built hierarchical file renders blank;
- [x] no sequence flow crosses a scope boundary (illegal in BPMN, and a
  plausible mistake for a generator that flattens ids).

- [x] Drop the `"OFC-001.bpmn"` default in `main()` and take a bundle of
paths, so one invocation validates a whole multi-file output.

- [x] Unit and regression coverage verifies structured geometry findings,
  nested and parallel scope traversal, multiple-plane geometry isolation,
  link pairing and reachability, subprocess DI placement, scope-boundary
  flows, called-process bundles, global-process lane rules, and CLI behavior.

## Phase 3 — Define the intermediate representation (IR) [x]

A plain JSON file is the contract between "understanding the SOP" and
"drawing the diagram" — mirroring the existing `Node`/`Edge` fields:

```json
{
  "schema_version": 1,
  "process_id": "Process_OFC004",
  "participant_name": "Oklahoma Forensic Center — Case Manager Intakes Consumer",
  "process_doc": "...",
  "lanes": [{"id": "CM", "name": "Case Manager", "ann_above": false}],
  "phases": [{"id": "P1", "name": "1. Elopement Form & Protective Order Review"}],
  "nodes": [
    {"id": "Task_BeginElopementForm", "kind": "task", "lane": "CM",
     "phase": "P1", "name": "Begin the Elopement Form", "ttype": "user",
     "doc": ["..."], "note": null, "parent": null}
  ],
  "edges": [
    {"source": "...", "target": "...", "label": "Yes",
     "condition": "...", "loop": false}
  ],
  "external_pools": [
    {"id": "Participant_AdmissionsCoordinator",
     "name": "Admissions Coordinator", "anchor": "Start_..."}
  ],
  "message_flows": [
    {"source": "Participant_...", "target": "Start_...", "name": "..."}
  ]
}
```

The engine from Phase 1 consumes this directly (`col`/`subrow` omitted —
Phase 2 computes them). Points the original sketch left out:

- [x] **Enumerate the `kind` and `ttype` vocabularies in the schema.**
  `kind` ∈ `task | gateway_x | gateway_p | start_message | catch_timer |
  catch_message | end`, extended by Phase 3b with `subprocess |
  call_activity | link_throw | link_catch`; `ttype` ∈ `manual | user |
  send | receive` and applies to tasks only. These are load-bearing:
  `element_tag()` switches on them, and a typo currently produces a
  silently wrong element type.
- [x] **`parent` is what makes the IR hierarchical.** `null` means top-level;
  otherwise the id of the containing `subprocess` node. Keep nodes in one
  flat list rather than nesting them — id uniqueness, edge resolution, and
  "no flow crosses a scope boundary" all stay one-pass checks that way,
  and the layout engine reads a scope as a simple filter.
- [x] **Gateway defaults are a validated invariant, not a convention.**
  `check_gateways` requires that a branching gateway have exactly one
  outgoing flow with no `conditionExpression` (the default) and that every
  other branch has one. `Edge.condition == ""` is what marks the default.
  Encode that rule in the JSON Schema so a malformed IR fails at load, not
  after layout.
- [x] **`phase` stays documentation + Mermaid grouping + the Phase 2 column
  constraint; it does not render into BPMN `group` elements.**
- [x] `external_pools` / `message_flows` per Phase 1.
- [x] `doc` is a list of paragraph strings (feeds `add_doc`), and `note`
  is a single string that becomes an associated text annotation.

- [x] Unit and regression coverage verifies IR schema loading, vocabulary and
  reference validation, hierarchy checks, gateway defaults, deterministic
  defaults, and engine/XML integration.

This is the same modeling judgment applied to build OFC-004 (which actor
owns which step, where each lettered Option's gateway belongs, which notes
attach where) — just captured as data instead of Python source.

## Phase 3b — Decomposition: splitting a large SOP across diagrams

OFC-004 is 55 flow nodes on one sheet and still reads. The next SOP may not.
This phase adds the three standard BPMN breakdown mechanisms, in a defined
preference order, driven from the IR.

### Two different meanings of "multiple documents"

Keep these separate — conflating them is the main way hierarchical BPMN
goes wrong:

- **Multiple planes in one `.bpmn` file.** A collapsed subprocess's
  children live inside the `<bpmn:subProcess>` element in the *same*
  process; what makes it a separate sheet is DI, not structure — the
  parent shape carries `isExpanded="false"` and the children get their own
  `<bpmndi:BPMNPlane bpmnElement="SubProcess_X">`. One file, one
  deliverable, drill-down navigation. **This is the default.**
- **Multiple `.bpmn` files.** Only a call activity produces this: a
  separate top-level `<bpmn:process>` referenced by `calledElement`.
  Needed only for genuine reuse across SOPs. Note that `calledElement` is
  resolved **by process id**, not by file path — tools resolve it within a
  deployment or workspace, and some modelers additionally want a
  `<bpmn:import>`. Cross-file references are the least portable thing here,
  so don't reach for them to solve a size problem.

### Mechanism preference order

1. **Collapsed subprocess** — the default for "this phase has too many
   steps." One file, drilldown, no cross-file resolution risk.
2. **Call activity + separate process** — only when a block is genuinely
   reused across SOPs. There is at least one real candidate already:
   completing an ROI appears in OFC-004's Option A *and* Option E, and the
   contact/ROI procedure recurs across processes. Reuse is the
   justification; size is not.
3. **Link events** — last resort, and discouraged. They are purely
   cosmetic off-page connectors: they create no hierarchy, they pair
   *within a single process* (so they do not actually yield a second
   document), and they force a special case into `check_connectivity`
   (Phase 2b). Support them because the notation is standard and someone
   will want them, but don't let the auto-decomposer choose them.

### Where to split

**Split at phase boundaries, never mid-phase.** The SOPs already carry
authored, ordered phases (`## Main Path` step groups → `PHASES`), and a
phase is exactly the "chunk of detailed work" a collapsed subprocess is
meant to hide. The subprocess name comes free from the phase name
(`"5. Security Search and Property Inventory"`). This is the third job
`phase` picks up in this plan — documentation, the Phase 2 column
constraint, and now the decomposition unit — which is reason enough to
stop treating it as dead data.

Trigger thresholds (tunable, but pick concrete numbers so the behaviour is
predictable rather than vibes-based):

- more than ~50 flow nodes on a single plane, or
- more than ~14 columns, or
- computed pool width beyond what prints legibly.

Below the threshold, emit one sheet — OFC-001 and OFC-004 should keep
producing exactly what they produce today. Decomposition must be opt-in per
process via the IR, never a surprise.

### The lane problem — flag this before implementing

**A collapsed subprocess occupies exactly one lane on the parent sheet, but
these phases are inherently multi-actor.** OFC-001's phase 2, "Receive
Consumer from Law Enforcement," spans Security Officer, Deputy, and
Consumer. Collapsing it forces one box into one lane, which loses the
handoff structure that is arguably the most important thing the diagram
shows.

Three options, and this is a modeling decision worth making deliberately:

- put the collapsed box in the lane of the phase's *owning* actor (first
  step's actor) and give the **child plane its own `laneSet`** so the
  handoffs survive one level down — BPMN permits a `laneSet` inside a
  `subProcess`; **verify how bpmn-js v17 renders it before committing**;
- only auto-collapse single-actor phases, and leave multi-actor phases
  expanded on the parent sheet;
- don't collapse at all for cross-lane processes; use link events to break
  the sheet instead, accepting that this is cosmetic.

Default to the first, fall back to the second when a phase's steps are
spread across more than ~3 lanes.

### IR additions

```json
{
  "documents": [
    {"id": "Process_OFC004", "file": "OFC-004.bpmn", "role": "main"},
    {"id": "Process_CompleteROI", "file": "OFC-004-ROI.bpmn",
     "role": "global"}
  ],
  "decomposition": {"mode": "auto", "max_nodes_per_plane": 50,
                    "collapse_phases": ["P5", "P7"]}
}
```

- `subprocess` nodes carry the children that name them as `parent`, plus
  `collapsed: true|false`.
- `call_activity` nodes carry `called_element` (a process id from
  `documents`).
- `link_throw` / `link_catch` nodes carry a shared `link_name`.
- Each scope needs **its own start and end events**; the auto-decomposer
  must synthesise them when it lifts a phase into a subprocess, and rewire
  the flows that crossed the boundary to enter/leave the subprocess node.
  That rewiring is the part most likely to produce a subtly wrong diagram,
  so it deserves its own unit tests against a small hand-built fixture,
  not just end-to-end golden diffs.

### Engine work

- `compute_layout()` / `build_xml()` run per scope (already parameterised
  in Phase 1); emit one `BPMNPlane` per scope into one `BPMNDiagram`.
- `element_tag()` gains the four new kinds; `subProcess` needs
  `triggeredByEvent="false"` and the collapsed marker is DI-side
  (`isExpanded="false"`), not an attribute on the element.
- `write_bpmn()` becomes `write_bundle()` — returns a list of paths.
- Mermaid: a collapsed subprocess maps to a Mermaid subgraph, which is what
  `build_mermaid()` already does with phases. Keep them consistent or drop
  the Mermaid path for decomposed processes rather than letting the two
  representations disagree.

## Phase 4 — Markdown → IR conversion

The existing SOPs share one template: `Actors` / `Context` / `Preconditions`
/ `Outcome` / `Version` / `Main Path` (numbered, bold actor per step) /
`Options from main path` (lettered, each with a `Trigger:` line) / `Notes`
(lettered, referenced inline as `[a]`, `[b]`, …).

Conventions confirmed against `OFC-004 — Case Manager Intakes Consumer.md`,
including the ones that will break a naive parser:

- Note references are **backslash-escaped** in the source: `\[a\]`, and the
  Notes section entries begin `\[a\] `. The file terminates with a
  `\[ end \]` sentinel. Match both escaped and bare forms.
- Steps end with **two trailing spaces** (markdown hard line breaks).
  Strip before matching.
- Actors are a `*` bullet list, one per line, also with trailing spaces.
- Options are `### Option A — Title` followed by a blank line and a
  `Trigger: …` line, then a numbered body.
- **Bold actors appear only in the Main Path.** Option bodies are written
  unbolded ("Case Manager completes an ROI with the Consumer"), so actor
  attribution inside options cannot be regex-extracted the same way.
- **A step can name several bold actors** ("**Case Manager** contacts
  **Prospective Treatment Advocate**"). The convention is first bold =
  owning lane, subsequent bolds = counterparties — and deciding whether a
  counterparty gets its own task node or stays folded into the sender's is
  exactly the judgment call below. Document the rule; don't leave it
  implicit.
- **Option bodies contain their own inline branching** ("If the Prospective
  Contact agrees… / If the Prospective Contact declines…"), which becomes a
  gateway *inside* the option, not just the option's entry gateway.

Two pieces:

1. **Structural extraction** (deterministic, regex/markdown-parser): pull
   out the actor list, the numbered main-path lines, the lettered option
   blocks with their trigger sentences, and the lettered notes with their
   inline reference markers. Mechanical; no judgment. Emit it as its own
   inspectable JSON so parse failures are debuggable separately from
   modeling failures.
2. **Semantic modeling** (judgment-heavy — this is the part done by hand for
   OFC-001/OFC-004): lane groupings, where each Option's gateway inserts
   into the main path, simple detour vs. loop-back, whether a receiving
   actor needs its own task node. This doesn't reduce to regex — plan for
   it to stay an LLM-assisted step (Claude reads the structurally-extracted
   pieces and emits the Phase 3 IR JSON), constrained by the published JSON
   Schema so the output is validated for *shape* before it reaches the
   layout engine.

Decomposition is mostly judgment too, and the markdown carries no signal
for it. The size trigger (Phase 3b) is mechanical and can stay in code, but
*which* phases collapse well, and whether a repeated block is genuinely the
same reusable procedure across two SOPs or merely similar prose, is a
modeling call. Have the semantic step propose `decomposition` in the IR
with a one-line rationale per split, and let the human reviewing the IR
accept or override it. Don't invent a new markdown convention for
subprocesses — the phase headings already there are the right signal.

Note the ceiling honestly: schema validation catches malformed IR, not
*wrong* IR. A model that puts a step in the wrong lane or attaches Option C
to the wrong gateway produces a diagram that validates cleanly and is still
incorrect. The IR being a reviewable, diffable artifact (Phase 5) is the
mitigation.

Document the markdown authoring conventions this depends on so future SOPs
stay auto-parseable rather than every one needing a bespoke read-through.

## Phase 5 — CLI wrapper

Split into two commands rather than one, because an LLM call in the middle
of a build pipeline makes every re-layout slow, costly, and
non-reproducible:

```
py sop_to_ir.py "OFC-00X — Some Process.md"   →   OFC-00X.ir.json   (LLM-assisted, run once, reviewed, committed)
py ir_to_bpmn.py OFC-00X.ir.json              →   OFC-00X.bpmn      (deterministic, re-runnable, free)
```

`sop_to_bpmn.py` stays as a convenience wrapper that runs both when the IR
doesn't exist yet. This also settles the first Open Question: the IR is a
committed artifact, so the LLM step happens once per SOP (and on demand
when the SOP changes), while layout iteration is pure and offline.

Steps:

1. Structural extraction (Phase 4.1) on the markdown.
2. Produce the IR (Phase 4.2 — LLM-assisted, validated against the IR
   schema), write it to `<slug>.ir.json` for human review.
3. Run the shared engine (Phase 1 + Phase 2 + Phase 3b) to emit
   `<slug>.bpmn` plus any additional called-process files, and print the
   file list with per-plane node counts so an unintended split is obvious.
4. Validate automatically by importing `Validator` and calling it on
   **every** emitted file — not by shelling out to
   `validate_bpmn.main()`, which reads `sys.argv` and returns a process
   exit code. Include the cross-document checks from Phase 2b
   (`calledElement` resolution, link pairing), which by definition can't
   run on a single file in isolation. Fail loudly with the error list;
   never hand back an unchecked file. Non-zero exit on failure so this can
   gate CI.

## Phase 6 — Migrate existing processes

Re-express OFC-001 and OFC-004 as IR JSON files and generate through the new
pipeline. **Change the acceptance criterion here:** byte-identity was the
Phase 1 gate and is no longer achievable once Phase 2 computes coordinates
itself. Phase 6 asks for *semantic* equivalence instead:

- identical sets of node ids, edge (source, target, label, condition,
  loop) tuples, annotations, documentation strings, lane assignments, and
  element types — compare parsed BPMN trees, ignoring DI geometry, and
  compare across the whole emitted bundle rather than one file;
- `validate_bpmn.py` passes on both;
- a visual spot-check through `build_preview.py` before retiring anything,
  since auto-layout can be collision-free and still read worse than the
  hand-tuned version.

Retire `generate_bpmn.py` and `generate_bpmn_ofc004.py` only after all
three hold — and only after Phase 1b, since `build_preview.py` imports the
former.

**Migrate both processes undecomposed first.** OFC-001 and OFC-004 both fit
on one sheet today; proving the pipeline reproduces them flat isolates
"did the engine extraction work" from "did decomposition work." Only then
try OFC-001 with its 12 phases collapsed, as the first real exercise of
Phase 3b — it has the phase structure and the multi-actor lane problem
both, so it is the honest test case.

## Risks

- **Layout quality regression.** The hand-tuned diagrams encode judgment
  ("SO's annotation band goes above because every edge climbs into that
  lane") that a generic algorithm will not rediscover. Phase 2 should keep
  per-process overrides (an optional `col`/`subrow` pin in the IR that
  wins over the computed value) so a bad auto-layout is a one-line fix,
  not a reason to abandon the pipeline.
- **The comment loss already happened once.** `generate_bpmn_ofc004.py`
  shows what copying without the rationale looks like. Whatever moves into
  `bpmn_engine.py` must carry the OFC-001 comments forward verbatim.
- **No test suite exists.** Phase 0's golden-file check is the entire
  safety net; treat it as required infrastructure, not a nicety.
- **Decomposition can make a diagram worse.** Hiding a phase behind a `[+]`
  costs the reader the at-a-glance overview that is the whole point of an
  SOP diagram, and it hides cross-lane handoffs one level down. Splitting
  is a readability trade, not a pure win — which is why Phase 3b makes it
  opt-in and threshold-gated rather than automatic.
- **Hierarchical BPMN files fail quietly.** A collapsed subprocess whose
  child plane is missing, or whose `isExpanded` flag disagrees with where
  the DI actually lives, renders as an empty box in some tools and as an
  expanded blob in others — no error anywhere. The Phase 2b plane/scope
  checks are what turn that class of bug into a build failure.
- **Cross-file `calledElement` is the least portable construct here.**
  Resolution is by process id within a deployment, and modeler support
  varies. Keep call activities rare and reuse-justified.

## Open Questions

- How much markdown-template deviation to tolerate before structural
  extraction should fail fast vs. guess. (Recommendation: fail fast and
  loudly — a wrong guess produces a plausible-looking wrong diagram, which
  is worse than an error.)
- Whether external/collapsed pools (like OFC-001's Admissions Coordinator)
  need a markdown convention to be detected automatically, or stay a manual
  addition to the IR. *(Their engine support is no longer open — that moved
  into Phase 1.)*
- Whether `phase` should render into the BPMN as group elements or stay
  documentation + layout constraint + decomposition unit (Phases 3, 3b).
  Groups and collapsed subprocesses are alternative treatments of the same
  phase data — decide which, rather than doing both.
- How bpmn-js v17 renders a `laneSet` **inside** a collapsed subprocess
  plane. This gates the preferred answer to Phase 3b's lane problem and is
  cheap to settle with a ten-line hand-built fixture — do it before
  implementing decomposition, not after.
- Whether decomposed output should also produce a one-sheet "overview"
  variant for printing/review, since drill-down doesn't survive paper.
- Where the OFC-001 source markdown and generated outputs currently live —
  they are not in this directory, and Phase 0 needs them.
