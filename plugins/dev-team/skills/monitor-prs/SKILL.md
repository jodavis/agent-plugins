---
name: monitor-prs
user-invocable: false
description: >
  Front door for the long-lived PR monitor, in two modes. Stack mode (default) is a
  one-per-epic monitor for a whole GitHub stack; PR mode (`--pr-numbers`) is a lighter-weight
  monitor for one or more explicit PRs that aren't part of (or aren't known to be part of) a
  stack. Resolves the one-time identity this monitor needs (an epic id, or a synthetic key for
  an explicit PR list) — the only thing that must happen before a context file can even be
  addressed — then hands off into `workflow-orchestrate`, which drives the actual long-lived
  poll/react state machine (see `monitor-stack-plan.md`/`monitor-pr-plan.md`). Replaces the
  per-task `monitor-pr` fleet.
argument-hint: [--work-item-id <epic-id> | --pr-numbers <pr1>[,<pr2>...]]
---

Use this skill when:
- **Stack mode:** The first task in an epic's target set has reached hand-off (its PR is open,
  registered into the epic's `gh stack`) and something needs to keep every task's PR in that
  stack in sync until it merges. You were spawned to do exactly this — auto-started by
  `concurrent-orchestrate` the moment the first task in an epic's target set hands off (always
  with `--work-item-id`, into a fresh isolated worktree), or invoked manually via `/watch-stack`,
  in-session, with no argument, when already checked out on one of the stack's own branches
- **PR mode:** One or more specific, already-open PRs need the same review-comment/CI-failure/
  human-comment monitoring, but aren't part of a stack you want to (or can) run `gh stack`
  operations against — invoked manually via `/watch-pr <PR#> [PR#...]`, in-session

Do NOT use this skill when:
- Stack mode, no task in the epic's target set has reached hand-off yet — there is no stack
  entry to monitor
- Stack mode, every task in the target set has already merged and a prior run of this skill
  already halted for this epic
- PR mode, every given PR has already merged and a prior run of this skill already halted

## Determining which mode to run

- **`--pr-numbers <pr1>[,<pr2>...]` given** — **PR mode**. Skip straight to "## PR mode" below;
  none of "## Stack mode"'s steps apply.
- **Otherwise** (`--work-item-id <epic-id>` given, or no argument at all) — **stack mode**.
  Continue with "## Stack mode" below, exactly as before PR mode existed.

The two are mutually exclusive — `--pr-numbers` is never combined with `--work-item-id`; a
stack's PRs are always discovered via the epic id or the current worktree, never listed by hand.

## Role

You resolve the one identity question `workflow-orchestrate` cannot resolve for itself —
computing a context-file path requires a `--work-item-id` first, and stack mode's `/watch-stack`
path (no argument) doesn't know its own epic id until it's derived from the current branch — then
hand off. You do not poll, react to events, bootstrap `gh stack` awareness, resolve conflicts, or
clean up a worktree yourself; the state machine you hand off into
(`monitor-stack-plan.md`/`monitor-pr-plan.md`, driven by `monitor_prs.py`) does all of that,
including the one-time worktree bootstrap the auto-started path needs (`stack_checkout.py`, via
the `bootstrapping` state). This skill only ever runs `git status`/`git rev-parse` against the
*current* worktree to resolve identity — never `gh stack`/`gh pr` at all.

**Never attempt to:**
- Poll for review comments, CI failures, or merges yourself — that's the state machine's job once
  you hand off
- Call `gh stack` or `gh pr`, directly or indirectly — nothing in this skill needs to
- Resolve a rebase conflict, fix a review comment, or notify the user yourself — all of that is
  the state machine's job now, not this front door's
- Guess an epic id when it can't be determined — step 2's own hard-stop case applies exactly as
  before

## Stack mode

Reached when `--work-item-id <epic-id>` was given, or no argument at all was given — see
"Determining which mode to run" above.

### 1 — Worktree-freshness check

Run this first, unconditionally, before anything else:

```bash
git status --short
```

