# Concurrent Development

> **Status:** Draft
> **Epic:** [ADR-296](https://jodasoft.atlassian.net/browse/ADR-296)
> **Design doc:** `_doc_ConcurrentDevelopment.md` — authored by the final documentation task once
> implementation completes; this spec persists afterward for harvesting

## Overview

Today the dev-team pipeline (`dev_team.py` / `workflow-orchestrate`) implements exactly one
task-work-item at a time, in a single shared working directory, with its working branch always
based on the feature branch. This feature lets a spec's tasks declare dependencies on each
other so that independent tasks can be developed by two dev teams at once, and a dependent task
can start — based on its dependency's *task branch* — while that dependency is still in review,
instead of waiting for it to merge. A new scheduler reads the dependency graph from the spec and
spawns each task's pipeline as soon as it becomes eligible, so a whole queue of tasks can run —
several at once, respecting their dependency order — unattended overnight. Once a task's PR is
handed off to a human reviewer, a separate long-lived monitor (started by the user, one per PR)
takes over keeping it in sync: rebasing when its base branch moves or its dependency merges, and
reacting to review comments and CI failures — so that by the time the user works through a queue
of PRs in order, each one is already up to date.

## Responsibilities & Boundaries

- **Owns:** the `Depends on:` task-field convention in a spec's `## Tasks` section; parsing that
  section into a dependency graph; the readiness check that decides when a dependency can be
  built upon (its PR is open); the new concurrent scheduler that spawns one `workflow-orchestrate`
  run per eligible task; per-task-work-item git worktree isolation so concurrent pipelines don't
  collide in one working directory; extending `ensure-working-branch`'s base-branch computation
  to prefer a ready dependency's task branch (initial base selection only); the `dev-team:watch-pr`
  PR monitor that owns the entire post-hand-off lifecycle — rebase-on-base-update,
  rebase-on-dependency-merge, review-comment fixes, CI-failure fixes, and halting on merge.
- **Does not own:** the single-task pipeline's internal states (implementing, validating,
  reviewing, signoff, etc. — unchanged, reused as-is by the scheduler); the pre-hand-off AI
  review/fix loop (`reviewing`/`fixing-pr`/`signoff`), untouched by the new monitor; Jira/GitHub
  adapter internals; automatic resolution of a genuine rebase conflict (the monitor attempts it
  first, but an unresolved conflict goes to the human running the monitor, never guessed at).
- **Integrates with:**
  - `spec-task-breakdown` — tasks gain a `Depends on:` field (local task-number references) in
    step 1; step 5 rewrites those references into real keys alongside the existing title rewrite
  - `ensure-working-branch` — gains only the initial dependency-aware base-branch-selection step;
    no mid-pipeline rebase logic
  - `workflow-orchestrate` / `dev_team.py` — reused unchanged as the per-task pipeline; the new
    scheduler is a layer above it, spawning one run per task
  - `use-context-file` — the scheduler and the PR monitor both read/write context-file fields
    (readiness, `base_branch_sha`)
  - the existing `fix-pr` skill — reused by the PR monitor to address review comments and CI
    failures
  - the developer agent — reused by the PR monitor to attempt resolving a rebase conflict
  - `get-project-configuration` — gains a new `concurrency.max-parallel-tasks` key (default 3)

## Key Design Decisions

### Dependencies are declared inline in the spec's task list

_Context:_ The epic asks for dependencies to be "added to the spec." The task list already
lives in a spec's `## Tasks` section (written by `spec-task-breakdown`), and both humans (during
spec review) and agents (parsing the spec) need to read it easily.

_Decision:_ Each task gains a `**Depends on:** <ref>[, <ref>...]` line directly under its title
(or `**Depends on:** — none —` when it has no dependencies). A task may depend on more than one
other task. Only dependencies on other tasks within the *same* spec are supported for now — a
task depending on a task-work-item tracked in a different spec/epic is out of scope (see Related
Features).

Task-work-item keys don't exist yet at the point this field is first authored: `spec-task-breakdown`
writes titles and descriptions in its step 1, pauses for human approval in step 2, and only
assigns real tracked-work-item keys in step 4, rewriting titles into hyperlinks in step 5. So
`<ref>` is the task's local numbering (e.g. `Task 3`, matching the `### Task N: ...` heading
convention already used in `## Tasks`) when first authored in step 1 — the only identifier that
exists at that point — and `spec-task-breakdown` is extended so that step 5, which already
rewrites each task's title into a hyperlink once keys are assigned, also rewrites every
`Depends on:` line's local task-number references into the corresponding real keys at the same
time. By the time a spec leaves `spec-task-breakdown`, every `Depends on:` reference is a real
key; nothing downstream (the dependency graph parser, `concurrent_schedule.py`, etc.) ever needs
to understand the local-numbering form.

Step 1 populates the initial value the same way it already drafts each task's description: a
best-effort inference from the design content (a task whose description says it builds on
another task's interfaces gets that task named as a dependency), defaulting to `— none —` when
no dependency is evident. No new pause is needed for this — the existing step-2 human-approval
pause is exactly where the user already reviews and corrects titles, descriptions, and exit
criteria, and `Depends on:` is corrected the same way, at the same point.

Step 5's rewrite is also the first point where the graph is guaranteed complete (every reference
now a real key), so it's where `parse_task_dependencies` is run once as a validation pass, not
just for later scheduling use: it rejects immediately, with a clear error naming the offending
task and reference, if any `Depends on:` entry names a local task number with no matching task
heading (or, post-rewrite, a key that isn't itself a task in this spec), or if the resulting graph
contains a cycle. This is the same "reject upfront rather than fail silently or loop forever"
posture the Concurrent scheduler decision below takes for an out-of-scope dependency in an
explicit task list.

_Consequences:_ No separate graph file to keep in sync with the task list; the dependency graph
is derived by parsing this one field across all tasks. Cross-spec dependencies remain unsupported
until a future pass. `spec-task-breakdown` carries one additional responsibility (rewriting
`Depends on:` references alongside titles) but no additional pause or user interaction — it
happens as part of the existing step 5; that same step now also catches a dangling reference or a
dependency cycle before the spec ever leaves task breakdown, rather than surfacing much later as
a task that never becomes eligible or a scheduler run that polls forever.

### A dependent task may start once its dependency's PR is open — or, with multiple dependencies, once all but one have merged

_Context:_ The epic's own text: "Tasks that have a dependency can be started while the
dependency is in review." Waiting for a full merge would forfeit the concurrency this epic is
for. But a task can declare *more than one* dependency, and a git branch can only have one base —
so a task with several still-open dependencies has no single unambiguous branch to build on.

_Decision:_ For a task with exactly one dependency, that dependency counts as "ready to build
upon" once its `pr_url` is set in its own context file (i.e. it has reached `creating-pr` or
later in the existing pipeline) — a single field read, already tracked by every task's context
file today. For a task with more than one dependency, it isn't eligible to start until **all but
at most one** of its dependencies has reached `done` (merged into wherever its own PR actually
merged — see the base-re-target decision below); if one dependency remains un-merged, that one
must also be "ready" (`pr_url` set) for the dependent to start. Once eligible, the dependent's
`base_branch` is always unambiguous: no override needed (`None`) if every dependency has already
merged — `ensure-working-branch` just runs its own existing default feature-branch resolution,
unchanged — or the one remaining dependency's branch otherwise, the exact same single-dependency
mechanic, just gated on a stricter readiness condition. A task with two or more dependencies still
short of `done` simply isn't eligible yet (`"waiting"`); if any dependency has instead ended in
`dev_team.py`'s other terminal state, `failed`, the dependent can never become eligible at all
(`"blocked"` — see the Concurrent scheduler interface).

_Consequences:_ A dependent starts against a real, stable, pushed branch — but that branch can
still receive new commits during the dependency's own fix/review cycle. That's exactly what the
rebase mechanic (below) exists to absorb. Multi-dependency tasks wait longer to start than
single-dependency ones (by design — the epic's "start while in review" concurrency benefit only
applies to the one dependency allowed to still be open), but never need more than one base
branch or a synthetic merge of several unmerged branches.

### Concurrent pipelines require per-task-work-item git worktrees

