---
name: implement-tdd
user-invocable: false
description: >
  Use when implementing one Testable component from a task brief's Components in scope list.
  Drives the tdd-tester / tdd-implementer pair through the structural-then-behavioral
  red/green loop until the component is fully covered, then commits.
argument-hint: <component-row> <task-brief-path> <spec-path>
---

Use this skill when:
- You (Developer) are implementing one component classified `Testable` in a task brief's
  Components in scope list

Do NOT use this skill when:
- The component is `Wrapper` or `Orchestrator` — use `implement-direct` instead
- The task brief has no Components in scope section at all — fall back to
  `test-driven-development`'s single-agent flow

## Role reminder

This skill is driven by Developer, the orchestrator. `tdd-tester` and `tdd-implementer` never
invoke this skill themselves and never spawn sub-agents of their own — they only ever reply
with the one-line status Developer reads each turn. Full detail always lives on disk (test
files, production files, the per-component log file); Developer's job is to route turns, check
the changed-file list after each one, and act on the one-line replies — not to read the diffs
itself unless a protocol violation or escalation forces it to look closer.

## Steps

### 1 — Set up the per-component log file

Compute the log path following the existing `~/.dev-team/<repo-slug>/logs/` convention (same
`<repo-slug>` resolution `use-context-file` uses):

```
~/.dev-team/<repo-slug>/logs/<task-work-item-id>-tdd-<Component>.log
```

This one file is appended to across every turn for this component, by both sub-agents. Include
its path in each sub-agent's first-turn message so they can append their own build/test output
to it themselves, rather than folding that output into their one-line reply.

### 2 — Spawn the pair

Use `Agent` to spawn one `tdd-tester` and one `tdd-implementer` sub-agent for this component.
Track the `agentId` each spawn returns for as long as this component is being implemented — use
`SendMessage` addressed to that id to continue that specific sub-agent's turn. A fresh pair is
spawned per Testable component; ids from a finished component are never reused.

The first turn to each newly spawned sub-agent includes:
- the task brief path and spec path,
- this component's own Component Breakdown row (name, tier, responsibility, dependencies),
  inline,
- the per-component log file path from step 1.

Later turns stay one line each — don't re-summarize context already given on the first turn.

### 3 — Decide whether the next behavior needs a structural turn

For each behavior `tdd-tester` is about to cover next, judge from what you already know about
it (not by asking `tdd-tester` first):

- **Needs a structural turn** — the behavior requires a new test method, or exercises a member
  with no existing passing coverage of that shape (a build break or an uncaught throw/crash is
  a real risk).
- **Already known-clean, skip straight to the behavioral turn** — appending an `Assert` to an
  existing frozen-Arrange/Act method, adding a case to an already-parameterized test, or
  testing an already-implemented member with new inputs.

This mirrors the exit criteria's "only when Arrange/Act isn't already known-clean" — most
behaviors after the component's first should skip the structural turn.

### 4 — Structural turn (only when step 3 says it's needed)

1. Send `tdd-tester`: `"write Arrange and Act only for the next uncovered behavior of
   <Component> — no Assert yet."`
2. `tdd-tester` replies one of:
   - `structural-red: <TestName> — <reason>` — send `tdd-implementer`: `"resolve the build
     break for <TestName> with the smallest possible stub."` `tdd-implementer` replies
     `structural-green: <TestName>`. Proceed to the behavioral turn (step 5) for the same
     `<TestName>`.
   - `red: <TestName> — <reason>` — `tdd-tester` found Arrange/Act already clean and added the
     `Assert` in the same turn per its own rubric. Skip straight to step 6 (the implementer's
     behavioral turn) for this `<TestName>`.

