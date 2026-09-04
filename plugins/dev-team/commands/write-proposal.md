---
description: >
  Use when writing a complete new PM-style design doc for a feature.
  Guides through context gathering, first draft, iterative refinement, breakdown into independently cuttable deliverables, critical readiness review, and work item creation.
argument-hint: <work-item-id | #issue | feature name and description | pasted notes>
---

Use this skill when:
- A user asks to design a feature, answering "what is the problem? what is the solution? does this solution solve the problem?"
- You need to produce a complete _design_*.md design document, broken into independently cuttable deliverables

You are writing a complete new design doc, working with the user to refine it, breaking it down
into deliverables, and verifying it actually solves the stated problem. This is a PM-style design
of observable system behavior — not an implementation plan. Once each deliverable has a
feature-work-item, `write-dev-spec` picks it up to plan the "how."

## Steps

### 1 — Resolve the brief

Use the `gather-brief-sources` skill to resolve the argument into a feature brief, from whatever
mix of sources it points to (a tracked work item, pasted notes, a file, a link, or a combination).
A brief with no tracked work item among its sources is fine, as long as at least one source
resolved — `gather-brief-sources` already warns the user and asks them to fix or drop any
individually-referenced source (e.g. a work-item key) that doesn't actually resolve.

If `gather-brief-sources` could not resolve any sources at all, tell the user and stop.

### 2 — Identify related existing work items

Ask the user: "Are there any existing work items — tickets, epics, tasks — related to this design
that should be factored in, even if the design ends up changing direction?" If they name any,
resolve each via `identify-project-work-items` and the matching `work-with-<provider>` adapter,
and read its summary/description.

Keep this list for the rest of this flow: it can inform `design-first-draft`'s research (step 3)
even for items that turn out to no longer apply, and `design-create-work-items` (step 7) uses
it to reuse or repurpose existing items instead of asking about them again from scratch.

### 3 — Write the first draft

Use the `design-first-draft` skill with the brief (and any related existing work items from step
2) to gather context from docs, prior art, and the user, and write the draft design doc.

**PAUSE — wait for the user to review the draft.**

### 4 — Refine the design

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 5 — Deliverable breakdown

Use the `design-deliverable-breakdown` skill to draft the design's deliverable breakdown into
independently cuttable deliverables and pause for user approval.

### 6 — Readiness review

Use the `document-readiness-review` skill on the design doc with `researcher-design-review` to
verify it — problem/solution fit and deliverable breakdown together — actually solves the stated
problem, is complete, and each deliverable is genuinely independently cuttable.

### 7 — Create tracked work items

Use the `design-create-work-items` skill to reconcile deliverables with existing work items,
create (or reuse) tracked feature-work-items, and update the design doc with links. Pass it the
related existing work items identified in step 2, if any.

### 8 — Update the source work item

Use the `design-work-items` skill to update the source work item (if any) with a summary of the
finalized design and links to its deliverables.

### 9 — Hand off

Tell the user: each deliverable now has a feature-work-item. Run `/write-dev-spec
<feature-work-item-id>` on any of them to produce its implementation spec.
