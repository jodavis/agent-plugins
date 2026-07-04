---
name: researcher-spec-review
user-invocable: false
description: >
  Use when verifying a spec file is ready for implementation.
  Reads the spec, architecture docs, and source code, then returns blocking questions or an implementation-ready confirmation.
argument-hint: <path to _spec_*.md file>
---

Use this skill when:
- You need to verify a spec is ready for implementation
- You are reviewing a spec file for blocking gaps before task breakdown

## Steps

### 1 — Read the spec

Read the spec file at the provided path in full — every section.

### 2 — Read architecture docs

Use the `find-repo-documentation` skill to discover and read the architecture docs relevant to the areas described in the spec.

### 3 — Read relevant source

Use the `research-sources` skill to read the source files and interfaces the spec's planned implementation references or depends on.

### 4 — Research external resources

Use the `research-learn` skill if the spec touches patterns, frameworks, or APIs not fully covered by local docs.

### 5 — Assess and return

From the perspective of an implementer with only the spec and the codebase — no conversation history, no prior context:

- Can every item be implemented without guessing?
- Can unit tests and Gherkin scenarios be written without guessing expected behavior?
- Are there missing decisions, ambiguous behavior, unspecified error cases, or unclear interfaces?

**Component Breakdown check** — run this whenever the spec's own prose (Overview,
Responsibilities & Boundaries, Key Design Decisions) describes any logic that would need
Wrapper/Testable/Orchestrator classification, regardless of whether a `## Component
Breakdown` section exists. A documentation-only or pure-process spec whose prose describes no
such logic is exempt — do not flag it for lacking the section.

When the gate above applies, check the spec's `## Component Breakdown` table for exactly
these three gap types. If the table is missing entirely, only check 1 is mechanically
evaluable — it iterates over the spec's prose-described components independently of the
table, so it fails (raises one blocking question) for every one of them. Checks 2 and 3 each
iterate over rows already in the table; with no table, there are no rows to iterate over, so
they find no gaps to raise — do not treat a missing table as also failing checks 2 or 3.

1. **Undocumented component** — for every component the spec's prose names, confirm it
   appears as a row in the table. Raise one blocking question per prose-described component
   missing from the table.
2. **Dangling dependency** — for every `Depends on` entry in the table, confirm the named
   component is itself a row in the table. Raise one blocking question per dangling `Depends
   on` reference.
3. **Missing verification mechanism** — for every row of `Type` `Testable`, confirm it has an
   identified verification mechanism: search the target repo for existing test-file patterns
   scoped to the component's area, using the same method `missing-test-harness` uses (`find .
   -name "*Test*" -o -name "*Spec*" -o -name "*.feature"`). If nothing fits, the gap is
   covered only if the component's own `Depends on` entry names another `Testable` row in the
   same table whose `Responsibility` text describes building or providing a verification
   mechanism (a harness-building line item) — a plausible-sounding description elsewhere in
   the table is not enough without that dependency edge. A harness-building row itself is
   covered by its own `Responsibility` text — it verifies the components that depend on it, so
   it does not also need an outgoing dependency to another harness. Raise one blocking
   question per Testable component with neither an identified mechanism, a covering
   harness-building dependency, nor a `Responsibility` that itself describes building or
   providing a verification mechanism.

Do not run these checks, and do not penalize the spec for a missing Component Breakdown
section, when the gate above doesn't apply.

**If no blocking gaps exist**, return exactly:

> No blocking questions — spec is implementation-ready.

**If gaps exist**, return:
- A numbered list of concrete questions. Each must be specific enough to resolve the gap, reference the section or concept it pertains to, and be a genuine blocker — not a suggestion or style preference. Only include questions where a reasonable implementer would be forced to guess at intended behavior.
- Under a `## Useful resources` heading: any external resources from step 4 that would inform implementation.

Do not include summaries, recommendations, or file quotes.
