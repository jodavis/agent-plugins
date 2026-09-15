---
name: proposal-first-draft
user-invocable: false
description: >
  Use when writing a Proposal document — a new one, or revising an existing one with new
  information. Gathers context from docs and prior art, interviews the user section by section,
  then writes the draft to a file at the user-chosen location.
argument-hint: <feature brief | work-item-id | proposal-file-path>
---

Use this skill when:
- You are writing a Proposal document, whether drafting a new one or revising an existing one with new information

You are writing a Proposal document — a new one, or revising an existing one whose path the
caller passed in. This skill designs observable system **behavior** — the problem and the
proposed solution — not implementation. Do not draft interfaces, classes, or component
breakdowns here; that is the `dev-spec-first-draft` skill's job once a deliverable moves into
implementation.

## Steps

### 1 — Gather context

If revising, the calling command has already found the existing Proposal and passed its path —
read it in full now, and treat the new brief as the reason for revision rather than a
from-scratch rewrite. Its `> **Source:**` header line and `## Alternatives Considered` section
already record the prior pass's research — reuse that instead of researching from scratch, and
only spawn new research for gaps the new brief actually raises.

Use the `find-repo-documentation` skill to read any existing architecture docs relevant to the
feature area, so the proposal doesn't propose something the system already does.

Spawn one or more `dev-team:researcher` agents to research the *problem space*, not implementation
patterns — skip this if revising and the existing Proposal's research already covers the new
brief's scope. Ask each agent to look into:

- Similar problems and how they were solved elsewhere (prior art, case studies)
- Existing 3rd-party or internal solutions that already address this problem, in whole or in part
- Any other resources — standards, competitor products, prior internal proposals — that would
  usefully inform the proposed solution

Each agent returns findings as prose with source links, for citation in `## Alternatives
Considered`.

### 2 — Interview the user section by section

Use the `document-section-interview` skill against
[`assets/proposal_template.md`](assets/proposal_template.md), passing the existing Proposal from
step 1 if revising.

### 3 — Write the draft

If drafting new, determine the proposal's save location by asking the user where to save it (a
file path or an external location) — the Proposal is not part of the `documentation` config
schema, so there is no automated placement to derive a location from. If revising, use the
existing document's location instead.

Write (or update) the file following the template at
[`assets/proposal_template.md`](assets/proposal_template.md). Each section there carries a note on
its goal and the questions to open with — treat those as interview prompts, not just section
descriptions. Fill every section with resolved content from step 2's interview. Write or
regenerate the `## Contents` section last, once every other section is in its final form.

Once the draft is complete, invoke the `document-concision-pass` skill on the file to tighten it.

### 4 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
