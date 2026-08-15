---
name: implement-tdd
user-invocable: false
description: >
  Use when implementing one Testable component from a task brief's Components in scope list.
  Writes all of the component's unit tests in one pass, confirms they fail for the right
  reason, implements until green, then commits. (Simplified flow for issue #152 — the
  tdd-tester/tdd-implementer/tdd-refactorer trio and its driver script are parked, not
  deleted, pending a fix.)
argument-hint: <component-row> <task-brief-path> <spec-path>
---

Use this skill when:
- You (Developer) are implementing one component classified `Testable` in a task brief's
  Components in scope list

Do NOT use this skill when:
- The component is `Wrapper` or `Orchestrator` — use `implement-direct` instead

## Steps

### 1 — Read the component's row

From the task brief's Components in scope list, read this component's name, tier (`Testable`),
responsibility, and dependencies. If more detail is needed, read the spec file's Component
Breakdown table for the same row.

### 2 — Write unit tests

Write *all* of this component's unit tests before writing any implementation. Cover the full
coverage checklist `code-change-expectations` and `implement-task`'s self-review already expect
for a `Testable` component: the nominal/happy path, every branch, every source of error
(a dependency that throws, returns invalid data, or reports an error), boundary/invalid inputs,
and log output that differs by branch or condition.

Follow `tdd-practices`' AAA structure and naming convention by name for every test. Do **not**
apply `tdd-practices`' frozen-Arrange/Act rule here — that rule exists to stop rewriting a
test's Arrange/Act after incremental green; it's moot when every test is authored before any
implementation exists.

Run the full batch and confirm every test fails, and fails for the right reason —
`tdd-practices`' "red must fail for the right reason" rule: a missing-implementation failure,
never a compile error, typo, or broken setup in disguise.

### 3 — Implement

Implement the component until every test from step 2 passes. If you discover a behavior you
missed while implementing, stop and add its test first — confirm it's red for the right reason —
then resume implementing. Never write code for a behavior that doesn't already have a failing
test.

### 4 — Build and test, scoped to this component

Same build/test command syntax already documented in `code-change-expectations` for the target
project. An incremental build (never a clean rebuild); a test run scoped to this component's new
tests, never the full project suite.

Fix any build errors or test failures before proceeding to step 5 — never commit a component
that doesn't build cleanly or pass its own tests.

### 5 — Commit

Use `commit-changes` with message `<work-item-id>: implement <Component>` — one commit for this
component.

## Skills

- `tdd-practices` — AAA structure, naming convention, and red-for-the-right-reason rules
  followed in step 2
- `code-change-expectations` — the coverage checklist step 2 writes tests against, and the
  build/test command convention for step 4
- `behavior-driven-development` — the E2E re-run step that still runs after all components
  (including this one) are implemented
- `commit-changes` — the single commit in step 5
