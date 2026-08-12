# Dev Plan: [Title]
*A one-sentence statement of the outcome this plan delivers.*

> **How to use this template.** A plan has a document **header** (below), one or more **phase
> blocks** (the numbered section further down), and a document **footer**. The header, the
> per-phase block, and the footer apply to every plan. The sections marked *Multi-phase plans
> only* (`Cross-Phase Engineering Contract` and each `Phase Handoff`) should be omitted from a
> single-phase fix — don't leave empty scaffolding. Throughout, cite concrete `path/file.js:line`
> references so an implementer can verify each claim against the code rather than re-deriving it.

## Why this plan
*The need, bug, or opportunity, and the intended end state. State the problem before the solution.*

### Root cause (verified against the code)
*Expected for a bugfix; optional for pure greenfield work. Bullet points that trace the actual
behavior to specific `path/file.js:line` locations, so the diagnosis is checkable, e.g.:*
* Victory is only re-evaluated on destruction (`src/ui/InspectorController.js:116`); the capture
  path (`src/combat/CombatController.js:1872`) has no equivalent hook, so a capture never ends the
  game.

### Design rationale
*The chosen approach and — importantly — the alternatives considered and **why they were
rejected**. This is where a reviewer learns the plan didn't miss the obvious option; it chose
against it, e.g. "Why a single-point fix (not a new combat-layer event)."*

## Cross-Phase Engineering Contract
*Multi-phase plans only; omit for a single-phase fix.*
*Shared invariants every phase must honor, stated once up front so a later phase never has to
reverse an early convenience shortcut. Typical entries: state/authority boundaries, a single
documented result shape and one mutation point, determinism/idempotency rules, information/visibility
boundaries, backward-compatibility guarantees, and the phase-handoff rule (a phase isn't complete
until its new public API has a focused test and the next phase can consume it without reaching into
private fields).*

---

## [ ] Phase [Number]: [Phase Title]
*Quick one-sentence summary and complexity of the focus (e.g., "Establishing the core data models and state transitions without UI dependency. Complexity of coding: [Very High | High | Medium | Low]")*

### 1. Objectives & Scope
* **What is in scope:** Clear bullet points of what must be completed.
* **What is in scope:** Include affected systems, files, or user workflows when useful.
* **What is OUT of scope:** Boundaries to prevent scope creep (e.g., "No UI elements or layout changes will be touched in this phase.").

### 2. Implementation Checklist
- [ ] **Task 1:** Actionable development item (e.g., "Create `EnergyPool` class in `src/models/`").
- [ ] **Task 2:** Actionable development item.
- [ ] **Task 3:** Actionable development item.

### Implementation Notes
* Capture relevant current code paths, data contracts, sequencing constraints, and compatibility hazards.
* Record concrete `path/file.js:line` paths, keys, selectors, events, commands, or fallback behavior that implementation should preserve — prefer verifiable citations over prose description.
* Note any dependencies on previous phases or cleanup that should wait for later phases.
* If implementation uncovers and fixes an in-scope bug, record it here as a **"Bug found in scope"** note: what was wrong, how it was found, and the fix — so the plan documents reality, not just the original intent.

### Phase [Number] Handoff
*Multi-phase plans only; omit for a single-phase fix.*
*What this phase publishes as the supported contract for the next phase: the new public API/entry
points, any state that must be reset/reloaded safely, and the guarantee that the next phase can
consume this work without reaching into private controller/renderer fields.*

### 3. Testing & Verification
* **Test Location:** `tests/[specific_subdirectory]/`
* **Unit Tests to Write:**
    * [ ] `test_allocation_bounds`: Ensures players cannot allocate more energy than they possess. [example]
    * [ ] `test_state_transition_on_completion`: Verifies the game advances cleanly out of EAP once energy is locked in. [example]
* **Browser/Integration Tests to Run:**
    * [ ] `npm test`
    * [ ] `npm run verify:[feature]`
* **Acceptance Criteria:** What must pass for this phase to be considered 100% complete?

---

## Deferred Items And Explicit Non-Goals
*What this plan deliberately does not do: out-of-scope work, dependency-gated follow-ons (name the
prerequisite), and rulebook/config values chosen as decisions rather than assumed as defaults.
Keeping this explicit prevents a later phase from silently absorbing work the plan meant to defer.*