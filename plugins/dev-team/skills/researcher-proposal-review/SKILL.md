---
name: researcher-proposal-review
user-invocable: false
description: >
  Use when verifying a design doc actually solves the problem it describes.
  Reads the design and related docs, then returns blocking questions or a ready confirmation.
argument-hint: <path to _design_*.md file>
---

Use this skill when:
- You need to verify a design doc is complete and actually solves the stated problem
- You are reviewing a design doc for blocking gaps

This is an objective, critical review of problem/solution fit — not an implementation-readiness
review. Do not ask about interfaces, classes, or code-level concerns; that is
`researcher-dev-spec-review`'s job on the resulting dev spec.

## Steps

### 1 — Read the design doc

Read the design doc at the provided path in full — every section.

### 2 — Read related docs

Use the `find-repo-documentation` skill to discover and read any existing architecture docs
relevant to the problem area, to check the design isn't solving an already-solved problem or
missing a constraint the system already has.

### 3 — Research external context

Use the `research-learn` skill if the design cites prior art, competing solutions, or standards
that are worth double-checking or that the design doc doesn't fully substantiate.

### 4 — Assess and return

From the perspective of a critical, objective reviewer — does this solution actually solve the
stated problem?

- Is the problem concrete and falsifiable (not just an assertion)?
- Does the proposed solution plausibly resolve the stated problem, not just something adjacent to it?
- Are non-goals explicit, or could scope quietly creep?
- Were reasonable alternatives (including existing solutions) genuinely considered, with real reasons for rejecting them?

### 5 — Return results

**If no blocking gaps exist**, return:

> No blocking questions — design is ready.

**If gaps exist**, return:
- A numbered list of concrete questions. Each must be specific enough to resolve the gap, reference the section or deliverable it pertains to, and be a genuine blocker — not a suggestion or style preference.
- For each question, rate how confidently you could answer it yourself if forced to guess, on a 1–5 scale:
  - 1 — you could answer this easily with high confidence (an obvious, low-risk inference)
  - 5 — you cannot continue without this answered (no reasonable inference exists; it requires a human decision)
  Format each question as `N. [Rating: X/5] <question text>`.

**In both cases**, if while researching you learned a concrete fact worth recording (e.g. prior art, an existing internal solution, or a constraint not already captured) or made a reasonable, low-stakes decision to fill a small gap without it rising to a blocking question, add a `## Findings & Decisions` section: a bullet list of concrete statements, each naming the design section or deliverable it belongs in. Omit this section entirely if there is nothing to add beyond what the questions above already surface.

Under a `## Useful resources` heading: any external resources from step 3 that would inform the design.

Do not include summaries or recommendations about the document itself, or file quotes — `## Findings & Decisions` entries are limited to new facts or decisions, not commentary on what's already written.
