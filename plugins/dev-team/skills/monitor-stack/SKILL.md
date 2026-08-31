---
name: monitor-stack
user-invocable: false
description: >
  Long-lived, one-per-epic PR monitor for a GitHub stack. Owns the entire post-hand-off
  lifecycle for every task in an epic's target set: repeatedly polls the whole stack via
  `stack_pr_poll.py`, reacting to exactly the one outcome each call returns — spawning `fix-pr`
  for a review comment or CI failure, notifying the user instead of auto-fixing a human-authored
  PR comment, resolving a rebase conflict via the developer agent, or halting once every task in
  the target set has merged.
argument-hint: [--work-item-id <epic-id>]
---

Use this skill when:
- The first task in an epic's target set has reached hand-off (its PR is open, registered into
  the epic's `gh stack`) and something needs to keep every task's PR in that stack in sync until
  it merges
- You were spawned to do exactly this — auto-started by `concurrent-orchestrate` the moment the
  first task in an epic's target set hands off (always with `--work-item-id`, into a fresh
  isolated worktree), or invoked manually via `/watch-stack`, in-session, with no argument, when
  already checked out on one of the stack's own branches

Do NOT use this skill when:
- No task in the epic's target set has reached hand-off yet — there is no stack entry to monitor
- Every task in the target set has already merged and a prior run of this skill already halted
  for this epic

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. `stack_pr_poll.py`, `stack_rebase_continue.py`, and `stack_checkout.py` all
live in the sibling `workflow-orchestrate` skill's `scripts/` directory, so they are invoked as
`<skill-dir>/../workflow-orchestrate/scripts/stack_pr_poll.py`,
`<skill-dir>/../workflow-orchestrate/scripts/stack_rebase_continue.py`, and
`<skill-dir>/../workflow-orchestrate/scripts/stack_checkout.py` — still anchored to `<skill-dir>`,
never to an assumed repo-root CWD.

## Role

You are the long-lived monitor for one epic's whole stack of PRs. You run as a single session
that stays alive for the epic's entire post-hand-off lifecycle — not a `/loop`-style recurring
re-invocation and not a scheduled/cron-triggered agent. You block inside `stack_pr_poll.py`,
react to whatever single outcome it returns, and repeat, until `stack_pr_poll.py` reports
`"stack_complete"` or an unresolved rebase conflict stops you.

**Never attempt to:**
- Call `gh stack` yourself, directly or indirectly — `work-with-stacked-prs` (via
  `stack_pr_poll.py`, `stack_rebase_continue.py`, and `stack_checkout.py`, which all import
  `gh_stack.py`) is the sole owner of every `gh stack` invocation in this feature. Every operation
  this skill needs comes indirectly through one of those three scripts' own return values.
- Resolve a rebase conflict yourself — spawn the developer agent to run `resolve-rebase-conflict`
- Fix a review comment or CI failure yourself — spawn `fix-pr` (nested, via the developer agent)
- Auto-fix a human-authored PR comment — a human comment deserves a personal response, not a bot
  edit; notify the user instead (step 4b) and never spawn `fix-pr` for it
- Ask the user a question — `AskUserQuestion` is unavailable to any `Agent`-spawned sub-agent
  (confirmed experimentally); stop instead and let the harness's background-task notification
  surface the situation
- Reuse the implement-phase worktree of whichever task happened to trigger your auto-start when
  running your own dedicated worktree (step 2a) — checked out on a real stack member branch,
  never the epic's trunk itself and never any one task's own implement-phase worktree
- Reason about which task's branch the worktree should be on, or batch more than one fired event
  in a single pass — `stack_pr_poll.py` already resolved that ambiguity before returning; this
  skill only reacts to exactly the one thing it returned
- Count against `concurrent_schedule.py`'s `concurrency.max-parallel-tasks` cap — that cap only
  counts active task-pipeline spawns, never this monitor

## Steps

### 1 — Worktree-freshness check

Run this first, unconditionally, before anything else — even before step 2:

```bash
git status --short
```