_Context:_ Every step of today's pipeline (`ensure-working-branch`, the developer/reviewer
agents, `_commit_and_push` in `dev_team.py`) operates directly on one shared repository working
directory and does `git checkout <branch>`. Two pipelines running at once would check out two
different branches into the same tree and corrupt each other. `_spec_TddForImplementation.md`
already flagged exactly this as deferred future work ("true concurrent implementation would need
per-component isolation... a real risk for compiled languages").

_Decision:_ Each task's `workflow-orchestrate` run is spawned with the `Agent` tool's native
`isolation: "worktree"` support, which creates and later cleans up an isolated git worktree for
that one spawn automatically. `ensure-working-branch` needs no changes to become
worktree-compatible: it already does `git checkout -b <working-branch> origin/<base-branch>`
itself, so it doesn't care what branch the fresh worktree starts on. Every existing skill and
script that assumes a single fixed repo-root cwd (`commit-changes`, `workflow-script`, etc.)
keeps working unmodified, because the entire spawned agent's session — its whole task pipeline,
start to finish — already runs with that worktree as its cwd.

_Consequences:_ No changes needed to the many existing skills/scripts that assume a fixed
repo-root cwd — this is the main reason this option was chosen over the alternative of the
scheduler managing `git worktree add` itself, which would have required threading a
working-directory parameter through nearly all of them.

Confirmed experimentally during spec design: an agent spawned via the `Agent` tool from inside
an already-isolated (`isolation: "worktree"`) agent, with no `isolation` parameter of its own,
inherits the exact same worktree cwd — verified by spawning a nested agent from inside a
worktree-isolated one and confirming both reported byte-identical `git rev-parse --show-toplevel`
output and the nested agent could read a marker file the outer agent had just written. No
fallback (explicitly passing the worktree path to nested spawns) is needed.

**Known upstream risk:** `isolation: "worktree"` derives the worktree's branch name from an
8-hex-char prefix of the spawned agent's own ID (`worktree-agent-<8hex>`). Three independently
reported, currently-unresolved upstream issues (anthropics/claude-code#51596, #37873, #41010 —
confirmed real via `gh issue view`, auto-closed as stale duplicates, not fixed) document that on a
prefix collision with a branch left over from a prior session, the tool **silently reuses** that
stale branch/worktree — including its old uncommitted files and stash stack — rather than
creating a genuinely fresh one, with no indication to the agent that its "isolated" worktree
isn't actually clean. This is exactly the failure mode this decision exists to prevent, and a
project that spawns many worktree-isolated agents per overnight run (this feature's whole
premise) is squarely the kind of usage where a collision eventually becomes likely. Mitigation:
immediately after obtaining a worktree via `isolation: "worktree"` — both at the start of each
task's `workflow-orchestrate` run and at the start of `dev-team:watch-pr` — verify it's actually
fresh before doing anything else: `git stash list` must be empty and `git status --short` must
show no unexpected pre-existing modifications. If either check fails, treat it as a hard failure
(stop and report) rather than silently proceeding on a potentially contaminated worktree.

### `PipelineContext` must round-trip every context-file field, not just its own named ones

_Context:_ Confirmed by reading `dev_team.py`: `PipelineContext.save()` rewrites the context
file's entire YAML frontmatter block from a fixed list of named dataclass fields, and `load()`
reconstructs a `PipelineContext` from that same fixed list — neither round-trips a frontmatter key
it doesn't itself declare. This is already true today for `working_branch`, `base_branch`, and
`parent_work_item` (all written directly via `Edit`, per `use-context-file`, never through
`PipelineContext`) — currently harmless only because `ensure-working-branch` recomputes any of
them that comes back empty. `workflow-orchestrate`'s orchestration loop invokes `dev_team.py` (and
so calls `ctx.save()`) on every iteration of a task's pipeline, on the very same context file these
skill-level fields live in.

This feature is the first thing that makes the gap actually harmful. `concurrent-orchestrate` (see
below) pre-populates `base_branch` before a task's `workflow-orchestrate` run even starts — but
`dev_team.py`'s first `ctx.save()` call happens at pipeline boot, before `ensure-working-branch`
ever runs, so it would silently wipe that pre-populated value, and the task would fall back to the
ordinary feature branch instead of its dependency's branch with no error at all. The same problem
hits `worktree_path`/`worktree_branch` (recorded right after spawn, needed by `dev-team:watch-pr`
at hand-off) and every field the PR monitor decision introduces (`base_branch_sha`,
`last_seen_review_comment_id`, `last_seen_ci_conclusion`, `watch_worktree_path`,
`watch_worktree_branch`) — none of these are `PipelineContext` dataclass fields either.

_Decision:_ Rework `PipelineContext.save()`/`load()` to round-trip any frontmatter key it doesn't
itself declare as a named field, alongside the ones it does — reading the full frontmatter block
into a dict first, overwriting only the keys it knows how to interpret as typed fields, and
writing back every other key unchanged in `save()`. This fixes the pre-existing silent-drop for
`working_branch`/`base_branch`/`parent_work_item` at the same time it makes every new field this
spec introduces durable, without requiring a matching named dataclass field for each one going
forward.

_Consequences:_ One shared fix covers every current and future skill-managed frontmatter field, so
neither this spec nor a later one needs to keep extending `PipelineContext`'s own field list just
to avoid data loss. Tracked as its own task (see Task 0 below), since it's a `dev_team.py` change
that every other task in this breakdown touching `base_branch`, `worktree_path`/`worktree_branch`,
or the PR-monitor fields depends on being fixed first.

### A new scheduler spawns one pipeline run per eligible task

_Context:_ The user chose full scope for this spec: not just the branch/rebase mechanics, but
the actual "queue tasks up and let them run overnight" scheduling behavior.

_Decision:_ The existing `/implement` command is extended to recognize a phrase naming more than
one work item — an inclusive **"up to" target task** (e.g. `/implement up to ADR-310`) or an
explicit list (e.g. `/implement ADR-310, ADR-311, and ADR-312`) — rather than eagerly running
everything in the spec. A single work item still dispatches to `workflow-orchestrate` exactly as
today; either multi-item form dispatches to the new `concurrent-orchestrate` instead, running as
a single long-lived agent session — not a `/loop`-style recurring re-invocation and not a
scheduled/cron-triggered agent — that stays alive for the whole run.

All of the actual scheduling logic — parsing `## Tasks`, computing the target's dependency
closure for the "up to" form (or taking the list as-is, with no closure expansion), tracking each
task's status, and enforcing a concurrency cap (default 3, overridable via project configuration)
— lives entirely in `concurrent_schedule.py`, not in `concurrent-orchestrate` itself (see the
Data Flow section below for the full call sequence). `concurrent-orchestrate`'s own job reduces
to a thin loop: invoke the script, spawn whatever it returns, and re-invoke it on an interval and
whenever a spawned pipeline finishes — since a task pipeline finishing is one thing the
orchestrator is notified on automatically, but a dependency merely reaching "PR open"
mid-pipeline (the actual readiness gate for its dependents) is not a terminal event, so periodic
re-invocation is still needed to catch that earlier milestone. Either way, the run is scoped to
just the target set — tasks outside it are left alone even if they'd otherwise be independently
ready — and newly eligible tasks beyond the concurrency cap simply wait for a free slot on a
later call. The existing single-task pipeline is reused unmodified; only this scheduling layer is
added above it.

For an explicit list, "no closure expansion" creates a validation obligation: if a listed task
depends on a task-work-item that's neither in the list nor already `done`, it can never become
eligible — not even `"blocked"`, since that requires an actual `failed` dependency, not merely an
out-of-scope one. `concurrent_schedule.py` validates this upfront, before spawning anything: every
dependency of every listed task must itself be in the list or already `done`, or the whole request
is rejected immediately with a clear error naming the offending task and missing dependency,
rather than silently polling forever.

The concurrency cap counts only active task-pipeline spawns tracked in `concurrent_schedule.py`'s
own data files; a `dev-team:watch-pr` monitor (started separately at hand-off, per the PR monitor
decision below) is never counted against it. A monitor spends nearly all its time blocked inside
`watch_pr_poll.py`, not consuming compute, and it's gated on hand-off having already happened, not
on a scheduler decision — counting it the same as an active implement/validate/review pipeline
would let a backlog of PRs simply awaiting human review permanently starve the cap even though
those monitors are comparatively idle.

_Consequences:_ Multiple task pipelines genuinely run in parallel, each independently
progressing through the existing implement/validate/review/signoff/handoff states, but a run
always stops at a boundary the user chose rather than consuming the whole remaining graph.
Because the script — not the orchestrator agent — holds the dependency graph and all scheduling
state, `concurrent-orchestrate` doesn't accumulate that context across a long run. If a task's
own pipeline ends in `dev_team.py`'s other terminal state, `failed` (never reaching hand-off), any
not-yet-started task depending on it can never become eligible — the script reports `"blocked"`
instead of `"waiting"` once every currently-spawned task has also reached a terminal state, so
`concurrent-orchestrate` stops and reports the specific blocked tasks rather than polling forever.

### A user-started PR monitor owns the entire post-hand-off lifecycle