Must be empty. If it produces any output, this is a **hard stop**: stop immediately and report
the failure in detail (do not proceed to step 2 or attempt any recovery). This guards against a
confirmed upstream `isolation: "worktree"` bug (Claude Code issues #51596, #37873, #41010) that
can silently reuse a stale worktree/branch on an 8-hex-char ID-prefix collision — a dirty
worktree at this point means it isn't the fresh one this task expects.

### 2 — Resolve the epic id

This step's shape depends on whether `--work-item-id` was given.

#### 2a — `--work-item-id <epic-id>` given

The `concurrent-orchestrate` auto-start path — the only caller that ever passes `--work-item-id`;
`/watch-stack` never does (see 2b). The epic id is already known — nothing to derive. Use the
`use-context-file` skill with `<epic-id>` to locate and read (creating if necessary) the epic's
own context file, then set `own_worktree: true` on it. This session bootstrapped its own
dedicated, isolated worktree — the `bootstrapping` state (see "Hand off" below) needs this flag
to know it must do real bootstrap work, and `cleaning_up` needs it to know this worktree is this
monitor's own to remove once the epic's target set is fully merged.

#### 2b — No `--work-item-id` given

`/watch-stack` takes no epic-key argument at all — it always runs this path, direct and
non-isolated, from whatever worktree the user already put this session in. There is no
fresh-worktree bootstrap to do — this path's whole premise is that the current worktree is
already checked out on one of the stack's own branches, so the epic id is derived from it instead
of taken as an argument:

```bash
git rev-parse --abbrev-ref HEAD
```

Take the last `/`-separated segment and extract `<task_work_item_id>` from it the same way
`detect_next_stack_event.py`'s `_WORK_ITEM_ID_RE` does (the `[A-Za-z]+-\d+` prefix, falling back
to the whole segment if it doesn't match), then use the `use-context-file` skill to read that
id's own context file. Read its `parent_work_item` field — the same field `concurrent-orchestrate`
step 2e reads to learn a task's epic — that is `<epic-id>`. If it's empty, this is a **hard
stop**: report that the current branch has no recorded epic to derive an epic id from, rather
than guessing. The most common cause is being checked out on the epic's own trunk branch instead
of a task branch (`gh-stack` doesn't consider the trunk a stack member, and a trunk's own context
file has no `parent_work_item` pointing anywhere) — mention this in the report, and that the user
should `gh stack checkout <pr-number-or-branch>` onto a member branch first, then re-invoke
`/watch-stack`.

With `<epic-id>` now known, use the `use-context-file` skill with it to locate and read (creating
if necessary) the epic's own context file. Leave `own_worktree` at its default `false` — this
worktree is the user's own, not this monitor's to bootstrap, track, or later clean up.

### 3 — Hand off

Invoke the `workflow-orchestrate` skill with arguments:
`--work-item-id <epic-id> --workflow monitor-stack-plan --script monitor_prs`

Then stop — `workflow-orchestrate` now drives the long-lived poll/react/conflict-resolution/
cleanup state machine (`monitor-stack-plan.md`) until every task in the epic's target set has
merged, or an unresolved rebase conflict halts it. See that asset's own notes for the full
behavior this hands off into: bootstrapping `gh stack` awareness (step 2a only), `gh stack sync`,
scanning for review comments/CI failures/merges, reacting to a review comment or CI failure
(`fix-pr`, against the affected task's own context file) or a human comment (a direct
notification, never auto-fixed), resolving a rebase conflict via the developer agent, and
cleaning up this session's own dedicated worktree/branch — only if it bootstrapped one (step
2a) — once the epic's target set is fully merged.

## PR mode

Reached when `--pr-numbers <pr1>[,<pr2>...]` was given — see "Determining which mode to run"
above. Always a direct, in-session `/watch-pr` invocation (there is no auto-started, isolated-
worktree path for PR mode — `concurrent-orchestrate` only ever auto-starts stack mode).

### 1 — Parse the PR numbers and derive a synthetic identity

The given comma-separated PR list has no natural epic/work-item-id of its own — PR mode monitors
an arbitrary, explicit PR list, not anything already tracked by a spec or context file. Derive a
stable, deterministic key from it instead: sort the given PR numbers ascending and join them with
`-`, e.g. `--pr-numbers 456,123` becomes `watch-pr-123-456` — this is `<work-item-id>` for every
step below, so re-invoking `/watch-pr` with the same PRs (in any order) always resolves to the
same context file and resumes the same monitor rather than starting a fresh one.

Use the `use-context-file` skill with `<work-item-id>` to locate and read (creating if necessary)
its own context file, then write the canonical (sorted, comma-separated) PR number list to its
`pr_numbers` field.

### 2 — Hand off

Invoke the `workflow-orchestrate` skill with arguments:
`--work-item-id <work-item-id> --workflow monitor-pr-plan --script monitor_prs`

Then stop — `workflow-orchestrate` now drives the long-lived poll/react state machine
(`monitor-pr-plan.md`) until every given PR has merged. See that asset's own notes for the full
behavior this hands off into.

## Skills

- `use-context-file` — locating/creating the epic's own context file (stack mode) or the
  synthetic PR-list key's own context file (PR mode), and setting `own_worktree`/`pr_numbers`
- `workflow-orchestrate` — the hand-off target; drives the actual poll/react state machine