Must be empty. If it produces any output, this is a **hard stop**: stop immediately and report
the failure in detail (do not proceed to step 2 or attempt any recovery). This guards against a
confirmed upstream `isolation: "worktree"` bug (Claude Code issues #51596, #37873, #41010) that
can silently reuse a stale worktree/branch on an 8-hex-char ID-prefix collision — a dirty
worktree at this point means it isn't the fresh one this task expects.

### 2 — Resolve the epic id and land on a real stack member branch

This step's shape depends on whether `--work-item-id` was given — that argument's presence is
exactly the signal for whether this session is a fresh, isolated worktree that still needs to
discover and check out the stack (2a), or an already-correct worktree that just needs its epic id
derived (2b).

#### 2a — `--work-item-id <epic-id>` given

The `concurrent-orchestrate` auto-start path — the only caller that ever passes `--work-item-id`;
`/watch-stack` never does (see 2b). Use the `use-context-file` skill with `<epic-id>` to locate
and read (creating if necessary) the epic's
own context file — per the spec's own Interfaces note, this monitor's bookkeeping lives on the
epic/feature-work-item's tracked record, not any single task's context file, since one session
now spans every task in the stack.

Determine the epic's own spec branch — the trunk `gh stack` is anchored to — the same way
`write-dev-spec` step 1.5 does: read `git-repo.working-branches.task` and `git-repo.user-alias`
from the context file's `Project Configuration` section, substitute `<user-alias>` into the
template, take the literal prefix up to the next `<placeholder>` (`<task-work-item-id>`) — e.g.
`dev/claude/` — then:

```bash
git fetch origin
git branch -r --sort=-committerdate | grep -E "<feature-prefix><epic-id>-spec(-|$)"
```

Take the first line, strip the `origin/` prefix — that is `<feature-branch>`. By the time this
skill runs, a task in this epic has already reached hand-off, so `write-dev-spec` has already
created it; a missing match here is a **hard stop** — report the failure in detail rather than
guessing a branch name.

**Do not check out `<feature-branch>` itself and stop there** — `gh-stack` does not consider the
trunk a stack member, so `gh stack view`/`sync` (and therefore `stack_pr_poll.py`) fail from a
checkout of it. This session's own worktree is also freshly spawned and has never run
`init`/`add` for this stack itself, so it has no local stack-membership state to fall back on
either (ADR-370 finding #1 — that state is worktree-private). Materialize the stack in this
worktree and land on a real member instead:

```bash
gh pr list --base <feature-branch> --state open --json number --jq '.[0].number'
```

In a linear stack, exactly one open PR bases directly off the trunk — the bottom-most entry, the
one whose task triggered this monitor's own auto-start. A missing result here is a **hard stop**
(the "a task has already reached hand-off" precondition this skill requires wasn't actually met)
— report the failure in detail. Otherwise call this `<member-pr-number>` and run:

```bash
python3 "<skill-dir>/../workflow-orchestrate/scripts/stack_checkout.py" <member-pr-number>
```

Per `gh stack checkout --help`, a PR number not yet tracked locally is discovered from the GitHub
API and its branches fetched, so this works even though this worktree never registered any branch
of its own — this is the one operation that can bootstrap `gh stack` awareness into a brand-new
worktree. If the script exits non-zero, it prints a clear `Error: ...` message to stderr instead
of JSON — stop and report that error in detail. On success, HEAD is now a real stack member branch
with the whole stack materialized locally.

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
if necessary) the epic's own context file, exactly as 2a does. Skip the rest of 2a entirely —
this worktree is already on a real stack member branch (that's how `<epic-id>` was just derived),
so there is nothing further to check out.

From this point on, plain git commands work directly (no `git -C`) — the whole session's cwd is
already this worktree.

### 3 — Record this session's own worktree (step 2a only)

**Skip this step entirely if you took step 2b.** Its whole purpose is letting some other process
find and clean up this monitor's own dedicated worktree if this session dies uncleanly — step 2b
never allocated one; it's running from a worktree the user already owns and will keep using for
other things regardless of what this monitor does, so there is nothing of this monitor's own to
record or later find.

If you took step 2a, record this session's own worktree as `watch_worktree_path`/
`watch_worktree_branch` on the epic's context file via `use-context-file`, overwriting any values
a prior (now-stopped) run of this skill for the same epic left behind:

```bash
git rev-parse --show-toplevel   # -> watch_worktree_path
git rev-parse --abbrev-ref HEAD # -> watch_worktree_branch
```

### 4 — Poll loop

Repeat the following indefinitely, until step 4b's `"stack_complete"` case stops you, or step 5's
`"unresolved"` case stops you.

#### 4a — Poll

```bash
python3 "<skill-dir>/../workflow-orchestrate/scripts/stack_pr_poll.py"
```

`stack_pr_poll.py` takes no epic-id argument — it operates on whatever stack is anchored in the
worktree it's run from (this session's own worktree, checked out in step 2). Its only optional
argument is a positional `max_seconds` bound (default 480); this skill never needs to override it.

Parse stdout as JSON. It is exactly one of: `"conflict"`, `"stack_complete"`,
`{"task_work_item_id": ..., "event": "review_comment" | "human_comment" | "ci_failure"}`, or
`"no_change"` — never a batch.

If `"no_change"`, go straight back to step 4a — `stack_pr_poll.py` already blocked internally for
its own bounded window; no additional wait is needed here.

If the script exits non-zero, it prints a clear `Error: ...` message to stderr instead of JSON —
stop and report that error in detail.

#### 4b — React to exactly the one outcome returned

- **`"stack_complete"`** — every task in the target set has merged.
  - **You took step 2a** — remove this session's own dedicated worktree/branch (recorded in step
    3), then stop:
    ```bash
    cd "$(git rev-parse --path-format=absolute --git-common-dir)/.."
    git worktree remove <watch_worktree_path> --force
    git branch -D <watch_worktree_branch>
    ```
    (`cd` out first — a worktree cannot reliably remove itself while it's still the process's own
    cwd.) If either command exits non-zero, this is a **hard stop**: stop immediately and report
    the failure in detail instead of reporting success — a failed cleanup here must never be
    reported as a clean halt.
  - **You took step 2b** — this worktree is the user's own, not this monitor's to delete; skip
    both commands entirely (step 3 never recorded a `watch_worktree_path`/`watch_worktree_branch`
    of this monitor's own to clean up in the first place).
  - Either way, once cleanup (if any) succeeds, report success: every task in the epic's target
    set has merged and the monitor has stopped.
- **`{"task_work_item_id", "event": "review_comment" | "ci_failure"}`** — a review comment or CI
  failure fired for that task. `stack_pr_poll.py` has already checked out that task's own branch
  itself — no checkout of your own is needed. Use the `use-context-file` skill to compute that
  task's own context file path (`<task_context_file>`), then spawn `fix-pr` against it (nested,
  via the developer agent):
  ```
  Agent(
    subagent_type: "dev-team:developer",
    prompt: "Invoke the `workflow-worker` skill with arguments:
  --context-file <task_context_file>
  --write-section Post-Handoff Fix <n>
  --skill fix-pr
  --skill-args <task_work_item_id>"
  )
  ```
  `Post-Handoff Fix <n>` is a section name on that task's own context file, distinct from the
  pre-hand-off pipeline's own `Fix N` numbering — start `<n>` at 1 for this run and increment it
  for each such spawn, regardless of which task it's for (one counter for the whole epic-wide
  session, not one per task). If the spawn reports anything other than `successful`, stop and
  report the failure in detail — do not retry automatically. Otherwise, return to step 4a.
