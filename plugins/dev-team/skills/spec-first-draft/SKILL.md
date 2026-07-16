---
name: spec-first-draft
user-invocable: false
description: >
  Use when writing a first draft of a complete new spec or a new part of an existing spec.
  Gathers context from docs, source code, and the user, then writes the draft to a _spec_*.md file.
  In instance mode (a playbook reference supplied), drafts a thin instance spec from that
  playbook's spec-template.md instead of the default template.
argument-hint: <feature brief | work-item-id | spec-file-path> [playbook reference]
---

Use this skill when:
- You are writing a first draft of a complete new spec or a new part of an existing spec
- A playbook reference (a path or bare name) was supplied — draft a thin instance spec from that
  playbook's `spec-template.md` instead of the default template (instance mode)

Use the `playbook-contract` skill for: the playbook directory contract and bare-name playbook
resolution order. This skill cites those definitions — it does not restate them.

## Steps

### 1 — Gather context

Use the `find-repo-documentation` skill to read the architecture docs relevant to the feature area.

Spawn one or more `dev-team:researcher` agents to research any frameworks, libraries, or patterns the feature will use. Each agent uses the `research-learn` skill and returns findings with source links.

Use `AskUserQuestion` to ask the user focused questions that fill gaps the docs and feature description don't answer. Good questions cover:

- Ownership and boundaries (what this feature owns vs. delegates)
- Integration points with existing subsystems
- Key design choices where multiple reasonable approaches exist
- Constraints (performance, accessibility, testability requirements)
- Anything the planned implementation section will need to be concrete

Skip questions you can already answer from docs or source. Provide 2–4 concrete option choices per question; the user can always pick "Other". Batch up to 4 questions per `AskUserQuestion` call.

**PAUSE — wait for the user's answers before continuing.**

If answers raise new ambiguities that would materially affect the spec, ask one more targeted follow-up round. Otherwise proceed.

### 2 — Write the first draft

Determine the spec file location: the `_spec_*.md` lives next to the code it describes — in the directory where the new feature's code will live.

Name: `_spec_<FeatureName>.md` in PascalCase.

**Instance mode.** If a playbook reference (a path or a bare name) was supplied when this skill
was invoked, resolve it per `playbook-contract`'s bare-name resolution order (cite, don't
restate). Once resolved, read the playbook directory's `spec-template.md` and use its own
sections as the draft's body in place of the default `## Overview` through `## Related Docs`
sections below. Keep the header block's `> **Status:**` and `> **Design doc:**` lines unchanged,
and add one more line — `> **Playbook:** <name or path>` — stamping the resolved playbook
reference into the header. If no playbook reference was supplied, use the default structure
below unchanged — instance mode is additive, never the default path.

Write the file using this structure:

---

# \<Feature Name\>

> **Status:** Draft
> **Design doc:** `_doc_<FeatureName>.md` — authored by `spec-task-breakdown`'s unconditional
> final "Author design documentation" task once implementation completes; this spec persists
> afterward for harvesting

This line names an obligation owned by `spec-task-breakdown`, not by this skill: every task
breakdown must append that unconditional final documentation task, so the reference above is
always honored. If `spec-task-breakdown` does not yet append it, treat that as a gap in
`spec-task-breakdown`, not a reason to omit the header line here.

## Overview

One paragraph: what this feature does and why it exists.

## Responsibilities & Boundaries

- **Owns:** ...
- **Does not own:** ...
- **Integrates with:** ...

## Key Design Decisions

### \<Decision title\>

_Context:_ Why this choice was needed.
_Decision:_ What was decided.
_Consequences:_ Trade-offs accepted.

_(Repeat for each significant decision.)_

## Component Breakdown

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `<Name>` | Wrapper \| Testable \| Orchestrator | One sentence | `<Component>`, `<Component>`, or — |

Use the `component-taxonomy` skill for the Wrapper/Testable/Orchestrator definitions and the
property-level Wrapper carve-out to classify every planned component.

When identifying Testable components, apply these isolation patterns as authoring guidance:

- Prefer dependency injection to isolate a component from its collaborators.
- Consider the **State Object** pattern for stateful components: state lives as plain,
  directly-observable fields on a data object. By default, only the owning/controller
  service mutates it; other services may read it. Some components legitimately invert
  this — a ViewModel-style State Object is written directly by its consumer (e.g. the UI),
  and the owning controller subscribes to change notifications on it to react. In this
  inverted case, both sides may read and write the object; design each field's ownership
  deliberately rather than assuming a single default direction.
- Prefer synchronous logic for anything complex; gather async data up front and pass the
  results in, rather than doing async work on demand inside complex logic.
- Where practical, build each component before its dependencies exist, using mocks of the
  interfaces, so the dependency interfaces reflect real usage rather than speculative design.

## Planned Implementation

### Interfaces

Public interfaces — method signatures, types, and responsibilities.

### Key Classes

Planned classes, their roles, and important relationships.

### Data Flow

How data moves through the feature from trigger to output.

## Related Features

Features identified during drafting that are out of scope here and will be spec'd separately.

| Feature | Scope |
|------|-------|
| (this feature) | ... |

_(Omit if there are no related features.)_

## Open Questions

- [ ] Unresolved question

## Related Docs

Links to the documentation files consulted during drafting.

---

Fill every section. For anything genuinely unresolved, use `> TBD: reason` inline and list it again in Open Questions.

### 3 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed; it records the rationale in place until it's harvested into a playbook. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
