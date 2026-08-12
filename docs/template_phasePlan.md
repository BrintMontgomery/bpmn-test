# Dev Plan: [Title]
*A one-sentence statement of the outcome this plan delivers.*

> **How to use this template.** A plan has a document **header** (below), one or more **phase
> blocks** (the numbered section further down), and a document **footer**. The header, the
> per-phase block, and the footer apply to every plan. The sections marked *Multi-phase plans
> only* (`Cross-Phase Engineering Contract` and each `Phase Handoff`) should be omitted from a
> single-phase fix - do not leave empty scaffolding. Throughout, cite concrete `path/file.py:line`
> references so an implementer can verify each claim against the code rather than re-deriving it.

## Why this plan
*The need, bug, or opportunity, and the intended end state. State the problem before the solution.*

### Root cause (verified against the code)
*Expected for a bugfix; optional for pure greenfield work. Bullet points that trace the actual
behavior to specific `path/file.py:line` locations, so the diagnosis is checkable, e.g.:*
* `[Observed behavior]` starts in `src/[module].py:line`; the related path in
  `src/[module].py:line` does not apply `[required validation or transformation]`, so
  `[user-visible result]` occurs.

### Design rationale
*The chosen approach and, importantly, the alternatives considered and **why they were rejected**.
This is where a reviewer learns the plan did not miss the obvious option; it chose against it, e.g.
"Why validate the IR at the conversion boundary rather than add another emitter-specific validation
pass."*

## Cross-Phase Engineering Contract
*Multi-phase plans only; omit for a single-phase fix.*
*Shared invariants every phase must honor, stated once up front so a later phase never has to
reverse an early convenience shortcut. Typical entries: state/authority boundaries, a single
documented result shape and one mutation point, determinism/idempotency rules, BPMN scope and
geometry boundaries, backward-compatibility guarantees, and the phase-handoff rule (a phase is not
complete until its new public API has a focused test and the next phase can consume it without
reaching into private implementation details).*

---

## [ ] Phase [Number]: [Phase Title]
*Quick one-sentence summary and complexity of the focus (e.g., "Add a validated IR field while
preserving deterministic BPMN generation. Complexity of coding: [Very High | High | Medium | Low]")*

### 1. Objectives & Scope
* **What is in scope:** Clear bullet points of what must be completed.
* **What is in scope:** Include affected pipeline stages, source files, generated artifacts, or user
  workflows when useful.
* **What is OUT of scope:** Boundaries to prevent scope creep (e.g., "No changes to the Markdown
  authoring convention or BPMN layout algorithm in this phase.").

### 2. Implementation Checklist
- [ ] **Task 1:** Actionable development item (e.g., "Add the IR validation helper in `src/ir.py`").
- [ ] **Task 2:** Actionable development item.
- [ ] **Task 3:** Actionable development item.

### Implementation Notes
* Capture relevant current pipeline paths, data contracts, sequencing constraints, and compatibility
  hazards.
* Record concrete `path/file.py:line` paths, IR keys, BPMN element IDs, CLI commands, or fallback
  behavior that implementation should preserve - prefer verifiable citations over prose description.
* Note any dependencies on previous phases or cleanup that should wait for later phases.
* If implementation uncovers and fixes an in-scope bug, record it here as a **"Bug found in scope"**
  note: what was wrong, how it was found, and the fix - so the plan documents reality, not just the
  original intent.

### Phase [Number] Handoff
*Multi-phase plans only; omit for a single-phase fix.*
*What this phase publishes as the supported contract for the next phase: new public API or CLI entry
points, IR or BPMN data that must remain compatible, any state that must be reset or reloaded
safely, and the guarantee that the next phase can consume this work without reaching into private
implementation details.*

### 3. Testing & Verification
* **Test Location:** `tests/test_[module].py`
* **Unit Tests to Write:**
    * [ ] `test_rejects_invalid_ir`: Ensures invalid workflow data is rejected before BPMN emission. [example]
    * [ ] `test_preserves_valid_bpmn_structure`: Verifies a valid IR produces a BPMN file accepted by the validator. [example]
* **Integration/Regression Tests to Run:**
    * [ ] `python -m unittest discover -s tests -t .`
    * [ ] `python scripts/check_golden.py`
* **Acceptance Criteria:** What must pass for this phase to be considered 100% complete?

---

## Deferred Items And Explicit Non-Goals
*What this plan deliberately does not do: out-of-scope work, dependency-gated follow-ons (name the
prerequisite), and Markdown, IR, or BPMN decisions chosen deliberately rather than assumed as
defaults. Keeping this explicit prevents a later phase from silently absorbing work the plan meant
to defer.*
