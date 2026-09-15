---
name: detailed-design-first-draft
user-invocable: false
description: >
  Use when writing a Detailed Design document — a new one, or revising an existing one with new
  information. Reads the approved Proposal, interviews the user section by section, then writes
  the draft to the location resolved via `documentation.specs`.
argument-hint: <proposal-file-path | work-item-id | design-file-path>
---

Use this skill when:
- You are writing a Detailed Design document, whether drafting a new one or revising an existing one with new information

You are writing a Detailed Design document — a new one, or revising an existing one whose path
the caller passed in. This skill elaborates an approved Proposal into a full behavior spec — user
scenarios, functional requirements, detailed behavior, and non-functional requirements. Do not
draft interfaces, classes, or component breakdowns here; that is the `dev-spec-first-draft`
skill's job once a deliverable moves into implementation.

## Steps

### 1 — Gather context

If revising, the calling command has already found the existing Detailed Design and passed its
path — read it in full now, and treat the new brief as the reason for revision rather than a
from-scratch rewrite. Its existing content already reflects the architecture docs and prior-art
research consulted during the prior pass — reuse that instead of re-discovering it from scratch,
and only look further for gaps the new brief actually raises.

Read the approved Proposal in full — its path is passed in by the caller (`write-detailed-design`
resolves it before invoking this skill, and hard-stops if no Proposal is found — see that
command). The Proposal already answers the problem/approach/success-metrics questions at a high
level — do not re-ask those; use it as the narrative anchor for this document.

Use the `find-repo-documentation` skill to read any existing architecture docs relevant to the
feature area, so the detailed design doesn't propose something the system already does — skip
this if revising and the existing Detailed Design's content already reflects the current
architecture.

Spawn one or more `dev-team:researcher` agents to research any prior art, existing solutions, or
external resources that would usefully inform the detailed behavior — the same kind of research
the Proposal already drew on, refreshed now that more detail is being decided — skip this if
revising and the existing Detailed Design's research already covers the new brief's scope.

### 2 — Interview the user section by section

Use the `document-section-interview` skill against
[`assets/detailed_design_template.md`](assets/detailed_design_template.md), passing the existing
Detailed Design from step 1 if revising.

### 3 — Write the draft

Resolve the file's location and naming via the `write-repo-documentation` skill's
`documentation.specs` placement. If revising, use the existing document's location instead.

Write (or update) the file following the template at
[`assets/detailed_design_template.md`](assets/detailed_design_template.md). Each section there
carries a note on its goal and the questions to open with — treat those as interview prompts, not
just section descriptions. Fill every section with resolved content from step 2's interview,
except `## Deliverables` — leave its placeholder comment as-is; `design-deliverable-breakdown`
fills it in later, once the design content above is finalized. Write or regenerate the
`## Contents` section last, once every other section is in its final form.

Once the draft is complete, invoke the `document-concision-pass` skill on the file to tighten it.

### 4 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
