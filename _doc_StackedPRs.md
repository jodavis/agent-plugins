Summary: GitHub-native `gh stack`-based concurrent development pipeline — epic bootstrap,
deferred post-signoff stack registration, and one epic-wide monitor — that replaces ADR-296's
dependency-graph/rebase/monitor machinery end to end.

# Stacked PRs for Concurrent Development

## Overview

This subsystem lets several dependent task-work-items under one epic be implemented concurrently,
each on its own branch, PR'd and kept in sync against one another via GitHub's native `gh stack`
CLI extension (`github/gh-stack`) rather than this repo's own bespoke dependency-graph/rebase/
monitor code. An epic's tasks form a single linear stack of branches, each based on the one before
it; a task starts as soon as its real dependencies are fully "done" (signed off *and* linked into
the stack); its PR is opened directly against its own base branch, then registered into the
epic's `gh stack` once its own sign-off approves (`add-to-pr-stack`); and one long-lived monitor
per epic keeps every PR in that stack in sync — reacting to review comments, CI failures, rebase
conflicts cascading down the stack, and merges — until the whole stack has landed.

Registration is deliberately deferred this late, rather than done eagerly when a task starts:
`gh stack`'s own local tracking state is worktree-private (see Key Design Decisions below), and a
task's own implementation runs in its own freshly spawned per-task worktree — registering there
would race against `monitor-stack`'s shared-worktree view of the same stack. `add-to-pr-stack`
sidesteps this entirely by using `gh stack link`, the one `gh stack` operation that doesn't need
local tracking state at all.

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

- **Owns:** bootstrapping an epic's spec branch and committed spec (`write-dev-spec` step 1.5);
  computing and validating an epic's linear stack order from its spec (`validate_stack_order` in
  `task_dependencies.py`); picking which of a task's own dependencies its working branch is based
  on (`ensure-working-branch`'s `stack_registration.py`); real-dependency readiness gated on full
  completion, not just an open PR (`is_task_eligible` in `task_readiness.py`); registering a
  task's already-signed-off PR into the epic's `gh stack` (`add-to-pr-stack`); expanding an "up
  to" target into every task from the start of the epic's document order through the target
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
- **Integrates with:** `ensure-working-branch` (picks a task's base branch as part of the normal
  pre-implementation branch-setup step every task already runs, but never touches `gh stack`
  itself — see Key Design Decisions), `concurrent-orchestrate` (spawns one `monitor-stack` per
  epic, the moment the first task in that epic's target set reaches hand-off — now correctly
  after that task's PR is actually linked into the stack, not merely open — and hard-stops with a
  clear error, rather than bootstrapping anything itself, if an epic's spec branch doesn't exist
  yet), `create-pr-from-context` (creates the PR directly against `base_branch`, with no stack
  involvement at all), and `PipelineContext`'s
  `added_to_stack` field (a named frontmatter field, not a passthrough extra — see
  `pipeline_context.py` line 34) that records whether `add-to-pr-stack` has registered a task's
  signed-off PR into the stack.
- **Isolation boundary:** `work-with-stacked-prs`/`gh_stack.py` is the sole owner of every direct
  `gh stack` CLI invocation across this whole feature; every other skill and script references
  its named operations rather than shelling out to `gh stack` itself. This is deliberate risk
  mitigation for a days-old public-preview GitHub CLI feature — one place to change if the CLI's
  behavior does.

## Key Design Decisions

- **`gh stack` fully replaces ADR-296's dependency-graph/rebase/monitor machinery, rather than
  layering on top of it.** `ensure-working-branch` computes a task's base branch itself (from its
  own dependencies), but the actual GitHub stack object is populated later, entirely by
  `add-to-pr-stack`. ADR-296's `rebase_mechanic.py`, `watch_pr_poll.py`, the `monitor-pr` skill,
  `/watch-pr`, and the base-branch-selection half of `is_task_eligible` are retired outright —
  confirmed absent from the repo, not merely deprecated.