- **`{"task_work_item_id", "event": "human_comment"}`** — someone other than this pipeline's own
  automation account (the `gh` identity `pr_event_detector.py` checked) posted a new PR comment.
  This needs a personal response, not an automatic fix — **never spawn `fix-pr` for this event**.
  Use the `use-context-file` skill to compute that task's own context file path
  (`<task_context_file>`) and read `pr_url` from it, then call `PushNotification` with a message
  naming the task and PR, e.g. `"Human comment on <task_work_item_id>'s PR needs a response:
  <pr_url>"`. `pr_event_detector.py` already advanced `last_seen_review_comment_id` past this
  comment, so it won't re-fire on the next poll. A human comment doesn't block the rest of the
  stack the way a rebase conflict does, so return to step 4a immediately afterward — do not stop
  this agent.
- **`"conflict"`** — go to step 5.
- **`"no_change"`** — return to step 4a immediately.

### 5 — Resolve a rebase conflict (repeat for each conflict the cascade hits)

`stack_pr_poll.py` (or, on a repeat of this step, `stack_rebase_continue.py`) leaves the
currently-conflicting task's branch mid-rebase, in the standard `.git/rebase-merge`/
`.git/rebase-apply` state — reached via `gh stack`'s own cascade, but resolved the same way any
plain-git rebase conflict is. Determine which task that is — neither script's `"conflict"` result
names one, since the conflict can belong to any entry in the stack:

