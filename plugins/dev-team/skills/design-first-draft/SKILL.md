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

### 2 — Write the first draft

Determine the design doc file location and name per `write-repo-documentation`'s configured
`documentation.specs` placement: `_design_<FeatureName>.md` in PascalCase.

Write the file using this structure:

---

# \<Feature Name\>

> **Status:** Draft
> **Source:** \<citation(s) from the sources gathered in step 1, or "— none"\>

## Problem

What problem exists, for whom, and what evidence supports it.

## Goals & Non-Goals

- **Goals:** what this design must achieve
- **Non-Goals:** what it deliberately does not address

## Proposed Solution

The solution at the level of observable system behavior — what changes for the user or the
system, not how it's built.

## Behavior

Key scenarios described as concrete, observable behavior (what happens, from the outside, in each
case). Concrete enough that "does this solve the problem?" can be checked without guessing.

## Success Criteria

How to tell, after shipping, whether this solved the problem.

## Alternatives Considered

Other solutions considered (including prior art / existing solutions found in step 1) and why
they weren't chosen.

## Risks & Open Questions

- [ ] Unresolved question

## Deliverables

_(Added later by `design-deliverable-breakdown`.)_

## Related Docs

Links to the documentation and research sources consulted during drafting.

---

Fill every section. For anything genuinely unresolved, use `> TBD: reason` inline and list it again in Risks & Open Questions.

### 3 — Pause for review

After writing, tell the user:

> Draft written to `<path>`. Please review it — edit any section directly and add `> **Review:** your comment or question` anywhere you want a change made or a question answered. If you notice a methodology worth recording for later reuse, drop a `> [!NOTE]` / `> **Method:** ...` callout instead — it's not a review comment and won't be resolved or removed. Tell me when you're ready for the next pass.

**PAUSE — wait for the user to review and signal readiness.**
