---
description: Validate completed work against a task's exit criteria, returning a structured pass/fail result for each criterion
argument-hint: <work-item-id | context-file>
user-invocable: false
---

## Steps

### 0 - Prepare

Determine the work-item-id for the active task.

Ensure the working repository and task context file are in a clean, ready-to-work state.

### 1 — Identify the authoritative exit criteria

The spec file path should be populated in the context file.
Read the spec file and locate the section for the task key. Extract the exit criteria
checklist as written in the spec — this is the authoritative source, not the task brief.
If the spec has been updated since the brief was written, use the spec version.

### 2 — Evaluate each criterion

For each exit criterion, determine its status by reading the evidence the caller provided:

- Read the changed files listed in the work summary
- Read each linked test file
- Check whether the criterion is demonstrably met, partially met, or not met

Do not assume a criterion passes because the Developer said it does. Read the actual code
and tests. For behaviour-level criteria (Gherkin scenarios), verify there is a test that
exercises the scenario — not just that the code path exists.

### 3 — Return the result

Output a JSON object as the very last line of your response (bare, not inside a code block).
Set `status` to `"validated"` if all criteria passed, `"failed"` if any criterion is
`fail` or `partial`. Include the full criteria array so the developer has details.

```
{"status": "validated|failed", "criteria": [{"criterion": "...", "status": "pass|fail|partial", "finding": "..."}]}
```

Each criterion entry:
- `criterion` — exact text of the exit criterion from the spec
- `status` — `pass`, `fail`, or `partial`
- `finding` — one-sentence explanation (required for `fail` and `partial`; omit for `pass`)

**Status definitions:**
- `pass` — criterion is fully and demonstrably met by the code and tests
- `partial` — criterion is met in part but not completely (e.g., happy path covered but
  error cases are not, or implementation exists but no test verifies it)
- `fail` — criterion is not met
