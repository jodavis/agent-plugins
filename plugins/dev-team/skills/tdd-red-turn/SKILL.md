---
name: tdd-red-turn
user-invocable: false
description: >
  Use when tdd-tester is taking a turn in the tdd-tester / tdd-implementer red/green loop.
  Picks the next behavior, decides whether it needs a structural turn first, adds exactly one
  test behavior, and reports the turn's outcome in one line.
---

Use this skill when:
- You (`tdd-tester`) are taking your next turn for the component you were spawned for —
  including a retry after Developer relays a `clarify` answer from `tdd-implementer`, and the
  turn right after `tdd-implementer` replies `structural-green`

## Steps

### 1 — Pick the next behavior

If you were already mid-behavior when this turn started (`tdd-implementer` just replied
`structural-green`, or Developer relayed a `revise-request` response or a `clarify` answer),
stay on that same `<TestName>` instead of picking a new one — skip to step 2.

Otherwise, pick the next behavior in order:
1. **Skip Wrapper-tier members.** A member that is itself a simple call-through or translation
   with no conditional or iteration logic doesn't get dedicated coverage just because it lives
   inside a Testable component — including a log statement inside an otherwise-trivial member.
2. **Cheapest structural fit:**
   - Add a case to an existing parameterized test if its Arrange/Act shape matches.
   - Otherwise, append an `Assert` to an existing frozen-Arrange/Act method if the scenario's
     Arrange/Act doesn't genuinely differ.
   - Otherwise, write a new test method.
   - Near-duplicate methods differing only by literal input/expected-output data are fine to
     leave as-is — consolidating them into a parameterized test is `tdd-refactorer`'s job
     later, not yours mid-loop.
3. **Happy path before edge cases.** Cover the nominal/typical case first, then expand into
   boundary, invalid-input, and error-handling cases. Cover every case where a dependency could
   throw an exception, return invalid data, or report an error. For async dependency methods,
   cover cases where it returns immediately, blocks asynchronously, blocks and then resumes, is
   cancelled by a passed-in `CancellationToken`, or throws `TaskCancelledException` without the
   `CancellationToken`.

### 2 — Decide whether this behavior needs a structural turn

Before adding an `Assert`, write the Arrange and Act only and attempt to build and run with no
assertion yet:

- If it fails to build, or throws/crashes at run: stop there for the turn and report
  `structural-red: <TestName> — <reason>`. Do not add the `Assert` yet.
- If Arrange/Act already completes cleanly — appending to an existing method, a new case on an
  already-parameterized test, testing an already-implemented member with new inputs, or this
  behavior's structural turn already resolved (`tdd-implementer` just replied
  `structural-green`) — add the `Assert` immediately in the same turn and report ordinary
  `red: <TestName> — <reason>`.

This keeps "a red test fails for the right reason" mechanically true: an `Assert` is only ever
added once Arrange/Act is already confirmed to complete cleanly, whether that confirmation
happened this turn or a prior `structural-green` turn.

### 3 — Check for done

Report `done: <coverage summary>` instead of picking a new behavior once
`code-change-expectations`' coverage checklist (branches, error sources, boundary/invalid
inputs, log output) is satisfied for the whole component — not just the member you tested
last.

## One behavior per turn

Add exactly one of: one new test method, one new case on an existing parameterized/data-driven
test, or one new `Assert` appended to an existing, Arrange/Act-frozen method. Never batch
multiple behaviors into a single turn, even if the fix looks trivial.

## Turn discipline

Reply with **exactly one line** — no diffs, no explanation, no restating what you changed:

```
structural-red: <TestName> — <reason>
red: <TestName> — <reason>
done: <coverage summary>
```

Run build/test commands the same way `code-change-expectations` documents for the target
project — an incremental build, never a clean rebuild, and a test run scoped to the one test
or the component's suite, never the full project suite.

## Skills

- `tdd-practices` — the Practice rules referenced by the `tdd-tester` agent
- `code-change-expectations` — the coverage checklist step 3 checks against
