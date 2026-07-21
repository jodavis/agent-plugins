---
name: design-deliverable-breakdown
user-invocable: false
description: >
  Use when breaking down a design doc into deliverables.
  Sizes deliverables to be independently cuttable, creates tracked feature-work-items, and updates the design with links.
argument-hint: <path to _design_*.md file>
---

Use this skill when:
- You are breaking down a design doc into deliverables
- You need to create tracked feature-work-items for a design's deliverables

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

Add a `## Deliverables` section to the design doc (the placeholder left by `design-first-draft`).
For each deliverable write:

- A short title
- A one-paragraph description of the independent value it delivers on its own
- A checklist of product-level "done" criteria (observable outcomes, not implementation tasks)

### 2 — Pause for approval

Save the updated design doc and tell the user:

> Deliverable breakdown written to `<path>`. Please review — edit any deliverable or add `> **Review:** your comment`. Tell me when you're ready to create tracked work items.

**PAUSE — wait for approval or change requests. Apply any changes before continuing.**

### 3 — Reconcile with existing work items

If `write-design-spec` already gathered a list of related existing work items (its step 2, before
the first draft was written), use that list here instead of asking fresh: match each drafted
deliverable against the list and reuse or repurpose the item that fits, if any. For any item on
the list that doesn't match any drafted deliverable, tell the user it may no longer be relevant
and ask whether to close it.

If no such list is available — for example this skill was invoked on its own, outside the
`write-design-spec` flow — ask the user now instead. Use `AskUserQuestion` to ask, per deliverable
(or in batches of up to 4): "Does this deliverable correspond to an existing feature-work-item?"
with options "Yes — I'll provide the key", "No — create a new one".

**PAUSE — wait for the answer.**

For any deliverable matched to an existing item, record its key and treat the design's
description as the source of truth to write into that item in step 4 (repurposing it rather than
creating a duplicate).

### 4 — Create or update tracked work items

Invoke `get-project-configuration` and read `work-tracking`. If it's `null` or empty, skip
straight to step 5 — no tracker is configured, so the design's deliverable list is the only record.

Use the matching adapter skill (per `get-project-configuration`'s provider dispatch table):

- For deliverables matched to an existing item in step 3, update that item's summary/description
  from the deliverable's title and description.
- For all other deliverables, create a new `feature-work-item` type
  (`work-tracking.<provider>.feature-work-item.type`, e.g. `Epic` for a Jira project; no parent —
  deliverables are siblings). Use the deliverable's title and description as the summary.

### 5 — Update the design doc

Replace each deliverable title in `## Deliverables` with a hyperlink to its tracked work item, if
one was created or matched. Keep all descriptions and done-criteria in place. The section remains
in the design doc permanently — future agents may not have tracker access.
