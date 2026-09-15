---
name: dev-spec-first-draft
user-invocable: false
description: >
  Use when writing a dev spec — a new one, or revising an existing one with new information.
  Gathers context from docs, source code, and the user, then writes the draft to the location
  resolved via `documentation.dev-specs`.
argument-hint: <feature brief | work-item-id | spec-file-path>
---

Use this skill when:
- You are writing a dev spec, whether drafting a new one or revising an existing one with new information

You are writing a dev spec — a new one, or revising an existing one whose path the caller passed
in.

## Steps

### 1 — Gather context

If revising, the calling command has already found the existing dev spec and passed its path —
read it in full now, and treat the new brief as the reason for revision rather than a
from-scratch rewrite. Its `## Related Docs` section already records the architecture docs and
design doc consulted during the prior pass — reuse that instead of re-discovering them from
scratch, and only look further for gaps the new brief actually raises.

Use the `find-repo-documentation` skill to read the architecture docs relevant to the feature area.

If a design doc is already known (passed in, or found via `documentation.specs.search` for the
resolved work item), read it in full first. It already answers the problem/goals/behavior
questions — do not re-ask those; only ask what the design doc leaves open for the implementation.

Spawn one or more `dev-team:researcher` agents to research any frameworks, libraries, or patterns
the feature will use — skip this if revising and the existing spec's research already covers the
new brief's scope. Each agent uses the `research-learn` skill and returns findings with source
links.

Use `AskUserQuestion` to ask the user focused questions that fill gaps the docs, design doc, and feature description don't answer — if revising, focus on what actually changes rather than re-asking settled ground. Good questions cover:

- Ownership and boundaries (what this feature owns vs. delegates)
- Integration points with existing subsystems
- Key design choices where multiple reasonable approaches exist
- Constraints (performance, accessibility, testability requirements)
- Anything the planned implementation section will need to be concrete

Skip questions you can already answer from docs, the design doc, or source. Provide 2–4 concrete option choices per question; the user can always pick "Other". Batch up to 4 questions per `AskUserQuestion` call.

**PAUSE — wait for the user's answers before continuing.**

If answers raise new ambiguities that would materially affect the spec, ask one more targeted follow-up round. Otherwise proceed.

Treat this step as the place unresolved questions get eliminated, not deferred. If you notice a gap while writing the draft in step 2, stop and go back through this same research/`AskUserQuestion` process before continuing — do not carry it forward into the draft's Open Questions section instead. An item belongs in Open Questions only if the user was asked and explicitly said something like "I don't know, we'll have to figure that out as we go" — a genuinely open question that can't be resolved by research or a decision right now. It is not for questions you simply haven't asked yet, or that research could answer.

### 2 — Write the draft

If drafting new, resolve the file's location and naming via the `write-repo-documentation` skill's
`documentation.dev-specs` placement. If revising, use the existing document's location instead.

Write (or update) the file following the template at
[`assets/dev_spec_template.md`](assets/dev_spec_template.md).

Fill every section with resolved content — research or ask about anything you don't yet know before writing it in, using step 1's process. A `> TBD: reason` or an Open Questions entry may only remain when the user has explicitly confirmed it should stay open (e.g. "we'll figure it out as we go") — never a silent default when drafting wraps up, and never for a question you simply haven't asked yet. Confirm with the user before leaving anything open.

Write or regenerate the `## Contents` section last, once every other section is in its final form, per the template's own note.

Once the draft is complete, invoke the `document-concision-pass` skill on the file to tighten it.

### 3 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed; it records the rationale in place until it's harvested into a playbook. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
