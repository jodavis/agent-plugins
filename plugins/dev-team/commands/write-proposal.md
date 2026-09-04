---
description: >
  Use when writing a complete new Proposal document for a feature — the short goal/approach/
  justification document that sells the problem and solution.
  Guides through context gathering, first draft, iterative refinement, critical readiness review, and an offer to continue straight into detailed design.
argument-hint: <work-item-id | #issue | feature name and description | pasted notes>
---

Use this skill when:
- A user asks to propose a feature, answering "what is the problem? what is the proposed approach? why should we do this?"
- You need to produce a complete Proposal document, ahead of a Detailed Design

You are writing a complete new Proposal document, working with the user to refine it and
verifying it actually justifies the work. This is a short problem/approach/justification
document — read by someone deciding whether to fund the work — not the full behavior spec (that's
`write-detailed-design`'s job) or an implementation plan (`write-dev-spec`'s job).

## Steps

### 1 — Resolve the brief

Use the `gather-brief-sources` skill to resolve the argument into a feature brief, from whatever
mix of sources it points to (a tracked work item, pasted notes, a file, a link, or a combination).
A brief with no tracked work item among its sources is fine, as long as at least one source
resolved — `gather-brief-sources` already warns the user and asks them to fix or drop any
individually-referenced source (e.g. a work-item key) that doesn't actually resolve.

If `gather-brief-sources` could not resolve any sources at all, tell the user and stop.

### 2 — Identify related existing work items

Ask the user: "Are there any existing work items — tickets, epics, tasks — related to this
proposal that should be factored in, even if the proposal ends up changing direction?" If they
name any, resolve each via `identify-project-work-items` and the matching `work-with-<provider>`
adapter, and read its summary/description.

Keep this list for the rest of this flow: it can inform `proposal-first-draft`'s research (step
4), and — if the user continues straight into `write-detailed-design` at the end of this flow — it
carries forward without re-asking.

### 3 — Check for an existing Proposal

Ask the user: "Does a Proposal already exist for this feature/task — a file path or an external
location you can point me to?" Since Proposals aren't part of the `documentation` config schema,
there is no automated search to fall back on. If they name one, read it in full —
`proposal-first-draft` will be invoked in revise mode. If not, proceed to draft a new one.

### 4 — Write the first draft

Use the `proposal-first-draft` skill with the brief (and any related existing work items from step
2) to gather context from docs, prior art, and the user, and write the draft — passing the
existing Proposal's path from step 3 to invoke it in revise mode if one was found.

**PAUSE — wait for the user to review the draft.**

### 5 — Refine the proposal

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 6 — Readiness review

Use the `document-readiness-review` skill on the proposal with `researcher-proposal-review` to
verify it — problem/solution fit — actually justifies the work: a falsifiable problem, a solution
that plausibly resolves it, explicit non-goals, and genuinely considered alternatives.

### 7 — Update the source work item

Use the `source-work-item-sync` skill to update the source work item (if any) with a summary of
the finalized proposal.

### 8 — Final concision pass

Use the `document-concision-pass` skill on the proposal to tighten it, covering everything the
discussion round added since its own first-draft-time pass.

### 9 — Offer to continue into detailed design

Use `AskUserQuestion`: "Proposal finalized. Continue now into the detailed design phase, or stop
here and pick it up later with `/write-detailed-design <work-item-id>`?"

- **"Continue now"** → invoke `write-detailed-design`'s flow in this same turn, passing the
  proposal path, work-item-id, and the related-existing-work-items list from step 2 if still in
  context.
- **"Stop here for now"** → tell the user the resume command and stop.