- **An epic's dependency DAG is serialized into one linear stack using the spec's own task
  document order, validated rather than computed.** `validate_stack_order` (in
  `task_dependencies.py`, extending the existing `parse_task_dependencies`) confirms every task's
  declared dependencies appear earlier in the spec's `## Tasks` section than the task itself, then
  returns the task keys in that document order — the order the spec's author already committed to
  when writing the task breakdown, not a graph the system computes independently. Only used to
  break ties among a task's *own* dependencies now (`stack_registration.py`'s
  `compute_stack_anchor`), not to force strict document-order registration — see the deferred-
  registration decision below.
- **`write-dev-spec` bootstraps an epic's own trunk directly, in its own step 1.5 — there is no
  separate `ensure-feature-branch` skill, and no mandatory "feature branch" concept.** A feature
  branch is now entirely optional and user-driven: if the user wants their epic's tasks based on
  something other than `main`, they create and check out that branch themselves *before* running
  `write-dev-spec` — nothing in this pipeline creates one on their behalf. What `write-dev-spec`
  always does is create (or find) the feature's own spec branch and commit the spec onto it, PR'd
  against whichever branch was active (or the user explicitly confirmed) when it ran — reporting
  that branch and pausing for the user's confirmation every time, never assuming silently. This PR
  becomes the base of the first implementation PR. No `gh stack` is anchored here either — there's
  no empty-stack precondition to set up ahead of time, since `link` (see below) creates a stack
  from scratch itself the first time any task registers into it.
