# Simple Refactors

Small, behavior-preserving cleanups that make the code easier for a programmer to
read. Every item here must leave BPMN output, IR validation messages, CLI text,
and the desktop UI **byte-for-byte identical**; the regression suite
(`py -m pytest tests`) is the check. Items are grouped by module and cite
`path/file.py:line` so each claim is verifiable against the code.

Mark an item `[x]` when it is implemented.

**Status:** items 1-26 are implemented. Verification: 75 tests pass,
`scripts/check_golden.py` passes, every generated BPMN/Mermaid/IR/preview artifact
hashes identically to its pre-refactor output, and 1,495 mutated IR documents
produce byte-identical validation errors before and after the `ir.py` split.

---

## `src/bpmn_engine.py`

### [x] 1. Extract one shape-label geometry helper

* **Where:** the event/gateway label block is written three times —
  [bpmn_engine.py:879-893](src/bpmn_engine.py#L879-L893) (`_layout_labels`),
  [bpmn_engine.py:1382-1390](src/bpmn_engine.py#L1382-L1390) (`build_xml`, top plane),
  [bpmn_engine.py:1489-1497](src/bpmn_engine.py#L1489-L1497) (`build_xml`, child plane).
* **Why:** three copies of the same rule (events get `event_label_bounds`,
  gateways get a `GW_LBL_W` box `8px` above) must be kept in sync by hand, and
  the geometry gate silently stops matching the emitter if one copy drifts.
* **Change:** add `def shape_label_bounds(node, x, y, w, h, lay) -> Bounds | None`
  beside `event_label_bounds` and call it from all three sites.

### [x] 2. Extract the annotation-association waypoints

* **Where:** the same "annotation above → top edge, else bottom edge" branch appears at
  [bpmn_engine.py:941-946](src/bpmn_engine.py#L941-L946),
  [bpmn_engine.py:1456-1463](src/bpmn_engine.py#L1456-L1463), and
  [bpmn_engine.py:1511-1517](src/bpmn_engine.py#L1511-L1517).
* **Change:** add `def association_waypoints(node_bounds, ann_bounds) -> list[Point]`
  and use it in `_layout_edges` and both `build_xml` passes.

### [x] 3. Extract the message-flow geometry

* **Where:** message-flow endpoints, waypoints, and label offsets are recomputed in
  [bpmn_engine.py:902-926](src/bpmn_engine.py#L902-L926),
  [bpmn_engine.py:949-964](src/bpmn_engine.py#L949-L964), and
  [bpmn_engine.py:1426-1444](src/bpmn_engine.py#L1426-L1444).
* **Why:** the three copies already differ in how a missing endpoint is handled
  (two skip it, one raises via `lay.bounds[...]`), which makes it hard to tell
  which behavior is intended.
* **Change:** add a helper returning `(points, label_bounds | None)` for one
  `MessageFlow`, keeping each caller's existing missing-endpoint handling at the
  call site so behavior is unchanged.

### [x] 4. Name the wrapped-line-count idiom

* **Where:** `-(-len(text) // width)` appears at
  [bpmn_engine.py:403](src/bpmn_engine.py#L403),
  [bpmn_engine.py:834](src/bpmn_engine.py#L834),
  [bpmn_engine.py:886](src/bpmn_engine.py#L886),
  [bpmn_engine.py:1388](src/bpmn_engine.py#L1388),
  [bpmn_engine.py:1495](src/bpmn_engine.py#L1495).
* **Change:** `def _wrapped_lines(text: str, chars_per_line: int) -> int` with a
  one-line docstring explaining that it is a ceiling division. The double
  negation is the least readable expression in the layout code.

### [x] 5. Build the forward graph once

* **Where:** `_topological_layout_data`
  ([bpmn_engine.py:416-423](src/bpmn_engine.py#L416-L423)) and `_auto_placements`
  ([bpmn_engine.py:522-527](src/bpmn_engine.py#L522-L527)) build the same
  `forward` / `adjacency` / `incoming` structures from `_topology_edges`.
* **Change:** extract `_forward_graph(model, scope)` returning
  `(forward, adjacency, incoming)`; `_topological_layout_data` keeps its own
  `indegree` counter since only it consumes one.

### [x] 6. Share the phase-order scan between the strict and repair paths

* **Where:** [bpmn_engine.py:479-500](src/bpmn_engine.py#L479-L500) (raises
  `PhaseOrderError`) and [bpmn_engine.py:988-998](src/bpmn_engine.py#L988-L998)
  (returns `False`) implement the same "a phase may not begin left of an earlier
  phase" rule against different inputs.
* **Change:** one `_first_phase_violation(model, nodes, column_of) -> tuple | None`
  taking a `column_of` callable; the strict caller turns a non-`None` result into
  `PhaseOrderError`, the repair caller turns it into `False`. Divergence between
  these two is exactly what makes `--repair-layout` hard to reason about.

### [x] 7. Replace the `branch_tokens` dicts with a dataclass

* **Where:** [bpmn_engine.py:548-591](src/bpmn_engine.py#L548-L591) builds
  `list[dict[str, object]]` with `"key"`, `"start"`, `"end"`, `"desired"`,
  `"nodes"`, then reads them with string keys and an `int(token["desired"])` cast
  at [bpmn_engine.py:601](src/bpmn_engine.py#L601).
* **Change:** a frozen `@dataclass BranchToken` with typed fields. The cast and
  the `object` value type both disappear, and the interval-coloring loop at
  [bpmn_engine.py:595-611](src/bpmn_engine.py#L595-L611) becomes readable.

### [x] 8. Turn `element_tag` into a lookup table

* **Where:** [bpmn_engine.py:1118-1137](src/bpmn_engine.py#L1118-L1137) — an
  eight-branch `if` chain over `node.kind`.
* **Change:** a module-level `ELEMENT_TAG: dict[str, str]` beside the existing
  `TASK_ELEMENT` ([bpmn_engine.py:1110-1115](src/bpmn_engine.py#L1110-L1115)),
  keeping the `task` special case and the current fallback to
  `"intermediateCatchEvent"`.

### [x] 9. Name the event kinds that carry a caption

* **Where:** the literal tuple `("start_message", "end", "catch_timer",
  "catch_message")` is repeated at
  [bpmn_engine.py:879-881](src/bpmn_engine.py#L879-L881),
  [bpmn_engine.py:1383-1385](src/bpmn_engine.py#L1383-L1385), and
  [bpmn_engine.py:1490-1492](src/bpmn_engine.py#L1490-L1492).
* **Change:** a module constant `LABELED_EVENT_KINDS` near the other kind
  constants. (Folds naturally into item 1.)

### [x] 10. Delete dead names in the engine

* `N = Node` / `E = Edge` at
  [bpmn_engine.py:342-343](src/bpmn_engine.py#L342-L343) — no module imports
  them; they are leftovers from the pre-IR hand-written model files.
* `Layout.row_center` at
  [bpmn_engine.py:295-296](src/bpmn_engine.py#L295-L296) — never called, and it
  restates the formula inlined at
  [bpmn_engine.py:698](src/bpmn_engine.py#L698). Either delete it or give
  `_build_layout` a shared `row_center(row_top, lane, subrow)` helper so there is
  one definition.
* Unused locals: `by_id` at [bpmn_engine.py:937](src/bpmn_engine.py#L937) and
  [bpmn_engine.py:1446](src/bpmn_engine.py#L1446); `node_ids` at
  [bpmn_engine.py:1579](src/bpmn_engine.py#L1579); `nodes` / `src` / `tgt` at
  [bpmn_engine.py:851-852](src/bpmn_engine.py#L851-L852) (`edge_label_bounds`
  works purely off `pts`); `sy` / `sh` at
  [bpmn_engine.py:725](src/bpmn_engine.py#L725).
* `phase_names = dict(model.phases)` at
  [bpmn_engine.py:1582](src/bpmn_engine.py#L1582) is looked up as
  `phase_names[phase_id]` one line after the loop already bound `phase_name`.
* Keep `edge_label_bounds`'s `model` parameter — `tests/test_bpmn_engine.py:113`
  passes it — and drop only the dead body lines.

### [x] 11. Collapse the three `resolved_*_id` properties

* **Where:** [bpmn_engine.py:213-223](src/bpmn_engine.py#L213-L223) repeats
  `self.process_id.removeprefix("Process_")` three times.
* **Change:** a private `_id_suffix` property the three fall back to.

---

## `src/ir.py`

### [x] 12. Split `_validate_and_normalize` into per-section validators

* **Where:** [ir.py:135-500](src/ir.py#L135-L500) — one 365-line function that
  validates documents, decomposition, lanes, phases, nodes, edges, pools,
  message flows, and presentation fields, then assembles the normalized dict.
* **Why:** it is by a wide margin the hardest function in the repo to navigate,
  and the section boundaries are already obvious from the local `path = f"..."`
  prefixes.
* **Change:** pure extraction, no logic changes — `_validate_documents`,
  `_validate_decomposition`, `_validate_lanes`, `_validate_phases`,
  `_validate_nodes`, `_validate_edges`, `_validate_external_pools`,
  `_validate_message_flows` — each returning its normalized list plus the id set
  the later sections cross-check. `_validate_and_normalize` shrinks to the
  ordering of those calls and the final `normalized.update(...)`. Field order in
  the returned dict must not change: `model_to_document` round-trips are
  compared byte-for-byte by `scripts/check_golden.py`.

### [x] 13. Extract a `_duplicates` helper

* **Where:** `sorted({item for item in xs if xs.count(item) > 1})` appears at
  [ir.py:663](src/ir.py#L663), [ir.py:671](src/ir.py#L671), and
  [ir.py:694](src/ir.py#L694).
* **Change:** `def _duplicates(values: list[str]) -> list[str]` using a `Counter`.
  Same sorted output, one definition, and it drops the accidental O(n²) `count()`
  inside a comprehension.

---

## `src/validate_bpmn.py`

### [x] 14. Give `_direct_scope_items` a named result

* **Where:** [validate_bpmn.py:60-74](src/validate_bpmn.py#L60-L74) returns a bare
  4-tuple, read positionally as `_direct_scope_items(scope)[0]` at
  [validate_bpmn.py:151](src/validate_bpmn.py#L151) and
  [validate_bpmn.py:188](src/validate_bpmn.py#L188).
* **Change:** a frozen `@dataclass ScopeItems(nodes, flows, annotations,
  associations)`. Tuple-unpacking call sites become `items.nodes`, and the
  `[0]` indexing that currently requires reading the helper body goes away.

### [x] 15. Resolve the collaboration element once

* **Where:** `_participant_exists`
  ([validate_bpmn.py:262-267](src/validate_bpmn.py#L262-L267)) re-scans
  `self.root` for the `collaboration` element on every message-flow endpoint,
  even though `run` already found it at
  [validate_bpmn.py:131-132](src/validate_bpmn.py#L131-L132).
* **Change:** resolve it once in `__init__` into `self.collab` and have both
  `run` and `_participant_exists` read that field.

---

## `src/geometry.py`

### [x] 16. Hoist the obstacle sort and name the edge-ownership test

* **Where:** [geometry.py:88-100](src/geometry.py#L88-L100) calls
  `sorted(obstacles.items())` inside the per-segment loop, so the same list is
  rebuilt for every waypoint pair of every edge.
* **Change:** sort once before the loop. Separately, the ownership skip
  `if owner in edge_id` at [geometry.py:93](src/geometry.py#L93) is a *substring*
  test on ids, which is surprising on first read — move it into
  `def _edge_owns(edge_id: str, obstacle_id: str) -> bool` with a comment stating
  that flow ids embed their endpoint ids (`Flow_<source>__<target>`, see
  [bpmn_engine.py:1140-1141](src/bpmn_engine.py#L1140-L1141)).

---

## `src/markdown_extractor.py`

### [x] 17. Find the `Version` marker once

* **Where:** `_version_lines`
  ([markdown_extractor.py:236-250](src/markdown_extractor.py#L236-L250)) and
  `_outcome_lines`
  ([markdown_extractor.py:253-262](src/markdown_extractor.py#L253-L262)) each
  scan the same range for the same marker and each raise their own
  `"missing Version marker"`.
* **Change:** one `_version_marker_index(lines, start, end) -> int` that owns the
  duplicate-marker and missing-marker errors; the two slicing helpers become
  two-line functions. Keep the existing message text so CLI/UI output is unchanged.

### [x] 18. Parse actor lines once

* **Where:** [markdown_extractor.py:450-457](src/markdown_extractor.py#L450-L457)
  runs `ACTOR_RE.fullmatch` three times per line (once inside `_bullets`, once in
  the comprehension's `if`, once in its expression) and relies on the reader
  noticing that `_bullets` is called only for its error side effect.
* **Change:** have the comprehension walk `actor_lines` once with `:=` or a small
  loop, keeping the `_bullets(...)` call above it for its non-bullet error
  message and its "must not be empty" check.

### [x] 19. Drop the unused loop variable in `_paragraphs`

* **Where:** [markdown_extractor.py:163](src/markdown_extractor.py#L163) binds
  `line_number` and never uses it, unlike its sibling `_bullets`.
* **Change:** iterate `for _, raw in lines`, which also signals that
  `_paragraphs` — unlike every other parser here — cannot report a line number.

---

## `src/ir_to_bpmn.py`

### [x] 20. Fold the repeated argument guard into `preflight`

* **Where:** `if not ir_files: raise CLIError("at least one IR file is required")`
  plus `ir_paths = [Path(path) for path in ir_files]` appears in `preflight`
  ([ir_to_bpmn.py:105-107](src/ir_to_bpmn.py#L105-L107)),
  `planned_output_paths` ([ir_to_bpmn.py:129-131](src/ir_to_bpmn.py#L129-L131)),
  and `run` ([ir_to_bpmn.py:149-151](src/ir_to_bpmn.py#L149-L151)).
* **Change:** a `_ir_paths(ir_files) -> list[Path]` helper that guards and
  converts. The two outer functions still need their own `ir_paths` for the
  default output directory, so they call the helper rather than dropping the check.
* Also rename the unused `bundle` at [ir_to_bpmn.py:153](src/ir_to_bpmn.py#L153)
  to `_bundle` so the reader is not left looking for its use.

---

## `src/semantic_handoff.py`

### [x] 21. Remove the no-op `except`

* **Where:** [semantic_handoff.py:127-130](src/semantic_handoff.py#L127-L130) —
  `try: return load_ir(document) except IRValidationError: raise` catches and
  immediately re-raises, so it reads as if it were doing something.
* **Change:** call `load_ir(document)` directly; keep the docstring line that
  documents `IRValidationError` propagating to the caller.

---

## `src/build_preview.py`

### [x] 22. Compute lane slugs once per model

* **Where:** [build_preview.py:115-125](src/build_preview.py#L115-L125) —
  `lane_style_css` calls `lane_slugs(process_model)` inside the loop, rebuilding
  the whole map for every lane.
* **Change:** hoist to a single call above the loop, matching how
  `phase_summary` ([build_preview.py:131](src/build_preview.py#L131)) and `build`
  ([build_preview.py:192](src/build_preview.py#L192)) already do it.

---

## `src/sop_to_bpmn_ui.py`

### [x] 23. Share the overwrite-confirm flow

* **Where:** `_save_ir` ([sop_to_bpmn_ui.py:447-453](src/sop_to_bpmn_ui.py#L447-L453))
  and `_build_bpmn` ([sop_to_bpmn_ui.py:469-476](src/sop_to_bpmn_ui.py#L469-L476))
  repeat the same shape: catch `OverwriteRequired`, ask, re-enter the handler with
  `overwrite=True`, otherwise set a "not replaced" status.
* **Change:** one `_confirm_overwrite(error, title, prompt, retry, declined_status)`
  helper. Keep the two dialog titles, the two message bodies, and the two status
  strings exactly as they are — they are user-visible text, and this refactor must
  not touch the UI.

---

## `src/decomposition.py`

### [x] 24. Use a deque for the subprocess walks

* **Where:** `scopes_for` ([decomposition.py:219-226](src/decomposition.py#L219-L226))
  and the child-plane walk in `build_xml`
  ([bpmn_engine.py:1468-1473](src/bpmn_engine.py#L1468-L1473)) both use
  `list.pop(0)` for a breadth-first queue.
* **Change:** `collections.deque` with `popleft()` — `deque` is already imported
  in `bpmn_engine`. Same visit order, and the intent (a queue, not a stack) becomes
  explicit.

---

## `src/bpmn_engine.py` (continued)

### [x] 25. Make `_placement_order_valid` read as guard-then-check

* **Where:** [bpmn_engine.py:979-1002](src/bpmn_engine.py#L979-L1002) — the
  "every node's phase is known" check is the trailing `return all(...)`, after
  the phase-order loop that already assumed it.
* **Change:** move that check to the top as an early `return False` guard. The
  result is identical for every input (an unknown phase fails either way), and
  the function then reads top-to-bottom: validate inputs, check edge columns,
  check phase order.

---

## Found while implementing items 1-25

### [x] 26. Drop the unused imports in `decomposition.py`

* **Where:** [decomposition.py:8-23](src/decomposition.py#L8-L23) imported
  `Iterable`, `build_mermaid`, and `build_xml`; none of the three was referenced
  anywhere in the module.
* **Why:** `build_xml` in particular read as if this module emitted XML
  directly, when it actually delegates through `write_bpmn`.
* **Change:** delete the three names from the import list. `typing` was imported
  only for `Iterable`, so that import line goes away entirely.