_Context:_ Once a task's pipeline reaches hand-off, its state is terminal and nothing watches it
anymore — but the working branch can still need to change afterward: its base might get new
review-fix commits or merge, a human reviewer might leave comments, or a later push might fail
CI. Doing this reactively inside `ensure-working-branch`, mid-pipeline, was considered and
rejected: rebasing between the developer's and reviewer's turns risks derailing whatever either
of them has in flight.

_Decision:_ A new `dev-team:watch-pr` skill runs as a long-lived agent that repeatedly calls the
bounded, blocking `watch_pr_poll.py` (see Component Breakdown / Interfaces), re-checking five
conditions each time and acting on whichever fired. It is itself spawned with the `Agent` tool's
`isolation: "worktree"` support — a *fresh* worktree, not a reuse of the one from the task's
original `workflow-orchestrate` run — and its first action is `git fetch origin && git checkout
<working_branch>` to position that fresh worktree on the task's actual branch. Plain git commands
work directly from then on, no `git -C` needed, because the whole session's cwd already is that
worktree. The original `workflow-orchestrate` run's worktree (recorded as `worktree_path` /
`worktree_branch` in the context file) is no longer needed once hand-off happens, so
`dev-team:watch-pr` removes it as one of its first actions, and instead records its own
`watch_worktree_path` / `watch_worktree_branch` for its own eventual cleanup at halt.

`concurrent-orchestrate` auto-starts one the moment a task's `workflow-orchestrate` run reaches
hand-off, spawning it as a **local background `Agent`** (`run_in_background: true`) — not a cloud
routine — reusing the same sandboxed environment. A new `/watch-pr <task-key>` command, parallel
to `/implement`, covers the manual fallback for the case where the auto-start never happened (e.g.
`concurrent-orchestrate`'s own session was interrupted before reaching hand-off for that task) —
its entire job is spawning `dev-team:watch-pr` via the `Agent` tool with its own `isolation:
"worktree"`, since a human invoking the skill bare from their own session would get no isolation
at all.

A cloud routine (via `RemoteTrigger`, the mechanism behind the `/schedule` skill) was considered
and rejected: it would run outside the carefully configured local sandbox/permissions setup this
project depends on for unattended operation, reintroducing exactly the permission-prompt friction
that setup exists to eliminate. Its one advantage — surviving the local session being fully
closed, not just interrupted mid-run — isn't worth that cost; manual restart covers that gap.

(a) a new review comment on the PR → spawn `fix-pr` (a nested `Agent`, no `isolation` of its own,
    so it inherits `dev-team:watch-pr`'s isolated worktree cwd) to address it
(b) a CI check failure → spawn `fix-pr` the same way, to debug and fix it
(c) the recorded base branch has new commits → run the rebase mechanic
(d) the dependency's own PR has merged → re-target the base to wherever it actually merged (see
    the base-re-target decision below), then run the rebase mechanic
(e) the task's own PR has merged → remove its own worktree/branch and halt

`ensure-working-branch` keeps only its original, narrower job: choosing the *initial* base branch
for a task's working branch (preferring a ready dependency's branch — see the Base-branch
resolver decision). It gains no mid-pipeline rebase logic.

Confirmed experimentally during spec design: (1) `AskUserQuestion` is not available at all to an
`Agent`-tool-spawned sub-agent, background or otherwise — a probe agent found it absent from its
own tool list and from two independent `ToolSearch` queries. A spawned agent cannot "ask the
user a question" the way the top-level session can. (2) A nested `Agent` spawn does *not* inherit
a cwd the outer agent reached via a manual `cd` mid-session — a controlled test confirmed the
nested spawn resets to the default cwd, and separately that cwd changes don't even persist across
separate `Bash` calls within one agent's own session. Nested spawns only inherit cwd when the
*outer* agent itself was spawned with `isolation: "worktree"` (confirmed separately, see the
worktree decision above) — which is exactly why `dev-team:watch-pr` requests its own fresh
isolated worktree here, rather than trying to operate against the original one via `git -C`.

_Consequences:_ The pre-hand-off AI review/fix loop (`reviewing`/`fixing-pr`/`signoff`) is
entirely unaffected — the monitor only starts once a PR is out of draft. This is also the
mechanism for the epic's "review PRs in order" workflow: several tasks reach hand-off
autonomously, the user starts a monitor per PR, and as the user addresses the first PR's
comments, its dependents' monitors pick up the resulting commits and rebase automatically — so
by the time the user reaches the next PR, it's already up to date. A task now has two sequential
(never overlapping) worktrees over its lifetime — the implement-phase one and `watch-pr`'s own —
rather than one continuously reused worktree; each is cleaned up once its own phase ends.

A rebase conflict is never resolved by guessing: the monitor spawns the developer agent (a
nested, non-isolated `Agent`, inheriting the same worktree cwd) to run `resolve-rebase-conflict`
(see Interfaces) first. On `"resolved"`, `dev-team:watch-pr` pushes with `--force-with-lease`
itself. On `"unresolved"`, it runs `git rebase --abort` — leaving a clean worktree, not a
half-finished rebase for a human to find — since it cannot fall back to `AskUserQuestion` at that
point; nothing spawned via the `Agent` tool can ask the user directly. Instead it stops itself,
with its final message describing the conflict; this surfaces through the harness's own
background-task notification to whoever is watching (the same mechanism observed directly during
this spec's own design experiments). A human can resolve the conflict manually and resume the
same agent via `SendMessage`, or simply restart via `/watch-pr` once it's resolved — the same
manual fallback already covering the auto-start-never-happened case. This replaces routing through
the general-purpose troubleshooter agent used by the (still-unattended) pre-hand-off pipeline,
which assumes a session that can keep working, not one that has genuinely stopped. Halting affects
only this one task's monitor — a dependent task simply stops receiving further rebases from it
until
the conflict is resolved; the dependent's own independent progress (implementation, review, its
own unrelated rebases) continues unaffected.

The rebase mechanic force-pushes with lease immediately as part of `rebase_onto()` itself — no
separate tracking is needed for this. `_commit_and_push()` in `dev_team.py` (the plugin's one
other push call site, run during the main pipeline after validation passes and again before
reviewer sign-off) never needs to change: rebasing only ever happens inside `watch-pr`, entirely
after a task's own `dev_team.py` pipeline has already reached its terminal hand-off state, so
that call site never encounters a branch that's been rebased. The rebase mechanic's own
force-with-lease push is also what cascades the update onward: it moves the remote tip of this
task's branch, which is precisely the "base updated" condition the *next* dependent's `watch-pr`
monitor will detect on its own next wake — one rebase's push is what kicks off the next.

### Dependency completion re-targets the base to wherever it actually merged

_Context:_ Epic text: "when the dependency is completed... the base becomes the feature branch."
That's the common case, but it's a simplification: a dependency's PR is itself based on whatever
branch it was building on (the feature branch, or — if it had its own dependency still in
review — another task's branch). Tracing this through also caught a conflation worth calling
out explicitly: `dev_team.py`'s own terminal `done` state is reached right after **hand-off**
(`handoff --> done : handoff_done`), well before a human actually clicks merge. It cannot be used
to detect an actual merge — that requires polling the PR's real status on GitHub, which is
exactly what the PR event detector (used only by `watch-pr`) is for. The `Task readiness
checker`'s own `"done"` value (based on context-file `state`) means "reached hand-off," and stays
scoped to the scheduler's own eligibility computation — it is never used for merge detection.

This matters for ordering, too: nothing prevents a dependent's PR from merging before its own
dependency's PR does (e.g. ADR-123 depends on ADR-122; ADR-123's PR — based on ADR-122's branch —
merges first, landing its commits on ADR-122's branch, while ADR-122's own PR to the feature
branch is still open). This isn't a hazard to guard against; it falls out naturally once the
re-target rule is correct.

_Decision:_ When the PR event detector observes (via GitHub) that a dependency's PR has actually
merged, it also reads what branch it merged **into**. The dependent's `watch-pr` monitor
re-targets `base_branch` to that actual destination — usually the feature branch, but another
task's still-open branch in a stacked/out-of-order case like the one above — then proceeds as an
ordinary rebase onto that new base.

_Consequences:_ No separate "merge-up" step is needed; re-targeting the base is just an input to
the same rebase mechanic, triggered as event (d) in the PR monitor decision above. Because the
target always follows where the dependency's code actually landed, merge order across a
dependency chain is irrelevant to correctness — a dependent always ends up rebased onto its real
ancestor chain, whatever shape that took, with no data loss and no special-casing required for
out-of-order completion.

### Remove the existing todo-log/`TodoWrite`-mirroring plumbing