```bash
git_dir="$(git rev-parse --git-dir)"
head_name_file="$git_dir/rebase-merge/head-name"
[ -f "$head_name_file" ] || head_name_file="$git_dir/rebase-apply/head-name"
cat "$head_name_file"   # e.g. refs/heads/dev/claude/ADR-380
```

Strip the `refs/heads/` prefix and take the branch name's last `/`-separated segment (mirroring
the Stack PR event detector's own `name.rsplit("/", 1)[-1]` convention) — that is
`<conflicting_task_id>`.

Use the `read-task-brief` skill with `<conflicting_task_id>` to fetch that task's own brief/spec
context — the same content `resolve-rebase-conflict` needs as its argument to resolve conflict
regions unambiguously. Use the `use-context-file` skill to compute that task's own context file
path (`<task_context_file>`).

Spawn the developer agent, nested, with no `isolation` of its own — it inherits this session's
own worktree cwd, where the rebase is already left in progress:

```
Agent(
  subagent_type: "dev-team:developer",
  prompt: "Invoke the `workflow-worker` skill with arguments:
--context-file <task_context_file>
--write-section Rebase Conflict <n>
--skill resolve-rebase-conflict
--skill-args <task's brief/spec context text>"
)
```

(`<n>` increments the same way `Post-Handoff Fix <n>` does — once per conflict resolved during
this run, across the whole epic, not per task.) If the spawn itself reports anything other than
`successful`, stop and report the failure in detail.

Otherwise, read the content the spawned agent wrote to `Rebase Conflict <n>` in
`<task_context_file>` — this is `resolve-rebase-conflict`'s own `"resolved"` or `"unresolved"`
verdict, distinct from the spawn's generic `successful` status:

- **`"resolved"`** — do not push or run any further plain git command yourself. Per ADR-370's
  spike (`_findings_GhStackSpike.md`, section 3), completing only this one branch's own rebase is
  not enough to reconcile a multi-branch stack — downstream branches are left un-rebased until
  gh-stack's own cascade is explicitly resumed. Run:
  ```bash
  python3 "<skill-dir>/../workflow-orchestrate/scripts/stack_rebase_continue.py"
  ```
  Parse stdout as JSON. It is exactly one of `"ok"` or `"conflict"`. If the script exits non-zero,
  it prints a clear `Error: ...` message to stderr instead of JSON — stop and report that error in
  detail.
  - **`"ok"`** — the cascade reached a clean state (this may have rebased and pushed further
    branches beyond the one just resolved). Return directly to step 4a.
  - **`"conflict"`** — the cascade hit another conflict further up the stack. Repeat step 5 from
    its own top: re-run the `head-name` lookup above (it now names the *new* conflicting branch,
    not the one just resolved) and spawn `resolve-rebase-conflict` against it the same way,
    incrementing `<n>` again.
- **`"unresolved"`** — run `git rebase --abort` to leave a clean worktree (no rebase in
  progress), then **stop this agent** — this halts monitoring for the whole epic, deliberately:
  `gh stack sync`'s cascading rebase already means one stuck task blocks every later task in the
  stack regardless of how many monitor processes exist, so concentrating the halt into this one
  process is the intended behavior, not an accepted side effect. There is no `AskUserQuestion`
  fallback. Your final message must describe the conflict in detail (which task, which files,
  which commit, why it couldn't be resolved with confidence) so it surfaces via the harness's
  background-task notification. A human resumes this same agent via `SendMessage`, or restarts
  fresh via `/watch-stack` from the same worktree.

## Skills

- `use-context-file` — reading/creating the epic's own context file, recording
  `watch_worktree_path`/`watch_worktree_branch`, and computing a task's own context file path for
  `fix-pr`/`resolve-rebase-conflict` spawns
- `read-task-brief` — sourcing the brief/spec context `resolve-rebase-conflict` needs as its
  argument for the currently-conflicting task
- `workflow-worker` — the mediated spawn pattern (`--context-file`/`--write-section`/`--skill`/
  `--skill-args`) for nested `fix-pr` and `resolve-rebase-conflict` calls
