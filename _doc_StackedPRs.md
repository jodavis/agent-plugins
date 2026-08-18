Summary: GitHub-native `gh stack`-based concurrent development pipeline — epic bootstrap, lazy
recursive branch registration, stack-scoped PR submission, and one epic-wide monitor — that
replaces ADR-296's dependency-graph/rebase/monitor machinery end to end.

# Stacked PRs for Concurrent Development

## Overview

This subsystem lets several dependent task-work-items under one epic be implemented concurrently,
each on its own branch, PR'd and kept in sync against one another via GitHub's native `gh stack`
CLI extension (`github/gh-stack`) rather than this repo's own bespoke dependency-graph/rebase/
monitor code. An epic's tasks are serialized into a single linear stack of branches, each based on
the one before it; a task starts as soon as its real dependencies are "ready" (their PR is open,
not necessarily merged); its PR is submitted as part of the whole stack; and one long-lived
monitor per epic keeps every PR in that stack in sync — reacting to review comments, CI failures,
rebase conflicts cascading down the stack, and merges — until the whole stack has landed.

This doc is the first architecture-level description of the whole concurrent-development pipeline
(bootstrap → registration → PR submission → epic-wide monitoring), not a thin delta on top of a
prior doc — `_spec_ConcurrentDevelopment.md` (ADR-296), the mechanism this feature replaces, was
never followed up with its own `_doc_ConcurrentDevelopment.md`. Where relevant, sections below
note what ADR-296 used to do and why it was replaced, so this doc stands on its own for a reader
with no other context.

See `_spec_StackedPRs.md` for the full design rationale, Open Questions, and per-task breakdown,
and `_findings_GhStackSpike.md` (ADR-370) for the feasibility spike that confirmed `gh stack`'s
actual behavior — several of the decisions below exist specifically because the spike refuted or
refined an assumption the spec started with.

## Responsibilities & Boundaries

