# Star Fleet Battles Game Development Prompts

This document serves as a checklist and guide for iterating on a computer game version of Star Fleet Battles, focusing on feature suggestions, code refactoring, commit message generation, and phase completion updates. 

---

## Code Refactoring Review

### One
* Identify a simple refactor which would make the code easier for a programmer to understand. Your refactor should not affect behavior or UI in anyway.

* Identify a single, priority refactor which would make the code easier for a programmer to understand and/or make the overall structure of the project easier to work with.  Your refactor should not affect behavior or UI in anyway.

### Many
Are there any simple refactors which would make the code easier for a programmer to understand? If so, add them to a `docs\simpleRefactors.md` document, or create it if it does not exist. Otherwise, keep the new items with the same style and format as the other items in that document. Also, refactors should not affect behavior or UI in anyway.  

### Simple Mark-off
Implement all the suggestions in [simpleRefactors.md](docs/simpleRefactors.md) .  Mark them each off with an [x] as you progress.

### Robust

#### Role
You are assisting in refactoring the client-side codebase for **Start Fleet Battles**—a browser-based tactical starship combat simulator. 

Your goal is to review the codebase below and refactor it to make it cleaner, more modular, and highly maintainable without altering its external behavior or underlying game mechanics.

#### Refactoring Objectives
Please refactor the existing code focusing on these core AI-assisted clean code principles:
1. **Eliminate Code Duplication:** Identify redundant logic (especially common in game rules, state checking, or SSD box manipulations) and abstract them into reusable utility functions.
2. **Reduce Cognitive Complexity:** Flatten deeply nested conditional (`if/else`) statements—particularly common in combat automation or turn flow logic—using guard clauses, early returns, or lookup objects.
3. **Adhere to SOLID Principles:** Ensure functions follow the Single Responsibility Principle (SRP). If a function is handling both game state mutation and UI rendering adjustments, decouple them.
4. **Robust Error Handling & Logging:** Improve error reporting and exception management to ensure the automated runtime doesn't silently fail during hands-free turn execution.

#### Refactoring Constraints
* **Behavior Preservation:** Do not add new mechanics, tweak game balances, or alter existing system contracts. The inputs and outputs must remain functionally identical.
* **Separate Concerns:** Focus strictly on structural cleanup. If you spot critical game-rule logical flaws or missing input validation, list them out separately rather than weaving fixes into the refactored code.

#### Expected Output Format
Please structure your response as follows:

1. Breakdown of Improvements: A bulleted list detailing exactly what you changed and why (e.g., "Extracted weapon resolution logic into a standalone function to satisfy SRP").

2. Design Patterns & Principles Applied: Mention any architectural patterns or SOLID principles applied to make this specific module more extensible.

3. Code Smells & Logic Observations: Highlight any hidden edge cases, code smells, or validation gaps you uncovered while parsing the original logic.

4. Testing Checklist: Detail specific test cases, state variations, or asynchronous flows to target with the npm test suite to guarantee zero regression.



---

## Phase Creation

Review `foo` and build me a plan to implement these rules into the software. The plan should follow the style and guidelines as found in `docs\archive\template_phasePlan.md`, and the plan should have multiple phases so that not too much is happening at once.  The plan will be implemented in a linear fashion, one phase after another, each being accomplished one at a time. Put your plan into a markdown file called `docs\devPlan.md`. Make no other changes elsewhere. Assume that simpler LLM models will be used for low and medium complexity coding, and more advanced models will be used for high and very high complexity coding. Prefer to have more and smaller phases to favor the use of simpler LLM models. 

---

## Step Progression

### Context
Locate the item `FOO` in the provided task list.

### Tasks
1. **Refactor:** Execute the refactor required for this specific phase and all of its subcomponents.
2. **Update Task List:** When done, mark this item and all of its subcomponents as complete by changing `[ ]` to `[x]`.  
3. **Unit Tests:** When done and passing, mark the associated unit tests as complete in the list. 
4. **Regression Protection:** Analyze the refactored code and implement any additional unit tests necessary to safeguard against future regressions.

### Constraints
* Focus **strictly** on the indicated Phase above. Do not perform any other refactors or modify any other phases from the list.

---

## Extension Follow-up:
These worry me, and I would like a refactor to either fix the code or fix the tests: 'foo'

---

## Git Commit Message Generation

Give me a standard git commit message for this. Make it detailed enough for most teams while remaining concise.

---

## Prompt for QA LLM All Phases Completed Review.

### Role & Context
You are a Principal Technical Architect and Lead Product Strategist. 
Review the multi-phase development plan (docs\devPlan.md), where your task is to perform a rigorous Quality Assurance (QA) audit and sanity check on this plan.

