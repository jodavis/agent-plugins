---
name: dev-spec-first-draft
user-invocable: false
description: >
  Use when writing a first draft of a complete new dev spec or a new part of an existing dev spec.
  Gathers context from docs, source code, and the user, then writes the draft to a _spec_*.md file.
argument-hint: <feature brief | work-item-id | spec-file-path>
---

Use this skill when:
- You are writing a first draft of a complete new dev spec or a new part of an existing dev spec

## Steps

### 1 — Gather context

Use the `find-repo-documentation` skill to read the architecture docs relevant to the feature area.

If a design doc is already known (passed in, or found via `documentation.specs.search` for the
resolved work item), read it in full first. It already answers the problem/goals/behavior
questions — do not re-ask those; only ask what the design doc leaves open for the implementation.

Spawn one or more `dev-team:researcher` agents to research any frameworks, libraries, or patterns the feature will use. Each agent uses the `research-learn` skill and returns findings with source links.

Use `AskUserQuestion` to ask the user focused questions that fill gaps the docs, design doc, and feature description don't answer. Good questions cover:

- Ownership and boundaries (what this feature owns vs. delegates)
- Integration points with existing subsystems
- Key design choices where multiple reasonable approaches exist
- Constraints (performance, accessibility, testability requirements)
- Anything the planned implementation section will need to be concrete

Skip questions you can already answer from docs, the design doc, or source. Provide 2–4 concrete option choices per question; the user can always pick "Other". Batch up to 4 questions per `AskUserQuestion` call.

**PAUSE — wait for the user's answers before continuing.**

If answers raise new ambiguities that would materially affect the spec, ask one more targeted follow-up round. Otherwise proceed.

Treat this step as the place unresolved questions get eliminated, not deferred. If you notice a gap while writing the draft in step 2, stop and go back through this same research/`AskUserQuestion` process before continuing — do not carry it forward into the draft's Open Questions section instead. An item belongs in Open Questions only if the user was asked and explicitly said something like "I don't know, we'll have to figure that out as we go" — a genuinely open question that can't be resolved by research or a decision right now. It is not for questions you simply haven't asked yet, or that research could answer.

### 2 — Write the first draft

Determine the spec file location: the `_spec_*.md` lives next to the code it describes — in the directory where the new feature's code will live.

Name: `_spec_<FeatureName>.md` in PascalCase.

Write the file following the template at
[`assets/dev_spec_template.md`](assets/dev_spec_template.md).

Fill every section with resolved content — research or ask about anything you don't yet know before writing it in, using step 1's process. Reserve `> TBD: reason` and the Open Questions section only for items the user explicitly deferred (e.g. "we'll figure it out as we go"), not for questions you simply haven't asked yet.

### 3 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed; it records the rationale in place until it's harvested into a playbook. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
