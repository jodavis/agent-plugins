---
name: spec-first-draft
description: >
  Use when writing a first draft of a complete new spec or a new part of an existing spec.
  Gathers context from docs, source code, and the user, then writes the draft to a _spec_*.md file.
argument-hint: <feature brief | work-item-id | spec-file-path>
---

Use this skill when:
- You are writing a first draft of a complete new spec or a new part of an existing spec

## Steps

### 1 — Gather context

Use the `find-repo-documentation` skill to read the architecture docs relevant to the feature area. At minimum read `src/_doc_Projects.md`.

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

Write the file using this structure:

---

# \<Feature Name\>

> **Status:** Draft
> **Will become:** `_doc_<FeatureName>.md` once implementation is complete

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

## Planned Implementation

### Interfaces

Public interfaces — method signatures, types, and responsibilities.

### Key Classes

Planned classes, their roles, and important relationships.

### Data Flow

How data moves through the feature from trigger to output.

## Related Epics

Features identified during drafting that are out of scope here and will be spec'd separately.

| Epic | Scope |
|------|-------|
| (this epic) | ... |

_(Omit if there are no related epics.)_

## Open Questions

- [ ] Unresolved question

## Related Docs

Links to the `_doc_*.md` files consulted during drafting.

---

Fill every section. For anything genuinely unresolved, use `> TBD: reason` inline and list it again in Open Questions.

### 3 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
