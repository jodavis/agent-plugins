---
name: design-first-draft
user-invocable: false
description: >
  Use when writing a first draft of a complete new design doc or a new part of an existing one.
  Gathers context from docs, prior art, and the user, then writes the draft to a _design_*.md file.
argument-hint: <feature brief | work-item-id | design-file-path>
---

Use this skill when:
- You are writing a first draft of a complete new design doc, or a new deliverable/section of an existing one

This skill designs observable system **behavior** — the problem and the proposed solution — not
implementation. Do not draft interfaces, classes, or component breakdowns here; that is the
`dev-spec-first-draft` skill's job once a deliverable moves into implementation.

## Steps

### 1 — Gather context

Use the `find-repo-documentation` skill to read any existing architecture docs relevant to the
feature area, so the design doesn't propose something the system already does.

Spawn one or more `dev-team:researcher` agents to research the *problem space*, not implementation
patterns. Ask each agent to look into:

- Similar problems and how they were solved elsewhere (prior art, case studies)
- Existing 3rd-party or internal solutions that already address this problem, in whole or in part
- Any other resources — standards, competitor products, prior internal proposals — that would
  usefully inform the proposed solution

Each agent returns findings as prose with source links, for citation in `## Alternatives
Considered` and `## Related Docs`.

Use `AskUserQuestion` to ask the user focused questions that fill gaps the brief and research
don't answer. Good questions cover:

- The problem itself: who has it, how it manifests, what evidence supports it
- Target users / use cases
- Success criteria — how you'd know the problem is actually solved
- Explicit non-goals — what this design deliberately will not address
- Constraints (timeline, dependencies, things that must not change)
- Key behavioral choices where multiple reasonable solutions exist

Skip questions already answered by the brief or research. Provide 2–4 concrete option choices per question; the user can always pick "Other". Batch up to 4 questions per `AskUserQuestion` call.

**PAUSE — wait for the user's answers before continuing.**

If answers raise new ambiguities that would materially affect the design, ask one more targeted follow-up round. Otherwise proceed.

Treat this step as the place unresolved questions get eliminated, not deferred. If you notice a gap while writing the draft in step 2, stop and go back through this same research/`AskUserQuestion` process before continuing — do not carry it forward into the draft's Risks & Open Questions section instead. An item belongs in Risks & Open Questions only if the user was asked and explicitly said something like "I don't know, we'll have to figure that out as we go" — a genuinely open question that can't be resolved by research or a decision right now. It is not for questions you simply haven't asked yet, or that research could answer.

### 2 — Write the first draft

Determine the proposal's save location by asking the user where to save it (a file path or an
external location) — the Proposal is not part of the `documentation` config schema, so there is no
`documentation.proposals` placement to derive a location from.

Write the file following the template at
[`assets/proposal_template.md`](assets/proposal_template.md). Each section there carries a note on
its goal and the questions to open with — treat those as interview prompts, not just section
descriptions.

Fill every section with resolved content — research or ask about anything you don't yet know before writing it in, using step 1's process. Reserve `> TBD: reason` only for items the user explicitly deferred (e.g. "we'll figure it out as we go"), not for questions you simply haven't asked yet.

### 3 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
