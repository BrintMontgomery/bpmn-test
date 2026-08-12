# Star Fleet Battles Game Development Prompts

This document serves as a checklist and guide for iterating on a BPMN program, focusing on feature suggestions, code refactoring, commit message generation, and phase completion updates. 

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
You are assisting in refactoring the client-side codebase for this program, a BPMN utility.

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

## Add Synthetic Use Case

In [markdown](examples/markdown/) area, build me another example SOP.  It should be a simple one on using an ATM.  Make sure it follows the required conventions in [MARKDOWN_AUTHORING.md](docs/MARKDOWN_AUTHORING.md) .