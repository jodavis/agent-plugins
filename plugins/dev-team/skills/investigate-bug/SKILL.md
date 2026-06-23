---
name: investigate-bug
description: >
  Use when investigating a bug report.
  Fetches the GitHub issue, reads architecture docs, writes a repro test, traces the root cause, and produces a root-cause report.
argument-hint: <Issue-NNN>
---

Use this skill when:
- You are investigating a bug report
- You need to reproduce an issue and identify its root cause

You are identifying a work item to fix, reading architecture documentation in this repo, writing E2E or unit tests to reproduce the issue, and providing analysis of the root cause.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` (e.g. `Issue-444`) from the user's input.

### 2 — Fetch the GitHub issue

Use the `work-with-GitHub-issues` skill to fetch the issue title, body, and all comments. If the issue is not found, stop and report the error.

### 3 — Ensure a working branch

Use the `ensure-working-branch` skill with the `work-item-id`.

### 4 — Read architecture docs

Use the `find-repo-documentation` skill to read the architecture docs for each subsystem the issue touches. Do not skip this step — architecture context is essential for recognizing the responsible code path.

### 5 — Classify the issue

Determine whether the bug manifests in an **existing failing test** or requires a **new repro test**:

- **Existing test:** the issue references a specific test, or running the relevant test suite reveals a matching failure. Go to step 6a.
- **New repro needed:** no existing test covers the bad behaviour. Go to step 6b.

### 6a — Existing test: confirm the failure

Run the referenced test(s). Confirm the failure matches the behaviour described in the issue. If it does not match, continue at step 6b.

### 6b — New repro: write a failing test

Use the `write-e2e-test` skill to write a minimal Gherkin scenario that exercises the reported bad behaviour. Run it — it should **pass** (the bad behaviour is currently observable). If it does not pass, proceed to step 9 with status `not_reproduced`.

### 7 — Anchor the correct behaviour

Modify the repro test to assert the **correct** behaviour instead. Run it again — it should now **fail**. This failing test is the investigation anchor.

If you cannot reach a clean "correct assertion fails" state, document why in the report.

### 8 — Investigate the root cause

Read the source code along the relevant code path. Form 1–3 specific, falsifiable hypotheses. For each:

1. State the hypothesis clearly.
2. Identify what evidence would disprove it.
3. Look for that evidence in code, log output, or at runtime.

If logging is insufficient, add `[LoggerMessage]` entries in `src/AdaptiveRemote.App/Logging/MessageLogger.cs`, rebuild, and rerun. Use the event ID range appropriate to the subsystem.

Do not stop at "plausible" — keep going until at least one hypothesis is confirmed with direct evidence.

### 9 — Clean up

Remove any temporary investigation-only changes from production code. Keep:
- The repro test from step 6b / 7 (in its failing, correct-assertion form)
- Any `[LoggerMessage]` additions

Use the `commit-changes` skill to commit all kept changes with the message:
`<work-item-id>: repro test + diagnostic logging`

### 10 — Output

**If reproduction succeeded**, write:

```
# Debug report for <work-item-id>

## Reproduction steps
<Minimal steps that trigger the bug — enough for someone unfamiliar to observe it.>

## Confirmed root cause
<The specific class, method, and line(s) responsible. Cite file paths. Explain the mechanism.>

## Ruled-out hypotheses
<One bullet per hypothesis investigated and eliminated, with the evidence.>

## Supporting evidence
<Relevant log snippets, stack traces, or trace output. Keep it concise.>
```

Then on its own line: `{"status": "reproduced"}`

**If not reproduced**: brief explanation, then: `{"status": "not_reproduced", "reason": "<one sentence>"}`

### 11 — Comment on the GitHub issue

Use the `work-with-GitHub-issues` skill to add a comment summarizing the confirmed root cause that the fix will address.
