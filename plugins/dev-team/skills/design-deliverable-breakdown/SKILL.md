---
name: design-deliverable-breakdown
user-invocable: false
description: >
  Use when breaking down a Detailed Design doc into deliverables.
  Sizes deliverables to be independently cuttable and drafts the Detailed Design doc's Deliverables section for user approval.
argument-hint: <path to _design_*.md file>
---

Use this skill when:
- You are breaking down a Detailed Design doc into deliverables
- You need to draft a deliverable breakdown for user approval before tracked work items are created

## Sizing rule: independently cuttable

Each deliverable must be **independently cuttable**:

- It makes sense to do completely, or not at all — no half-finished version is meaningful.
- It provides value once done, without depending on a sibling deliverable shipping *after* it.
  Depending on a sibling that ships *before* it is fine — deliverables can build on each other in
  order — but a deliverable that only lays groundwork for a later one is not independently
  cuttable on its own.
- No part of it provides value until it is complete — do not split a deliverable just to make it
  smaller if the pieces have no standalone value.

Two failure modes this rule exists to prevent:
- A deliverable finishes but creates no visible value on its own (it was only groundwork for a
  later one) — the team moves on and the product carries dead code.
- A deliverable is half-done but already generating enough value that the team calls it "done
  enough" and moves on — leaving a half-finished item with no one coming back to close it out.

Deliverables are **feature-work-items**, siblings of one another with no shared parent. Each one
later becomes its own `write-dev-spec` pass.

## Steps

### 1 — Draft the deliverable breakdown

Add a `## Deliverables` section to the Detailed Design doc (the placeholder left by
`detailed-design-first-draft`). For each deliverable write:

- A short title
- A one-paragraph description of the independent value it delivers on its own
- A checklist of product-level "done" criteria (observable outcomes, not implementation tasks)

### 2 — Pause for approval

Save the updated Detailed Design doc and tell the user:

> Deliverable breakdown written to `<path>`. Please review — edit any deliverable or add `> **Review:** your comment`. Tell me when you're ready to continue.

**PAUSE — wait for approval or change requests. Apply any changes before continuing.**
