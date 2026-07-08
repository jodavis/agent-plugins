---
name: spec-readiness-review
user-invocable: false
description: >
  Use when verifying a spec is complete and ready for implementation or task breakdown.
  Spawns a researcher to review the spec, resolves questions itself where it confidently can, and
  surfaces only the rest to the user.
argument-hint: <path to _spec_*.md file>
---

Use this skill when:
- You need to verify a spec is complete before implementation or task breakdown
- You want a readiness review on either the design content or the task breakdown

## Steps

### 1 — Spawn a readiness review

Spawn a `dev-team:researcher` agent with the `researcher-spec-review` skill and the spec file path. Provide only the spec path — no conversation context. The researcher reviews from the perspective of an implementer who has only the spec and the codebase.

### 2 — Try to answer each question yourself

If the researcher returns questions, work through them one at a time before involving the user. For each question, re-read the relevant spec section, architecture docs, and source code, and draw on this conversation's history (prior decisions from `spec-discussion`, context the isolated researcher didn't have) to see if it's actually answerable without guessing.

- If you can answer it with confidence, note the answer for step 4 — do not ask the user about it.
- If you cannot answer it without guessing, queue it for step 3.

The question's 1–5 rating from the researcher reflects how blocking *it* judged the gap to be, not who should answer it — attempt every question yourself first regardless of its rating.

### 3 — Ask the user only what's left

If any questions remain unresolved after step 2:

Use `AskUserQuestion` to present the remaining questions to the user. Provide 2–4 option choices per question. Batch up to 4 questions per call.

**PAUSE — wait for answers before editing.**

### 4 — Integrate answers

Integrate all answers — self-resolved in step 2 and user-provided in step 3 — naturally into the appropriate sections of the spec (do not append a Q&A block). If the researcher cited external resources, add them to the `## Related Docs` section.

### 5 — Decide whether to loop again

If every question this round was rated 1 or 2, treat the spec as implementation-ready and stop here — do not spawn another review cycle. A round of only low-rated questions means the researcher itself judged them as easily inferable, so another pass is unlikely to surface anything blocking.

Otherwise, return to step 1. Repeat up to 3 times total.

### 6 — Proceed when ready

When the researcher returns:

> No blocking questions — spec is implementation-ready.

Or after 3 review iterations (whichever comes first), tell the user the spec is implementation-ready and proceed.
