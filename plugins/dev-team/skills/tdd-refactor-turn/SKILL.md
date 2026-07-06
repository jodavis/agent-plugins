---
name: tdd-refactor-turn
user-invocable: false
description: >
  Use when tdd-refactorer is taking its one turn for a component that just reached `done` in
  the tdd-tester / tdd-implementer / tdd-refactorer trio. Reviews the component for
  behavior-preserving cleanup opportunities, reruns the full component suite, and reports the
  outcome in one line.
---

Use this skill when:
- You (`tdd-refactorer`) are taking your turn for a component Developer just reported reached
  `done`

## Steps

### 1 — Review the component

Read the component's test and production files in full. Look for:
- Near-identical test methods — same Arrange/Act shape, differing only by input/expected-output
  literals — that should be consolidated into a single parameterized/data-driven test.
- Genuinely repeated test setup that a shared helper would clearly make more readable.
- A naive/fake implementation left over from an earlier green turn (e.g. a happy-path shortcut
  that a later edge case should have generalized but didn't quite) that can be cleaned up
  without changing observable behavior.
- Brittle test setup (e.g. over-specified mocks, order-dependent assertions) that can be made
  more resilient without changing what it verifies.

If none of the above applies, skip straight to step 3 and report `no-refactor-needed`.

### 2 — Make the change

Apply one cohesive behavior-preserving change per the Ground rules in the `tdd-refactorer`
agent. When consolidating near-identical test methods into a parameterized test, preserve every
case already covered — consolidation must never quietly drop a case, per
`code-change-expectations`' coverage checklist.

Rerun the full component suite (never the whole project suite — that's reserved for the
end-of-task E2E re-run). If anything that previously passed now fails, or the suite's coverage
of the component changed, revert and treat this as no cleanup opportunity — a behavior gap here
is never something you fix in place; it's a new red for `tdd-tester` to pick up next component
cycle. Report `no-refactor-needed` in that case.

If the suite passes with everything from before still covered, proceed to step 3.

### 3 — Report

Reply with **exactly one line** — no diffs, no explanation:

```
refactored: <summary>
no-refactor-needed
```

## Turn discipline

You get exactly one turn per component — there is no retry loop or escalation tier here, unlike
`tdd-red-turn`/`tdd-green-turn`. Either the behavior-preserving mandate covers what you found, or
you report `no-refactor-needed`; nothing routes back to Developer for a judgment call.

Run build/test commands the same way `test-driven-development` / `code-change-expectations`
document for the target project — an incremental build, never a clean rebuild, and a test run
scoped to the component's suite, never the full project suite.

## Skills

- `test-driven-development` — the Practice rules referenced by the `tdd-refactorer` agent
- `code-change-expectations` — the coverage checklist step 2 checks against