After every reply, check `git diff --name-only` (or the target project's VCS equivalent) —
`tdd-tester` and `tdd-implementer` must only ever appear against their own file class (test
files for `tdd-tester`, production files for `tdd-implementer`). A mismatch is a protocol
violation: stop the loop and treat it as a Tier 3 known ambiguity/failure per step 8, since
neither sub-agent should ever produce one.

### 5 — Behavioral turn — tdd-tester

Send `tdd-tester`: `"add the first Assert to <TestName>, or pick the next behavior per the
selection rubric, or reply 'done' if coverage is complete. Dependencies' interfaces:
<summary>."`

`tdd-tester` replies one of:
- `red: <TestName> — <reason>` — continue to step 6.
- `done: <coverage summary>` — the component is fully covered. Skip to step 9 (commit); there
  is no post-`done` refactor pass in this skill (see Scope note below).

### 6 — Behavioral turn — tdd-implementer

Send `tdd-implementer`: `"make <TestName> pass with the smallest change that satisfies only
that assertion."`

`tdd-implementer` replies one of:
- `green: <TestName>` — the behavior is done; go back to step 3 for the next behavior.
- `revise-request: <TestName> — <reason>` — `tdd-implementer`'s own Tier 1, pair-internal retry
  (its own behavior, not something you resolve). Relay the note verbatim to `tdd-tester`, relay
  `tdd-tester`'s one-line response back to `tdd-implementer` verbatim, and let it attempt the
  turn once more. This is a mechanical pass-through — you make no judgment call here. If
  `tdd-implementer` then replies `green`, continue as normal; if it replies `escalate` instead,
  go to step 7.
- `escalate: <reason> — recommended_action: clarify|resolve_directly|split_scope` — go to
  step 7.

After every reply, check `git diff --name-only` as in step 4.

### 7 — Tier 2 escalation (you resolve)

- **`clarify`** — answer directly from the spec/task-brief context you already hold. Send the
  answer to `tdd-implementer` as its next turn message; it retries the behavioral turn (step 6)
  with that answer in hand.
- **`resolve_directly`** — follow the `implement-direct` skill to implement the disputed piece
  yourself. Run the disputed test yourself to confirm it now passes before handing control
  back. The test is retained toward `tdd-tester`'s coverage exactly as if `tdd-implementer` had
  turned it green — do not discard or rewrite it. Return to step 3 for the next behavior.
- **`split_scope`** — the behavior needs something outside this component's declared boundary
  (an unbuilt dependency, or a Component Breakdown gap). Stop driving this component's loop and
  record the scope adjustment for the task as a whole (reordering remaining components, or
  adjusting scope) — this skill only implements one component and does not itself reorder
  others.

If you cannot confidently resolve an escalation through any of the above (Tier 3): make your
best defensible call, implement accordingly, and record the ambiguity in your work summary as
a known ambiguity (same pattern as `write-task-brief`'s Known ambiguities section), for human
review after the fact. Only treat this as an outright task failure if continuing would mean
knowingly producing wrong code.

### 8 — Protocol violations

If a changed-file check (steps 4 or 6) ever shows `tdd-tester` touching a production file, or
`tdd-implementer` touching a test file, stop the loop immediately. This should never happen —
treat it the same as an unresolved Tier 3 case: make your best defensible call to correct it
(e.g., revert the out-of-scope file and re-send the same turn's message), and record it as a
known ambiguity if you can't cleanly recover.

### 9 — Commit

Once `tdd-tester` reports `done`, use `commit-changes` with message format
`<work-item-id>: <short description>` (no push). This commits the component's base
implementation.

**Scope note:** the post-`done` `tdd-refactorer` review and its separate commit are not part of
this skill — that's wired in by a later change to this loop. This skill's loop ends cleanly at
"done → commit" by design.

## Build/test scope per turn

Same build/test command syntax already documented in `test-driven-development` /
`code-change-expectations` for the target project. Every turn's build is incremental (never a
clean rebuild); every turn's test run is scoped to the one test or the component's suite, never
the full project suite — that's reserved for the E2E re-run later in `test-driven-development`.

## Skills

- `test-driven-development` — practice rules the pair follows, and the E2E re-run step that
  still runs after all components (including this one) are implemented
- `code-change-expectations` — coverage checklist `tdd-tester` judges `done` against
- `commit-changes` — the post-`done` commit in step 9
- `implement-direct` — used for a `resolve_directly` Tier 2 escalation
