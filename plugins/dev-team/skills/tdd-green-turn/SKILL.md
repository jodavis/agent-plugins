---
name: tdd-green-turn
user-invocable: false
description: >
  Use when tdd-implementer is taking a turn in the tdd-tester / tdd-implementer red/green
  loop. Resolves whatever tdd-tester just reported (structural-red or red) with the smallest
  possible change, or escalates, and reports the outcome in one line.
---

Use this skill when:
- You (`tdd-implementer`) are taking your turn to resolve `tdd-tester`'s most recent
  `structural-red` or `red` reply — including a retry after `tdd-tester` relays a response to
  your `revise-request`, or after Developer answers a `clarify` escalation

## Steps

### 1 — Resolve a structural turn (`tdd-tester` reported `structural-red`)

Resolve it with the smallest possible stub or fix — just enough for Arrange+Act to complete
without throwing; an obviously-wrong return value is fine. Rerun to confirm it now completes
cleanly, then reply `structural-green: <TestName>`. Do not add any assertion-satisfying logic
yet; that only happens once `tdd-tester` adds the real `Assert` and reports ordinary `red`.

Escalation is possible here too: if the structural break itself is ambiguous, contradictory, or
needs something outside this component's boundary, go through the Tier 1 retry and `escalate`
reply in step 3 instead of forcing a `structural-green`.

### 2 — Resolve a behavioral turn (`tdd-tester` reported `red`)

Make `<TestName>` pass with the smallest change that satisfies only that assertion — the
"dumbest thing that could possibly work" (see the `tdd-implementer` agent for examples). Run
the targeted test plus the rest of the component's suite to confirm no regression, then reply
`green: <TestName>`.

### 3 — Escalation

**Tier 1 — one internal retry before escalating.** If `<TestName>`'s `Assert` or Arrange/Act
looks wrong, contradictory, or untestable as written, you get exactly one retry before
escalating to Developer: reply `revise-request: <TestName> — <reason>` instead of `green` or
`structural-green`. Developer relays this verbatim to `tdd-tester` as a one-line note and
relays `tdd-tester`'s one-line response back to you unmodified — this hand-off is mechanical on
Developer's part, not a judgment call; the resolution is entirely between you and `tdd-tester`.
If the test is revised (or explained) and you can now make it pass, do so and reply as usual
(step 1 or step 2). If the blocker still isn't resolved after this one retry, escalate to
Developer.

**Escalating to Developer.** If Tier 1 doesn't resolve the blocker, reply:

```
escalate: <reason> — recommended_action: clarify|resolve_directly|split_scope
```

- `clarify` — you need a factual answer Developer can supply from the spec/task-brief context
  (e.g., which of two behaviors is actually intended). Developer resends your same turn with
  the answer folded in — re-run this skill from step 1; it applies regardless of whether the
  blocker was structural or behavioral, so there's nothing to track about where the escalation
  originated.
- `resolve_directly` — the disputed piece is better implemented by Developer directly than
  mediated further through you.
- `split_scope` — the behavior needs something outside this component's declared boundary (an
  unbuilt dependency, or a gap in the Component Breakdown).

## Practice rules

Follow `test-driven-development`'s Practice rules exactly, by name, for anything that touches
how you reason about a test's intent — you don't edit tests yourself, but "Red must fail for
the right reason" governs what counts as a legitimate structural vs. behavioral turn, and
"Arrange and Act are frozen after first green" is why you never ask `tdd-tester` to rewrite a
passing test's setup instead of writing a new one.

## Turn discipline

Reply with **exactly one line** — no diffs, no explanation:

```
structural-green: <TestName>
green: <TestName>
revise-request: <TestName> — <reason>
escalate: <reason> — recommended_action: clarify|resolve_directly|split_scope
```

Run build/test commands the same way `test-driven-development` / `code-change-expectations`
document for the target project — an incremental build, never a clean rebuild, and a test run
scoped to the one test or the component's suite, never the full project suite.

## Skills

- `test-driven-development` — the Practice rules referenced above
- `code-change-expectations` — general build/test-after-each-change expectations
