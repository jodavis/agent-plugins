---
name: researcher-spec-review
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

**If no blocking gaps exist**, return exactly:

> No blocking questions — spec is implementation-ready.

**If gaps exist**, return:
- A numbered list of concrete questions. Each must be specific enough to resolve the gap, reference the section or concept it pertains to, and be a genuine blocker — not a suggestion or style preference. Only include questions where a reasonable implementer would be forced to guess at intended behavior.
- Under a `## Useful resources` heading: any external resources from step 4 that would inform implementation.

Do not include summaries, recommendations, or file quotes.