### Audit Objectives
Critically evaluate the plan across the following dimensions:
1. **Phase Dependencies & Handoffs:** Do the phases flow logically? Are there hidden dependencies or missing prerequisites between Phase N and Phase N+1?
2. **Gaps & Blindspots:** What critical edge cases, security concerns, testing strategies, or scaling bottlenecks were overlooked?
3. **Efficiency:** Are there redundant steps, over-engineered solutions, or opportunities to simplify?

### Required Output Format
Please organize your audit into the following sections:

#### 1. Executive Summary
* **Plan Health Rating:** [Score from 1 to 10 with a one-sentence justification]
* **Top 3 Strengths:** Brief list of what the plan gets right.
* **Top 3 Fatal Flaws / Blockers:** High-risk issues that must be addressed before developing the next phase plan.

#### 2. Phase-by-Phase Breakdown
For each phase in the plan, detail:
* **Critique:** Specific flaws, missing requirements, or unrealistic assumptions.
* **Edge Cases & Risks:** Scenarios the current plan fails to account for.

#### 3. Recommended Revisions
Provide concrete, updated action items or rewrites for the problematic sections of the plan, and place ther resuls in a file called docs\QA.md

---

Build an operations case on how to use `FOO`.  As a style example, use `docs\OC001 Scenario producer authors a sentry ambush scenario.md`.  Output your result as `docs\FOO.md.` Format the document into clear Markdown with section headings, lists, nested steps, and readable option/note subsections while preserving its content.

---

## Feature Suggestions

What would be another simple feature addition for this program? I am still slowly and carefully iterating toward writing a computer game version of the Star Fleet Battles board game. Just make sure your suggestions are consistent with the classic Star Fleet Battles rules where possible.

---

## Use PNG to Add a New Ship Type

I am providing a PNG that should become a selectable, renderable ship in the StartFleetBattles project. Complete the artwork normalization and the static catalog/gameplay registration in one pass.

### Inputs

Before editing, use these values as the source of truth. If a required value is missing, inspect the repository for an established convention; ask only if the choice would materially change the result.

- Source PNG path: [SOURCE_PNG_PATH]
- Target output path: [TARGET_OUTPUT_PATH]
- Ship name: [NAME]
- Race/faction ID: [FACTION_ID]
- Faction display label: [FACTION_LABEL]
- Art family ID: [ART_FAMILY_ID]
- Ship class: [CLASS]
- Art ID: [ART_ID]
- Hull/design ID: [HULL_ID]
- Design display name: [DISPLAY_NAME]
- Designation/abbreviation: [DESIGNATION]
- Include in the Const picker: [YES_OR_NO]
- Include in the shipped/default roster: [YES_OR_NO]
- Include in attract/default faction selection: [YES_OR_NO]
- Gameplay loadout source, if provisional: [LOADOUT_SOURCE_ID]
- Target canvas size, if known: [64x64_OR_128x128]

### Step 1: Inspect the source and repository conventions

1. Confirm the source PNG exists and inspect it visually.
2. Inspect `assets/ships/` and `src/config/hullArtCatalog.js`.
3. Inspect the catalog, built-in design catalog, shipbuilder frame/part library, naming schema, alliance configuration, attract-mode roster, visual resolver, and relevant tests before making changes.
4. Determine the closest existing artwork reference using faction/art family, ship class, canvas size, orientation, and occupied-pixel scale. Record the exact reference asset in the final report.
5. Identify whether this is a new art family, a new race/faction, or both. Do not silently treat a new race as only an art-family label.
6. Determine whether the gameplay profile is authoritative. If it is provisional, reuse the specified existing loadout via the project’s `loadoutSourceId` mechanism and mark it as placeholder metadata. Do not invent new combat statistics.

### Step 2: Normalize the PNG

Create the target PNG without overwriting the source.

- Keep PNG format with an RGBA channel.
- Remove matte/background color, halo, border, text, UI, cast shadow, and other non-ship pixels. Prefer the source alpha mask when it is reliable; remove low-alpha halo pixels without redesigning the ship.
- Preserve orientation, proportions, crisp pixel-art edges, and nearest-neighbor scaling. Do not stretch or distort.
- Use a square 64x64 canvas for frigates, scouts, fighters, bombers, destroyers, and other smaller hulls. Use 128x128 for large battlecruisers, dreadnoughts, and other large hulls when that matches the catalog convention.
- Center the ship with padding comparable to the selected reference and match its approximate occupied-pixel bounds.
- Use minimal editing. If the image already conforms, leave the ship artwork substantially unchanged.
- Keep filename, directory, and lowercase path conventions consistent with the catalog and `isSafeShipAssetPath`.

### Step 3: Measure and register the artwork

