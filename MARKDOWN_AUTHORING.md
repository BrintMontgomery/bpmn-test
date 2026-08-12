# SOP Markdown authoring conventions

The structural extractor expects the following stable template. Keep these
conventions intact so extraction remains deterministic and semantic modeling
can be reviewed separately from parsing.

## Required sections

Use these level-two headings, in this order:

1. `## Actors`
2. `## Context`
3. `## Preconditions`
4. `## Outcome`
5. `Version`
6. `## Main Path`
7. `## Options from main path:`
8. `## Notes`

`Context` and `Outcome` contain paragraphs. `Actors`, `Preconditions`, and
`Version` contain one `*` bullet per entry.

## Main path

Main-path entries are sequential numbered Markdown lines. The owning actor is
the first bold actor in the step; later bold actors are counterparties and are
preserved for semantic review.

```markdown
1. **Case Manager** receives the admission notification.  
2. **Case Manager** reviews the report with the **Consumer**.  
```

Two trailing spaces are the Markdown hard-break convention. The extractor
strips trailing whitespace before matching.

## Options

Each option uses a lettered heading, one `Trigger:` line, and sequential
numbered steps. Option bodies are intentionally unbolded; actor attribution
there is a semantic-modeling decision rather than a regex extraction.

```markdown
### Option A — Consumer Requests an Additional Contact

Trigger: The Consumer requests an additional contact.

1. Case Manager completes an ROI with the Consumer.  
2. If the contact agrees, Case Manager informs Floor Staff.  
```

Branching language inside an option is retained as source text and must be
modeled as an internal gateway by the semantic step when appropriate.

## Notes

Notes use letter markers and end with a sentinel. Both escaped and bare forms
are accepted:

```markdown
\[a\] Protective orders restrict contact.
\[ end \]
```

Inline references in main-path and option steps may likewise use `\[a\]` or
`[a]`. Every reference must have exactly one corresponding Notes entry.
