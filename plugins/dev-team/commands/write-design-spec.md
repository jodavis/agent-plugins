---
description: >
  Use when writing a complete new PM-style design doc for a feature.
  Guides through context gathering, first draft, iterative refinement, critical readiness review, and breakdown into independently cuttable deliverables.
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

If the work item does not exist, tell the user and stop.

### 2 — Write the first draft

Use the `design-first-draft` skill with the brief to gather context from docs, prior art, and the
user, and write the draft design doc.

**PAUSE — wait for the user to review the draft.**

### 3 — Refine the design

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 4 — Design readiness review

Use the `document-readiness-review` skill on the design doc with `researcher-design-review` to
verify it actually solves the stated problem and is complete.

### 5 — Deliverable breakdown

Use the `design-deliverable-breakdown` skill to break the design into independently cuttable
deliverables, pause for user approval, and create (or reuse) tracked feature-work-items.

### 6 — Deliverable breakdown readiness review

Use the `document-readiness-review` skill again with `researcher-design-review` — this time
focused on the deliverable breakdown — to verify each deliverable is genuinely independently
cuttable.

### 7 — Update the source work item

Use the `design-work-items` skill to update the source work item (if any) with a summary of the
finalized design and links to its deliverables.

### 8 — Hand off

Tell the user: each deliverable now has a feature-work-item. Run `/write-dev-spec
<feature-work-item-id>` on any of them to produce its implementation spec.