_Context:_ `workflow-orchestrate` currently has spawned agents write their todo updates to a
shared `todo_log` file instead of calling `TodoWrite` directly, then tails that log with
`Monitor` and mirrors each update into its own `TodoWrite` so the user can see sub-agent progress
in the visible task list. Each spawned agent also carries an instruction to maintain a to-do list
as it works. In practice this doesn't surface well and isn't working well even for a single
task's pipeline today, adding overhead to the top-level session for questionable benefit — and it
has no clean extension to `concurrent-orchestrate`, where several sub-agents' todo logs would need
to mirror into one flat list at once.

_Decision:_ Remove the todo-log-tailing/`TodoWrite`-mirroring mechanism from `workflow-orchestrate`
and `workflow-worker`, and remove the per-agent "maintain a to-do list" instruction. This is
unrelated to the dependency/rebase mechanics otherwise described in this spec, but is tracked as
its own task in this spec's task breakdown since it's prompted directly by this feature exposing
the mechanism's scaling limits.

_Consequences:_ Sub-agent progress is no longer mirrored into the top-level session's visible
task list. No replacement mechanism is scoped here — if progress visibility into a running
`concurrent-orchestrate` session is needed later, that's a separate design question, not answered
by this removal.

## Component Breakdown

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `Depends on:` task field | Wrapper | Declares a task's dependencies inline in the spec's `## Tasks` section — local task-number references until `spec-task-breakdown` step 5 rewrites them to real task-work-item keys | — |
| `PipelineContext` frontmatter round-trip (extends `dev_team.py`) | Testable | Preserves every context-file frontmatter field across `save()`/`load()`, not just the fields `PipelineContext` itself declares — fixes a pre-existing silent-drop this feature would otherwise make harmful | — |
| Task dependency graph parser | Testable | Parses a spec's `## Tasks` section into a `{task_id: [dependency_ids]}` graph; rejects a dangling reference or a dependency cycle with a clear error rather than accepting either silently | — |
| Task readiness checker | Testable | Given a task-work-item id and its full list of declared dependencies, reports per-dependency PR/merge status and whether the task as a whole is eligible to start (single ready dependency, or all-but-one of several already merged) | `use-context-file` (existing) |
| `/implement` argument parser | Wrapper | Recognizes a single task key, an inclusive "up to" phrase, or an explicit comma/"and"-separated list in the command argument, and dispatches to `workflow-orchestrate` (existing) or `concurrent-orchestrate` accordingly | `workflow-orchestrate` (existing), `concurrent-orchestrate` |
| Concurrent scheduler (`concurrent_schedule.py`) | Testable | Owns the dependency closure, each task's cached status, and the concurrency cap; exits with a status (including `"blocked"` when a failed dependency permanently stalls a task) and a spawn list; spawns nothing itself | Task dependency graph parser, Task readiness checker |
| `concurrent-orchestrate` | Orchestrator | Thin spawn loop: invokes the scheduler script, pre-populates each spawned task's `base_branch` when one is given, spawns an isolated (`isolation: "worktree"`) `workflow-orchestrate` run per descriptor, records its worktree path/branch, reports `"blocked"` to the user instead of continuing to poll | Concurrent scheduler, `workflow-orchestrate` (existing) |
| Base-branch resolver (extends `ensure-working-branch`) | Orchestrator | Uses a pre-populated `base_branch` if the context file already has one; if it's explicitly `None` (scheduler says no override needed) or absent entirely (non-scheduler run), falls back to its own existing default resolution | Task readiness checker |
| Rebase mechanic | Testable | Fetches, rebases a working branch onto an updated base, and force-pushes with lease; reports success or conflict | — |
| PR event detector | Testable | Given a task's context file and its PR's current GitHub/git state, determines which of the five monitor conditions have newly fired (possibly more than one at once) | `use-context-file` (existing) |
| `watch_pr_poll.py` | Testable | Loops the PR event detector on an interval, self-bounded to under Bash's 10-minute timeout cap; exits early with whichever condition(s) fired, or `"no_change"` at the window's end | PR event detector |
| `resolve-rebase-conflict` (new skill) | Testable | Given a rebase left in progress with conflicts, uses task context to resolve the conflicting hunks, stages them, and drives `git rebase --continue` to completion; reports resolved or unresolved, never pushes | — |
| `dev-team:watch-pr` (PR monitor) | Orchestrator | User-started, long-lived per-task agent, spawned with its own fresh `isolation: "worktree"`; repeatedly calls `watch_pr_poll.py` (re-invoking on `"no_change"`) and reacts to whatever condition(s) it returns by spawning `fix-pr` (existing), spawning the developer agent (existing) to run `resolve-rebase-conflict`, running the rebase mechanic, or halting | `watch_pr_poll.py`, Rebase mechanic, `resolve-rebase-conflict`, `fix-pr` (existing), developer agent (existing) |
| `/watch-pr` (new command) | Wrapper | Thin manual-invocation wrapper: spawns `dev-team:watch-pr` via the `Agent` tool with `isolation: "worktree"` — a bare skill invocation from the user's own session would get no isolation at all | `dev-team:watch-pr` |

## Planned Implementation

### Interfaces

- **Spec convention:** `**Depends on:** <ref>[, <ref>...]` (or `— none —`) — a local task-number
  reference (e.g. `Task 3`) until `spec-task-breakdown` step 5 rewrites it to a real task-key,
  one line per task in `## Tasks`, immediately under the task's title.
- **`PipelineContext` frontmatter round-trip:** `save()`/`load()` reworked to read the full
  frontmatter block as a dict, apply only the keys they interpret as typed fields, and write back
  every other key unchanged — so `working_branch`, `base_branch`, `parent_work_item`, and this
  spec's new fields (`base_branch_sha`, `worktree_path`, `worktree_branch`, `watch_worktree_path`,
  `watch_worktree_branch`, `last_seen_review_comment_id`, `last_seen_ci_conclusion`) all survive
  every `dev_team.py` invocation without needing a named dataclass field of their own.
- **Task dependency graph parser:** `parse_task_dependencies(spec_text: str) -> dict[str, list[str]]`
  — maps each task-key to its list of dependency task-keys (real keys only; called after
  `spec-task-breakdown` step 5 has already rewritten local references). Raises a clear error
  (naming the offending task and reference) if any dependency names a task that isn't itself a
  task in the same spec, or if the graph contains a cycle — `spec-task-breakdown` step 5 calls this
  once as a validation pass immediately after rewriting, so either failure is caught at task
  breakdown time, never later.