- **Owns:** anchoring an epic's `gh stack` to its feature branch (`ensure-feature-branch`);
  computing and validating an epic's linear stack order from its spec (`validate_stack_order` in
  `task_dependencies.py`); registering a task's branch into that stack, including lazily
  backfilling any not-yet-started ancestor with an empty placeholder branch
  (`ensure-working-branch`'s `stack_registration.py`); real-dependency readiness independent of
  stack position (`is_task_eligible` in `task_readiness.py`); submitting PRs through the stack
  rather than a manually threaded base branch (`create-pr-from-context`); expanding an "up to"
  target into every task from the start of the epic's document order through the target
  (`concurrent_schedule.py`'s `compute_next_batch`); and the single epic-wide post-hand-off
  monitor that reacts to review comments, CI failures, rebase conflicts, and merges across the
  whole stack (`monitor-stack`, `stack_pr_poll.py`, `detect_next_stack_event.py`).
- **Does not own:** the `gh stack` CLI itself, or any of its internal state/behavior — that's
  upstream, days-old public-preview GitHub tooling (see Known Design Decisions below); resolving
  the git-level content of a rebase conflict once one is left in progress — that's
  `resolve-rebase-conflict`, unchanged by this feature (see Key Design Decisions); the
  spawn/scheduling loop that decides which tasks are eligible to spawn concurrently — that's
  `concurrent-orchestrate`'s own prose, which only reads this subsystem's outputs and never
  computes stack membership or eligibility itself.
- **Integrates with:** `ensure-working-branch` (branch registration happens as part of the normal
  pre-implementation branch-setup step every task already runs), `concurrent-orchestrate` (spawns
  one `monitor-stack` per epic, the moment the first task in that epic's target set reaches
  hand-off, and invokes `ensure-feature-branch` in-session on a `"bootstrap_needed"` result since
  it holds real MCP/`gh` credentials that a bare script does not), `create-pr-from-context`
  (submits through the stack instead of a manually-passed `base`), and `PipelineContext`'s
  `added_to_stack` field (a named frontmatter field, not a passthrough extra — see
  `pipeline_context.py` line 34) that records whether a task's branch registration has completed.
- **Isolation boundary:** `work-with-stacked-prs`/`gh_stack.py` is the sole owner of every direct
  `gh stack` CLI invocation across this whole feature; every other skill and script references
  its named operations rather than shelling out to `gh stack` itself. This is deliberate risk
  mitigation for a days-old public-preview GitHub CLI feature — one place to change if the CLI's
  behavior does.

## Key Design Decisions

- **`gh stack` fully replaces ADR-296's dependency-graph/rebase/monitor machinery, rather than
  layering on top of it.** `ensure-working-branch` no longer computes or searches for a base
  branch on its own; it registers a task's branch into a GitHub stack via the `add` operation.
  ADR-296's `rebase_mechanic.py`, `watch_pr_poll.py`, the `monitor-pr` skill, `/watch-pr`, and the
  base-branch-selection half of `is_task_eligible` are retired outright — confirmed absent from
  the repo, not merely deprecated.
- **An epic's dependency DAG is serialized into one linear stack using the spec's own task
  document order, validated rather than computed.** `validate_stack_order` (in
  `task_dependencies.py`, extending the existing `parse_task_dependencies`) confirms every task's
  declared dependencies appear earlier in the spec's `## Tasks` section than the task itself, then
  returns the task keys in that document order — the order the spec's author already committed to
  when writing the task breakdown, not a graph the system computes independently.
- **`ensure-feature-branch` bootstraps an epic's own trunk.** It creates and pushes the epic's
  feature branch from `main` if missing, commits and opens a PR for the epic's spec file against
  that branch if it isn't already committed there, and anchors a `gh stack` to that branch via
  `init` — every step check-before-act, so the whole skill is safely re-runnable. `init` against
  an already-anchored trunk is a hard error (exit code 5), confirmed by ADR-370's spike, not an
  idempotent no-op — this is exactly why every step here checks first rather than relying on
  `init` itself being safe to repeat.
- **A task's working branch is always a new, distinct ref, never the feature branch itself**
  (closes GitHub issue #126). `ensure-working-branch`'s `stack_registration.py` module runs a
  `verify_branch_identity` guardrail immediately after registering a task's own branch, confirming
  `HEAD` is genuinely that branch and not the feature branch — a non-zero exit here is a hard stop.
- **Task PRs are submitted via the stack's `submit` operation, never a manually threaded
  `base_branch` value** (closes GitHub issue #129). `create-pr-from-context` checks the context
  file's `added_to_stack` field and, if true, runs `submit` instead of constructing an explicit
  `base` — `gh stack` already knows the correct base from the `add` call made at registration
  time, which is the single source of truth. ADR-370's spike confirmed `submit` is always scoped
  to the entire active stack (no per-branch flag exists) but only *creates* PRs for entries that
  don't already have one, so resubmitting the whole stack is safe and idempotent for already-PR'd
  lower entries.
- **Branch registration is lazy, recursive, and decoupled from real-dependency readiness.**
  `ensure-working-branch`'s `compute_registration_plan()` (in `stack_registration.py`) backfills an
  empty placeholder branch for any not-yet-registered ancestor task before registering the
  requested task itself, pushing each one in turn and writing `added_to_stack: true` only after
  each push succeeds — so a task can register into its correct stack position even if an earlier,
  not-yet-started task in the same epic has never run.
- **Implementation only starts once every real dependency has reached "ready" (its PR is open) —
  never an actual merge.** `is_task_eligible` (`task_readiness.py`) was simplified accordingly:
  its return value no longer carries a `base_branch`, since stack position and real-dependency
  readiness are now fully decoupled concerns.
- **"Up to Task X" means "Task X and everything before it" in the epic's document order, not just
  its dependency closure.** `concurrent_schedule.py`'s `compute_next_batch` expands an `up_to`
  target using `validate_stack_order`'s document order — a linear stack means an earlier,
  unrelated task still needs implementing regardless of whether the target actually depends on
  it.
- **One `monitor-stack` monitor per epic replaces the per-task `monitor-pr` fleet.** It is
  auto-started by `concurrent-orchestrate` the moment the first task in an epic's target set
  reaches hand-off (not once per task), and polls the whole stack via `stack_pr_poll.py`, reacting
  to exactly one outcome per call: a conflict routes to `resolve-rebase-conflict` via the developer
  agent, an actionable review-comment/CI-failure event spawns `fix-pr` against the already-checked-
  out branch `stack_pr_poll.py` names, and every branch in the stack merging halts the monitor.
- **`gh stack` state is not visible across git worktrees** — ADR-370's highest-risk finding, a
  confirmed refutation, not a theoretical concern. `gh stack`'s local stack-membership state lives
  in the worktree-private `.git/worktrees/<name>/gh-stack` file, not the shared common git
  directory, so a second worktree sees a false "not part of a stack" result even for a branch
  genuinely registered from another worktree of the same repo. Every `gh stack` operation for one
  feature's stack — task-branch registration and the ongoing `sync`/`view` polling in
  `monitor-stack` — must run from one shared worktree per feature, never a task's own per-task
  worktree. `work-with-stacked-prs/SKILL.md` documents this explicitly as a structural constraint,
  not a corner case.
- **Rebase/sync conflicts still route through the existing `resolve-rebase-conflict` skill for the
  git-level mechanics of the currently-conflicted branch.** ADR-370's spike confirmed its plain-git
  contract (find `.git/rebase-merge`, resolve conflict markers, `git rebase --continue`) works
  unchanged when the conflict is reached via `gh stack`'s own cascading rebase.
  `resolve-rebase-conflict/SKILL.md` was updated to name `dev-team:monitor-stack`, not the retired
  `monitor-pr`, as its caller.
- **The multi-branch rebase cascade is explicitly resumed after a resolved conflict.** ADR-370's
  spike found that after `resolve-rebase-conflict` finishes the currently-conflicted branch, a
  plain `git rebase --continue` only completes that one branch's own rebase; downstream branches
  in the stack are left un-rebased until a `gh stack rebase --continue` call specifically resumes
  gh-stack's own cascade — a fresh `sync` call alone is not sufficient. `monitor-stack`'s
  `"resolved"` path calls `stack_rebase_continue.py` (which wraps `gh_stack.rebase_continue()`,
  i.e. `gh stack rebase --continue`) before returning to the poll loop, looping back into another
  `resolve-rebase-conflict` round if that call surfaces a further conflict higher in the stack.
  Closed [issue #179](https://github.com/jodavis/agent-plugins/issues/179).
- **`monitor-stack` is script-driven and whole-stack, not epic-id-scoped.** `stack_pr_poll.py`
  (`plugins/dev-team/skills/workflow-orchestrate/scripts/stack_pr_poll.py`) takes only an optional
  `max_seconds` argument — no epic id — and its `poll()` function returns `"stack_complete"` on
  completion; it operates on whatever stack is anchored in the worktree it's run from, which is
  why `monitor-stack` must run from the epic's own shared worktree (see the cross-worktree
  decision above). `monitor-stack/SKILL.md`'s own prose has not yet been updated to match this
  exactly (see [issue #180](https://github.com/jodavis/agent-plugins/issues/180)); this doc
  describes the actually-shipped script behavior.

## Key Classes / Interfaces

- **`work-with-stacked-prs`/`gh_stack.py`** — sole owner of every `gh stack` CLI invocation.
  Exposes seven operations as plain Python functions (`init`, `add`, `submit`, `sync`, `view`,
  `merge`, `rebase_continue`), each returning `("ok" | "error", detail)` (`view`'s `detail` is the
  parsed `--json` dict; the other six return stdout/stderr text), plus
  `check_gh_stack_extension_installed()` for the extension preflight.
- **`ensure-feature-branch(<feature-work-item-id>)`** — bootstraps an epic's feature branch, spec
  PR, and anchored stack; every step check-before-act.
- **`ensure-working-branch`'s `stack_registration.py`** — `compute_registration_plan()` (lazy
  recursive backfill plan), `is_added_to_stack()`, and `verify_branch_identity()` (the #126
  guardrail).
- **`create-pr-from-context`'s `pr_from_context.py`** — `should_submit_via_stack()` and
  `resolve_submitted_pr_url()`, the decision logic behind the #129 fix.
- **`task_dependencies.py`'s `validate_stack_order(spec_text) -> list[str]`** — extends
  `parse_task_dependencies` with the stack-order check; returns task keys in document order.
- **`task_readiness.py`'s `is_task_eligible(task_id, dependency_ids) -> "eligible" | "waiting" |
  "blocked"`** — real-dependency readiness, decoupled from stack position; no longer returns a
  `base_branch`.
- **`detect_next_stack_event.py`'s `detect_next_stack_event() -> dict | None`** — scans a stack's
  branches (via `gh_stack.view()`) and returns the first actionable event
  (`review_comment`/`ci_failure`/`task_merged`) across the whole stack, or `None`.
- **`stack_pr_poll.py`'s `poll(max_seconds=480, ...) -> "conflict" | "stack_complete" |
  "no_change" | dict`** — bounded polling loop over `gh stack sync` and
  `detect_next_stack_event()`; runs `sync` first each iteration, then checks for a rebase in
  progress (`"conflict"`) before consulting the detector.
- **`stack_rebase_continue.py`'s `rebase_continue() -> "conflict" | "ok"`** — one-shot follow-up
  `monitor-stack` calls after `resolve-rebase-conflict` reports `"resolved"`; runs
  `gh_stack.rebase_continue()` (`gh stack rebase --continue`) to resume the cascade across
  downstream branches, and reports whether it hit a further conflict or reached a clean state.
- **`concurrent_schedule.py`'s `compute_next_batch(target) -> dict`** — computes the next batch of
  tasks to spawn for an "up to" or explicit-list target, including a live check for whether the
  epic's feature branch is bootstrapped yet (`"bootstrap_needed"`) and the repo-wide concurrency
  cap.
- **`monitor-stack`** — the epic-wide, long-lived post-hand-off monitor; polls via
  `stack_pr_poll.py` and reacts to exactly one outcome per call.
- **`/watch-stack <epic-key>`** — manual fallback that spawns `monitor-stack` in its own isolated
  worktree, for when `concurrent-orchestrate`'s auto-start never happened.
- **`PipelineContext.added_to_stack`** — a named boolean frontmatter field (`pipeline_context.py`
  line 34), `true` once a task's branch has been successfully registered and pushed into the
  stack.

## Data Flow

1. **Epic bootstrap.** The first task under an epic to reach `ensure-working-branch` (either
   directly, in the single-task path, or via `concurrent-orchestrate`'s own
   `"bootstrap_needed"`-triggered call) invokes `ensure-feature-branch`: it creates the epic's
   feature branch from `main` if missing, commits/PRs the epic's spec file against that branch if
   needed, and anchors a `gh stack` to it via `init`.
2. **Task branch registration.** `ensure-working-branch` computes the task's working-branch name,
   then registers it into the stack: `stack_registration.py`'s `compute_registration_plan()`
   determines which not-yet-registered ancestor tasks (in stack order) need an empty placeholder
   branch created first, backfills each one via the `add` operation and pushes it, then registers
   this task's own branch the same way. The `verify_branch_identity` guardrail confirms `HEAD` is
   genuinely the new branch, not the feature branch, before `added_to_stack: true` is written.
3. **Eligibility and scheduling.** Independently of stack position, `is_task_eligible` gates when
   a task's implementation actually starts: once every declared dependency has reached "ready" (PR
   open) or "done". `concurrent_schedule.py`'s `compute_next_batch` uses this alongside
   `validate_stack_order`'s document order to decide which tasks are eligible to spawn next, up to
   the configured concurrency cap.
4. **PR submission.** Once a task's implementation is complete, `create-pr-from-context` checks
   `added_to_stack`; if true, it runs the stack's `submit` operation (scoped to the whole stack,
   but idempotent for already-PR'd lower entries) instead of constructing an explicit base, then
   resolves the task's own new PR URL via a direct `gh pr list` lookup.
5. **Epic-wide monitoring.** The moment the first task in an epic's target set reaches hand-off,
   `concurrent-orchestrate` auto-starts one `monitor-stack` session for that epic (or a human
   starts it manually via `/watch-stack`). It runs from the epic's own shared worktree and loops
   on `stack_pr_poll.py`: each call runs `sync` first, then checks for a rebase conflict, then
   consults `detect_next_stack_event` for the first review-comment/CI-failure/merge event across
   the whole stack.
6. **Reacting to poll outcomes.** A `{"task_work_item_id", "event"}` result spawns `fix-pr` against
   that task's already-checked-out branch. A `"conflict"` result hands off to the developer agent
   running `resolve-rebase-conflict` against the currently-conflicted branch; on `"resolved"`, the
   monitor calls `stack_rebase_continue.py` to resume gh-stack's own cascade across any downstream
   branches, looping back into another `resolve-rebase-conflict` round if that call surfaces a
   further conflict higher in the stack, or returning to polling once it reports a clean state; on
   `"unresolved"`, the monitor aborts the rebase and halts entirely, since one stuck task blocks
   every later task in the stack regardless of how many monitor processes exist.
7. **Completion.** Once every branch in the stack has merged, `stack_pr_poll.py` reports
   `"stack_complete"`, and `monitor-stack` removes its own worktree/branch and stops.
