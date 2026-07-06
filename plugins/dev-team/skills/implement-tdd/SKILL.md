---
name: implement-tdd
user-invocable: false
description: >
  Use when implementing one Testable component from a task brief's Components in scope list.
  Drives the tdd-tester / tdd-implementer pair through the structural-then-behavioral
  red/green loop until the component is fully covered, commits, then gives tdd-refactorer one
  post-done cleanup turn and commits again if it made changes.
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
invoke this skill themselves and never spawn sub-agents of their own — each turn, they invoke
their own turn skill (`tdd-red-turn` / `tdd-green-turn`) to decide what to do, then reply with
one line. Developer's job is to route turns, check the changed-file list after each one, stage
verified turns, and act on the one-line replies — not to predict which kind of turn is coming
next, and not to read the diffs itself unless a protocol violation or escalation forces it to
look closer.

## Steps

### 1 — Spawn the pair

Use `Agent` to spawn one `tdd-tester` and one `tdd-implementer` sub-agent for this component.
Track the `agentId` each spawn returns for as long as this component is being implemented — use
`SendMessage` addressed to that id to continue that specific sub-agent's turn. A fresh pair is
spawned per Testable component; ids from a finished component are never reused.

The first turn to each newly spawned sub-agent includes:
- the task brief path and spec path,
- this component's own Component Breakdown row (name, tier, responsibility, dependencies),
  inline.

Later turns stay one line each — don't re-summarize context already given on the first turn.

### 2 — tdd-tester's turn

Send `tdd-tester` a generic turn message: `"take your next turn for <Component>."` Send this
same message every time you come back to this step — on the very first turn, right after
`tdd-implementer` replies `structural-green`, and after any later behavior. `tdd-tester`
invokes `tdd-red-turn` itself to decide what that means; you never predict or name the turn
type.

`tdd-tester` replies one of:
- `structural-red: <TestName> — <reason>` — go to step 3.
- `red: <TestName> — <reason>` — go to step 3.
- `done: <coverage summary>` — go to step 6 (commit).