- **The spec branch is named like a task branch, not a special "feature" scheme, and is the
  spec's own branch — not a separate spec-commit branch PR'd against it** (closes GitHub issue
  #218). Built from `git-repo.working-branches.task`, substituting `<feature-work-item-id>-spec`
  for `<task-work-item-id>`; the spec is committed directly onto it, for as long as the epic is in
  flight, rather than onto a dedicated `docs/<id>-spec` branch merged separately. `write-dev-spec`
  bootstraps this branch right after resolving a feature-work-item id — before any draft exists —
  so the working tree is already on this branch for the whole drafting session, and again at the
  end (after work items are created) to guarantee the spec is committed and PR'd even if the user
  never staged anything themselves. This removes the old three-manual-step bootstrap (create a
  root branch and push it; create a separate spec branch, push it, and PR it against the root
  branch; merge that PR or redirect the first `/implement` call at the spec branch instead) the
  user previously had to do by hand before implementation could start. `ensure-working-branch` and
  `concurrent-orchestrate` only ever search for this branch by its naming convention — neither
  creates it if missing; a task starting before its epic's spec exists is a hard error directing
  the user to run `/write-dev-spec` first, not a silent auto-bootstrap.
- **A task's working branch is always a new, distinct ref, never the feature branch itself**
  (closes GitHub issue #126). `ensure-working-branch`'s `stack_registration.py` module runs a
  `verify_branch_identity` guardrail immediately after creating a task's own branch, confirming
  `HEAD` is genuinely that branch and not the feature branch — a non-zero exit here is a hard stop.
- **A task's PR is opened directly against its own `base_branch`, with no `gh stack` involvement
  at all** (closes GitHub issue #129, now by construction rather than by branching on
  `added_to_stack`). `create-pr-from-context` always uses `create-pr` with the `base_branch`
  `ensure-working-branch` computed — there is no separate stack-relative code path left to drift
  out of sync with it, since a task's branch is never part of a `gh stack` at PR-creation time in
  the first place (see the deferred-registration decision below).
- **Stack registration is deferred to sign-off, not eager — and, once deferred, no longer needs to
  be recursive.** `ensure-working-branch` never registers a task's branch into the epic's `gh
  stack` at all; it only picks which of the task's own dependencies to base the branch on
  (`stack_registration.py`'s `compute_stack_anchor`, whichever sorts latest in document order).
  Registration itself happens once, later, in `add-to-pr-stack`, right after `signoff` resolves
  `approved` — at which point every declared dependency is already fully `done` (see the
  readiness decision below), so there is nothing to backfill: an ancestor that hasn't started yet
  can never be a real dependency of a task that's already eligible to run. `add-to-pr-stack` calls
  `link` with just this task's own PR and its anchor dependency's branch (or `--base
  <feature-branch>` for the epic's first task) — never the whole stack, and never from the
  feature's shared worktree (see the cross-worktree decision below); `link` "does not rely on
  gh-stack local tracking state," so no shared-worktree routing is needed for this one operation.
- **Implementation only starts once every real dependency has reached "done" — fully signed off
  *and* linked into the stack, never merely an open PR.** `is_task_eligible`
  (`task_readiness.py`) is stricter than ADR-374's original "ready or done" rule for exactly this
  reason: since registration no longer happens eagerly at a dependency's own start, an open PR no
  longer implies that dependency is actually in the stack yet. Its return value still doesn't
  carry a `base_branch` — stack position and real-dependency readiness remain fully decoupled
  concerns — and no dependency ever needs to actually *merge*.
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
  feature's stack that relies on this local tracking state — `init`/`add`/`submit`/the ongoing
  `sync`/`view` polling in `monitor-stack`/`merge`/`rebase --continue`/`checkout` — must run from
  one shared worktree per feature, never a task's own per-task worktree. `work-with-stacked-prs/
  SKILL.md` documents this explicitly as a structural constraint, not a corner case. `link` is the
  deliberate exception (see the deferred-registration decision above): it "does not rely on
  gh-stack local tracking state" at all, which is exactly why `add-to-pr-stack` uses it instead of
  `add`/`submit` and can run from a task's own per-task worktree with no shared-worktree routing.
- **`monitor-stack`'s own worktree lands on a real stack member, never the trunk.** A consequence
  of the previous decision: `monitor-stack` runs in its own freshly spawned worktree, which has
  never run `add`/`link` for this stack itself — and `gh-stack` doesn't consider the trunk branch
  a stack member in the first place — so simply checking out the trunk there leaves `gh stack
  view`/`sync` erroring (closed [issue #189](https://github.com/jodavis/agent-plugins/issues/189)).
  Step 2 instead finds the one open PR that bases directly off the trunk (the bottom-most stack
  entry, whose task triggered the monitor's own auto-start) and runs `gh stack checkout
  <pr-number>` (via `stack_checkout.py`) — per `gh-stack`'s own behavior, a PR number not yet
  tracked locally is discovered from the GitHub API and used to materialize the stack in this
  worktree, landing on a real member branch. The `link` call that registered that PR, run in a
  *different* worktree (the task's own), cannot be "propagated" to fix this — the whole point of
  the cross-worktree decision is that local tracking state is worktree-private, so every worktree
  that needs it must independently
  materialize it.
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
  decision above). `monitor-stack/SKILL.md`'s own prose was updated to match this exactly (closed
  [issue #180](https://github.com/jodavis/agent-plugins/issues/180)).

## Key Classes / Interfaces

- **`work-with-stacked-prs`/`gh_stack.py`** — sole owner of every `gh stack` CLI invocation.
  Exposes nine operations as plain Python functions (`init`, `add`, `submit`, `sync`, `view`,
  `merge`, `rebase_continue`, `checkout`, `link`), each returning `("ok" | "error", detail)`
  (`view`'s `detail` is the parsed `--json` dict; the other eight return stdout/stderr text), plus
  `check_gh_stack_extension_installed()` for the extension preflight. `link` is the only one that
  doesn't rely on local `gh stack` tracking state — see the cross-worktree decision above.
- **`write-dev-spec` step 1.5** — bootstraps an epic's spec branch and spec PR directly, inline
  in the command's own prose; every sub-step check-before-act. No `ensure-feature-branch` skill
  exists; no `gh stack` is anchored here either (see Key Design Decisions).
- **`ensure-working-branch`'s `stack_registration.py`** — `compute_stack_anchor()` (picks which of
  a task's own dependencies its branch bases on, by document order) and `verify_branch_identity()`
  (the #126 guardrail). No longer registers anything into a `gh stack`.
- **`add-to-pr-stack`/`add_to_pr_stack.py`** — the sole place a task's branch is ever registered
  into its epic's `gh stack`; runs once, right after `signoff` resolves `approved`, calling `link`
  with just this task's own PR and its anchor dependency's branch (or `--base <feature-branch>`
  for the epic's first task). Fully script-driven — the skill's own prose is limited to the
  interactive `gh` extension preflight; the script also writes an extra-frontmatter
  `stack_link_status` key (`"linked"` or `"not_applicable"`) so a "nothing to register" outcome
  is as durable across a crash-and-retry as an actual link, since `added_to_stack` alone (a plain
  boolean) can't represent that third state.
- **`checkout-stack-pr-for-review`/`checkout_stack_pr_for_review.py`** — ad hoc/manual escape
  valve for reading or running a stacked PR's code outside the automated pipeline: creates a
  disposable `review/<pr-number-or-branch-slug>` branch off the PR's own tip via `gh pr view` +
  plain `git`, never touching the shared branch or any `gh stack` operation itself (see
  `work-with-stacked-prs/SKILL.md`'s "Ad hoc/manual use" note).
- **`task_dependencies.py`'s `validate_stack_order(spec_text) -> list[str]`** — extends
  `parse_task_dependencies` with the stack-order check; returns task keys in document order. Used
  by `compute_stack_anchor` to break ties among a task's own dependencies, not to force strict
  document-order registration.
- **`task_readiness.py`'s `is_task_eligible(task_id, dependency_ids) -> "eligible" | "waiting" |
  "blocked"`** — real-dependency readiness, decoupled from stack position; requires every
  dependency to have reached "done" (signed off and linked into the stack), not merely "ready"
  (an open PR); no longer returns a `base_branch`.
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
- **`stack_checkout.py`'s `checkout(pr_number)`** — one-shot bootstrap `monitor-stack` calls in
  step 2, before the poll loop starts; runs `gh_stack.checkout(pr_number)` (`gh stack checkout
  <pr-number>`) to materialize the stack in a fresh worktree and land on a real member branch.
- **`concurrent_schedule.py`'s `compute_next_batch(target) -> dict`** — computes the next batch of
  tasks to spawn for an "up to" or explicit-list target, including a live check for whether the
  epic's spec branch exists yet (raises `RuntimeError` if not — no auto-remediation) and the
  repo-wide concurrency cap.
- **`monitor-stack`** — the epic-wide, long-lived post-hand-off monitor; polls via
  `stack_pr_poll.py` and reacts to exactly one outcome per call.
- **`/watch-stack`** — manual entry point, no arguments. Invokes `monitor-stack` directly in the
  current session from whatever worktree the user is already checked out into — the only entry
  point; not being on a stack at all is a hard stop (`monitor-stack` step 2b), not a fallback to
  an epic-key argument.
- **`PipelineContext.added_to_stack`** — a named boolean frontmatter field (`pipeline_context.py`
  line 34), `true` once `add-to-pr-stack` has registered a task's signed-off PR into the epic's
  `gh stack`. `false` for the entire implementation/review/signoff cycle before that, and stays
  `false` permanently for a task that was never part of a tracked epic in the first place.

## Data Flow

1. **Epic bootstrap.** `write-dev-spec`'s own step 1.5 establishes the epic's spec branch right
   after resolving a feature-work-item id, before any spec draft exists — reporting the branch it
   found (or the currently checked-out branch, for a brand-new one) and pausing for the user's
   confirmation every time, rather than assuming silently. It creates the branch from whichever
   branch the user confirmed (`main` by default, or a feature branch the user created and checked
   out themselves beforehand) if missing — there is no separate spec-commit branch. Step 6, once
   work items are created, runs the same branch-confirmation logic again if step 1.5 hasn't
   already run this session, then commits/pushes/PRs the spec directly onto that same branch
   (against the confirmed base) using the spec's own already-known path. This PR becomes the base
   of the first implementation PR. No `gh stack` is anchored at any point here either — there's no
   empty-stack precondition to set up ahead of time. A task reaching `ensure-working-branch`
   (directly, in the single-task path, or via `concurrent-orchestrate`) before this has ever run
   for its epic is a hard error naming the missing spec branch and directing the user to run
   `/write-dev-spec` first — neither ever bootstraps one itself.
2. **Task base-branch selection.** `ensure-working-branch` computes the task's working-branch
   name, then picks its base — never registering into a `gh stack`: `stack_registration.py`'s
   `compute_stack_anchor()` picks whichever of the task's own declared dependencies sorts latest
   in the epic's document order (or `None`, meaning base on the feature branch directly, for a
   task with none). The branch is created with a plain `git checkout -b`, and the
   `verify_branch_identity` guardrail confirms `HEAD` is genuinely the new branch, not the feature
   branch.
3. **Eligibility and scheduling.** Independently of stack position, `is_task_eligible` gates when
   a task's implementation actually starts: once every declared dependency has reached "done"
   (fully signed off *and* linked into the stack — not merely "ready," an open PR).
   `concurrent_schedule.py`'s `compute_next_batch` uses this alongside `validate_stack_order`'s
   document order to decide which tasks are eligible to spawn next, up to the configured
   concurrency cap.
4. **PR creation.** Once a task's implementation is complete, `create-pr-from-context` opens the
   PR directly via `create-pr`, using `base_branch` (from step 2) as the explicit base — no `gh
   stack` involvement at all at this point.
5. **Stack registration.** Once `signoff` resolves `approved`, `add-to-pr-stack` runs `link` once:
   just this task's own PR and its anchor dependency's branch (resolved the same way step 2 did),
   or `--base <feature-branch>` and just this task's own PR for the epic's first task. `link`
   creates the stack from scratch the first time, and extends it every time after — all without
   needing the feature's shared worktree, since `link` doesn't rely on local tracking state. Only
   once this succeeds does the task's pipeline reach `done` — the "hand-off" signal
   `concurrent-orchestrate` waits for to auto-start `monitor-stack`.
6. **Epic-wide monitoring.** The moment the first task in an epic's target set reaches hand-off
   (now correctly meaning its PR is actually linked into the stack, not merely open),
   `concurrent-orchestrate` auto-starts one `monitor-stack` session for that epic, always in its
   own freshly spawned worktree passed `--work-item-id` explicitly (it has other pipeline work of
   its own to protect). A human can instead start it manually via `/watch-stack`, in-session, from
   whatever worktree they're already sitting in — it takes no `--work-item-id` argument at all;
   `monitor-stack` always derives the epic from the current branch instead. Either way, if the
   worktree has no local `gh stack` state of its own yet (the auto-started, freshly spawned case),
   step 2 finds the one open PR based directly on the trunk and runs `stack_checkout.py` to
   materialize the stack there and land on that real member branch (never the trunk itself, which
   `gh-stack` doesn't consider a member) before the poll loop starts; a worktree already sitting on
   a stack member branch skips this bootstrap. It then loops on `stack_pr_poll.py`: each call runs
   `sync` first, then checks for a rebase conflict, then consults `detect_next_stack_event` for the
   first review-comment/CI-failure/merge event across the whole stack.
7. **Reacting to poll outcomes.** A `{"task_work_item_id", "event"}` result spawns `fix-pr` against
   that task's already-checked-out branch. A `"conflict"` result hands off to the developer agent
   running `resolve-rebase-conflict` against the currently-conflicted branch; on `"resolved"`, the
   monitor calls `stack_rebase_continue.py` to resume gh-stack's own cascade across any downstream
   branches, looping back into another `resolve-rebase-conflict` round if that call surfaces a
   further conflict higher in the stack, or returning to polling once it reports a clean state; on
   `"unresolved"`, the monitor aborts the rebase and halts entirely, since one stuck task blocks
   every later task in the stack regardless of how many monitor processes exist.
8. **Completion.** Once every branch in the stack has merged, `stack_pr_poll.py` reports
   `"stack_complete"`, and `monitor-stack` removes its own worktree/branch and stops.