1. Programmatically measure the final PNG’s width, height, alpha values, transparent corners, occupied-pixel bounds, occupied-pixel count, and center.
2. Measure `contentRadius` using the project convention: consider pixels with alpha greater than 8 and measure to the far corner of each occupied pixel from the canvas center. Store the measured value, normally rounded to the catalog precision.
3. Add or update the art family in `HULL_ART_FAMILIES`, including its asset root, allowed factions, roster rules, and artwork record.
4. Register the artwork with its `artId`, filename, catalog class, width, height, `hexFit`, and measured `contentRadius`.
5. Confirm `getHullArt([ART_ID])` and `resolveShipVisual([ART_ID])` resolve the new PNG through the normal image pipeline. Do not embed image data in JavaScript.

### Step 4: Register the selectable ship

1. Add the built-in design record with the requested ID, faction/race, art family, art ID, display name, designation, frame ID, and `constVisible` setting.
2. If the design is provisional, set the loadout source to the specified existing design and add clear placeholder metadata explaining the inherited gameplay profile. Check the project’s definition generator before adding duplicate JSON; placeholder definitions may be generated from the design catalog.
3. Add a matching frame part with the correct geometry, size class, movement cost, turn mode, towing cost, maximum speed, and HET profile. Mirror the selected reference frame only when the design calls for the same movement profile.
4. Add the frame to the hull/frame ID registry and add its frame capacity and shield limits to the hull catalog when required.
5. If this is a new race, add its naming-schema label and abbreviation prefix. Confirm the hull is eligible for that race and does not appear under incompatible races.
6. Add the race/faction to attract-mode or default faction selection when requested.
7. Add it to the shipped/default roster when requested, and leave it out of `DEFAULT_ALLIANCES` when it should use the independent-team fallback. Add an explicit alliance test for that behavior.
8. Ensure any derived DAC/damage-table or gameplay projection lookup resolves the new placeholder name/design without changing existing designs.

### Step 5: Update tests and counts

Update affected tests rather than leaving stale hard-coded counts or snapshots. At minimum, cover the applicable items below:

- PNG dimensions, alpha, transparent corners, occupied bounds, center, and measured radius.
- Art-family and artwork catalog counts, paths, class, `hexFit`, and `contentRadius`.
- `getHullArt` and `resolveShipVisual` lookup behavior.
- Race/faction gating and hull-picker eligibility.
- Naming label and abbreviation prefix.
- Frame geometry, movement profile, capacity, and shield limits.
- Built-in design identity, placeholder source, projected movement, shields, weapons, cloak, plasma, mines, and other inherited systems.
- Shipped roster/default ship counts and identity snapshots.
- Attract-mode/default faction selection and alliance fallback.
- Browser Const-picker counts and image decoding, including selecting the new hull under its race.
- Documentation/static asset counts and any generated manifest checks.

Search for old counts and hard-coded hull lists across `src/` and `tests/` before declaring the work complete.

### Step 6: Verify the final integration

Run the full unit suite:

```text
npm.cmd test
```

Run the browser checks against a local server. The project’s browser scripts expect `http://localhost:8080/index.html`, so start `npm.cmd run serve` first or provide the project-supported `HEXGRID_URL`.

```text
npm.cmd run verify:const-builder
npm.cmd run verify:startup-attract
```

Also run `git diff --check`, visually inspect the final sprite, and confirm the original source PNG is still present and unchanged. Stop any temporary local server after verification.

### Final report

Report:

1. The exact reference asset and why it was the closest match.
2. Source and target paths, plus every artwork adjustment.
3. Final dimensions, PNG/RGBA format, alpha behavior, occupied-pixel count, bounds, center, `hexFit`, and measured `contentRadius`.
4. Catalog, race/faction, design, frame, naming, roster, attract-mode, alliance, and gameplay-profile changes.
5. Verification commands and results, including unit/browser test counts.
6. Any remaining concerns, especially provisional inherited gameplay statistics.

This is a programmer-maintained static asset. Do not add a runtime “Set Image” button, store image data in localStorage, embed the PNG as base64, or create a runtime image-editing control.

---

### Reference Ship Classes

**Ships:**

**Federation:**
*   **CA (Heavy Cruiser):** The iconic Constitution class. The baseline by which almost all other ships in the game are measured.
*   **DD (Destroyer):** The workhorse of the smaller fleet actions. Decent phaser suites and usually carrying a pair of photon torpedoes.

**Klingon:**
*   **D7 (Heavy Cruiser):** The absolute icon of the Klingon fleet. Highly maneuverable, carrying a potent mix of disruptors and anti-drone phasers.
*   **D6 (Heavy Cruiser):** The predecessor to the D7. Slightly less efficient power systems, but still a formidable frontline combatant.

## Get Rules
Give me the full movement rules for star fleet battles. Make sure there is plenty of detail, and present your output in markdown format as code.