After the reply, check `git diff --name-only` (or the target project's VCS equivalent) — it
must show only test files. A mismatch is a protocol violation: see step 5. Once it checks out,
stage the change (see "Staging between turns" below) before continuing.

### 3 — tdd-implementer's turn

Send `tdd-implementer` a generic turn message that relays `tdd-tester`'s reply verbatim:
`"tdd-tester reported: <reply>."` `tdd-implementer` invokes `tdd-green-turn` itself to decide
how to resolve it — you never tell it whether the turn is structural or behavioral.

`tdd-implementer` replies one of:
- `structural-green: <TestName>` — go back to step 2 for the same `<TestName>` (`tdd-tester`
  will add the `Assert` this time and report `red`).
- `green: <TestName>` — go back to step 2 for the next behavior.
- `revise-request: <TestName> — <reason>` — this is `tdd-implementer`'s own Tier 1,
  pair-internal retry (its own behavior, not something you resolve). Relay the note verbatim to
  `tdd-tester`, relay `tdd-tester`'s one-line response back to `tdd-implementer` verbatim, and
  let it attempt the turn once more. This is a mechanical pass-through — you make no judgment
  call here. If `tdd-implementer` then replies `green` or `structural-green`, continue as
  normal; if it replies `escalate` instead, go to step 4.
- `escalate: <reason> — recommended_action: clarify|resolve_directly|split_scope` — go to
  step 4.

After the reply, check `git diff --name-only` as in step 2 — it must show only production
files. Once it checks out, stage the change.

### 4 — Tier 2 escalation (you resolve)

- **`clarify`** — answer directly from the spec/task-brief context you already hold. Resend
  `tdd-implementer` the same generic turn message from step 3 with the answer folded in:
  `"tdd-tester reported: <original reply>. <answer>."` `tdd-green-turn` re-derives whether it's
  resolving a structural or behavioral turn from that same input — you don't track or
  distinguish where the escalation originated.
- **`resolve_directly`** — follow the `implement-direct` skill to implement the disputed piece
  yourself. Run the disputed test yourself to confirm it now passes before handing control
  back. The test is retained toward `tdd-tester`'s coverage exactly as if `tdd-implementer` had
  turned it green — do not discard or rewrite it. Stage the change, then return to step 2 for
  the next behavior.
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

### 5 — Protocol violations

If a changed-file check (steps 2 or 3) ever shows `tdd-tester` touching a production file, or
`tdd-implementer` touching a test file, stop the loop immediately. Nothing from the current
turn has been staged yet at this point (see "Staging between turns" below), so the
out-of-scope file is still a plain unstaged change — discard it (`git checkout -- <file>`, or
the target project's VCS equivalent) and re-send the same turn's message. This should never
happen; treat it the same as an unresolved Tier 3 case and record it as a known ambiguity if
you can't cleanly recover.

### 6 — Commit

Once `tdd-tester` reports `done`, use `commit-changes` with message format
`<work-item-id>: <short description>` (no push). This is the only real commit for the
component's base implementation — everything up to this point was staged, never committed, so
no commit ever captures a broken (red, or half-resolved structural) intermediate state.

### 7 — Refactor pass

Use `Agent` to spawn one `tdd-refactorer` sub-agent for this component. Send it this exact turn
message: `"review <Component> for duplication, brittle setup, or naive implementations left
over from green turns. No behavior changes."` `tdd-refactorer` invokes `tdd-refactor-turn`
itself to decide what to do — it gets exactly one turn, never a retry loop.

`tdd-refactorer` replies one of:
- `refactored: <summary>` — it already reran the full component suite itself as part of its
  turn and confirmed no behavior changed. Use `commit-changes` again with message format
  `<work-item-id>: <short description>` (no push) — this is a second, separate commit for the
  same component, never folded into step 6's commit.
- `no-refactor-needed` — no files changed; nothing to commit. Move on to the next component.

This is the only turn `tdd-refactorer` gets for this component — there is no escalation tier or
retry here, unlike steps 2–4's ping-pong. Only proceed to this step once `tdd-tester` has
reported `done`; never run a refactor pass against a component with a failing test.

## Staging between turns

Never commit mid-loop — a commit while a test is red, or while a structural stub is only
half-resolved, would be a broken checkpoint. Instead, once a turn's changed-file check (steps 2
or 3) confirms only the expected file class changed, stage those files with `git add` before
sending the next turn. This has two effects:
- The working tree/index accumulate the component's progress without ever creating a commit of
  a broken state.
- Each subsequent turn's unstaged `git diff --name-only` reflects only that turn's own change,
  since every prior turn is already staged — giving an exact file-scope check per turn instead
  of one that accumulates across the whole loop.

The single commit in step 6 picks up everything staged so far plus any final unstaged bits,
exactly once, when the component is fully green and coverage-complete.

## Build/test scope per turn

Same build/test command syntax already documented in `test-driven-development` /
`code-change-expectations` for the target project. Every turn's build is incremental (never a
clean rebuild); every turn's test run is scoped to the one test or the component's suite, never
the full project suite — that's reserved for the E2E re-run later in `test-driven-development`.

## Skills

- `test-driven-development` — practice rules the pair follows, and the E2E re-run step that
  still runs after all components (including this one) are implemented
- `code-change-expectations` — coverage checklist `tdd-tester` (via `tdd-red-turn`) judges
  `done` against, and that a `tdd-refactorer` consolidation must still satisfy
- `commit-changes` — the commit in step 6, and the second, separate commit in step 7 when
  `tdd-refactorer` makes changes
- `implement-direct` — used for a `resolve_directly` Tier 2 escalation
- `tdd-red-turn` / `tdd-green-turn` — the turn-mechanics skills `tdd-tester` and
  `tdd-implementer` invoke themselves each turn; Developer's messages to them stay generic
- `tdd-refactor-turn` — the turn-mechanics skill `tdd-refactorer` invokes for its single
  post-`done` turn
