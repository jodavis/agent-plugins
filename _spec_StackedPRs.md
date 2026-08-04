# Stacked PRs for Concurrent Development

> **Status:** Draft
> **Epic:** [ADR-369](https://jodasoft.atlassian.net/browse/ADR-369)
> **Design:** — none
> **Architecture doc:** `_doc_StackedPRs.md` — authored by `dev-spec-task-breakdown`'s
> unconditional final "Author design documentation" task once implementation completes; this
> spec persists afterward for harvesting

## Overview

`_spec_ConcurrentDevelopment.md` (epic [ADR-296](https://jodasoft.atlassian.net/browse/ADR-296))
already ships a hand-built mechanism for concurrent task development: a `Depends on:` graph parsed
from each spec, a readiness rule that decides which dependency's branch a task should build on, a
custom rebase mechanic, and a `monitor-pr` monitor — one long-lived agent per task PR — that
individually polls its own PR and manually re-targets its base branch when its dependency merges.
GitHub now ships a native "stacked pull requests" platform feature (public preview as of
2026-07-30) with an official `gh-stack` CLI extension that does the same job — chaining branches,
cascading rebase-on-merge, and multi-PR status queries — as a first-class product feature instead
of bespoke scripts. This feature replaces ADR-296's hand-built graph/rebase/monitor machinery with
`gh stack`: every task-work-item in an epic becomes one entry in a single GitHub stack rooted at
that epic's feature branch, and one long-lived `monitor-stack` monitor per epic keeps the whole stack
in sync instead of one monitor per task.

Reading `gh-stack`'s own model also surfaced a real, previously-undocumented gap this feature closes
along the way: nothing in the pipeline today actually *creates* an epic's feature branch — a task's
`ensure-working-branch` only searches for one and hard-stops if it's missing — and a spec file is
never committed by the writing pipeline at all (confirmed live: `_spec_ConcurrentDevelopment.md`
itself currently sits untracked in this very worktree). `gh stack init` needs a pushed trunk branch
to anchor to, which makes fixing this a hard prerequisite rather than optional polish: a new
`ensure-feature-branch` bootstrap creates the feature branch from `main`, pushes it with no changes
(so it exists even if direct pushes to protected branches are otherwise locked down), commits the
epic's spec file to its own PR against that branch, and initializes the stack.

This rework of branch and PR-base creation also directly addresses two open bugs in the current
mechanism: [GitHub issue #126](https://github.com/jodavis/agent-plugins/issues/126) (an agent can
mistake having just created the *feature* branch for having created its *working* branch, losing
the ability to squash a task's PR into the feature branch) and
[#129](https://github.com/jodavis/agent-plugins/issues/129) (a task's PR is sometimes opened against
`main` instead of the `base_branch` computed for it, requiring a human to catch and correct it).
See the two decisions below addressing each directly.

## Responsibilities & Boundaries

- **Owns:**
  - `work-with-stacked-prs` (new): the sole owner of every direct `gh stack` CLI invocation; every
    other component in this feature calls its named operations instead of the CLI directly.
  - Validating that an epic's spec lists every task after all of its own `Depends on:` entries, so
    the document's own task order can serve directly as the stack order (see Key Design Decisions —
    GitHub stacks are confirmed strictly linear, so a task with multiple dependencies or multiple
    dependents no longer waits on a multi-dependency merge rule; it simply occupies its document
    position).
  - `ensure-feature-branch` (new): bootstraps an epic's feature branch from `main`, commits and PRs
    its (possibly locally-uncommitted) spec file against that branch, and runs `gh stack init`.
  - `ensure-working-branch`'s replacement base-branch logic: registers each task's branch into the
    epic's stack via `gh stack add` instead of computing or searching for a base branch itself, and
    verifies the resulting checked-out branch is a genuinely new task branch, never the feature
    branch itself (closes [#126](https://github.com/jodavis/agent-plugins/issues/126)).
  - `create-pr-from-context`'s extension: task PRs for stack-registered tasks are submitted via
    `gh stack submit`, which derives the correct base from the stack's own bookkeeping instead of a
    separately-threaded `base_branch` value (closes [#129](https://github.com/jodavis/agent-plugins/issues/129)).
  - `concurrent_schedule.py`'s replacement eligibility rule: a task is eligible once every one of its
    declared `Depends on:` dependencies has reached "ready" — none need to be merged, not the old
    all-but-one-dependency-merged computation. Separately, `ensure-working-branch` registers a task's
    branch structurally once its immediate stack predecessor is registered, entirely decoupled from
    this eligibility check (see the two "Branch registration..."/"Implementation only starts..." Key
    Design Decisions).
  - `monitor-stack` (new, replaces `monitor-pr`): one long-lived monitor per epic that watches every PR
    in that epic's stack, running `gh stack sync`/`gh stack merge` instead of a custom rebase
    mechanic and per-task dependency-merge detection, while still reacting to review comments and
    CI failures per individual PR the same way `monitor-pr` did.
- **Does not own:**
  - The single-task pipeline's internal implement/validate/review/signoff *states* — unchanged,
    reused as-is. (The `creating-pr` state still invokes `create-pr-from-context`; only that one
    skill's internals gain a stack-aware branch, not `dev_team.py`'s state machine itself.)
  - `resolve-rebase-conflict` — its conflict-resolution logic is reused unmodified (a `gh stack sync`
    conflict leaves git in the same mid-rebase state today's `rebase_onto()` does), but its own
    `SKILL.md` names its caller as `dev-team:monitor-pr` in two places (documentation only, not
    behavior) — those references need updating to `dev-team:monitor-stack` alongside `monitor-pr`'s
    retirement, a one-line documentation fix each.
  - `fix-pr` — reused unmodified, invoked per-PR by `monitor-stack` exactly as `monitor-pr` invoked it.
  - Cross-spec/cross-epic task dependencies — still out of scope, per
    [ADR-315](https://jodasoft.atlassian.net/browse/ADR-315), unaffected by this feature.
  - Migrating an epic that already created its feature branch under the old ADR-296 mechanism —
    no migration path is defined, deliberately: concurrent implementation is in limited use (a
    single user, no in-flight epics beyond this one), and the new mechanism won't even be available
    until this epic itself is done, so no epic could have started under it prematurely.
- **Integrates with:**
  - `spec-task-breakdown` — no changes to how `Depends on:` is authored or rewritten; this feature
    only changes how that graph is *consumed* (a document-order validation instead of per-dependency
    waiting logic), plus one new authoring rule (dependencies always listed before dependents).
  - `get-project-configuration` — reuses `concurrency.max-parallel-tasks` unchanged; no other
    changes (the `gh`/`gh-stack` extension preflight lives entirely in `work-with-stacked-prs`, not
    here).
  - `create-pr` — reused unmodified for the one PR that is never part of a stack: the epic's own
    spec PR opened by `ensure-feature-branch`, which still needs an explicitly passed `base`
    (the feature branch) exactly as it does today.
  - `fix-pr`, the developer agent, `resolve-rebase-conflict` — reused unmodified by `monitor-stack`,
    the same nested-spawn patterns `monitor-pr` already established.

## Key Design Decisions

### `gh stack` fully replaces ADR-296's dependency-graph/rebase/monitor machinery, rather than layering on top of it

_Context:_ Two shapes were considered: layer `gh stack` registration on top of the existing
dependency-graph/base-branch-selection logic while only replacing the post-hand-off monitor fleet,
or let `gh stack` become the actual source of truth for branch topology end to end. The narrower
option would have been a smaller diff against ADR-296's already-implemented code, but it would keep
two parallel dependency-tracking mechanisms alive indefinitely — one computing "which branch should
this task build on," a second recomputing the same thing implicitly via stack position — with no
clear reason for the split once `gh stack`'s own primitives (`add`, `sync`, `merge`, `view --json`)
cover the whole lifecycle a task's branch goes through.

_Decision:_ `gh stack` owns branch topology and rebase-on-dependency-merge end to end.
`ensure-working-branch` no longer computes or searches for a base branch itself — it runs
`gh stack add` to create and register a task's branch. `rebase_mechanic.py` and the
dependency-merge-retargeting half of `pr_event_detector.py` are retired outright, not kept as a
fallback path. The Task readiness checker's `is_task_eligible` survives — a task's real dependencies
still gate when its *implementation* may start — but shrinks: it no longer selects a base branch
(the stack always determines that from document position) and no longer needs its "all dependencies
but one merged" branch-selection exception, since no dependency ever needs to reach an actual
GitHub merge anymore, only "ready" (see "Implementation only starts once every real dependency is
ready" below).

_Consequences:_ A meaningful share of ADR-296's already-shipped code (`rebase_mechanic.py`, the
base-branch-selection half of `is_task_eligible`, the dependency-merge branch of `detect_pr_events`)
is removed rather than reused, while its core readiness computation survives in simplified form.
There is exactly one mechanism deciding branch topology, not two running in parallel — and the one
that remains is a maintained GitHub platform feature instead of bespoke rebase-conflict-prone
scripting. This is the highest-risk decision in this spec: it commits to a feature that reached
public preview only days before this spec was written (see the "Known upstream risk" decision
below), with no fallback if it proves unworkable mid-implementation.

### The epic's dependency DAG is serialized into one linear stack, using the spec's own task order — validated, not computed

_Context:_ Confirmed directly against GitHub's own documentation and the `gh-stack` CLI reference: a
GitHub stack is strictly linear — `gh stack add` requires being run "while on the topmost branch of
a stack," which structurally forbids two branches sharing one parent, and the REST/GraphQL schema
models stack membership as an integer `position` within a bounded `size`, a total order, not a
parent-reference graph. A spec's `Depends on:` graph is a general DAG: `_spec_ConcurrentDevelopment.md`'s
own task list fans in (ADR-310 depends on ADR-307, ADR-308, *and* ADR-335) and fans out (ADR-335 is
depended on by four different later tasks). A single GitHub stack cannot represent that shape
directly — but a spec's `## Tasks` section is already a flat, linearly-ordered document, and
checking `_spec_ConcurrentDevelopment.md`'s own task list confirms every dependency is already
listed before its dependents there today (ADR-335 first, since four later tasks need it, then 307,
308, 309...) — an informal convention, not an enforced one, since `dev-spec-task-breakdown` writes
tasks in a natural build-up order without an explicit rule requiring it.

_Decision:_ The stack order is the spec document's own task order — nothing computes or persists a
separate sort. `dev-spec-task-breakdown` gains an explicit rule formalizing what it already does
informally: every task must be listed after all of its own `Depends on:` entries. `concurrent_schedule.py`
validates this on *every* run (not just the first, and no "already validated" flag is cached to skip
it) — a cheap linear scan confirming no task's dependency appears later in the list — and halts with
a clear error naming the offending task if it's ever violated (e.g. a human manually reordered tasks
during a later spec edit and broke the invariant). A task's branch is always based on whichever task
appears immediately before it in the document, full stop. Because the invariant guarantees every real
dependency of a task appears somewhere before it, and because a git branch stacked on another
transitively contains everything below it, a task still transitively contains the code of all of its
actual dependencies — it just also transitively contains every other unrelated task that happened to
be listed earlier.

_Consequences:_ Exactly one stack per epic, satisfying "one `monitor-stack` worker per epic" with no
special-casing for forks. Task N can still be forced to rebase because an entirely unrelated,
earlier-sorted task N-2 changed, not just because of a genuine dependency — but this isn't a new
risk this design introduces: ADR-296's per-task `monitor-pr` already had to rebase whenever any
preceding branch in a chain changed, to avoid conflicts compounding later or stale code affecting
testing. This design just makes that existing possibility uniform and explicit, managed centrally
by `gh stack sync`, instead of being an implicit property of whichever ad hoc chain a task happened
to sit on. Each PR's own diff stays incremental regardless — GitHub computes a PR's diff against
its own base ref, so task N's PR shows only N's changes against N-1, not a cumulative diff against
`main`, exactly as any stacked PR does today. Revisit if the rebase-frequency trade-off turns out to
cause disruptive churn in practice — see Open Questions.

### `ensure-feature-branch`: a new bootstrap step creates the epic's feature branch, PRs its spec, and initializes the stack

_Context:_ Confirmed by reading every relevant skill: nothing in the pipeline today creates a
feature branch — `ensure-working-branch` only searches remote branches and hard-stops for
Jira-tracked work if none is found — and no skill in the spec-writing pipeline (`dev-spec-first-draft`,
`dev-spec-task-breakdown`) ever commits the spec file it writes. This was a latent gap under
ADR-296 (a human could `git push` the feature branch manually before running `/implement`); it
becomes a hard blocker here because `gh stack init` needs an actual pushed trunk branch to anchor
the epic's stack to.

_Decision:_ A new `ensure-feature-branch` skill runs the first time anything needs that epic's
feature branch (see Data Flow for exactly where it's invoked from both the single-task and
concurrent-orchestrate paths). Every one of its four steps is check-before-act, making the whole
skill safely re-runnable, not just its first two steps: (1) checks whether `feature/<epic-id>-<slug>`
already exists on the remote; if not, (2) creates it from `origin/main` and pushes it immediately
with no changes — establishing the ref even if the repo's push rules would otherwise block a later
push carrying real content; (3) if the epic's spec file(s) exist locally but aren't yet committed
anywhere, commits them to a new branch based on the feature branch and opens a separate PR targeting
the feature branch, giving the spec its own reviewable PR decoupled from any task's PR — skipped if
already committed; (4) checks whether a stack is already anchored to this trunk (via the `view`
operation) before running `init` — skipped if one already exists, rather than assuming `init` is
itself a no-op against an existing stack (unconfirmed; see Open Questions).

This idempotency is also why `concurrent_schedule.py` gates `bootstrap_needed` on a *live* check —
does `feature/<epic-id>-<slug>` exist on the remote? — rather than on whether its own persisted data
file exists. The data file is keyed by **target** (`concurrent-<target-slug>.json`, confirmed in the
actual script), not by epic, so tying the bootstrap signal to the file's presence would either loop
forever (if the file is never written on a `bootstrap_needed` call) or force every *different* target
landing on an already-bootstrapped epic to needlessly re-invoke `ensure-feature-branch` before it
could proceed. A live branch check avoids both: once any target's call to `ensure-feature-branch` has
created the branch, every other target — same one retrying, or a different one — sees it exists on
its very next call and proceeds straight to computing a batch, no re-bootstrap needed.

_Consequences:_ Every epic gets a real, pushed feature branch and a committed, reviewable spec
before any task work begins — closing a gap that existed even before this feature and would
otherwise have kept surfacing as an ad hoc manual step. `gh stack init` anchoring to a non-default
branch as trunk is confirmed working (used directly, not just inferred from docs), so this is safe
to build on rather than a spike item. Whether `init` itself would error, reset, or silently no-op if
run again against an existing stack is not confirmed either way — the explicit existence check in
step 4 above sidesteps needing that answer, but the spike should still confirm it as a defense in
depth.

### A task's working branch is always a new, distinct ref — never the feature branch itself (closes #126)

_Context:_ [GitHub issue #126](https://github.com/jodavis/agent-plugins/issues/126): "Occasionally,
an implementation workflow will create a new feature branch, and consider that having 'created a
working branch' to start coding in. That removes the ability to squash a task PR down into a
feature branch. `ensure-working-branch` needs clarity on the difference between working branches and
feature branches... Perhaps a deterministic script to create branches, instead of reasoning through
it every time." ADR-296's version of `ensure-working-branch` already tried to keep these distinct via
five branchy prose steps (4a–4f: search remote branches, query Jira for a parent, check nearest
ancestor, fall back to `main`) — exactly the "reasoning through it every time" the issue names as the
failure mode; a long-running agent occasionally collapses that reasoning and treats the branch it's
currently on (the feature branch) as good enough to just start writing code in.

_Decision:_ This spec's redesign already replaces that whole reasoning chain with one deterministic
command, `gh stack add <branch-name>`, which by its own documented contract *always* creates a new
branch at HEAD and checks it out — there is no code path where "the feature branch" and "the task's
working branch" can end up being the same ref. `ensure-working-branch` adds one explicit guardrail on
top of that: immediately after `gh stack add` returns, it verifies
`git rev-parse --abbrev-ref HEAD` equals the working-branch name computed in step 3 (the
`git-repo.working-branches.task` template) and is *not* equal to the feature branch name. A mismatch
is a hard stop — reported in detail, never silently proceeded past — the same posture the
worktree-freshness check already takes for a different integrity risk.

_Consequences:_ The ambiguity #126 names is closed structurally, not just documented against: a task
branch is always a genuinely new ref, verified by an explicit check rather than trusted to agent
reasoning. `ensure-feature-branch` (previous decision) reinforces the same invariant from the other
side — it commits the epic's spec to its *own* new branch, never to the feature branch directly,
so the feature branch is never a place any content gets written directly, by either bootstrap or
per-task code.

### Task PRs are submitted via `gh stack submit`, not a manually threaded `base_branch` value (closes #129)

_Context:_ [GitHub issue #129](https://github.com/jodavis/agent-plugins/issues/129): "the `base_branch`
is computed in `ensure-base-branch`. But PRs are often created against `main` instead of the
`base_branch` listed in the context file. This requires the human user to watch for this problem...
The `base_branch` should always be computed, and `create-pr-from-context` should always look for that
branch and use it to create PRs." Under ADR-296, `base_branch` is computed once early
(`ensure-working-branch`) and then has to survive, unmangled, all the way to the much-later
`creating-pr` state, where `create-pr-from-context` reads it back out of the context file and passes
it as an explicit `base` argument — a value threaded through two skills, a context-file round-trip,
and a state-machine gap, with every hop a place for it to go missing or stale.

_Decision:_ For a task whose branch was created via `gh stack add` (i.e. every task under this
spec's full-takeover design), `create-pr-from-context` no longer reads `base_branch` from the context
file or passes an explicit `base` to a generic PR-creation call at all. It instead runs
`gh stack submit` for that task's branch, which creates or updates the PR using the base `gh stack`
itself already established when the branch was added to the stack — the same source of truth
`ensure-working-branch` wrote to moments earlier, never a second, separately-computed value. The
existing `create-pr` skill (with its explicit `base` parameter) is kept only for the one PR that
isn't part of a stack — the epic's own spec PR from `ensure-feature-branch`.

_Consequences:_ There is no longer a `base_branch` value anywhere to go stale or get silently
dropped: a task's context file never gets one written to it in the first place. `ensure-working-branch`
only needs the predecessor's `working_branch` name (an existing field) to check it out before running
`gh stack add`; `gh stack` itself is the only place a branch's actual base is recorded, for every
task including the first (whose base is the feature branch, `gh stack init`'s own trunk). The only
durable per-task signal this feature's context files carry is `added_to_stack: bool` — stack
membership, not a branch name. Anything that needs to know a branch's *current* base queries
`gh stack view --json` live rather than trusting a duplicated value — the class of bug #129
describes is closed by removing the separate value entirely, everywhere, not by adding stricter
validation around one call site. The one open question this leaves (see Open Questions) is
confirming `gh stack submit` can submit a single newly-added stack entry's PR without forcing every
other entry in the stack to also submit at that moment — each task reaches `creating-pr`
independently, on its own pipeline's schedule.

### Branch registration is lazy, recursive, and decoupled from real-dependency readiness

_Context:_ A task's stack position (structural: which branch it's based on) and its real
implementation readiness (semantic: whether the code it actually depends on exists yet) are two
different questions. Collapsing them into one signal — "start once your stack predecessor's branch
exists" — is wrong: an agent could start writing code against an empty or half-built foundation
just because *some* branch happened to exist at that stack position. They also don't need to be
gated on each other in the direction that matters for concurrency: an independent, agent-ready task
shouldn't have to wait for a human-owned task that merely happens to sit earlier in the document,
if the human task isn't actually one of its real dependencies.

_Decision:_ Registering a task's branch in the stack is a separate, purely structural operation from
starting its implementation, and it's lazy and recursive rather than eagerly cascading forward.
Whenever anything needs task N's branch to exist — N's own `ensure-working-branch` starting real
implementation, or a later task needing N as its base — it checks whether N is already registered
(`added_to_stack: true` on N's context file). If not, it recurses to N-1 first (creating N-1 as an
empty branch and registering it if *that* isn't registered either), continuing backward until it
finds an already-registered ancestor, then builds forward from there, creating one empty placeholder
branch per skipped task along the way, ending with N's own branch. The `add` operation itself only
creates the branch locally and checks it out — it does not push (only `submit`/`sync` do) — so
`ensure-working-branch` follows every `add` with an explicit `git push -u origin <branch>` and waits
for that push to succeed before writing `added_to_stack: true`; the hierarchy is established and
visible on the remote first, even for an empty placeholder created purely to satisfy a descendant's
backfill, before any real implementation commits exist. Because this can require writing
`added_to_stack: true` to a task *other than the one currently running* (e.g. task 2's agent
backfilling task 1's empty branch while task 1 is still an unstarted human task), `ensure-working-branch`
uses `use-context-file` with an explicit work-item-id argument for each ancestor it backfills, not
just its own. When the skipped task's own turn eventually comes, its `ensure-working-branch` finds
`working_branch`/`added_to_stack` already set (the same "already-known values" skip in step 2 ADR-296's
version already had) and simply checks out the branch someone else already created for it.
`added_to_stack` is added as a proper named field on the `PipelineContext` dataclass, not left to
round-trip generically through the "extra properties" passthrough ADR-335 introduced — that
mechanism exists as a safety net for fields a skill manages ad hoc via `Edit`, not as a substitute
for declaring a field this feature genuinely owns and depends on.

_Consequences:_ Out-of-order implementation falls out naturally: an agent-owned task can lay
groundwork immediately, without waiting on an earlier-listed but unrelated human task, and once the
human's real work lands, `gh stack sync` propagates it forward through every backfilled descendant
automatically. This does introduce a race to watch for: if `concurrent_schedule.py` spawns two
tasks in the same pass whose backfill chains overlap (e.g. task 2 and task 4 both become eligible at
once, and task 4's chain needs task 2 and 3 registered first), two processes could attempt to
backfill the same gap concurrently — see Open Questions.

### Implementation only starts once every real dependency is ready — no dependency ever needs to be merged

_Context:_ ADR-296's `is_task_eligible` required all but one of a task's dependencies to actually
*merge* (not just reach an open PR) before the task could start, because combining two still-open
sibling branches had no representation other than a real GitHub merge — there was no other way to
get both dependencies' changes onto one branch. That "all but one merged" exception was the single
most complex part of ADR-296's readiness rule.

_Decision:_ `is_task_eligible` survives, simplified: a task is eligible to *start real implementation*
once every one of its declared dependencies has reached "ready" (PR created — implemented, building,
tests passing) — no dependency ever needs to be actually merged. This works because dependencies of
the same task are never siblings under one linear stack; whichever one sorts later in document order
is already stacked on top of every dependency that sorts before it, so once *all* of them
independently reach "ready," the later one's branch already transitively contains everything the
earlier ones contributed via ordinary ongoing `gh stack sync` — no merge event needed to combine
them. `concurrent_schedule.py`'s spawn gate is exactly this: are all of task N's real dependencies
ready? Nothing about stack registration (the previous decision) factors into this check — that's
handled lazily, inside the spawned task's own first `ensure-working-branch` step, not as a
pre-spawn condition.

_Consequences:_ A more permissive concurrency rule than ADR-296's ever was — ADR-296 still required
a real merge for all-but-one dependency when a task had two or more; this design requires zero
merges for any number of dependencies, only "ready" status for each. Combined with the previous
decision, a task's branch can exist (as a backfilled placeholder) well before its own implementation
starts, and its implementation can start well before any sibling-in-spirit dependency has actually
merged into the feature branch — both fully decoupled from stack position.

### "Up to Task X" now means "Task X and everything before it," not just its dependency closure

_Context:_ ADR-296's "up to" form computed only the target task's dependency closure — e.g. "up to
Task 4," where Task 4 depends only on Task 1, would implement just {1, 4}, leaving Tasks 2 and 3
(unrelated to Task 4) unimplemented and forcing the user to separately figure out what to request
next to get them done. With one linear stack per epic, that gap is avoidable, and avoiding it makes
"up to Task X" a much simpler mental model: everything up to that point, no gap-filling arithmetic
required afterward.

_Decision:_ "Up to Task X" implements every task from the start of the epic's stack order through
Task X inclusive — not just X's transitive dependency closure. A task with no relationship to X
still gets implemented if it's earlier in document order. As a companion authoring guideline (not
an enforced rule), `dev-spec-task-breakdown` should order human-operator tasks (already marked 🧑 in
the existing task-list legend, vs. 🤖 for agent tasks) as late as the dependency graph allows, so
agent-implementable tasks aren't needlessly sequenced behind a human task that isn't actually their
dependency — minimizing how often "up to X" ends up blocked on a human who happens to sit early in
the order.

_Consequences:_ A deliberate behavior change from ADR-296, not just an implementation detail — "up
to X" does more work than before for the same target, but the result has no gaps and needs no
follow-up requests to fill them in. A human task anywhere in the inclusive range can still block the
run the same way it always could; the late-scheduling guideline reduces how often that happens but
doesn't eliminate it, since a human task might still be a genuine dependency of something early in
the chain.

### A single `monitor-stack` monitor per epic replaces the per-task `monitor-pr` fleet, auto-started at the first hand-off

_Context:_ ADR-296 spawns one `monitor-pr` per task, each independently polling its own PR and
manually detecting + reacting to its dependency merging. With one shared GitHub stack per epic,
that per-task duplication is exactly what `gh stack sync`/`gh stack merge` exist to collapse: a
single command already knows how to walk and update every PR in a stack.

_Decision:_ `concurrent-orchestrate` auto-starts one `monitor-stack` monitor per epic — as a local
background `Agent` with its own fresh `isolation: "worktree"`, the same pattern `monitor-pr` already
used — the moment the *first* task in the epic's target set reaches hand-off, not once every target
task has. From there, `monitor-stack` keeps discovering newly-handed-off tasks' PRs as later `add`
calls extend the stack, rather than needing the full membership known upfront.
`/watch-stack <epic-key>` replaces `/watch-pr <task-key>` as the manual fallback entry point,
spawning `monitor-stack` the same isolated way.

Because `monitor-stack` runs in *one* shared worktree for the whole epic — unlike `monitor-pr`, which
only ever had one task's branch to worry about — it can only ever be checked out on one branch at a
time. Batching "every fired event across every task" into one pass, as `monitor-pr` did for its single
task, doesn't translate directly: spawning `fix-pr` for task 2 while the worktree still points at
task 5's branch (left over from handling task 5's event moments earlier) would have `fix-pr`
operating on the wrong code entirely, since it inherits `monitor-stack`'s cwd with no isolation of its
own. So `stack_pr_poll.py` is designed to do every mechanical step itself before ever returning
control to the agent, and to surface exactly one actionable item at a time rather than a batch:

- **`sync` runs every iteration, silently, unless it hits a genuine conflict.** A clean sync isn't
  reported as an event at all — the script just continues its internal poll loop. Only a real
  conflict interrupts, returned as its own distinct outcome (never lumped in with review/CI events),
  since resolving it needs the developer agent's judgment, not something the script can do itself.
- **One actionable task at a time, already checked out.** On each iteration, the script looks for
  the first task (by stack position) with a new review comment or CI failure. If it finds one, it
  runs `git checkout <that task's working_branch>` itself — mechanically, before returning — then
  returns identifying just that one task and event. `monitor-stack` spawns `fix-pr` against an
  already-correctly-positioned worktree; it never has to reason about which branch it should be on.
  The script surfaces the next actionable task, if any, on `monitor-stack`'s very next call.
- **A single task's merge is silent bookkeeping, not a returned event.** The script just stops
  tracking that PR internally and keeps polling. Only once *every* task in the target set has merged
  does it return a terminal `epic_complete` outcome — the one thing only the agent itself can act on,
  since only the agent can end its own session.

`stack_pr_poll.py` otherwise follows the exact same blocking-poll pattern already proven in
`watch_pr_poll.py` (confirmed by reading it: an internal `sleep(30)` between checks, bounded under
`max_seconds`, itself kept under `Bash`'s 10-minute timeout cap) — blocking and re-checking every 30
seconds internally, so the agent is only woken when something genuinely actionable is ready, on the
order of minutes, not every 30 seconds itself.

_Consequences:_ One monitor process, not N, for an entire epic's worth of PRs — directly what the
epic text asked for, and a genuine operational improvement, not just a wash: if `monitor-stack` stops
(e.g. on an unresolved conflict, per the next decision), there's exactly one process to notice and
restart — not the harder N-monitor problem of checking which of several are still alive, figuring
out which one(s) stopped, and restarting only those. Pausing or restarting monitoring for an entire
epic is also simpler with one process than coordinating N. This does concentrate risk that used to
be distributed — every PR in the epic loses its monitor at once when `monitor-stack` stops — but
`gh stack sync`'s cascading rebase already means one task's stuck conflict blocks every later task
in the stack from progressing regardless of how many monitor processes exist, so the fleet model
never actually gave independent forward progress past a blocking conflict in the first place. Pushing
the checkout-before-return and silent-bookkeeping work into the script also means `monitor-stack`
itself stays a thin reactor — it never juggles worktree state, only responds to exactly what's
already been prepared for it — the same "agent does judgment, script does mechanics" split
`watch_pr_poll.py` established, now load-bearing for correctness rather than just convenience.

### Rebase/sync conflicts still route through the existing `resolve-rebase-conflict` skill

_Context:_ `gh stack sync`'s cascading rebase can still hit a genuine content conflict — the
platform feature automates the mechanics (fetch, rebase, force-push, PR retargeting), not conflict
resolution itself.

_Decision:_ No change to `resolve-rebase-conflict`'s own conflict-resolution contract — it still
reads conflicting hunks, resolves them, stages them, and drives completion via plain
`git rebase --continue`, exactly as it does today. When `gh stack sync` reports a conflict,
`monitor-stack` spawns the developer agent (nested, no isolation of its own — inherits `monitor-stack`'s
worktree cwd) to run `resolve-rebase-conflict` exactly as `monitor-pr` did, using the same task-brief
context and the same `"resolved"`/`"unresolved"` verdict contract. On `"resolved"`, `monitor-stack`
runs `gh stack sync` again (rather than a raw `git push --force-with-lease`, since `gh stack` needs
to also update its own PR-position bookkeeping, not just the git ref) — this is an assumption
flagged for the feasibility spike (see Open Questions): GitHub's own docs describe resuming a
`gh stack rebase` via `gh stack rebase --continue`, not a plain `git rebase --continue`, which
suggests `gh stack` may track its own cascade state across the stack's multiple branches that a bare
`git` command wouldn't advance correctly — if so, `resolve-rebase-conflict`'s own completion step
might need a stack-aware follow-up rather than a fresh `sync` invocation being sufficient on its own.
On `"unresolved"`, it aborts the in-progress rebase and stops itself, surfacing via the harness's
background-task notification — no `AskUserQuestion` fallback, same as `monitor-pr`.

_Consequences:_ No changes needed to `resolve-rebase-conflict`'s own conflict-resolution logic; the
only difference from today is which command re-drives completion after a resolved conflict (`gh stack
sync` instead of a
raw push), and that stopping now halts monitoring for the whole epic's stack rather than one task
(see the consequence noted in the previous decision). This is deliberately for the best, not just an
accepted side effect: when a conflict can't be resolved automatically, the whole epic *should* stop
making automatic progress until a human untangles it, rather than risk compounding the problem.
ADR-296's N-monitor fleet only avoided this by hoping a stuck watcher simply wouldn't push anything
for its dependents to react to; this design makes that halt explicit and guaranteed instead of
implicit and hoped-for.

### Known upstream risk: GitHub's native stacked-PR feature is a days-old public preview

_Context:_ GitHub's stacked pull requests platform feature reached public preview on 2026-07-30 —
four days before this spec was drafted (2026-08-03). `gh-stack` is GitHub's own official CLI
extension for it (`github.com/github/gh-stack`, not to be confused with two unrelated
community-maintained tools of the same name: `VladimirAnaniev/gh-stack` and `boneskull/gh-stack`).
Merge-queue support for stacks was still described as "rolling out progressively" at the preview
announcement.

_Decision:_ Proceed with the full-takeover design in this spec, but treat the platform's newness as
an explicit, tracked risk rather than a settled assumption, mitigated three ways. First, the task
breakdown's first task is a small feasibility spike (create a real stack across two branches, two
worktrees, and a protected trunk in a scratch repo) that confirms or refutes the open questions
below *before* any other task in this breakdown builds on `gh stack`. Second, every later task in
the breakdown should be designed as an independently testable piece (manually or automated) that
verifies its own slice of `gh stack` usage actually works, rather than one large task whose
correctness is only visible at the end — the whole feature commit can be rolled back if `gh stack`
proves unworkable partway through. Third, every direct `gh stack` CLI invocation in this feature
(`init`, `add`, `submit`, `sync`, `view --json`, `merge`) is consolidated into one new skill,
`work-with-stacked-prs`, following this repo's existing `work-with-<system>` convention
(`work-with-Jira-tasks`, `work-with-pr`, `work-with-github-issues`) — every other skill in this
spec references its operations by name rather than invoking `gh stack` directly. Building on a
brand-new platform feature is a deliberate choice, not an oversight: the existing `monitor-pr`
mechanism already has open bugs (#126, #129) and isn't working as intended, so investing in getting
a maintained platform feature right is judged better than continuing to debug a shaky bespoke
design — but that judgment call is exactly why isolating every `gh stack` touchpoint behind one
skill matters, since the CLI is still evolving and this plan may need reworking as it changes.

_Consequences:_ If the spike surfaces a blocker (e.g. stack state genuinely not shared across
worktrees — non-default trunk support is already confirmed working, no longer a spike risk), this
spec's "full takeover" decision needs to be revisited before implementation proceeds further —
cheaper to find out from one scoped spike than partway
through building on top of an incorrect assumption. If `gh stack`'s CLI changes shape, or the whole
strategy needs replacing later, `work-with-stacked-prs` is the one place that changes — no other
skill in this feature needs to know it's `gh stack` specifically, only that it can register a branch
in a stack, submit its PR, sync the stack, and query stack membership.

## Component Breakdown

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `work-with-stacked-prs` (new skill, plus a `gh_stack.py` script module) | Wrapper | Sole owner of every direct `gh stack` CLI invocation (`init`, `add`, `submit`, `sync`, `view --json`, `merge`), following this repo's `work-with-<system>` convention; every other component below references its operations by name rather than invoking `gh stack` directly, so a CLI change or a strategy replacement touches one place. Unlike `work-with-Jira-tasks`/`work-with-pr` (which wrap MCP tools an agent session must hold credentials for), `gh stack` is a plain local CLI — no MCP involved — so the same operations are also exposed as importable functions in a sibling `gh_stack.py` module — each function internally shells out to `subprocess.run(["gh", "stack", ...])` — that bare scripts (`concurrent_schedule.py`, `stack_pr_poll.py`) `import` directly as a plain Python module, the same way they already `import task_dependencies`/`task_readiness` today (confirmed: plain `from task_dependencies import ...`, not subprocess); the skill's prose and `gh_stack.py`'s functions both ultimately shell out to the identical `gh stack <cmd>` invocations, so there's still exactly one place that changes if the CLI does. Also owns a one-time preflight: verifies `gh extension list` includes `github/gh-stack` specifically (not either unrelated same-named community tool), offers to install it if missing, and hard-stops if the user declines — no fallback stacked-PR mechanism is maintained "just in case" | — |
| Stack order validator (extends `task_dependencies.py`) | Testable | Validates that an epic's full `## Tasks` document order already lists every dependency before its dependents — the document order *is* the stack order; rejects a dangling reference, a cycle, or an out-of-order listing with a clear error naming the offending task; re-run on every call, not cached (reuses the existing `parse_task_dependencies` validation, extended with the ordering check) | — |
| `dev-spec-task-breakdown` (extended) | Wrapper | Gains one authoring rule (every task listed after all of its own `Depends on:` entries, so document order is a valid stack order — formalizing what it already does informally) plus a non-enforced guideline (order human-operator 🧑 tasks as late as the dependency graph allows) | — |
| `ensure-feature-branch` (new skill) | Orchestrator | Bootstraps an epic's feature branch (create from `main`, push empty if missing), commits and PRs its spec file(s) against that branch if not already committed, and runs the `init` operation — operates at the epic level, before any task-level stack entries exist, so it never itself consults the Stack order validator | `work-with-stacked-prs` |
| Task readiness checker (extends `task_readiness.py`) | Testable | `is_task_eligible`, simplified: reports whether every one of a task's real dependencies has reached "ready" (PR created) — no base-branch selection, no "all but one merged" exception, since no dependency ever needs to be merged | `use-context-file` (existing) |
| Concurrent scheduler (`concurrent_schedule.py`, extended) | Testable | Computes next batch to spawn using the Task readiness checker's simplified eligibility rule; reports `bootstrap_needed` (gated on a live check of whether the epic's feature branch exists remotely, not on its own data-file presence) instead of invoking anything itself — it's a bare script with no MCP credentials, same constraint that already keeps it from spawning agents directly | Stack order validator, Task readiness checker |
| `concurrent-orchestrate` (extended) | Orchestrator | Invokes `ensure-feature-branch` itself on `bootstrap_needed` (the scheduler script can't — no MCP credentials); no longer pre-populates a spawned task's `base_branch` context field (dropped entirely, see the `#129` decision); auto-starts `monitor-stack` once per epic instead of `monitor-pr` once per task | Concurrent scheduler, `ensure-feature-branch`, `monitor-stack` |
| `ensure-working-branch` (extended) | Orchestrator | Registers a task's branch into the stack via lazy, recursive backfill (the `add` operation, walking back to the nearest already-registered ancestor and filling gaps with empty branches) instead of computing or searching for a base branch; verifies HEAD is the new task branch, never the feature branch (closes #126); writes `added_to_stack` to its own context file, and to any ancestor's context file it backfilled along the way | Stack order validator, `ensure-feature-branch`, `work-with-stacked-prs` |
| `create-pr-from-context` (extended) | Orchestrator | For a stack-registered task, submits its PR via the `submit` operation instead of passing a manually-read `base_branch` to `create-pr` (closes #129); falls back to `create-pr`'s existing explicit-base behavior for a non-stack PR (the spec's own) | `ensure-working-branch`, `create-pr` (existing, spec-PR case only), `work-with-stacked-prs` |
| Stack PR event detector (extends `pr_event_detector.py`) | Testable | Uses the `view` operation only to enumerate current stack membership and each entry's PR link (branch/PR-link/commit metadata — `view` has no review-comment or CI-check data of its own), then reuses `pr_event_detector.py`'s existing per-PR GitHub API/MCP calls, unchanged, to check each linked PR for a new review comment or CI failure; iterates in stack-position order and returns the *first* actionable task found, checking out that task's branch itself before reporting it — no `base_updated`/`dependency_merged` events (subsumed by `sync`), no batching across tasks | `use-context-file` (existing), `work-with-stacked-prs` |
| `stack_pr_poll.py` (extends `watch_pr_poll.py`) | Testable | Bounded blocking poll loop: runs the `sync` operation every iteration (silent on success, returns immediately on a genuine conflict), then the Stack PR event detector; a merged task is untracked silently, with a terminal `epic_complete` returned only once every target task has merged; otherwise returns one checked-out, actionable `(task, event)` pair or `"no_change"` at the window's end | Stack PR event detector, `work-with-stacked-prs` |
| `monitor-stack` (new skill, replaces `monitor-pr`) | Orchestrator | One long-lived monitor per epic, spawned with its own fresh `isolation: "worktree"`; repeatedly calls `stack_pr_poll.py` and reacts to exactly the one thing it returns — spawns `fix-pr` against the already-checked-out branch, routes a conflict through the developer agent to `resolve-rebase-conflict` (unchanged contract), or halts on `epic_complete` — never juggles worktree state itself | `stack_pr_poll.py`, `resolve-rebase-conflict` (existing), `fix-pr` (existing), developer agent (existing) |
| `/watch-stack` (new command, replaces `/watch-pr`) | Wrapper | Thin manual-invocation wrapper: spawns `monitor-stack` via the `Agent` tool with `isolation: "worktree"` | `monitor-stack` |

**Retired components** (removed outright, not kept as a fallback path): `rebase_mechanic.py`
(`rebase_onto`), the base-branch-selection half of `is_task_eligible` (the "all dependencies but one
merged" exception and its returned `base_branch` value), and the `dependency_merged`/`base_updated`
branches of the original `pr_event_detector.py` — all superseded by `gh stack sync`'s native
cascading rebase or by the stack's own document-order basing. The Task readiness checker's core
"are all real dependencies ready" computation survives, simplified — see Key Design Decisions.
`monitor-pr` and `/watch-pr` are replaced by `monitor-stack` and `/watch-stack` respectively, not kept
alongside them.

## Planned Implementation

### Interfaces

- **`work-with-stacked-prs`:** exposes each `gh stack` operation by name, mirroring
  `work-with-Jira-tasks`'s pattern — every other skill in this feature references "the `<op>`
  operation from `work-with-stacked-prs`" rather than hardcoding a `gh stack` invocation directly.
  Because `gh stack` needs no MCP credentials (a plain local CLI, unlike `work-with-Jira-tasks`'s MCP
  tools), the same operations are also exposed as plain functions in a sibling `gh_stack.py` module —
  both the skill's prose (for agent-driven calls) and `gh_stack.py` (imported directly by
  `concurrent_schedule.py`/`stack_pr_poll.py`) shell out to the identical underlying commands, so
  there's still exactly one place to change if the CLI does:

  | Operation | What it does |
  |---|---|
  | `init` | Anchors a new stack to a trunk branch (the epic's feature branch); non-default trunk supported via `gh stack init --base <branch> <branch-list>` |
  | `add` | Creates a new branch at HEAD, adds it to the top of the stack, checks it out — does not push |
  | `submit` | Pushes and creates/updates PRs — scoped to the **entire stack** by default per GitHub's own CLI reference, not a single branch; see the per-entry-granularity Open Question |
  | `sync` | Fetches, cascades rebase across the stack, pushes, syncs PR state — aborts rather than proceeding when run in a non-interactive terminal and genuine divergence is hit; see the conflict-mechanics Open Question |
  | `view` | Reads current stack membership, branch ordering, and each entry's PR link/most-recent-commit — **not** review-comment or CI-check state; the only operation that supports `--json` |
  | `merge` | Merges one or more PRs in the stack |

  Every invocation is non-interactive per `github/gh-stack`'s own `skills/gh-stack/SKILL.md`
  guidance for agentic use: explicit positional arguments always, the interactive TUI never. `--json`
  output is only available from `view` — `init`/`add`/`submit`/`sync` do not support it, so any
  parsing of their outcomes (e.g. detecting a `sync` conflict) reads exit codes and stderr, not JSON.
- **Stack order validator:** `validate_stack_order(spec_text: str) -> list[str]` — returns every
  task-key in the spec in document order (no sorting — this *is* the order) after confirming no
  task's `Depends on:` entry appears later in the list than the task itself. Raises the same
  dangling-reference/cycle errors `parse_task_dependencies` already raises today, plus a new
  out-of-order error naming the offending task and which dependency follows it; this is an extension
  of that same function, not a parallel implementation. Called fresh on every invocation — its
  result is never cached or persisted across calls.
- **Task readiness checker:** `is_task_eligible(task_work_item_id: str, dependency_ids: list[str]) -> Literal["eligible", "waiting", "blocked"]`
  — `"eligible"` once every dependency has reached "ready" (`pr_url` set); `"waiting"` while any are
  still short of that; `"blocked"` if any dependency reached `dev_team.py`'s `failed` terminal state.
  No `base_branch` in the return value — stack position determines basing, not this check.
- **`ensure-feature-branch`:** given an epic id, checks `git branch -r | grep <feature-prefix><epic-id>`;
  if absent, `git checkout -b feature/<epic-id>-<slug> origin/main && git push origin feature/<epic-id>-<slug>`
  with no other changes. Checks for a locally-uncommitted spec file matching the epic (via
  `documentation.dev-specs.search`); if found uncommitted, commits it to a new branch off the
  feature branch and opens a PR against it via the existing `create-pr` skill. Runs
  the `init` operation with the feature branch itself as `<trunk>`, not `main` — confirmed working
  against a non-default trunk branch.
- **`ensure-working-branch` (replaces step 4b/4d/4e/4f of the ADR-296 version):** `register_in_stack(task_work_item_id: str) -> None`
  — reads the validated document order; if this task is first, its base is the feature branch
  (post-`ensure-feature-branch`). Otherwise, checks the immediate predecessor's context file for
  `added_to_stack: true`; if not set, recurses on the predecessor first (creating it as an empty
  branch and registering it, via the same function, before continuing) — walking back only as far as
  needed to reach an already-registered ancestor. Once the predecessor is registered, checks it out
  and runs the `add` operation for this task (creates and registers the branch locally, per
  `gh-stack`'s own documented behavior of operating "while on the topmost branch of a stack"), then
  verifies `git rev-parse --abbrev-ref HEAD` equals `<working-branch-name>` and not the feature
  branch (closes #126; hard stop on mismatch). Pushes the new branch (`git push -u origin
  <working-branch-name>` — `add` itself doesn't push) and only once that succeeds writes
  `added_to_stack: true` via `use-context-file` to the context file of *every* task it registered in
  this call (itself, plus any ancestors it had to backfill), not only its own. This registration step
  is unconditional — it never checks whether
  this task's own real dependencies are ready; that's the separate Task readiness checker, consulted
  by `concurrent_schedule.py` before a task is even spawned, not by this step.
- **`create-pr-from-context` (extended):** if the task's context file has `added_to_stack: true`,
  runs `gh stack submit` for that task's branch (no explicit `base` argument needed or passed —
  `gh stack` already knows it) and reads the resulting PR URL from its output; otherwise falls back
  to the existing `create-pr` skill with an explicitly passed `base_branch` unchanged, for the one
  case that's never part of a stack (the spec's own PR from `ensure-feature-branch`). Closes #129 by
  removing the separately-threaded `base_branch` value for the stack case rather than by adding
  stricter validation around it.
- **Stack PR event detector:** `detect_next_stack_event(epic_id: str) -> StackEvent | None`, where
  `StackEvent` is one of `{"type": "review_comment" | "ci_failure", "task_work_item_id": str}` or
  `{"type": "task_merged", "task_work_item_id": str}`. Uses the `view` operation only to enumerate
  current stack membership and each entry's PR link — `view` carries no review-comment or CI-check
  data itself — then reuses `pr_event_detector.py`'s existing per-PR GitHub API/MCP calls, unchanged,
  against each linked PR, compared against per-task `last_seen_review_comment_id`/
  `last_seen_ci_conclusion` context-file fields (same fields ADR-296 introduced, reused unchanged).
  Scans in stack-position order and returns the *first* actionable
  task found, never a batch — `None` if nothing fired. For a `review_comment`/`ci_failure` result, it
  runs `git checkout <that task's working_branch>` itself before returning, so the worktree is
  correctly positioned by the time anything downstream sees the result. For `task_merged`, it updates
  that task's tracking state internally (no checkout needed) and returns the result only so the
  caller can decide whether every target task is now merged.
- **`stack_pr_poll.py`:** `poll(epic_id: str, max_seconds: int = 480) -> Literal["conflict"] | Literal["epic_complete"] | {"task_work_item_id": str, "event": Literal["review_comment", "ci_failure"]} | Literal["no_change"]`
  — same bounded-blocking-loop shape as `watch_pr_poll.py`. Each iteration: runs the `sync`
  operation; if it reports a conflict, returns `"conflict"` immediately (worktree left mid-rebase,
  same as `rebase_onto`'s existing contract, just now reached via `sync`). On a clean sync, calls the
  Stack PR event detector; a `task_merged` result updates internal tracking silently and the loop
  continues without returning, unless every task in the target set is now merged, in which case it
  returns `"epic_complete"`. A `review_comment`/`ci_failure` result — worktree already checked out to
  that task's branch by the detector — is returned immediately as `{"task_work_item_id", "event"}`.
  Otherwise the loop sleeps and repeats until `max_seconds` elapses, returning `"no_change"`.
  Non-interactive throughout, consistent with the mediated-agent guidance in `github/gh-stack`'s own
  `skills/gh-stack/SKILL.md`: always pass explicit positional arguments, never the interactive TUI.
  `sync`'s own outcome (clean vs. conflict) is read from its exit code/stderr, not JSON — `sync`
  doesn't support `--json` (see the `work-with-stacked-prs` operations table); only the Stack PR
  event detector's `view` call parses JSON.
- **`monitor-stack`:** context-file fields `watch_worktree_path`/`watch_worktree_branch` (this
  session's own worktree, same as `monitor-pr`) are now recorded once per *epic* rather than once per
  task — the monitor's context lives on the epic/feature-work-item's own tracked record, not a
  single task's context file, since it now spans every task in the stack.

### Key Classes

- **`concurrent_schedule.py` (extended)** — stays a bare script with no MCP credentials, exactly the
  same constraint that already keeps it from spawning agents itself. `<epic-id>` for the live check
  below comes from parsing the spec's own `> **Epic:** [<key>](...)` header line out of the
  `spec_path` text the script already loads (per `find_spec_file()`) — the only local, MCP-free
  source of the epic key available to a bare script; `ensure-working-branch`'s own epic-discovery
  steps (4a/4c) aren't reachable here since 4c specifically needs the Jira MCP tool.
  `bootstrap_needed` is gated on a live check — `git branch -r | grep feature/<epic-id>` (pure git,
  no MCP needed), the same check `ensure-feature-branch` itself does as its own first step — never
  on whether the target's own data
  file exists, deliberately: gating on the data file would risk looping forever if the file is never
  written on a `bootstrap_needed` call, and would also force re-triggering `ensure-feature-branch`
  for a second, different target that happens to land on an already-bootstrapped epic. With a live
  branch check instead, the script still persists its data file on every call exactly as
  `_load_or_initialize_data` already does today (unrelated to the bootstrap signal), returns
  `{"status": "bootstrap_needed"}` only while the feature branch doesn't exist yet, and — once
  `concurrent-orchestrate` runs `ensure-feature-branch` and the branch exists — proceeds normally on
  the very next call, whether that call is a retry of the same target or a different target hitting
  the same, now-already-bootstrapped epic. Eligibility per not-yet-started task uses the Task
  readiness checker's simplified rule (every real dependency ready — see Key Design Decisions).
- **`ensure-working-branch` (extended)** — see Interfaces; the dependency-aware base-branch
  computation (ADR-296's steps 4b, 4d, 4e, 4f) is replaced wholesale by the recursive
  stack-registration logic described above. Steps 4a (search the repo for a spec file) and 4c (query
  the tracker for the parent feature-work-item if 4a found no spec) are both retained unchanged — this
  feature still needs the epic id from one of them to know which feature branch to check for or
  bootstrap, including in the single-task path below, where `ensure-working-branch` must discover the
  epic id before it can even check whether `ensure-feature-branch` needs to run. Also the
  single-task-path trigger for `ensure-feature-branch`: when
  `/implement <key>` dispatches straight to `workflow-orchestrate` with no `concurrent-orchestrate`
  involved at all, this step is what discovers the epic has no feature branch/stack yet and bootstraps
  it itself, safely, since it's the only task running. For a `concurrent-orchestrate`-spawned task,
  this same check always finds the bootstrap already done (concurrent-orchestrate guaranteed it
  before spawning anything), so no race occurs in practice — one shared check covers both paths. The
  worktree-freshness check (step 1) is unchanged. Step 5 (raw `git checkout -b`) is also subsumed —
  the `add` operation itself creates and checks out the branch, so no separate raw branch-creation
  step runs after it.
- **`monitor-stack` (new skill)** — structurally mirrors `monitor-pr`'s poll-loop shape (worktree
  freshness check, checkout, poll, react, repeat) but polls the whole epic's stack via
  `stack_pr_poll.py` instead of one task's PR via `watch_pr_poll.py`. Reacts to exactly the single
  outcome each call returns, never a batch: `"conflict"` spawns the developer agent for
  `resolve-rebase-conflict`; `{"task_work_item_id", "event"}` spawns `fix-pr` directly, with no
  checkout of its own to do first, since `stack_pr_poll.py` already positioned the worktree;
  `"epic_complete"` cleans up and halts; `"no_change"` just calls `poll()` again. `monitor-stack` never
  reasons about which branch it should be on — that's entirely the script's job now.
- **`/watch-stack` (new command)** — parallel structure to the retired `/watch-pr`: its entire job
  is spawning `monitor-stack` via the `Agent` tool with `isolation: "worktree"`.

### Data Flow

1. A human invokes `/implement`. A single key dispatches to `workflow-orchestrate` exactly as
   today — the single-task path (step 2 below). An "up to" target or an explicit list dispatches to
   `concurrent-orchestrate` — the concurrent path (steps 3–4 below). Both paths converge from step 5
   onward.
2. **Single-task path:** inside that one task's `workflow-orchestrate` run, `ensure-working-branch`
   checks whether its epic already has a feature branch and stack. If not — nothing else is running
   concurrently, so no coordination is needed — it invokes `ensure-feature-branch` itself, directly,
   before registering its own branch. This is what lets a human start an epic with a single first
   item and still get a real stack that later concurrent or single-task runs can build on.
3. **Concurrent path:** `concurrent-orchestrate` invokes `concurrent_schedule.py`. While the epic's
   feature branch doesn't exist yet on the remote (a live check, not a data-file check — see the
   `ensure-feature-branch` decision's Consequences), the script — a bare script with no MCP
   credentials, the same constraint that already keeps it from spawning agents itself — returns
   `{"status": "bootstrap_needed"}` instead of computing a batch (it still persists its own
   per-target data file on this call as it always does, just gates the *returned status* on the live
   check). `concurrent-orchestrate` (the skill, running with real MCP credentials) is what actually
   invokes `ensure-feature-branch` — creating the feature branch if missing, committing/PR-ing the spec if
   it was uncommitted, and running the `init` operation — then re-invokes `concurrent_schedule.py`.
   This single-threaded, once-per-epic sequencing (one long-lived `concurrent-orchestrate` session,
   never itself parallelized) is what avoids two tasks racing to bootstrap the same feature branch
   or stack.
4. On every subsequent call, `concurrent_schedule.py` validates the epic's document order (see the
   Stack order validator) and determines which not-yet-started tasks are now eligible — every real
   dependency has reached "ready" (the Task readiness checker's simplified rule) — and returns a
   spawn batch, same shape as ADR-296's `compute_next_batch` otherwise (still enforces the repo-wide
   concurrency cap, still reports `"blocked"`/`"complete"`).
5. `concurrent-orchestrate` spawns each batch entry's `workflow-orchestrate` run with
   `isolation: "worktree"`, exactly as before. Inside that run, `ensure-working-branch` registers
   this task's branch into the stack — recursively backfilling any not-yet-registered ancestor first
   (see "Branch registration is lazy, recursive..."), then adding its own branch on top — verifies
   HEAD is genuinely that new branch and not the feature branch (closes #126), then writes
   `added_to_stack: true`. This registration is unconditional and structural; it doesn't wait on
   this task's own real dependencies, which the Task readiness checker already confirmed were ready
   before this task was ever spawned (step 4).
6. Later in that same task's pipeline, once validation passes, `dev_team.py`'s existing `creating-pr`
   state invokes `create-pr-from-context` unchanged; internally it now runs the `submit` operation
   for this task's branch instead of computing and passing a `base` argument, so the PR always opens
   against the correct base by construction (closes #129).
7. The moment the *first* task in the epic's target set reaches hand-off, `concurrent-orchestrate`
   auto-starts one `monitor-stack` monitor for the whole epic (a local background `Agent`, its own
   fresh `isolation: "worktree"`) — not one per task. `/watch-stack <epic-key>` covers the manual
   fallback if the auto-start never happened.
8. `monitor-stack` calls `stack_pr_poll.py` in a loop. Each call runs the `sync` operation for the
   entire stack first (cascading rebase across every entry whose base moved or whose predecessor
   merged, entirely inside `gh stack`'s own mechanics) — silently, unless it hits a genuine conflict,
   in which case the call returns `"conflict"` immediately (step 10). On a clean sync, it looks for
   the first task (in stack order) with a new review comment or CI failure, checks out *that task's*
   branch itself, and returns `{"task_work_item_id", "event"}` — the worktree is already correctly
   positioned by the time `monitor-stack` sees the result. A task's merge is tracked silently and never
   returned on its own; `"epic_complete"` is returned only once every target task has merged (step
   11). Otherwise the call returns `"no_change"` once its bounded window elapses.
9. `monitor-stack` reacts to exactly the one thing each call returned — never a batch, since the
   worktree can only be on one branch at a time and the script already resolved that ambiguity before
   returning: a `{"task_work_item_id", "event"}` result spawns `fix-pr` (nested, inheriting
   `monitor-stack`'s already-correctly-positioned worktree) with no checkout of its own required; a
   `"no_change"` result just calls `poll()` again immediately.
10. `"conflict"` routes to the developer agent running `resolve-rebase-conflict`, unchanged contract
    from ADR-296. `"resolved"` re-runs the `sync` operation to complete, then `monitor-stack` returns to
    step 8; `"unresolved"` aborts the rebase and stops the whole epic's monitor (see consequence in
    the corresponding Key Design Decision).
11. As each task's PR merges, the `sync` operation retargets and rebases whatever remains above it
    automatically, and `stack_pr_poll.py` stops tracking that PR internally. `monitor-stack` halts only
    when `stack_pr_poll.py` returns `"epic_complete"` — every task in the target set merged.

## Related Features

| Feature | Scope |
|---|---|
| (this feature) | Full-takeover replacement of ADR-296's dependency-graph/rebase-mechanic/`monitor-pr` fleet with GitHub's native stacked-PR feature and `gh-stack` CLI, plus the new feature-branch/spec-PR bootstrap |
| [ADR-296: Concurrent Development](https://jodasoft.atlassian.net/browse/ADR-296) (`_spec_ConcurrentDevelopment.md`) | The existing implementation this feature retires; the single-task implement/validate/review/signoff pipeline it built is reused unchanged |
| [ADR-315: Cross-spec/cross-epic task dependencies](https://jodasoft.atlassian.net/browse/ADR-315) | Still out of scope; unaffected by the switch to `gh stack` |

## Open Questions

- [ ] **Simultaneous bootstrap from two different targets on the same epic.** Because
  `bootstrap_needed` is a live check (does the feature branch exist remotely?), two truly
  simultaneous `/implement` runs against different targets on the same not-yet-bootstrapped epic
  (e.g. `up to ADR-5` and `up to ADR-8` launched at nearly the same moment) could both observe the
  branch doesn't exist yet and both invoke `ensure-feature-branch` concurrently — a real race the
  "single-threaded, once-per-epic" framing only covers *within* one target's own session, not across
  two independent sessions. `ensure-feature-branch`'s check-before-act steps handle a *sequential*
  re-run safely, but not necessarily two processes racing on the same `git push`/branch-creation at
  once. `> TBD: likely acceptable given this system's actual current usage pattern (documented
  elsewhere as single-user, no concurrent multi-target runs today), but not structurally prevented —
  worth a note in implementation, not necessarily a fix.`
- [ ] **Cross-worktree `gh stack` state (highest-risk item).** Each task's `workflow-orchestrate` run
  operates in its own isolated git worktree. `gh stack`'s local notion of "which branch is currently
  topmost" needs to be visible and correct from a *different* worktree than the one that last ran
  `gh stack add`, for the successor task's `ensure-working-branch` to add itself correctly. `> TBD:
  unconfirmed from documentation — the feasibility spike (see the "Known upstream risk" decision)
  must verify this before any other task in the breakdown builds on it.`
- [ ] **`gh stack submit` per-entry granularity — evidence leans against per-branch targeting.**
  GitHub's own CLI reference documents `submit`'s scope as "Entire stack; all branches included by
  default," with no argument to target one branch/entry — stronger evidence than "unconfirmed" that
  the "`create-pr-from-context` runs `submit` for just this task's branch" design (the `#129` fix)
  may not be directly supported as described. `> TBD: the spike must confirm this either way; if
  submit truly can't be scoped to one entry, the `#129` decision needs a concrete reconciliation —
  e.g. gating submission on whether every entry below the newly-added one is already a real PR (safe
  to submit the whole stack), or sourcing a task's base fresh from the `view` operation at PR-creation
  time and creating its PR directly (still satisfying the "never trust a duplicated stale value"
  principle even without using `submit` itself) — neither is designed here, pending the spike's
  finding.`
- [ ] **Conflict-resolution mechanics under `gh stack` — plain `git rebase --continue` may not be
  enough.** Two findings suggest `resolve-rebase-conflict`'s existing plain-git conflict-resolution
  contract may not cleanly apply to a `gh stack sync` conflict: GitHub's docs describe resuming a
  `gh stack rebase` via `gh stack rebase --continue` specifically (implying stack-level cascade state
  a bare `git rebase --continue` wouldn't advance), and separately that `sync` "aborts in
  non-interactive terminals" when it hits real divergence — which could mean a `sync` conflict
  doesn't even leave the plain mid-rebase git state (`.git/rebase-merge`) `resolve-rebase-conflict`
  expects to find in the first place. `> TBD: the spike must exercise a real `sync` conflict end to
  end and confirm what git state it actually leaves behind, and whether `resolve-rebase-conflict`'s
  existing contract needs any adjustment as a result — see the "Rebase/sync conflicts..." decision.`

## Related Docs

- `_spec_ConcurrentDevelopment.md` — the ADR-296 implementation this feature replaces; read in full
  to determine exactly what's retired vs. reused
- `_doc_Projects.md` — repository layout and plugin structure
- [GitHub issue #126: Ensure working branch must create task branches, not work from feature branches](https://github.com/jodavis/agent-plugins/issues/126) — closed by the branch-identity guardrail decision
- [GitHub issue #129: PR creation is not using the correct base branch](https://github.com/jodavis/agent-plugins/issues/129) — closed by the `gh stack submit` decision
- [GitHub Changelog: Stacked pull requests are now in public preview (2026-07-30)](https://github.blog/changelog/2026-07-30-stacked-pull-requests-are-now-in-public-preview/)
- [About stacked pull requests](https://docs.github.com/en/pull-requests/get-started/about-stacked-prs)
- [Stacked pull requests CLI commands reference](https://docs.github.com/en/pull-requests/reference/stacked-prs-cli-commands)
- [Stacked pull requests REST and GraphQL APIs](https://docs.github.com/en/pull-requests/reference/stacked-pull-requests-rest-and-graphql-apis)
- [github/gh-stack repository](https://github.com/github/gh-stack) and its
  [`skills/gh-stack/SKILL.md`](https://github.com/github/gh-stack/blob/main/skills/gh-stack/SKILL.md)
  (written for agentic/non-interactive use — directly relevant to how this pipeline drives it)
- Two unrelated, differently-maintained tools of the same name, noted here only to avoid confusion
  during implementation: [VladimirAnaniev/gh-stack](https://github.com/VladimirAnaniev/gh-stack),
  [boneskull/gh-stack](https://github.com/boneskull/gh-stack)

## Tasks

> **Legend:** 🤖 = agent task · 🧑 = human operator task

---

### [ADR-370: `gh stack` feasibility spike](https://jodasoft.atlassian.net/browse/ADR-370) 🤖

**Depends on:** — none —

A scoped spike (scratch repo, real GitHub remote) that confirms or refutes every unresolved
technical assumption this spec depends on, before any other task builds on `gh stack`. Produces a
short findings note (not shipped code) that later tasks can cite. "Not shipped code" describes
what the PR *contains* — a findings document, not production code — not an exemption from the
normal task lifecycle: this task still goes through the standard implement → PR → hand-off
pipeline like every other task, since ADR-371's own eligibility (per the Task readiness checker)
depends on this task reaching "ready" (`pr_url` set). The findings note is committed as
`_findings_GhStackSpike.md` at the repo root.

- [ ] Create a real stack across two branches in one repo, then check its state from a *second*,
  independently-cloned worktree of the same repo — confirms or refutes whether `gh stack`'s local
  notion of "topmost branch"/stack membership is visible and correct across worktrees (the
  highest-risk Open Question)
- [ ] Attempt `gh stack submit` for a single, newly-added topmost branch and observe whether it
  submits only that branch or the entire stack (the `#129`-adjacent Open Question)
- [ ] Deliberately create a genuine rebase conflict during `gh stack sync`, in a non-interactive
  terminal, and record: what git state it leaves behind (`.git/rebase-merge` present or not,
  matching `resolve-rebase-conflict`'s expectation, or something else), and whether completing it
  requires a plain `git rebase --continue` or `gh stack rebase --continue`
- [ ] Confirm whether re-running `gh stack init` against a trunk that already has a stack anchored
  to it errors, resets, or silently no-ops (informs `ensure-feature-branch`'s idempotency, though
  the spec's own explicit existence-check already sidesteps needing this to be a no-op)
- [ ] Findings are written up (which assumptions held, which didn't, and what changes as a result)
  and shared before Tasks 2–9 begin

---

### [ADR-371: `work-with-stacked-prs` skill and `gh_stack.py` module](https://jodasoft.atlassian.net/browse/ADR-371) 🤖

**Depends on:** ADR-370

Adds the sole owner of every direct `gh stack` CLI invocation — a prose skill for agent-driven
calls and a sibling `gh_stack.py` module bare scripts import directly — plus the `gh`/`gh-stack`
extension preflight.

- [ ] `work-with-stacked-prs` skill documents each operation (`init`, `add`, `submit`, `sync`,
  `view`, `merge`) by name, per the spec's operations table, reflecting ADR-370's actual findings
  for `--json` support and non-interactive behavior per operation
- [ ] `gh_stack.py` exposes the same operations as plain Python functions, each shelling out via
  `subprocess`; importable directly by other scripts (no MCP involved)
- [ ] Preflight check: verifies `gh extension list` includes `github/gh-stack` specifically (not
  either unrelated same-named community tool); offers to install it if missing; hard-stops if the
  user declines, with no fallback stacked-PR mechanism
- [ ] Given `github/gh-stack` is not installed, when the preflight runs and the user accepts the
  install offer, then the extension is installed and the calling flow proceeds
- [ ] Given the user declines the install offer, when the preflight runs, then it hard-stops with a
  clear message — no epic bootstrap or task work proceeds
- [ ] Unit tests for `gh_stack.py`: each function invokes the expected `gh stack <cmd>` arguments,
  correctly surfaces exit-code/stderr failures for operations without `--json` support
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-372: Stack order validator and `dev-spec-task-breakdown` authoring rule](https://jodasoft.atlassian.net/browse/ADR-372) 🤖

**Depends on:** — none —

Extends `task_dependencies.py`'s existing validation so a spec's own task-list order can serve as
its stack order, and formalizes the authoring convention that already holds informally today.

- [ ] `validate_stack_order(spec_text: str) -> list[str]` extends `parse_task_dependencies`: returns
  every task-key in document order after confirming no task's `Depends on:` entry appears later in
  the list than the task itself; raises the same dangling-reference/cycle errors as today, plus a
  new out-of-order error naming the offending task and which dependency follows it
- [ ] `dev-spec-task-breakdown` step 1 gains the explicit rule: every task is written after all of
  its own `Depends on:` entries
- [ ] Given a spec whose tasks are listed in a valid dependency order, when `validate_stack_order`
  runs, then it returns that same order unchanged
- [ ] Given a spec where a task is listed before one of its own dependencies, when
  `validate_stack_order` runs, then it raises a clear error naming both tasks
- [ ] Unit tests: valid order, out-of-order pair, dangling reference, and a two/three-task cycle
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-373: `ensure-feature-branch` skill](https://jodasoft.atlassian.net/browse/ADR-373) 🤖

**Depends on:** ADR-371

The new bootstrap: creates an epic's feature branch, commits and PRs its (possibly
locally-uncommitted) spec file against it, and initializes the epic's stack — all four steps
check-before-act, so the whole skill is safely re-runnable.

- [ ] Checks whether `feature/<epic-id>-<slug>` exists on the remote; if not, creates it from
  `origin/main` and pushes it immediately with no other changes
- [ ] Checks for a locally-uncommitted spec file matching the epic; if found, commits it to a new
  branch off the feature branch and opens a PR against it via the existing `create-pr` skill
  (explicit `base`, unchanged behavior) — skipped if already committed
- [ ] Checks whether a stack is already anchored to this trunk (via the `view` operation) before
  running `init` with the feature branch as trunk — skipped if one already exists
- [ ] Given no feature branch exists yet for an epic, when `ensure-feature-branch` runs, then the
  branch exists on the remote afterward with no content beyond `main`
- [ ] Given the epic's spec file is untracked locally, when `ensure-feature-branch` runs, then a PR
  exists targeting the feature branch containing that file
- [ ] Given `ensure-feature-branch` is run a second time for the same, already-bootstrapped epic,
  when it runs, then every step is skipped and it completes as a no-op
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-374: Concurrent scheduler, Task readiness checker, and `concurrent-orchestrate` bootstrap flow](https://jodasoft.atlassian.net/browse/ADR-374) 🤖

**Depends on:** ADR-372, ADR-373

These ship together — the simplified readiness rule, the scheduler that consumes it and reports
`bootstrap_needed`, and the orchestrator skill that's the only one of the three with MCP
credentials to act on that report.

- [ ] `is_task_eligible(task_work_item_id, dependency_ids) -> Literal["eligible", "waiting", "blocked"]`
  simplified: `"eligible"` once every dependency has reached "ready" (`pr_url` set) — no
  `base_branch` in the return value, no "all but one merged" exception
- [ ] `concurrent_schedule.py`'s `compute_next_batch` uses the simplified rule; `<epic-id>` is
  parsed from the spec's own `> **Epic:** [<key>](...)` header line, out of the `spec_path` text
  the script already loads — the only local, MCP-free source available to a bare script;
  `bootstrap_needed` is gated on a live check (`git branch -r | grep feature/<epic-id>`, the same
  check `ensure-feature-branch` itself does first) — never on whether this target's own data file
  exists, so it cannot loop forever waiting on a file nothing writes to resolve it. The data file
  is still persisted on every call exactly as it is today, independent of this signal.
- [ ] `concurrent-orchestrate` invokes `ensure-feature-branch` on `bootstrap_needed`, then re-invokes
  the script; no longer pre-populates a spawned task's `base_branch` context field (removed
  entirely)
- [ ] `compute_next_batch`'s "up to `<key>`" target-set computation changes from ADR-296's
  dependency-closure-only form to every task from the start of the epic's document order through
  `<key>` inclusive — a deliberate behavior change (see the "'Up to Task X'..." Key Design
  Decision), not just an implementation detail
- [ ] Given a task with two independent dependencies, when both reach "ready" (neither merged),
  then the task is reported eligible
- [ ] Given a task with one dependency that reached `failed`, when eligibility is checked, then it
  reports `"blocked"`
- [ ] Given the same target's second call, after `ensure-feature-branch` has created the feature
  branch in response to the first call's `bootstrap_needed`, when `compute_next_batch` runs again,
  then it finds the branch now exists and proceeds to compute a batch — never returns
  `bootstrap_needed` a second time for a branch that already exists
- [ ] Given a second, different target's first call against an already-bootstrapped epic, when
  `compute_next_batch` runs, then the live check already finds the feature branch exists and it
  proceeds directly to computing a batch, with no `bootstrap_needed` round-trip at all
- [ ] Given "up to `<key>`" where `<key>` depends only on the first task in the epic, when the
  target set is computed, then it includes every task from the first through `<key>`, not just the
  two that are directly dependency-related
- [ ] Unit tests for `is_task_eligible` (all-ready, one-waiting, one-failed) and for
  `compute_next_batch`'s `bootstrap_needed` detection (both the same-target retry and
  different-target cases) and its inclusive "up to" target-set
  computation
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-375: `ensure-working-branch` recursive stack registration (closes #126)](https://jodasoft.atlassian.net/browse/ADR-375) 🤖

**Depends on:** ADR-371, ADR-372, ADR-373

Replaces the old dependency-aware base-branch computation with lazy, recursive branch registration,
and the guardrail that closes the feature-branch/working-branch conflation bug.

- [ ] Steps 4b, 4d, 4e, 4f replaced: reads the validated document order (ADR-372); if this task is
  first, its base is the feature branch (invoking `ensure-feature-branch` itself first if the
  epic hasn't been bootstrapped yet — the single-task-path trigger); otherwise checks the immediate
  predecessor's `added_to_stack` field, recursing to backfill an unregistered predecessor (as an
  empty branch) before continuing, walking back only as far as needed
- [ ] Steps 4a and 4c retained unchanged (spec-file search and Jira-parent fallback — still needed
  to discover the epic id)
- [ ] Step 5 ("Prepare the working branch," ADR-296's raw `git checkout -b <working-branch>
  origin/<base-branch>`) is also subsumed, not left running alongside the new flow: the `add`
  operation itself both creates and checks out the branch, so nothing after step 4's replacement
  logic performs a separate raw branch-creation step
- [ ] Runs the `add` operation for this task's own branch, then verifies
  `git rev-parse --abbrev-ref HEAD` equals the computed working-branch name and *not* the feature
  branch — hard stop on mismatch
- [ ] Pushes the new branch explicitly (`add` itself doesn't push); writes `added_to_stack: true` —
  added as a named `PipelineContext` field, not a passthrough extra — only after the push succeeds,
  to every task's context file it registered in this call (itself and any backfilled ancestors)
- [ ] Given a task whose stack predecessor already exists, when `ensure-working-branch` runs, then
  it registers only its own branch, no backfilling needed
- [ ] Given a task whose predecessor is an unstarted human task with no branch yet, when
  `ensure-working-branch` runs, then it creates and pushes an empty placeholder branch for the
  predecessor first, then its own branch on top
- [ ] Given `ensure-working-branch` completes successfully, when its result is checked, then HEAD is
  never the feature branch (closes #126)
- [ ] Given a single `/implement <key>` run against an epic with no feature branch yet, when
  `ensure-working-branch` runs, then it bootstraps the feature branch/stack itself before
  registering its own branch
- [ ] Unit/integration tests: no backfill needed, one-level backfill, multi-level backfill, and the
  branch-identity mismatch hard stop
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-376: `create-pr-from-context` stack-aware PR submission (closes #129)](https://jodasoft.atlassian.net/browse/ADR-376) 🤖

**Depends on:** ADR-371, ADR-375

Task PRs for stack-registered tasks are submitted via `gh stack submit`, removing the
separately-threaded `base_branch` value that could go stale.

- [ ] If the task's context file has `added_to_stack: true`, runs the `submit` operation for that
  task's branch — no explicit `base` argument constructed or passed
- [ ] Otherwise falls back to the existing `create-pr` skill's explicit-`base` behavior unchanged,
  for the one PR that's never part of a stack (the epic's own spec PR)
- [ ] Given a stack-registered task ready to open its PR, when `create-pr-from-context` runs, then
  the resulting PR's base is exactly what `gh stack` established at registration time, never `main`
- [ ] Given ADR-370's spike found `submit` cannot be scoped to a single entry, this task implements
  whatever reconciliation the spike's findings called for instead of the originally-assumed
  per-branch `submit` (see the spec's Open Question on this)
- [ ] Tests covering both the stack and non-stack (spec PR) paths
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-377: Stack PR event detector and `stack_pr_poll.py`](https://jodasoft.atlassian.net/browse/ADR-377) 🤖

**Depends on:** ADR-371

The detection half of the epic-wide monitor: a bounded blocking poll loop that does every
mechanical step itself — silent sync, checkout-before-return — so the caller only ever reacts to
one already-positioned, actionable item at a time.

- [ ] `detect_next_stack_event(epic_id) -> StackEvent | None`: uses the `view` operation only to
  enumerate stack membership/PR links (no review/CI data of its own), then reuses
  `pr_event_detector.py`'s existing per-PR review-comment/CI-check calls, unchanged, against each
  linked PR; scans in stack-position order, returns the *first* actionable task; for a
  `review_comment`/`ci_failure` result, checks out that task's branch itself before returning
- [ ] `poll(epic_id, max_seconds=480)`: runs `sync` every iteration (silent on success; returns
  `"conflict"` immediately on a genuine conflict, per ADR-370's findings on what state that leaves);
  on a clean sync, calls the detector; a `task_merged` result is untracked silently and the loop
  continues, unless every target task is now merged (`"epic_complete"`); otherwise returns the one
  checked-out `{"task_work_item_id", "event"}` pair, or `"no_change"` once the window elapses
- [ ] Given a review comment fires for a task other than the one last checked out, when `poll`
  returns, then the worktree is already on that task's branch
- [ ] Given two conditions would fire in the same window (e.g. two tasks each with a review
  comment), when `poll` returns, then only the first (by stack position) is reported — the second
  is picked up on the very next call
- [ ] Given `sync` reports a conflict, when `poll` returns, then it returns `"conflict"` immediately
  without checking for review/CI events that pass
- [ ] `poll`'s loop/timeout mechanics are unit-tested with an injectable sleep/clock (no real
  wall-clock sleeps)
- [ ] Unit tests for `detect_next_stack_event`: each event type individually, none fired, and an
  already-seen item never re-firing
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-378: `monitor-stack` skill, `/watch-stack` command, and retirement of `monitor-pr`](https://jodasoft.atlassian.net/browse/ADR-378) 🤖

**Depends on:** ADR-374, ADR-376, ADR-377

The epic-wide monitor itself: one long-lived agent per epic that reacts to exactly what
`stack_pr_poll.py` returns, plus retiring the per-task fleet it replaces. Depends on ADR-374 as
well as ADR-376/ADR-377 — the auto-start wiring below is a direct edit to `concurrent-orchestrate`,
the skill ADR-374 builds, and neither ADR-376 nor ADR-377 pulls that dependency in transitively.

> **Naming note:** this spec's own `plugins/dev-team/skills/` still has the pre-rename skill
> named `watch-pr` as of the commit this branch is based on, but the repo's `main` branch has
> already renamed it to `monitor-pr` (confirmed directly against `main`'s checkout, not just this
> worktree). This task should rebase onto (or otherwise pick up) that rename before starting, so
> "retire `monitor-pr`" and the `resolve-rebase-conflict` caller-reference fix below are both
> operating on the skill's actual current name, not this branch's stale one.

- [ ] Auto-started by `concurrent-orchestrate` (ADR-374) the moment the first task in an epic's
  target set reaches hand-off, spawned with its own fresh `isolation: "worktree"`
- [ ] Reacts to exactly the one outcome each `poll()` call returns: `"conflict"` spawns the
  developer agent for `resolve-rebase-conflict` (unchanged contract) and re-runs `sync` on
  `"resolved"`; `{"task_work_item_id", "event"}` spawns `fix-pr` directly, no checkout of its own
  needed; `"epic_complete"` cleans up and halts; `"no_change"` polls again
  immediately
- [ ] `/watch-stack <epic-key>` spawns `monitor-stack` via the `Agent` tool with
  `isolation: "worktree"`, the manual fallback matching `/watch-pr`'s existing pattern
- [ ] `monitor-pr` skill, `rebase_mechanic.py`, the retired base-branch-selection half of
  `is_task_eligible` (already removed in ADR-374), and the `dependency_merged`/`base_updated`
  branches of the original `pr_event_detector.py` (already removed in ADR-377) are deleted outright
  — not kept as a fallback path
- [ ] `resolve-rebase-conflict/SKILL.md`'s two hardcoded `dev-team:monitor-pr` caller references
  updated to `dev-team:monitor-stack`
- [ ] Given a task's PR receives a review comment after hand-off, when `monitor-stack` is running,
  then `fix-pr` addresses it without any other task in the epic being affected
- [ ] Given every task in the target set has merged, when `monitor-stack` next polls, then it cleans
  up its own worktree/branch and halts
- [ ] Given a sync conflict `resolve-rebase-conflict` can't resolve, when `monitor-stack` detects
  `"unresolved"`, then the worktree is left clean and the monitor has stopped, resumable via
  `SendMessage` or by restarting `/watch-stack`
- [ ] PR description reports, for each Given/When/Then scenario above, whether it was verified
  (manually or via automated test) and the result observed

---

### [ADR-379: Author design documentation](https://jodasoft.atlassian.net/browse/ADR-379) 🤖

**Depends on:** ADR-370, ADR-371, ADR-372, ADR-373, ADR-374, ADR-375, ADR-376, ADR-377, ADR-378

Unconditional final task: once implementation completes, write `_doc_StackedPRs.md` per
`write-repo-documentation`, and this spec (`_spec_StackedPRs.md`) persists afterward for
harvesting.

- [ ] `_doc_StackedPRs.md` written describing the shipped architecture
- [ ] Cross-references this spec and `_spec_ConcurrentDevelopment.md` (the mechanism it replaces)
