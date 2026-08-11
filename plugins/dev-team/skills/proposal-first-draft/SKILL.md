---
name: proposal-first-draft
user-invocable: false
description: >
  Use when writing a first draft of a complete new Proposal document, or revising an existing
  one. Interviews the user section by section, gathering context from docs and prior art, then
  writes the draft to a file at the user-chosen location.
argument-hint: <feature brief | work-item-id | proposal-file-path>
---

Use this skill when:
- You are writing a first draft of a complete new Proposal document, or revising an existing one

This skill designs observable system **behavior** — the problem and the proposed solution — not
implementation. Do not draft interfaces, classes, or component breakdowns here; that is the
`dev-spec-first-draft` skill's job once a deliverable moves into implementation.

## Steps

### 1 — Gather context

Use the `find-repo-documentation` skill to read any existing architecture docs relevant to the
feature area, so the proposal doesn't propose something the system already does.

Spawn one or more `dev-team:researcher` agents to research the *problem space*, not implementation
patterns. Ask each agent to look into:

- Similar problems and how they were solved elsewhere (prior art, case studies)
- Existing 3rd-party or internal solutions that already address this problem, in whole or in part
- Any other resources — standards, competitor products, prior internal proposals — that would
  usefully inform the proposed solution

Each agent returns findings as prose with source links, for citation in `## Alternatives
Considered`.

Interview the user section by section, following
[`assets/proposal_template.md`](assets/proposal_template.md)'s section order:

- Open each section with its own opening question from the template.
- Follow up in plain conversation — not constrained to `AskUserQuestion`'s multiple-choice shape
  — until there's enough to draft that section.
- When you can infer a likely answer from the brief, prior docs, or research already gathered,
  offer it as a suggestion and explicitly ask the user to confirm or correct it (e.g. "It looks
  like the problem you're trying to solve is.... Do I have that right?"). Never assume an
  inference is correct.
- On a section with a genuine, material trade-off — a design choice with more than one
  reasonable approach, or a proposed solution that only partially addresses the stated problem —
  state the alternative(s) and their pros/cons before accepting the user's answer, and ask
  probing follow-ups to refine a half-formed answer rather than drafting from it as-is. Reserve
  this for real trade-offs (scope, cost, risk, UX) — not reflexive pushback on every answer.
- **Exception: the Background section is always treated as fact**, not opinion — ask clarifying
  questions to get it right, but never challenge it or offer alternatives to what already exists.

`AskUserQuestion` remains available for genuinely discrete-option decisions; it just isn't the
default shape of the whole gathering phase.

Treat this step as the place unresolved questions get eliminated, not deferred. If you notice a
gap while writing the draft in step 3, stop and go back through this same interview process
before continuing — do not carry it forward into the draft's `## Open Questions` section instead.
Before finalizing the draft, if there's a question you could ask that would close a gap, ask it.
A `> TBD: reason` or an `## Open Questions` entry is only allowed to remain when the user has
explicitly agreed it should stay open (e.g. "I don't know, we'll have to figure that out as we
go") — never a silent default when drafting wraps up, and never for a question you simply
haven't asked yet.

### 2 — Revising an existing document

If a Proposal document for this feature/task already exists, the calling command will have
already found it and will be invoking this skill in revise mode, passing its path. Read the
existing document in full. Treat the new brief as the reason for revision, not as a
from-scratch rewrite: walk the document's sections in order using step 1's interview process,
asking what actually changes in each one — a revision may touch several existing sections, not
just append one bounded new part. Continue to step 3 once every changed section is resolved.

### 3 — Write the first draft

Determine the proposal's save location by asking the user where to save it (a file path or an
external location) — the Proposal is not part of the `documentation` config schema, so there is no
`documentation.proposals` placement to derive a location from. Skip this if revising an existing
document — use its current location instead.

Write (or update) the file following the template at
[`assets/proposal_template.md`](assets/proposal_template.md). Each section there carries a note on
its goal and the questions to open with — treat those as interview prompts, not just section
descriptions. Fill every section with resolved content from step 1 or 2's interview. Write or
regenerate the `## Contents` section last, once every other section is in its final form.

Once the draft is complete, invoke the `document-concision-pass` skill on the file to tighten it.

### 4 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
