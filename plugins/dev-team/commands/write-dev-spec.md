---
description: >
  Use when writing a complete new dev spec for a feature or GitHub issue.
  Guides through context gathering, first draft, iterative refinement, task breakdown, readiness review, and work item creation.
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

### 1.5 — Bootstrap the feature branch

Skip this step if step 1 resolved no `work-item-id` at all — there is no feature-work-item to
bootstrap a branch for yet; the user just keeps drafting on whatever branch they're already on,
and this happens later instead, in step 6, once (or if) a feature-work-item exists.

Otherwise, use the `ensure-feature-branch` skill with the resolved `work-item-id`. This creates
(or finds) the feature's own branch and checks it out — before any draft exists yet, so the spec
can be staged and committed directly onto it as drafting happens, with no separate root-branch or
spec-commit-branch step required first. If it does not respond `successful`, stop and report the
failure in detail.

### 2 — Write the first draft

Use the `dev-spec-first-draft` skill with the feature brief (and design doc, if found) to gather
context from docs, source code, and the user, and write the draft spec file.

**PAUSE — wait for the user to review the draft.**

### 3 — Refine the spec

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 4 — Task breakdown

Use the `dev-spec-task-breakdown` skill to draft the spec's task breakdown and pause for user
approval.

### 5 — Readiness review

Use the `document-readiness-review` skill on the spec file with `researcher-dev-spec-review` to
verify the full spec — design content and task breakdown together — is implementation-ready and
complete.

### 6 — Create tracked work items

Use the `dev-spec-create-work-items` skill to create tracked work items for the approved tasks
(and any related features), link task dependencies in the tracker, and update the spec with the
assigned keys.

If this step resolved (or created) a feature-work-item — whether or not step 1.5 already ran for
it — use the `ensure-feature-branch` skill with that feature-work-item's id. This guarantees the
spec is committed and PR'd by the end of this command even if the user never staged/committed it
themselves while drafting, and is a no-op if step 1.5 already left everything in order. Skip this
if no feature-work-item exists at all (the user chose to skip work-item tracking entirely) — there
is nothing to bootstrap a branch for.

### 7 — Update work items

Use the `dev-spec-task-work-items` skill to update project work items with summaries of the finalized design decisions.