- **Task readiness checker:** `dependency_status(task_work_item_id: str) -> Literal["ready", "in_progress", "done", "failed", "not_started"]`
  (per-dependency status; `"ready"` once `pr_url` is set, `"done"`/`"failed"` mirror
  `dev_team.py`'s two terminal states) plus
  `is_task_eligible(task_work_item_id: str, dependency_ids: list[str]) -> tuple[Literal["eligible", "waiting", "blocked"], base_branch: str | None]`
  — `"eligible"` once every dependency is `"done"` (`base_branch: None` — no override, let
  `ensure-working-branch` fall back to its own existing default resolution) or every dependency
  but one is `"done"` and that one is `"ready"` (`base_branch`: that one's branch); `"waiting"`
  while two or more dependencies are still short of `"done"`; `"blocked"` if any dependency is
  `"failed"` (a `failed` dependency can never reach `"done"`, so this task can never become
  eligible). `"done"` here means the pipeline reached hand-off, not that the PR actually merged —
  never used for
  merge detection; see the PR event detector below for that. Called internally by
  `concurrent_schedule.py` to refresh cached status and compute eligibility; not invoked directly
  by anything else.
- **`/implement` argument parser:** recognizes, in order: a single `[A-Z]+-\d+` key (existing
  behavior, unchanged); the case-insensitive literal phrase `up to <key>` (inclusive "up to"
  form); otherwise, two or more `[A-Z]+-\d+` keys separated by commas and/or `and` (explicit list
  form, e.g. `ADR-310, ADR-311, and ADR-312`). A single key dispatches to `workflow-orchestrate`;
  either multi-item form dispatches to `concurrent-orchestrate`, passing along which form it was
  (so the scheduler knows whether to expand a closure or use the list as-is).
- **Concurrent scheduler:** `compute_next_batch(target: TargetSpec) -> {"status": Literal["waiting", "complete", "blocked"], "spawn": list[{"task_id": str, "base_branch": str | None}], "blocked_tasks": list[str]}`
  — `TargetSpec` is either an "up to" task id (closure computed on first call) or an explicit task
  list (no closure expansion). Maintains its own data file at
  `~/.dev-team/<repo-slug>/concurrent-<target-slug>.json`, where `<target-slug>` is derived from
  the target itself (the "up to" task's key, or the sorted explicit list joined together) so two
  different targets never collide; running the identical target concurrently from two sessions at
  once is unsupported and undefined. The file is populated once on first invocation (dependency
  graph, each task's cached status/branch, which tasks have already been spawned) and refreshed on
  every call by re-checking, via the Task readiness checker, any task it doesn't yet know is
  `"ready"`. The cap is a **repo-wide** limit, not a per-target one — its whole purpose is
  bounding compute/API load, which two independent `/implement` runs against the same repo would
  both consume — so before computing `spawn`, the script sums the still-active (non-terminal)
  spawn count across *every* `concurrent-<target-slug>.json` file under
  `~/.dev-team/<repo-slug>/`, not just its own, and only fills whatever slots remain free
  repo-wide. The cap's default (3) and override live in `get-project-configuration`'s schema as a
  new `concurrency.max-parallel-tasks` key (`null`/absent falls back to the default 3).
  `base_branch: None` in a `spawn` entry means "no override" — `ensure-working-branch` should just
  run its own existing default resolution (which already finds the feature branch correctly) —
  used whenever a task has no dependencies, or all of them have already merged; a real branch name
  is only returned for the one-dependency-still-open case. Returns `"complete"` once every task in
  the target set has reached a terminal pipeline state (`done`) and `spawn` is empty. Returns
  `"blocked"` — with `blocked_tasks` naming which ones — when every currently-spawned task has
  reached a terminal state (`done` or `failed`) but some not-yet-started task's dependency chain
  includes a task that ended in `failed` (dev_team.py's other terminal state, alongside `done`),
  so it can never become eligible; `concurrent-orchestrate` stops on `"blocked"` rather than
  polling forever. Otherwise `"waiting"`, with `spawn` possibly empty (cap full, or nothing newly
  eligible).
- **Rebase mechanic:** `rebase_onto(working_branch: str, new_base: str, worktree: Path) -> Literal["rebased", "conflict"]`
  — fetches, rebases, force-pushes with lease on success; leaves the rebase in progress and
  returns `"conflict"` without resolving anything on failure.
- **`resolve-rebase-conflict` (new skill, invoked by the developer agent):** given the task's
  brief/spec section for context and a rebase currently in progress with conflicts, reads the
  conflicting hunks, resolves them, stages them (`git add`), and repeats `git rebase --continue`
  until either the rebase completes cleanly or it hits a conflict it can't resolve with confidence.
  Returns `"resolved"` (rebase complete, working tree clean, ready to push) or `"unresolved"`
  (some conflict remains) — never pushes itself. On `"unresolved"`, `dev-team:watch-pr` runs
  `git rebase --abort` to return to a clean pre-rebase state before stopping — never leaves a
  half-finished rebase sitting in the worktree for a human to find. On `"resolved"`,
  `dev-team:watch-pr` itself runs `git push --force-with-lease` directly — `rebase_onto()`'s own
  call already exited when it first detected the conflict, so completion isn't re-routed through
  it; `resolve-rebase-conflict` only gets the rebase itself to a clean, ready-to-push completion.
  Verification is an open implementation-time decision: this is agent-skill prose making judgment
  calls about resolving conflicting hunks, not a pure function — per `component-taxonomy`,
  Testable-tier components like this are verified by "whatever mechanism actually fits," and
  neither existing pattern in this repo fits cleanly (`pytest` suits the plugin's Python scripts;
  there's no Gherkin/E2E harness for a mid-git-operation skill like this). A scripted
  rebase-conflict fixture harness (set up a repo with a deliberate conflict, run the skill, assert
  the final git state) covering at minimum: a single-file, single-hunk conflict resolvable from
  task context; a multi-file conflict, still resolvable from task context; and a conflict
  genuinely requiring information the skill doesn't have, correctly returning `"unresolved"`
  without guessing — implementers may add more scenarios, but these three are the objective bar.
- **PR event detector:** `detect_pr_events(task_work_item_id: str) -> list[Literal["review_comment", "ci_failure", "base_updated", "dependency_merged", "task_merged"]]`
  — compares the PR's actual current state on GitHub (never the context-file `state` field, which
  only reflects hand-off) and in git (base branch tip) against what's recorded in the context file
  (`base_branch_sha`, `last_seen_review_comment_id`, `last_seen_ci_conclusion`), and returns the
  events that fired since the last check — each detected review comment or CI conclusion updates
  its corresponding `last_seen_*` field immediately, so an already-handled item never re-fires.
  When `dependency_merged` fires, it also reports the branch the dependency's PR actually merged
  into — usually the feature branch, but possibly another still-open task's branch — which
  `watch-pr` uses as the new `base_branch` (see the base-re-target decision above).
- **`watch_pr_poll.py`:** `poll(task_work_item_id: str, max_seconds: int = 480) -> list[Literal["review_comment", "ci_failure", "base_updated", "dependency_merged", "task_merged"]] | Literal["no_change"]`
  — loops the PR event detector on a fixed interval (e.g. every 30s) until it reports at least one
  fired event or `max_seconds` elapses, whichever comes first; `max_seconds` defaults comfortably
  under the `Bash` tool's 10-minute timeout cap. Both the sleep function and the elapsed-time check
  are injectable (defaulting to real `time.sleep`/`time.monotonic`), so tests can drive many
  simulated iterations without any real wall-clock delay. Returns the *whole* list `detect_pr_events` fired
  in that check — never just one arbitrarily chosen event — so `dev-team:watch-pr` can react to
  everything that happened in this window; `last_seen_*` fields are only updated for events
  actually included in the returned list, so nothing gets silently marked "seen" without being
  acted on. `dev-team:watch-pr` reacts to every event in the list (rebase-related events first,
  since a stale base can affect how a review comment should be addressed) before calling this
  again; it just calls this again immediately on `"no_change"` — a chain of bounded blocking calls
  covers arbitrarily long gaps between real events without any async monitor.
- **Context-file additions:** `base_branch_sha` (the base tip last rebased onto); `last_seen_review_comment_id`
  / `last_seen_ci_conclusion` (what the PR event detector last saw, so an already-handled review
  comment or CI result never re-fires); `worktree_path` / `worktree_branch` (the *implement-phase*
  worktree, recorded by `concurrent-orchestrate` right after spawning, from the `Agent` tool's
  result; removed by `dev-team:watch-pr` at start, since it uses its own instead — see the PR
  monitor decision); `watch_worktree_path` / `watch_worktree_branch` (`dev-team:watch-pr`'s own
  worktree, recorded by itself at start and removed by itself at halt). All tracked by the PR
  monitor and/or `concurrent-orchestrate` — never by `ensure-working-branch`.

### Key Classes

- **`/implement` (extended)** — gains the argument parser described in Interfaces; a single key's
  behavior is unchanged, either multi-item form now dispatches to `concurrent-orchestrate`.
- **`PipelineContext` (extended, in `dev_team.py`)** — `save()`/`load()` preserve any frontmatter
  key they don't declare as a named field, fixing the pre-existing silent-drop of skill-managed
  fields (`working_branch`, `base_branch`, `parent_work_item`) and making this spec's new fields
  durable across pipeline invocations.
- **`concurrent_schedule.py`** (new script, sibling to `dev_team.py`) — deterministic computation
  only, no spawning and no worktree provisioning (that's the `Agent` tool's job at spawn time, see
  above). Owns the dependency graph, the closure/list computation, each task's cached status, and
  concurrency-cap enforcement — all backed by its own persisted data file (see Interfaces), so
  `concurrent-orchestrate` never has to hold or re-derive any of that itself. Exits with a JSON
  descriptor (`status`, `spawn`) — mirroring exactly how `dev_team.py` already exits with
  descriptors instead of spawning agents itself, since script-spawned processes can't authenticate
  to MCP connectors.
- **`concurrent-orchestrate`** (new skill, sibling to `workflow-orchestrate`) — runs in the
  top-level session, which holds real MCP credentials, as a thin spawn loop with minimal state of
  its own: invoke `concurrent_schedule.py` → on `"blocked"`, report the named `blocked_tasks` and
  the reason to the user and stop (never poll forever); otherwise, for each `{task_id, base_branch}`
  in `spawn`, pre-populate that task's context file with `base_branch` only if it isn't `None`
  (leaving the field unset otherwise, so `ensure-working-branch` falls back to its own default) and
  spawn an `Agent` running `workflow-orchestrate` with `isolation: "worktree"` → once the spawn
  call returns its worktree path/branch, record them into that task's context file → repeat,
  re-invoking the script on an interval and whenever a spawned pipeline finishes, until it reports
  `"complete"` or `"blocked"`.
- **`spec-task-breakdown` (extended)** — step 1 authors `Depends on:` using local task-number
  references (the only identifier that exists before step 4 assigns real keys), best-effort
  inferred from the design the same way titles/descriptions already are, corrected during the
  existing step-2 approval pause; step 5, which already rewrites each task's title into a
  hyperlink once keys are assigned, also rewrites those
  local references into the corresponding real keys at the same time.

- **`ensure-working-branch` (extended)** — gains only the base-branch preference check, and only
  runs it when `base_branch` isn't already set to a real value in the context file (a
  scheduler-spawned task either has one pre-populated, or has the field left unset entirely
  meaning "no override" — both cases fall through to this same existing-default computation; a
  plain single-task `/implement <key>` run also has nothing pre-populated, so it always computes
  independently here). The computation applies the Task readiness checker's same
  `is_task_eligible` rule directly rather than a separate one — a ready dependency's branch for a
  single dependency, the feature branch (via its own existing lookup, unchanged) once every
  dependency but one has merged, or the sole still-open one otherwise. No mid-pipeline rebase
  logic is added here. Also gains the worktree-freshness check (`git stash list` empty, `git
  status --short` clean) as its first action, given the confirmed upstream worktree-collision risk
  above — a failure here is a hard stop, not a recoverable condition.
- **`watch_pr_poll.py`** (new script) — the bounded blocking poll loop described in Interfaces.
- **`resolve-rebase-conflict`** (new skill) — the conflict-resolution contract described in
  Interfaces; invoked by the developer agent, never pushes, reports resolved/unresolved.
- **`dev-team:watch-pr`** (new skill, always spawned with the `Agent` tool's `isolation:
  "worktree"` — either auto-started by `concurrent-orchestrate` at hand-off, or via the new
  `/watch-pr` command as a manual fallback, never invoked bare from a user's own session, which
  would get no isolation at all) — its first actions are the same worktree-freshness check
  described above (hard stop on failure, given the confirmed upstream collision risk), then `git
  fetch origin && git checkout <working_branch>` in its fresh worktree, removing the now-unneeded
  implement-phase worktree (`worktree_path`/`worktree_branch` from the context file), and
  recording its own worktree as `watch_worktree_path`/`watch_worktree_branch`. From there it
  repeatedly calls `watch_pr_poll.py`,
  immediately re-calling it on `"no_change"`. Reacts to every condition in whatever list it
  returns: spawns `fix-pr` (a nested `Agent`, no `isolation` of its own, so it inherits this
  worktree cwd) for a review-comment or CI-failure event; runs the rebase mechanic for a
  base-update or dependency-merge event (re-targeting `base_branch` first in the dependency-merged
  case); on `task_merged`, removes its own worktree/branch and stops. A rebase conflict spawns the
  developer agent (same nested, non-isolated pattern) to run `resolve-rebase-conflict`. On
  `"resolved"`, `dev-team:watch-pr` pushes with `--force-with-lease` itself. On `"unresolved"`, it
  runs `git rebase --abort` to leave a clean worktree, then — since it cannot fall back to
  `AskUserQuestion` (confirmed unavailable to any `Agent`-spawned sub-agent — see the PR monitor
  decision) — stops itself, surfacing the conflict through the harness's background-task
  notification, resumable via `SendMessage` or by restarting `/watch-pr` fresh once resolved.
- **`/watch-pr` (new command)** — the manual entry point, parallel to `/implement`: its entire job
  is spawning `dev-team:watch-pr` via the `Agent` tool with `isolation: "worktree"`, so the manual
  fallback path gets the same isolation guarantee the auto-started path gets from
  `concurrent-orchestrate`.

### Data Flow

1. A human invokes the existing `/implement` command with a phrase naming more than one work
   item — an inclusive "up to" target (e.g. `/implement up to ABC-124`) or an explicit list
   (e.g. `/implement ABC-124, ABC-125, and ABC-127`). `/implement` parses the argument: a single
   key dispatches to `workflow-orchestrate` exactly as it does today; an "up to" phrase or a list
   dispatches to `concurrent-orchestrate` instead. For an explicit list, the scheduler's target
   set is exactly those tasks (respecting dependency order among them) — no closure expansion;
   that only happens for the "up to" form.

2. `concurrent-orchestrate` repeatedly invokes `concurrent_schedule.py`, passing it the target
   (the "up to" id or the explicit list). On its first call for this target, the script parses
   `## Tasks` into a dependency graph, computes the closure (or takes the list as-is), and
   persists both to its own data file, keyed by the target so a different target never collides.
   On every call, it refreshes any task's cached status it doesn't yet know is `"ready"`, computes
   which not-yet-started tasks are now eligible, enforces the concurrency cap itself, and returns
   `{"status": "waiting" | "complete" | "blocked", "spawn": [...], "blocked_tasks": [...]}`.
   `concurrent-orchestrate` itself never computes or holds the dependency graph, eligibility, or
   the cap — it only spawns whatever `spawn` contains, or reports `blocked_tasks` and stops on
   `"blocked"` (see step 5).
3. For each `{task_id, base_branch}` in `spawn`: if `base_branch` isn't `None`, pre-populate that
   task's context file with it (a task with no dependencies, or whose dependencies are all
   already merged, gets `None` — no pre-population at all, so `ensure-working-branch` falls
   through to its own existing default). Spawn a `workflow-orchestrate` run with `isolation:
   "worktree"` — this run proceeds exactly as a single-task pipeline does today, inside its own
   isolated worktree that the `Agent` tool creates. Once the spawn call returns, record its
   worktree path and branch into the task's context file (`worktree_path` / `worktree_branch`) —
   the `Agent` tool only auto-cleans a worktree if the spawned agent made *no* changes, which
   never applies here, so this is what makes the worktree findable for cleanup later (see step 9).
4. Before anything else, `ensure-working-branch` checks the fresh worktree is actually clean
   (`git stash list` empty, `git status --short` clean) — a hard stop if not, given the confirmed
   upstream risk of a stale worktree/branch being silently reused on an ID-prefix collision. Then
   it uses `base_branch` directly if the context file has
   it. If nothing is pre-populated — either the scheduler explicitly said `None` (no dependency
   override needed), or this is a plain single-task `/implement <key>` run that never went through
   the scheduler at all — it computes independently, reading the task's own `Depends on:` entries
   from the spec and calling `is_task_eligible` itself (the exact same rule `concurrent_schedule.py`
   uses), falling back to its pre-existing default feature-branch lookup only when the task
   declares no dependencies at all. This is the only dependency-aware step in the pipeline itself
   — no rebasing happens here or anywhere else mid-pipeline.
5. `concurrent-orchestrate` re-invokes `concurrent_schedule.py` on an interval (to catch a
   dependency reaching "PR open" mid-pipeline, which isn't a terminal event) and whenever a
   spawned pipeline finishes, repeating step 3 for anything newly eligible. If a task's own
   pipeline instead ends in `dev_team.py`'s `failed` terminal state (never reaching hand-off), any
   task depending on it can never become eligible; once every currently-spawned task has also
   reached a terminal state, the script reports `"blocked"` with the specific stuck tasks named,
   and `concurrent-orchestrate` reports that to the user and stops rather than re-invoking
   forever. Otherwise it keeps re-invoking until the script reports `"complete"`.
6. Once a task's pipeline reaches hand-off, `dev-team:watch-pr` is spawned — auto-started by
   `concurrent-orchestrate`, or via the manual `/watch-pr <task-key>` command as a fallback — with
   its own fresh `isolation: "worktree"` either way. It runs the same worktree-freshness check
   first (hard stop if it fails), then checks out the task's `working_branch` in that fresh
   worktree, removes the now-unneeded implement-phase worktree
   (`worktree_path`/`worktree_branch`), and records its own worktree as
   `watch_worktree_path`/`watch_worktree_branch`. From there it calls `watch_pr_poll.py`, which
   blocks internally — sleeping and checking the five conditions on an interval — for up to its
   bounded window, then returns either the list of whatever condition(s) fired or `"no_change"`.
   On `"no_change"`, the monitor just calls it again; this chain of bounded blocking calls covers
   arbitrarily long gaps between real events with no async monitor and no repeated context
   reloading.
7. The monitor reacts to every condition in that list (rebase-related ones first, since a stale
   base can affect how a review comment should be addressed) before polling again. A review
   comment or CI failure spawns `fix-pr` as a nested `Agent` (no `isolation` of its own, so it
   inherits `dev-team:watch-pr`'s worktree cwd). A moved base (new commits, or a merged dependency
   re-targeting the base to wherever its PR actually merged — usually the feature branch, but
   possibly another still-open task's branch) runs the rebase mechanic and force-pushes the
   updated working branch.
8. A rebase conflict is never resolved by guessing: the monitor spawns the developer agent (the
   same nested, non-isolated pattern) to run `resolve-rebase-conflict` — using full task context
   to read and resolve the actual conflicting hunks, beyond what git's own mechanical merge
   strategies can do unassisted, then driving `git rebase --continue` to completion without
   pushing. On `"resolved"`, `dev-team:watch-pr` pushes with `--force-with-lease` itself. On
   `"unresolved"`, it runs `git rebase --abort` first, leaving a clean worktree rather than a
   half-finished rebase — then, since `AskUserQuestion` isn't available to any `Agent`-spawned
   sub-agent, it stops itself instead of asking, surfacing the conflict through the harness's
   background-task notification. A human resolves it and resumes the same agent via `SendMessage`,
   or restarts via `/watch-pr` fresh.
9. The task's own PR merging removes `dev-team:watch-pr`'s own worktree and branch
   (`watch_worktree_path`/`watch_worktree_branch`) and halts its monitor.

## Related Features

| Feature | Scope |
|------|-------|
| (this feature) | Same-spec task dependencies, concurrent scheduling, and the rebase mechanic that keeps a dependent branch in sync with its dependency |
| [ADR-315: Cross-spec/cross-epic task dependencies](https://jodasoft.atlassian.net/browse/ADR-315) | A task depending on a task-work-item tracked in an entirely different spec or epic — out of scope here, deferred to a future pass |

## Open Questions

None outstanding.

## Tasks

> **Legend:** 🤖 = agent task · 🧑 = human operator task

---

### [ADR-335: `PipelineContext` frontmatter round-trip](https://jodasoft.atlassian.net/browse/ADR-335) 🤖

Fixes a pre-existing bug in `dev_team.py`'s `PipelineContext.save()`/`load()` that this feature's
mechanism depends on being fixed: neither round-trips a frontmatter field it doesn't itself
declare, silently dropping `working_branch`/`base_branch`/`parent_work_item` today and every new
field this spec adds. No dependencies — everything else that persists a new context-file field
builds on this.

- [ ] `PipelineContext.save()`/`load()` reworked to read/write the full frontmatter block as a
  dict, applying only the keys they interpret as typed fields and preserving every other key
  unchanged
- [ ] `working_branch`, `base_branch`, and `parent_work_item` (already written via `Edit` per
  `use-context-file`, never through `PipelineContext`) survive a `dev_team.py` invocation unchanged
- [ ] Given a context file with a frontmatter field `PipelineContext` doesn't declare as a named
  field, when `dev_team.py` runs and calls `ctx.save()`, then that field's value is preserved
  unchanged in the rewritten file
- [ ] Given `base_branch` is pre-populated before a task's `workflow-orchestrate` run starts, when
  the pipeline reaches `ensure-working-branch`, then `base_branch` still has its pre-populated
  value
- [ ] Unit tests: an unknown frontmatter key survives a load/save cycle unchanged; every existing
  known dataclass field still round-trips exactly as before

---

### [ADR-307: Dependency declaration and graph parsing](https://jodasoft.atlassian.net/browse/ADR-307) 🤖

Extends `spec-task-breakdown` with the `Depends on:` field convention (local task-number
references, rewritten to real keys in step 5) and adds the script that parses a spec's `## Tasks`
into a dependency graph. No other task in this breakdown can be tested end-to-end without this.

- [ ] `spec-task-breakdown` step 1 authors `**Depends on:** <ref>[, <ref>...]` (or `— none —`)
  under each task's title, best-effort inferred from the design the same way titles/descriptions
  already are
- [ ] `spec-task-breakdown` step 5 rewrites local task-number references into real task-work-item
  keys at the same time it rewrites titles into hyperlinks
- [ ] `parse_task_dependencies(spec_text: str) -> dict[str, list[str]]` implemented, mapping each
  real task-key to its list of dependency task-keys
- [ ] Given a spec with tasks declaring `Depends on:` entries via local task numbers, when
  `spec-task-breakdown` completes, then every `Depends on:` line contains real task-work-item keys
- [ ] Rejects, with a clear error naming the offending task and reference, a `Depends on:` entry
  that names a task not present in the spec (dangling reference) or a dependency graph containing
  a cycle
- [ ] Unit tests for `parse_task_dependencies`: no dependencies, single dependency, multiple
  dependencies, a task with `— none —`, a dangling reference, and a two/three-task cycle

---

### [ADR-308: Task readiness checker and base-branch resolver](https://jodasoft.atlassian.net/browse/ADR-308) 🤖

_Depends on [ADR-307](https://jodasoft.atlassian.net/browse/ADR-307), [ADR-335](https://jodasoft.atlassian.net/browse/ADR-335)._ Adds the single- and multi-dependency eligibility rule, and extends
`ensure-working-branch` to apply it (or use a pre-populated `base_branch`) plus the
worktree-freshness safety check.

- [ ] `dependency_status(task_work_item_id) -> Literal["ready", "in_progress", "done", "failed", "not_started"]`
  reads a task's context file (`pr_url`, `state`)
- [ ] `is_task_eligible(task_work_item_id, dependency_ids) -> tuple[Literal["eligible", "waiting", "blocked"], base_branch: str | None]`
  implements the rule: `"eligible"`/`None` once every dependency is `"done"`; `"eligible"`/`<branch>`
  once every dependency but one is `"done"` and that one is `"ready"`; `"waiting"` with two or
  more short of `"done"`; `"blocked"` if any dependency is `"failed"`
- [ ] `ensure-working-branch` uses a pre-populated `base_branch` from the context file directly
  when present; otherwise calls `is_task_eligible` against the task's own `Depends on:` entries,
  falling back to the pre-existing feature-branch lookup only when the task has no dependencies
- [ ] `ensure-working-branch` runs the worktree-freshness check (`git stash list` empty, `git
  status --short` clean) as its first action; treats a failure as a hard stop
- [ ] Unit tests for `is_task_eligible`: single dependency ready/not-ready, all dependencies done,
  all-but-one done, two-plus short of done, one dependency failed
- [ ] Given a task with one dependency whose PR is open, when `ensure-working-branch` runs with no
  pre-populated `base_branch`, then it selects that dependency's branch
- [ ] Given a task with two dependencies both already merged, when `ensure-working-branch` runs,
  then it falls back to the existing feature-branch lookup

---

### [ADR-309: Rebase mechanic](https://jodasoft.atlassian.net/browse/ADR-309) 🤖

Standalone git operation: fetch, rebase a working branch onto an updated base, force-push with
lease on success, leave the rebase in progress and report on conflict. No dependencies — the
first component every later task in this breakdown that touches rebasing builds on.

- [ ] `rebase_onto(working_branch, new_base, worktree) -> Literal["rebased", "conflict"]`
  implemented: fetches, rebases, force-pushes with lease on success
- [ ] On conflict, leaves the rebase in progress untouched — no automatic resolution attempted
  here
- [ ] Given a working branch cleanly rebasable onto a new base, when `rebase_onto` runs, then it
  returns `"rebased"` and the branch is force-pushed with lease
- [ ] Given a working branch with a genuine conflicting change against the new base, when
  `rebase_onto` runs, then it returns `"conflict"` and the rebase is left in progress
- [ ] Unit/integration tests covering both outcomes against fixture repos

---

### [ADR-310: Concurrent scheduler, `/implement` argument parser, and `concurrent-orchestrate`](https://jodasoft.atlassian.net/browse/ADR-310) 🤖

_Depends on [ADR-307](https://jodasoft.atlassian.net/browse/ADR-307), [ADR-308](https://jodasoft.atlassian.net/browse/ADR-308), [ADR-335](https://jodasoft.atlassian.net/browse/ADR-335)._ These three ship together — the script computes everything
deterministically and exits with a descriptor; the orchestrator only spawns what it's told;
`/implement`'s parser is what makes either reachable. None is independently useful without the
others.

- [ ] `/implement` argument parser recognizes a single key (unchanged), the case-insensitive
  phrase `up to <key>`, or an explicit comma/"and"-separated list of two or more keys
- [ ] A single key still dispatches to `workflow-orchestrate` unchanged; either multi-item form
  dispatches to `concurrent-orchestrate`
- [ ] `concurrent_schedule.py`: `compute_next_batch(target) -> {"status": ..., "spawn": [...], "blocked_tasks": [...]}`
  — computes the target's dependency closure (`"up to"` form) or takes the list as-is (no
  expansion), persists to `~/.dev-team/<repo-slug>/concurrent-<target-slug>.json`
- [ ] For an explicit list, validates upfront that every listed task's dependencies are either in
  the list or already `done`; rejects immediately with a clear error otherwise
- [ ] Enforces the concurrency cap **repo-wide** (summing active spawns across every
  `concurrent-<target-slug>.json` under the repo-slug directory, not just its own file)
- [ ] `get-project-configuration` schema gains `concurrency.max-parallel-tasks` (default 3)
- [ ] Returns `"complete"` once every task in the target set is `done` and `spawn` is empty;
  returns `"blocked"` (naming `blocked_tasks`) once every spawned task is terminal but some
  not-yet-started task depends on a `failed` one
- [ ] `concurrent-orchestrate`: invokes the script, pre-populates `base_branch` on a spawned
  task's context file only when it isn't `None`, spawns `workflow-orchestrate` with `isolation:
  "worktree"`, records the returned worktree path/branch, re-invokes on an interval and on spawned
  pipelines finishing, stops and reports on `"blocked"` instead of polling forever
- [ ] Given `/implement up to ADR-X` against a spec with a linear dependency chain, when run, then
  each task starts only once its dependency situation makes it eligible, and the run stops once
  the whole closure reaches a terminal state
- [ ] Given an explicit list where a listed task depends on something outside the list and not yet
  `done`, when `concurrent-orchestrate` starts, then it rejects the request immediately
- [ ] Unit tests for `compute_next_batch`: closure computation, list validation, cap enforcement
  (including repo-wide with multiple target files), `"blocked"` detection

---

### [ADR-311: PR event detector and `watch_pr_poll.py`](https://jodasoft.atlassian.net/browse/ADR-311) 🤖

_Depends on [ADR-308](https://jodasoft.atlassian.net/browse/ADR-308), [ADR-335](https://jodasoft.atlassian.net/browse/ADR-335)._ The detection half of the post-hand-off monitor — determines what changed on
a task's PR, independent of how the monitor reacts to it.

- [ ] `detect_pr_events(task_work_item_id) -> list[Literal["review_comment", "ci_failure", "base_updated", "dependency_merged", "task_merged"]]`
  compares GitHub/git state against `base_branch_sha`, `last_seen_review_comment_id`,
  `last_seen_ci_conclusion`; updates those fields only for events it actually returns
- [ ] `dependency_merged` also reports the branch the dependency's PR actually merged into
- [ ] `watch_pr_poll.py`: `poll(task_work_item_id, max_seconds=480) -> list[...] | Literal["no_change"]`
  loops the detector on a fixed interval, returns the full fired list or `"no_change"` when the
  bounded window elapses with nothing new
- [ ] Given a dependency's PR merging into a still-open task's branch (stacked/out-of-order case),
  when `detect_pr_events` runs, then `dependency_merged` fires with that actual merge target, not
  a hardcoded feature branch
- [ ] Given two conditions firing in the same window (e.g. a review comment and a base update),
  when `poll` returns, then both are included in the returned list
- [ ] `poll`'s own loop/timeout mechanics are unit-tested with an injectable sleep/clock (no real
  wall-clock sleeps): returns as soon as the first event fires without waiting out the rest of the
  window, and returns `"no_change"` once the injected clock reports `max_seconds` elapsed with
  nothing fired
- [ ] Unit tests for `detect_pr_events` covering each of the five event types firing individually,
  multiple at once, and none (no false re-fires on an already-seen item)

---

### [ADR-312: `resolve-rebase-conflict` skill](https://jodasoft.atlassian.net/browse/ADR-312) 🤖

_Depends on [ADR-309](https://jodasoft.atlassian.net/browse/ADR-309)._ Given a rebase left in progress with conflicts, resolves them using task
context and drives the rebase to completion — never pushes.

- [ ] Given the task's brief/spec section and a rebase in progress with conflicts, reads the
  conflicting hunks, resolves them, stages them, and repeats `git rebase --continue`
- [ ] Returns `"resolved"` (rebase complete, working tree clean) or `"unresolved"` (some conflict
  remains) — never runs `git push` itself
- [ ] Given a rebase conflict resolvable from task context alone, when the skill runs, then it
  returns `"resolved"` and `git status` shows no rebase in progress
- [ ] Given a conflict genuinely requiring information the skill doesn't have, when the skill
  runs, then it returns `"unresolved"` without guessing
- [ ] A scripted fixture-scenario harness (per the taxonomy's "whatever mechanism fits" for
  agent-skill-prose Testable components) covering at minimum: (1) a single-file, single-hunk
  conflict resolvable from task context alone; (2) a multi-file conflict, still resolvable from
  task context; (3) a conflict genuinely requiring information the skill doesn't have, correctly
  returning `"unresolved"` without guessing — implementers may add more scenarios, but these three
  are the objective bar for this criterion

---

### [ADR-313: `dev-team:watch-pr` and `/watch-pr`](https://jodasoft.atlassian.net/browse/ADR-313) 🤖

_Depends on [ADR-309](https://jodasoft.atlassian.net/browse/ADR-309), [ADR-311](https://jodasoft.atlassian.net/browse/ADR-311), [ADR-312](https://jodasoft.atlassian.net/browse/ADR-312), [ADR-335](https://jodasoft.atlassian.net/browse/ADR-335)._ The full post-hand-off PR monitor: owns the entire
lifecycle from hand-off to merge, and the manual entry point that gives it the same isolation
guarantee as the auto-started path.

- [ ] `dev-team:watch-pr` is spawned with `isolation: "worktree"` (fresh, not a reuse of the
  implement-phase worktree); runs the worktree-freshness check first, then `git fetch origin &&
  git checkout <working_branch>`
- [ ] Removes the now-unneeded implement-phase worktree/branch; records its own as
  `watch_worktree_path`/`watch_worktree_branch`
- [ ] `concurrent-orchestrate` auto-starts one as a local background `Agent` the moment a task's
  `workflow-orchestrate` run reaches hand-off
- [ ] `/watch-pr <task-key>` command spawns `dev-team:watch-pr` via the `Agent` tool with
  `isolation: "worktree"`, as the manual fallback
- [ ] Repeatedly calls `watch_pr_poll.py`, reacting to every event in the returned list
  (rebase-related events first): spawns `fix-pr` (nested, no isolation) for review-comment/CI
  events; runs the rebase mechanic for base-update/dependency-merge events, re-targeting
  `base_branch` first in the dependency-merged case
- [ ] On a rebase conflict, spawns the developer agent (nested, no isolation) to run
  `resolve-rebase-conflict`; on `"resolved"`, pushes with `--force-with-lease` itself; on
  `"unresolved"`, runs `git rebase --abort` then stops itself (no `AskUserQuestion` fallback),
  surfacing the conflict via the harness's background-task notification
- [ ] On `task_merged`, removes its own worktree/branch and halts
- [ ] Given a task's PR receiving a human review comment after hand-off, when its monitor is
  running, then `fix-pr` addresses it without any other task's monitor being affected
- [ ] Given a dependency merging while a dependent's monitor is running, when the monitor next
  polls, then it rebases onto the actual merge target and pushes
- [ ] Given a rebase conflict `resolve-rebase-conflict` can't resolve, when the monitor detects
  `"unresolved"`, then the worktree is left clean (no rebase in progress) and the monitor has
  stopped, resumable via `SendMessage` or by restarting `/watch-pr`

---

### [ADR-314: Remove todo-log/`TodoWrite`-mirroring plumbing](https://jodasoft.atlassian.net/browse/ADR-314) 🤖

Unrelated to the dependency/rebase mechanics above; can run independently of every other task in
this breakdown.

- [ ] Todo-log-tailing and `TodoWrite`-mirroring mechanism removed from `workflow-orchestrate`
  (its `SKILL.md` todo-log-tailing steps and `scripts/get_todo_log_path.py`) and `workflow-worker`
  (its `SKILL.md` log-redirection step and `scripts/append_todo_log.py`)
- [ ] Per-agent "maintain a to-do list" instruction removed from `agents/developer.md`,
  `agents/researcher.md`, and `agents/reviewer.md`
- [ ] Given a `workflow-orchestrate` run today mirrors sub-agent todo updates into the visible
  task list, when this task is complete, then no such mirroring occurs and no todo-log file is
  created

---

### [ADR-315: Cross-spec/cross-epic task dependencies](https://jodasoft.atlassian.net/browse/ADR-315)

A task depending on a task-work-item tracked in an entirely different spec or epic — out of scope
in this feature, deferred to a future pass.

## Related Docs

- `_doc_Projects.md` — repository layout and plugin structure
- `_spec_AgentOrchestration.md` — the current step-machine pipeline this feature schedules
  concurrently and extends
- `_spec_TddForImplementation.md` — flagged per-component worktree isolation as deferred future
  work; this spec picks that up at the task-pipeline level instead
- [anthropics/claude-code#51596](https://github.com/anthropics/claude-code/issues/51596),
  [#37873](https://github.com/anthropics/claude-code/issues/37873),
  [#41010](https://github.com/anthropics/claude-code/issues/41010) — independently reported,
  currently-unresolved upstream bugs where `isolation: "worktree"` can silently reuse a stale
  worktree/branch on an agentId-prefix collision; motivated the worktree-freshness check in the
  "Concurrent pipelines require per-task-work-item git worktrees" decision
