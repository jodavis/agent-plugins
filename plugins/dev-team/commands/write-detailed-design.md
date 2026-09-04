---
description: >
  Use when elaborating an approved Proposal into a complete Detailed Design document for a feature.
  Guides through proposal resolution, context gathering, first draft, iterative refinement, deliverable breakdown, critical readiness review, and work item creation.
argument-hint: <work-item-id | proposal-file-path>
---

Use this skill when:
- A Proposal has been approved and you need to elaborate it into full observable system behavior
- You need to produce a complete _design_*.md Detailed Design document, broken into independently cuttable deliverables

You are writing a complete new Detailed Design doc, working with the user to refine it, breaking
it down into deliverables, and verifying it is complete. This document elaborates an
already-approved Proposal (problem + approach) into full observable behavior — not an
implementation plan. Once each deliverable has a feature-work-item, `write-dev-spec` picks it up
to plan the "how."

## Steps

### 1 — Resolve the Proposal

If invoked in-line from `write-proposal`'s chain-offer step, use the proposal path,
`work-item-id`, and related-existing-work-items list already in hand — do not re-resolve any of
it.

Otherwise, use the `gather-brief-sources` skill to resolve the argument into the Proposal content
— a file path, pasted content, or a location the user names (a URL, a Confluence page, etc.).
There is no `documentation.proposals` search to fall back on, since Proposals are deliberately not
part of the `documentation` config schema.

If no Proposal is found at all: **hard stop**. Tell the user a Proposal is required before
Detailed Design — skipping it means skipping the "think about what the solution should be" phase
— and point them to `/write-proposal`. Do not offer to proceed without one.

### 2 — Check for an existing Detailed Design

Substitute the resolved `work-item-id` (if any) into `documentation.specs.search` (from
`get-project-configuration`) to check whether a Detailed Design doc already exists for this
feature/task. This is a different lookup from step 1 (finding the Proposal predecessor) — don't
conflate the two. If a matching document is found, read it in full — `detailed-design-first-draft`
will be invoked in revise mode. If no `work-item-id` is available (e.g. cold-started from a bare
proposal-file-path with no derivable id), skip this check and proceed to draft a new document.

### 3 — Write the first draft

Use the `detailed-design-first-draft` skill with the resolved Proposal (and any related existing
work items from step 1, if still in context) to gather context from docs, prior art, and the
user, and write the draft — passing the existing Detailed Design's path from step 2 to invoke it
in revise mode if one was found.

**PAUSE — wait for the user to review the draft.**

### 4 — Refine the design

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 5 — Readiness review

Use the `document-readiness-review` skill on the Detailed Design doc with
`researcher-detailed-design-review` to verify it — user-scenario completeness,
requirements-table well-formedness, and success-metric observability — is complete and correct.

### 6 — Deliverable breakdown

Use the `design-deliverable-breakdown` skill to draft the design's deliverable breakdown into
independently cuttable deliverables and pause for user approval.

### 7 — Readiness review on the breakdown

Use the `document-readiness-review` skill again on the Detailed Design doc with
`researcher-detailed-design-review` to verify the deliverable breakdown — each deliverable is
genuinely independently cuttable.

### 8 — Update the source work item

Use the `source-work-item-sync` skill to update the originating source (if any) with a summary of
whichever document(s) are finalized so far.

### 9 — Final concision pass

Use the `document-concision-pass` skill on the Detailed Design doc to tighten it, covering
everything the discussion and breakdown rounds added since its own first-draft-time pass.

### 10 — Hand off

Tell the user: each deliverable now has a feature-work-item. Run `/write-dev-spec
<deliverable-id>` on any of them to produce its implementation spec.
