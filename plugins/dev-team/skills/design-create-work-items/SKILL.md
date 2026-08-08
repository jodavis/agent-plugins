---
name: design-create-work-items
user-invocable: false
description: >
  Use when an approved, readiness-reviewed deliverable breakdown needs tracked work items.
  Reconciles deliverables with existing work items, creates or updates feature-work-items, and updates the design doc with the assigned links.
argument-hint: <path to _design_*.md file>
---

Use this skill when:
- A design doc's deliverable breakdown has been drafted, approved, and readiness-reviewed
- You need to create or reuse tracked feature-work-items for a design's deliverables

## Steps

### 1 — Reconcile with existing work items

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
description as the source of truth to write into that item in step 2 (repurposing it rather than
creating a duplicate).

### 2 — Create or update tracked work items

Invoke `get-project-configuration` and read `work-tracking`. If it's `null` or empty, skip
straight to step 3 — no tracker is configured, so the design's deliverable list is the only record.

Use the matching adapter skill (per `get-project-configuration`'s provider dispatch table):

- For deliverables matched to an existing item in step 1, update that item's summary/description
  from the deliverable's title and description.
- For all other deliverables, create a new `feature-work-item` type
  (`work-tracking.<provider>.feature-work-item.type`, e.g. `Epic` for a Jira project; no parent —
  deliverables are siblings). Use the deliverable's title and description as the summary.

### 3 — Update the design doc

Replace each deliverable title in `## Deliverables` with a hyperlink to its tracked work item, if
one was created or matched. Keep all descriptions and done-criteria in place. The section remains
in the design doc permanently — future agents may not have tracker access.
