---
name: implement-task
user-invocable: false
description: >
  Use when implementing a task from a task brief.
  Reads the task brief, loads developer standards, then dispatches each in-scope component to
  implement-direct or implement-tdd (or falls back to the single-agent TDD flow when the brief
  has no classified components), and returns a work summary.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You need to implement a task from a task brief
- You are writing new code for a work item

You are reading the workflow context file to find a task brief, writing new code to implement the task brief, and committing changes locally to the repo.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Get the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the task brief and ensure the working branch is set up.

### 3 — Load developer standards

Use the `developer-standards` skill to load code guidelines and quality gates.

**IMPORTANT**: In this workflow, full validation is the responsibility of another agent. Build and test only the code you modified — do not run the full validation suite.

### 4 — Understand the task

Read the task brief in full. Identify:

- The exit criteria — these define what "done" means
- Files to create or modify, and the design decisions that constrain each
- Existing utilities, base classes, and patterns to reuse (the brief will call these out)
- Whether the brief has a **Components in scope** section, and if so, whether it lists one or
  more components (see step 5)

If anything in the brief is ambiguous and the ambiguity would affect correctness, note it in your work summary and resolve it conservatively.

### 5 — Implement

Check the task brief's **Components in scope** section:

**No components to dispatch** — the section is absent entirely, or present but explicitly empty
(`write-task-brief`'s `(none — this task touches no classified components)` convention). Implement
the task directly, exactly as before this dispatcher existed: use the `test-driven-development`
skill in full — step 1 (E2E tests first), step 2 (one component at a time, unit tests before
implementation, no pairing), step 3 (confirm E2E tests pass) — then continue to step 6 (Commit)
below for a single commit covering the whole task.

**One or more components listed** — dispatch each component to its own implementation skill, in
the dependency order the list already reflects:

a. Write E2E tests first — `test-driven-development` step 1, by name (Gherkin scenarios covering
   the exit criteria; run them and confirm they fail for the right reason).
b. For each component row, in the order listed:
   - Tier `Wrapper` or `Orchestrator` → invoke the `implement-direct` skill with the component
     row, the task brief path, and the spec path.
   - Tier `Testable` → invoke the `implement-tdd` skill with the same three arguments.

   Each of these skills implements its own component and performs its own `commit-changes` call
   before returning — one commit per component. Do not commit again in this skill for any
   component handled this way.
c. Confirm E2E tests pass — `test-driven-development` step 3, by name (run the full new-scenario
   suite and confirm all new scenarios pass).

Skip step 6 (Commit) entirely in this branch — every component already committed itself, so
there is no remaining uncommitted work for the task as a whole.

### 6 — Commit

Only reached when step 5 took the "no components to dispatch" branch. Use the `commit-changes`
skill to commit all changes with a clear message.

### 7 — Self-review

Review the diff as if you were doing a code review. When step 5 dispatched components, this
reviews the cumulative diff across every per-component commit made for this task, not just one
flow's output:

- Does every exit criterion have demonstrable coverage (code + test)?
- Are there missing test cases (branches, error paths, invalid inputs)?
- Do all files follow the standards loaded in step 3?
- Is there any scope creep — changes not required by the brief?
- For each dispatched component, was its tier-appropriate test expectation honored — no
  dedicated test for a `Wrapper` (expected, not a gap), a narrow primary-scenario integration
  test for an `Orchestrator`, and full branch/error/boundary/logging coverage for a `Testable`
  component? Treat a `Wrapper`'s absent test, and an `Orchestrator`'s narrower-than-Testable
  coverage, as expected per `implement-direct`'s own self-review notes — not gaps to flag.

### 8 — Report

Return a work summary as structured prose:

**Files created or modified**
List each file by path with a one-line description of what changed.

**Key decisions made**
Anything not dictated by the brief that you chose during implementation (design choices, interface splits, tradeoffs). Omit this section if there are none.

**Unit tests**
File path(s) and test method names for all new or modified unit tests.

**E2E scenarios**
Feature file path(s) and scenario title(s) for all new or modified Gherkin scenarios.

**Known ambiguities**
Any Tier 3 "best-effort, documented, non-blocking" ambiguity notes bubbled up from an
`implement-tdd` escalation (or recorded directly during this skill's own step 5), for human
review after the fact. Omit this section if there are none.
