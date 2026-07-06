---
name: implement-direct
user-invocable: false
description: >
  Use when implementing one Wrapper or Orchestrator component from a task brief's Components
  in scope list directly, with no pairing. Also used by implement-tdd's Tier 2
  resolve_directly escalation to implement a disputed piece itself.
argument-hint: <component-row> <task-brief-path> <spec-path> [skip-commit]
---

Use this skill when:
- You (Developer) are implementing one component classified `Wrapper` or `Orchestrator` in a
  task brief's Components in scope list
- `implement-tdd`'s Tier 2 escalation resolves to `resolve_directly` and you need to implement
  the disputed piece yourself

Do NOT use this skill when:
- The component is `Testable` — use `implement-tdd` instead
- The task brief has no Components in scope section at all — fall back to
  `test-driven-development`'s single-agent flow

## Two callers, same implementation steps, different final step

- **Standalone** — invoked directly by `implement-task`'s dispatcher for a Wrapper or
  Orchestrator component. Follow steps 1–3 below, then commit in step 4 — one commit for this
  component.
- **Tier 2 `resolve_directly`** — invoked from `implement-tdd`'s step 4 while resolving an
  escalation for a Testable component. Follow steps 1–3 below, then pass the optional
  `skip-commit` argument so step 4 stages instead of committing. `implement-tdd` still owns the
  single commit for that component once `tdd-tester` reports `done`.

## Steps

### 1 — Read the component's row

From the task brief's Components in scope list, read this component's name, tier (`Wrapper` or
`Orchestrator`), responsibility, and dependencies. If more detail is needed, read the spec
file's Component Breakdown table for the same row.

### 2 — Implement

- **Wrapper** — implement the thin call-through directly. No dedicated unit test is written for
  it — visual inspection is sufficient, per the spec's Component taxonomy decision.
- **Orchestrator** — implement the component, wiring it to its real, non-mocked direct
  dependencies (the Wrapper/Testable components it depends on). Then write one narrow
  integration test covering only the primary/happy-path wiring scenario end-to-end, in the same
  test project/framework already established in the repo — use the `missing-test-harness` skill
  to confirm which harness applies, and follow `test-driven-development`'s AAA structure and
  naming convention practice rules by name for this test. This is deliberately narrower than the
  Testable tier's full coverage checklist (branches, error sources, boundary/invalid inputs,
  logging) — that rigor belongs to the Testable components the Orchestrator wires together, not
  the Orchestrator itself.

### 3 — Build and test, scoped to this component

Same build/test command syntax already documented in `test-driven-development` /
`code-change-expectations` for the target project. An incremental build (never a clean
rebuild); a test run scoped to just this component (the new integration test for an
Orchestrator, or a targeted manual/visual check for a Wrapper), never the full project suite.

### 4 — Commit or stage

- **No `skip-commit` argument** (standalone dispatcher call): use `commit-changes` with message
  `<work-item-id>: <short description>`.
- **`skip-commit` argument present** (Tier 2 `resolve_directly` reuse from `implement-tdd`):
  stage the change (`git add -A`, or the target project's VCS equivalent) and stop — do not
  commit. Control returns to `implement-tdd`'s step 4, which continues the loop from its own
  step 6 (refactor turn) itself; the single commit for that component still happens later, in
  `implement-tdd`'s step 7.

## Self-review notes for the holistic review

Record these notes so `implement-task`'s cumulative self-review (and
`code-change-expectations`' generic "missing test coverage" check) don't misread an
intentional, tier-appropriate choice as a gap:
- **Wrapper** — "no test for this component" is expected, not a gap.
- **Orchestrator** — the integration test intentionally covers only the primary/happy-path
  wiring scenario; it is not expected to carry the Testable tier's full
  branch/error/boundary/logging coverage.

## Skills

- `missing-test-harness` — reuse the existing test project/framework for the Orchestrator's
  integration test; never invent a new harness
- `test-driven-development` — AAA structure and naming convention practice rules, reused by
  name for the Orchestrator's integration test
- `code-change-expectations` — build/test command convention, scoped to this component
- `commit-changes` — the standalone caller's single commit for this component
