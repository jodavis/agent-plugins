---
name: spec-readiness-review
description: >
  Use when verifying a spec is complete and ready for implementation or task breakdown.
  Spawns a researcher to review the spec and surfaces blocking questions for the user to resolve.
argument-hint: <path to _spec_*.md file>
---

Use this skill when:
- You need to verify a spec is complete before implementation or task breakdown
- You want a readiness review on either the design content or the task breakdown

## Steps

### 1 — Spawn a readiness review

Spawn a `dev-team:researcher` agent with the `researcher-spec-review` skill and the spec file path. Provide only the spec path — no conversation context. The researcher reviews from the perspective of an implementer who has only the spec and the codebase.

### 2 — Handle blocking questions

If the researcher returns questions:

Use `AskUserQuestion` to present the questions to the user. Provide 2–4 option choices per question. Batch up to 4 questions per call.

**PAUSE — wait for answers before editing.**

Integrate the answers naturally into the appropriate sections of the spec (do not append a Q&A block). If the researcher cited external resources, add them to the `## Related Docs` section.

Then return to step 1. Repeat up to 3 times total.

### 3 — Proceed when ready

When the researcher returns:

> No blocking questions — spec is implementation-ready.

Or after 3 review iterations (whichever comes first), tell the user the spec is implementation-ready and proceed.
