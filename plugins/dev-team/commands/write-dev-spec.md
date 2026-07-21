---
description: >
  Use when writing a complete new dev spec for a feature or GitHub issue.
  Guides through context gathering, first draft, iterative refinement, readiness review, and task breakdown.
argument-hint: <work-item-id | #issue | feature name and description>
---

Use this skill when:
- A user asks to spec a new feature or GitHub issue at the implementation level
- You need to produce a complete _spec_*.md dev spec

You are writing a complete new dev spec, working with the user to refine it, breaking it down into
tasks, and verifying that it is complete.

## Steps

### 1 — Resolve the feature brief

Use the `gather-brief-sources` skill to resolve the argument into a feature brief, from whatever
mix of sources it points to (a tracked work item, pasted notes, a file, a link, or a combination).
A brief with no tracked work item among its sources is fine, as long as at least one source
resolved — `gather-brief-sources` already warns the user and asks them to fix or drop any
individually-referenced source (e.g. a work-item key) that doesn't actually resolve.

Additionally, check for an existing design doc: substitute the resolved `work-item-id` (if any)
into `documentation.specs.search` (from `get-project-configuration`). If a design doc is found,
read it in full and fold it in as the primary source — it already answers the problem/goals/
behavior questions. Record its path for `dev-spec-first-draft`'s `> **Design:**` header line.

If `gather-brief-sources` could not resolve any sources at all, tell the user and stop.

### 2 — Write the first draft

Use the `dev-spec-first-draft` skill with the feature brief (and design doc, if found) to gather
context from docs, source code, and the user, and write the draft spec file.

**PAUSE — wait for the user to review the draft.**

### 3 — Refine the spec

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 4 — Design readiness review

Use the `document-readiness-review` skill on the spec file with `researcher-dev-spec-review` to
verify the design content is implementation-ready.

### 5 — Task breakdown

Use the `dev-spec-task-breakdown` skill to break the spec into tasks, pause for user approval, and create tracked work items.

### 6 — Task breakdown readiness review

Use the `document-readiness-review` skill again with `researcher-dev-spec-review` — this time
focused on the task breakdown — to verify tasks are scoped and specified clearly enough to
implement.

### 7 — Update work items

Use the `dev-spec-task-work-items` skill to update project work items with summaries of the finalized design decisions.
