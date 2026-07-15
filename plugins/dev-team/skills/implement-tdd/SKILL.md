---
name: implement-tdd
user-invocable: false
description: >
  Use when implementing one Testable component from a task brief's Components in scope list.
  Drives the tdd-tester / tdd-implementer / tdd-refactorer trio through a genuine
  red-green-refactor loop — tdd-refactorer gets a turn after every real green, not just a pass
  at the end — until the component is fully covered, then commits.
argument-hint: <component-row> <task-brief-path> <spec-path>
---

Use this skill when:
- You (Developer) are implementing one component classified `Testable` in a task brief's
  Components in scope list

Do NOT use this skill when:
- The component is `Wrapper` or `Orchestrator` — use `implement-direct` instead

## Role reminder

The trio (`tdd-tester`, `tdd-implementer`, `tdd-refactorer`) run as isolated `claude` CLI
subprocesses, not as sub-agents of your own session — they never see your conversation and you
never see theirs directly. A driver script owns the mechanical turn-by-turn relay (routing turns,
checking each turn's changed-file scope, staging verified changes, driving the ping-pong loop) so
none of that traffic enters your context. Your job is to write the component's prompt, run the
script, and handle whatever it hands back to you: a Tier 2 escalation it can't resolve on its
own, or a finished/committed component.

## Steps

### 1 — Write the component prompt

Write a prompt file describing this component only — a focused subset of the task brief, not the
whole thing:
- the task brief path and spec path (so the trio can read the full brief/spec themselves if they
  need more context)
- this component's own Component Breakdown row (name, tier, responsibility, dependencies)
- the work item id

Save it to a scratch path.

### 2 — Run the driver script

`<skill-dir>` refers to this skill's own base directory — the "Base directory for this skill"
path shown when this skill was invoked. Resolve it to that literal path.

```bash
python "<skill-dir>/scripts/tdd_cycle.py" \
  --component-prompt <prompt-path> \
  --component-name "<Component>" \
  --repo-root <repo-root> \
  --work-item-id <work-item-id> \
  --state-file <state-path>
```

Use a `<state-path>` unique to this component (e.g. under the same scratch directory as the
prompt file) — it's how the script resumes a specific component's in-progress loop after you
resolve an escalation.

The script spawns (or resumes, via `--state-file`) three `claude -p` sessions running as the
`tdd-tester`, `tdd-implementer`, and `tdd-refactorer` agents, relays turns between them, stages
verified changes, and prints one of two JSON results to stdout:

- **`{"status": "done", "commit_message": ..., "coverage_summary": ...}`**, exit 0 — the
  component is fully covered and already committed. Nothing further for you to do for this
  component.
- **`{"status": "escalation", "recommended_action": ..., "reason": ..., "state_file": ...}`**,
  exit 1 — the loop hit something it can't resolve on its own. `recommended_action` is one of
  `clarify`, `resolve_directly`, `split_scope` (from `tdd-implementer`'s own Tier 2 escalation),
  or `protocol_violation` (the script's own detection of a trio member touching the wrong file
  class, an unrecognized reply, or a second `revise-request` after its one allowed retry).

### 3 — Resolve an escalation, if one comes back

- **`clarify`** — answer directly from the spec/task-brief context you already hold, then re-run
  step 2 with `--state-file <same-path> --answer "<answer>"` to inject it and continue the loop.
- **`resolve_directly`** — follow the `implement-direct` skill to implement the disputed piece
  yourself, in the same working tree the script has been staging into. Run the disputed test
  yourself to confirm it now passes. Then re-run step 2 with `--state-file <same-path>
  --resolved-directly` — the script stages your change, treats it as a real green (routing to a
  refactor turn), and continues the loop.
- **`split_scope`** — the behavior needs something outside this component's declared boundary (an
  unbuilt dependency, or a Component Breakdown gap). Stop here — do not re-run the script. Record
  the scope adjustment for the task as a whole in your own work summary; the script leaves
  whatever was staged as-is (nothing is committed for an incomplete component).
- **`protocol_violation`** — read the `reason` field; the offending file has already been
  reverted (or, for a double `revise-request`, nothing needs reverting). This should be rare.
  Re-run step 2 with the same `--state-file` and no extra flags to retry the same turn; if it
  recurs, treat it as an unresolved Tier 3 case per below.

If you cannot confidently resolve an escalation through any of the above (Tier 3): make your best
defensible call, implement accordingly (via the `resolve_directly` re-run path), and record the
ambiguity in your work summary, for human review after the fact. Only treat this as an outright
task failure if continuing would mean knowingly producing wrong code.

## What the script does for you

- Sends the same generic turn messages the protocol always used (`"take your next turn for
  <Component>."`, `"tdd-tester reported: <reply>."`, the refactor-turn review message) — it never
  tells a trio member whether its turn is structural or behavioral; each trio member's own turn
  skill (`tdd-red-turn` / `tdd-green-turn` / `tdd-refactor-turn`) still decides that itself.
- Checks each turn's changed-file list (test-only for `tdd-tester`, production-only for
  `tdd-implementer`) and surfaces a mismatch as a `protocol_violation` escalation after reverting
  the out-of-scope file.
- Handles `tdd-implementer`'s Tier 1 `revise-request` — a pure mechanical pass-through to
  `tdd-tester` and back for one retry — without involving you at all.
- Stages each verified turn (`git add`) but never commits mid-loop; the one real commit happens
  only once `tdd-tester` reports `done`, with message format `<work-item-id>: implement
  <Component> via TDD (<coverage summary>)`.
- Routes every real green (`tdd-implementer`'s `green`, or your `resolve_directly` resolution) to
  a `tdd-refactorer` turn before returning to `tdd-tester` for the next behavior.

## Build/test scope per turn

Same build/test command syntax already documented in `code-change-expectations` for the target
project — each trio member runs this itself as part of its own turn; the script does not run
builds/tests on their behalf.

## Skills

- `tdd-practices` — practice rules the trio follows (unchanged; still referenced by each trio
  member's own turn skill)
- `behavior-driven-development` — the E2E re-run step that still runs after all components
  (including this one) are implemented
- `code-change-expectations` — coverage checklist `tdd-tester` (via `tdd-red-turn`) judges `done`
  against
- `implement-direct` — used for a `resolve_directly` Tier 2 escalation, before re-running the
  script
