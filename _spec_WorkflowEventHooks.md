# Workflow Event Hooks

> **Status:** Draft
> **Epic:** [ADR-337](https://jodasoft.atlassian.net/browse/ADR-337)
> **Design:** — none
> **Architecture doc:** `_doc_WorkflowEventHooks.md` — authored by `dev-spec-task-breakdown`'s
> unconditional final "Author design documentation" task once implementation completes; this
> spec persists afterward for harvesting

## Overview

Today `.dev-team/config.yaml`'s `git-repo` section scatters project policy across four
independent, action-named blocks (`commit`, `push`, `create-pr`, `promote-pr`), each with its own
`enabled`/`when` prose — and none of it is actually read by the automated `workflow-orchestrate`
pipeline (`dev_team.py` never checks `enabled` or `when` for any of them; `push`/PR creation/PR
promotion happen unconditionally today, via a hardcoded `_commit_and_push()` call and two fixed
pipeline states). Separately, several behaviors the epic wants — assigning a work item to the
agent running it, transitioning it to "In Progress"/"In Review", and assigning the human reviewer
by name at hand-off — don't exist anywhere in the pipeline yet; hand-off's reviewer identity is
instead hardcoded behind a `$REVIEW_ASSIGNEE_EMAIL` environment variable.

This feature inverts the config's shape: instead of per-action blocks, a project declares, for
each named point in the pipeline's lifecycle (`before-implement`, `after-validate-success`,
`after-hand-off`, etc.), an ordered map of plain-language instructions to follow at that point,
each keyed by a short label. A new central mechanism actually executes these maps as part of the
automated pipeline — closing the gap where today's `enabled`/`when` fields are effectively
decorative — and the shipped default statements reproduce today's real behavior (commit, push,
create/promote PR) plus the new self-assignment, status-transition, and hand-off-assignment
behaviors the epic asks for. Keying each instruction by a label (rather than a bare list) lets a
more specific config tier override or disable just one default instruction — the same fine-grained
opt-out today's `enabled: false` fields gave per-block, now per-instruction, for free, via
`merge_config.py`'s existing recursive dict merge. The `REVIEW_ASSIGNEE_EMAIL` environment
variable is removed; the reviewer's identity becomes literal text a project writes into its own
`after-hand-off` instructions.

## Responsibilities & Boundaries

- **Owns:** the new `instructions:` config section (ordered map of label → instruction per named
  event); the event-name-per-pipeline-state mapping; the mechanism that executes an event's
  instructions (`workflow-worker`'s new before-/after-skill hook execution, and the matching
  lookup `workflow-script` gains for the `validating` run_script step); removal of
  `git-repo.commit`/`.push`/`.create-pr`/`.promote-pr`; removal of the `REVIEW_ASSIGNEE_EMAIL` env
  var from `final-sign-off` and `work-with-pr`; the `update-project-configuration` walkthrough for
  the new schema; the descriptive prose under the mermaid diagram in both
  `workflow-orchestrate/assets/implement-task-plan.md` and `fix-issue-plan.md` that currently says
  the `handoff` state's `final-sign-off` "converts the PR from draft to ready for review, assigns
  the Jira issue to the human reviewer, requests their GitHub review, and adds a Jira comment" —
  false once that work moves to `after-hand-off` instructions, needs updating to describe the new
  split (the diagram/transitions themselves are unchanged, only this prose is stale).
- **Does not own:** the pipeline state machine's transition table itself (`dev_team.py`'s
  `StateMachine`/`WorkflowDefinition` parsing, and both mermaid workflow files, entirely unchanged —
  no state is added or removed); the Jira/GitHub adapter operations event instructions ultimately call
  (`work-with-Jira-tasks`, `work-with-GitHub-issues`, `work-with-pr`, `commit-changes`,
  `create-pr-from-context` — all reused as-is); per-component internal commit granularity inside
  `implement-task`/`fix-draft`/`fix-pr`/the TDD trio (unchanged — those still make their own
  fine-grained commits regardless of this feature); event hooks for skills invoked *outside* the
  automated pipeline (a standalone `/dev-team:implement` or manual skill invocation does not
  consult `instructions:` at all — this is pipeline-only, matching the git-repo signals' existing
  scope).
- **Integrates with:**
  - `get-project-configuration` — schema gains `instructions:`; `git-repo` loses its four action
    blocks
  - `update-project-configuration` — the git-repo walkthrough section is rewritten around the new
    `instructions:` section
  - `workflow-worker` — gains outcome-aware before-/after-skill hook execution around every
    `spawn_agent` step (`creating-pr` and `handoff` included, unchanged in shape from today)
  - `workflow-script` — gains the same before-/after-success/after-failure/after lookup pattern,
    scoped to what `dev-team:script-runner`'s Bash-only toolset can actually do
  - `dev_team.py` / `workflow-orchestrate` assets — each `Step` gains an `EVENT_NAME`; descriptors
    gain an `event` field; mermaid workflow files and the state machine's transitions are otherwise
    unchanged
  - `final-sign-off` / `work-with-pr` — lose their hardcoded PR-promotion/reviewer-assignment
    steps and the `REVIEW_ASSIGNEE_EMAIL` lookup; that behavior now lives in `after-hand-off`
    config text, executed generically by the hook mechanism

## Key Design Decisions

### Event instructions are plain-language maps, executed by whichever agent already handles that pipeline step

_Context:_ The epic's own framing is a set of statements "to be followed," in the same register
as today's `git-repo.*.when` prose — not a structured DSL. Only `dev-team:developer` actually has
full Jira/GitHub/git tool access among the agents this pipeline spawns; `dev-team:reviewer` is
GitHub-PR-scoped only (no Jira), and `dev-team:researcher`/`dev-team:debugger` have neither. Each
instruction still runs inside whichever agent already handles that pipeline step — no new tooling
is added to any agent by this feature — so what a project can safely put in a given event's
instructions is bounded by that state's own agent, not uniform across every event (see the
`before-review` fix below, and the `validate`-scoped constraint noted elsewhere in this spec).

_Decision:_ `workflow-worker` — the shared wrapper every `spawn_agent` pipeline step already
routes through — is extended: before invoking `<skill>`, it looks up `before-<event>` from
project config (via `get-project-configuration`) and, if non-empty, follows those instructions
using whatever tools/skills are appropriate (exactly as an agent today follows a `git-repo.*.when`
description). After `<skill>` completes, `workflow-worker` follows the same pattern for the after
side, but with an outcome-aware, three-tier lookup: `after-<event>-success` if `<skill>` succeeded,
or `after-<event>-failure` if it failed — whichever matches the actual outcome — followed
unconditionally by `after-<event>` itself, every time, regardless of outcome. (`before-<event>` has
no success/failure variant — nothing has run yet to have an outcome at that point.) `<event>` is a
new `--event` argument workflow-orchestrate passes through from the descriptor's `event` field (see
below) — one extra argument alongside the existing `--skill`/`--skill-args`.

_Consequences:_ No new agent spawns for steps that already go through `workflow-worker` — hook
execution is additional instructions inside the same session, not an extra `Agent` call. A project
with no `instructions:` entries for a given key sees zero behavior change (empty/absent map =
nothing to follow, same as today for a skill with no hook mechanism at all). Outcome-aware
after-hooks are now a general capability of every event, not a validate-specific special case:
`after-validate-success`/`after-validate-failure` turn out to be this event's use of the same
three-tier pattern every other event now has too, rather than a one-off exception (see the next
decision for `validate`'s own remaining wrinkle — `workflow-script`, not `workflow-worker`, is what
actually dispatches it).

### Each event's instructions are a label → instruction map, so a more specific config tier can override or disable just one default without restating the rest

_Context (user correction during drafting):_ The old `git-repo.commit`/`.push`/`.create-pr`/
`.promote-pr` blocks each had their own `enabled: false` escape hatch, letting a more specific
tier (typically `config.local.yaml`, e.g. for a contributor without push rights on someone else's
repo) turn off just that one behavior. A bare list of instruction strings loses this:
`merge_config.py` replaces a list wholesale across tiers, never merges it, so overriding one entry
in an event's list would force a project's local config to repeat every other instruction in that
same list verbatim just to drop or reword one.

_Decision:_ Each event's value is an ordered map of `label: instruction` pairs — e.g.
```yaml
after-hand-off:
  promote: Promote GitHub PR to ready for review
  request-review: Request a GitHub review from the reviewer
```
— rather than a bare list. `merge_config.py`'s existing recursive dict-merge (unmodified — it
already merges any dict-shaped config value key-by-key, exactly like `documentation` or
`work-tracking` today) then merges these maps across tiers automatically: a project's
`config.local.yaml` setting only `promote: ""` overrides that one entry, leaving `request-review`
and anything else inherited from lower tiers untouched. An empty string or explicit `null` value
means "disabled" — `run-event-hooks` skips any entry whose value is empty/null, in the map's
iteration order. The label (`push`, `promote`, `self-assign`, ...) is otherwise never interpreted
by the hook mechanism; it exists only so a more specific tier has something stable to key an
override against. A project adding a genuinely new instruction picks any label that doesn't
collide with a default one it wants to keep.

_Consequences:_ Fine-grained, per-instruction opt-out is preserved (actually improved — per
instruction rather than per whole block) at zero cost to `merge_config.py`, since dict merging is
already its default behavior for every other config section; only lists and scalars get the
wholesale-replace treatment. `run-event-hooks` and every event value in this spec are
`dict[str, str]` (ordered map), not `list[str]`.

### The `instructions:` section fully replaces `git-repo.commit`/`.push`/`.create-pr`/`.promote-pr`

_Context:_ Confirmed by reading `dev_team.py`: none of the four blocks' `enabled`/`when` fields
are actually read anywhere in the automated pipeline today (`push`/PR-creation/PR-promotion run
unconditionally via `_commit_and_push()` and two fixed states) — they're advisory prose for
whichever skill or human reads them, and the pipeline itself never consulted them. The user
confirmed this section's config should fully replace, not sit alongside, the old blocks.

_Decision:_ Remove `git-repo.commit`, `.push`, `.create-pr`, `.promote-pr` (including `draft`)
from the config schema entirely. `git-repo` keeps only `user-alias` and `working-branches`. Every
behavior those blocks described that's genuinely hook-driven (commit, push, promote a PR to ready)
becomes a labeled entry in the relevant event's map, e.g. `push: "Push git changes to remote"` or
`promote: "Promote GitHub PR to ready for review"`. PR *creation* is the one exception — per the
`creating-pr` decision below, it stays `CreatePrStep`'s structural, always-fires job rather than a
hookable instruction, so the old `create-pr.draft: bool` flag isn't translated into instruction
text; `create-pr-from-context` keeps its own existing default (unchanged by this feature) rather
than being parameterized through config.

_Consequences:_ Opting out of an action a project doesn't want (e.g. a contributor without PR
rights in someone else's repo) is now a one-line override at whichever tier needs it — e.g.
`config.local.yaml` sets `instructions.after-hand-off.promote: ""` to skip PR promotion — using the
per-entry override mechanic from the previous decision, rather than a dedicated `enabled: false`
field. This is a genuine behavior change for the *automated pipeline specifically*: because the old
fields were never actually enforced there, this is the first time `push`/promote-PR become truly
config-driven inside `workflow-orchestrate`, not a net loss of a working capability. PR creation
itself has no such opt-out (see `creating-pr` decision below) — that's a deliberate, narrower scope
than the old `create-pr.enabled: false` nominally offered, since that flag was never actually
enforced by the pipeline either.

### Every pipeline state gets its own before-/after- event pair, named by `dev_team.py`

_Context:_ The epic names most, but not all, of the pipeline's states (`debugging`, `creating-pr`,
and `signoff`/`fixing-pr` aren't mentioned). The user confirmed states beyond the epic's list
should get their own event names automatically rather than being hand-enumerated, since
`workflow-worker` centralizes execution regardless of which state fires it.

_Decision:_ Only a `Step` that dispatches exactly **one** underlying `spawn_agent` or `run_script`
action gets an automatic `EVENT_NAME` — that's the shape `workflow-worker`/`workflow-script` can
wrap with a single before-hook/after-hook pair. `dev_team.py` already gives every such `Step`
subclass a stable identity (`handles`, the mermaid state name); add an `EVENT_NAME` class attribute
to each one, matching the epic's own vocabulary where it named one and a short kebab-case name
derived from the state otherwise, and include it as an `"event"` field on every descriptor
`get_actions()` emits:

| State (`handles`) | `EVENT_NAME` | Epic-specified? |
|---|---|---|
| `debugging` | `debug` | no |
| `researching` | `research` | yes |
| `implementing` | `implement` | yes |
| `validating` | `validate` | yes |
| `creating-pr` | `create-pr` | no (instruction wording is, but not as its own event) |
| `reviewing` | `review` | yes |
| `fixing` | `fix` | yes |
| `fixing-pr` | `fix` (shared with `fixing` — see below) | no |
| `handoff` | `hand-off` | yes |

`spec-finding` has no `EVENT_NAME` (it's an inline, non-agent step). `signoff` (`SignoffStep`) is
deliberately excluded: it's a `ParallelSteps` composite that emits three independent descriptors
(`review-sign-off` and `researcher-validate` via `workflow-worker`, a build-check script via
`workflow-script`) dispatched concurrently by `workflow-orchestrate` — there is no single agent
session whose start/end a `before-signoff`/`after-signoff` pair could wrap, and `dev_team.py`
itself is a headless script with no `Skill`/`Agent` tool access, so it cannot fire a hook directly
either. Giving `signoff` its own event would mean inventing a new orchestration step purely to wrap
the parallel group — exactly the two-phase-step complexity the `creating-pr` decision above already
rejected — so `signoff` has no hookable event in this feature; a project cannot customize behavior
around it. `fixing` and `fixing-pr` intentionally share one event name, `fix`, fired the same
generic once-per-invocation way as every other event in this table — see the "stay untouched"
decision below for why no per-commit granularity was added.

_Consequences:_ Adding a new pipeline state in the future automatically gets hookable
before-/after- events with no separate registration step, as long as its `Step` dispatches a single
`spawn_agent`/`run_script` action and declares an `EVENT_NAME`. A project's shipped default config
only needs `instructions:` entries for the events it wants to customize; the rest are silently
absent (no hooks fire), exactly like today's config-less defaults. A future `ParallelSteps`
composite would hit the same `signoff` limitation and would also need its hookability (or lack of
it) decided explicitly, not assumed.

### `creating-pr` stays a fixed, always-fires pipeline state; only `push` moves into `after-validate-success`

_Context (user correction during drafting):_ The initial draft folded PR creation into
`after-validate-success` and made `ValidateStep` two-stage to work around `script-runner`'s
missing GitHub MCP tools. The user rejected this: two-phase pipeline steps have caused problems
before, and — separately — PR creation isn't actually an optional, config-driven action the way
"push" is: without a PR, the reviewer has nothing to comment on and the pipeline cannot proceed at
all. It needs to stay a structural, always-fires part of the pipeline, even though a project might
still want to layer *extra* instructions around it.

_Decision:_ `CreatePrStep`/the `creating-pr` state is **not** removed — it stays exactly as it
works today: dispatched via `workflow-worker` (`dev-team:developer`, full GitHub MCP access,
`create-pr-from-context`), unconditionally on the `clean` trigger, same as every other
`spawn_agent` state. It gains only an ordinary `before-create-pr`/`after-create-pr` event pair
(via the same `workflow-worker` mechanism every other state uses) for a project that wants to
layer extra instructions around PR creation — the creation itself remains the state's fixed job,
not something a hook list can skip. `ValidateStep` goes back to being single-phase: run the
validation script, then transition directly, exactly as today. `workflow-script` (not
`workflow-worker`, since `validating` is a `run_script` action) gains the same
`before-<event>`/`after-<event>-success`/`after-<event>-failure`/`after-<event>` lookup pattern
`workflow-worker` has, and follows only what it can actually do with `dev-team:script-runner`'s
Bash-only toolset — which is exactly "push" (`git push`), the one instruction the shipped default
`after-validate-success` map still carries. `_commit_and_push()`'s call from `ValidateStep`'s
`handle_results()` is deleted **only for the path where a `run_script` action was actually
dispatched**; `workflow-script` following `after-validate-success`'s `push` entry replaces it,
inside the same single agent turn that ran the validation script — not a second pipeline action,
so this isn't the two-phase-step pattern the user objected to.

`_resolve_validation_script` returning `None` (no `validation.script` configured) is a different
path: `ValidateStep.get_actions()` sets `ctx.validate_result` directly and returns `[]`, so
`handle_results()` runs **inline inside `dev_team.py`'s own process** — no `run_script` action is
ever dispatched, `workflow-script` never runs, and there is no hook mechanism available at all
(same fundamental constraint as `SignoffStep`'s second call site below: `dev_team.py` itself has no
`Skill`/`Agent` tool access). `_commit_and_push()`'s call is **kept, hardcoded, for this one path
only** — a project with no validation script still gets pushed automatically after a "clean"
result, exactly as today, just not through the hook mechanism, since nothing in that path is
capable of running one.

`workflow-script`'s `outcome` for the after-hook call (`"success"`/`"failure"`) is **not** the same
thing as its own existing Step 3 contract, which already treats a build/test failure as a
successful *script run* (it ran without infrastructure error, so it returns `successful` to the
orchestrator regardless of whether the build/tests themselves passed). `outcome` instead reflects
the *validation result itself* — the same signal `ValidateStep.handle_results()` already parses via
`result.startswith("Succeeded")` — computed before `workflow-script`'s own Step 2 (writing the log)
so it's available in time for the after-hook call. These are two independent judgments living in
the same skill: "did the script run" (governs `workflow-script`'s own return-to-orchestrator
status, unchanged) and "did validation pass" (governs which of `after-validate-success`/
`-failure` fires).

`dev_team.py` has a second, independent `_commit_and_push()` call site inside `SignoffStep`
(`"Push first so the reviewer can see the latest commits"`) — unrelated to `validating` entirely,
since `fixing-pr --> signoff` never routes back through it. This call is **not** deleted and stays
hardcoded exactly as today. It isn't `after-validate-success`'s job (that event never fires on this
path) and it isn't `after-fix`'s job either (that already fired once, generically, when `fix-pr`
itself returned, before `signoff` starts) — it's the same kind of structural, non-optional
necessity `creating-pr`'s PR creation is: `signoff`'s three parallel
reviewers (`review-sign-off`, `researcher-validate`, the build-check script) need to see the actual
latest commits, so this push can't be something a project's config silently omits.

_Consequences:_ The epic's original single `after-validate-success` grouping of "push" and "create
PR" splits across two different mechanisms on two different states — `after-validate-success`
(`workflow-script`, push only) and `before-create-pr`/`after-create-pr` (`workflow-worker`,
extensible but PR creation itself non-optional) — because only one of the two instructions is
actually achievable by the executor validate already uses. No pipeline state is removed or added
relative to today; `ValidateStep`/`CreatePrStep` are structurally unchanged, only both gain hook
lookups. A project that writes an `after-validate-success`/`.-failure` instruction requiring
Jira/GitHub API access will find `workflow-script` unable to follow it — worth calling out in
`update-project-configuration`'s walkthrough, since it's a real constraint on what belongs in a
`validate`-scoped instruction versus a `create-pr`/`implement`/etc.-scoped one. A project with
`validation.script: null` never gets `after-validate-success`/`.-failure` hooks at all (nothing
dispatches, nothing can run them) — it keeps today's unconditional push via the retained
hardcoded `_commit_and_push()` call and nothing else; if that project also wants
self-assign/status-transition-style behavior around validation, there's currently no hook point
that fires for it, since the entire event never activates on that path. Not fixed here — flagged
as an Open Question.

### `fix`/`fix-draft`/`fix-pr` stay untouched — no per-commit hook granularity

_Context (user simplification during drafting):_ An earlier pass of this spec special-cased
`after-fix` to fire once per individual commit inside `fix-draft`/`fix-pr`'s existing per-issue
loop, rather than once per skill invocation like every other event — reasoning that `after-fix`
was meant to react to each build-break/feedback-item fix individually. Revisiting it: the
per-component/per-issue commit points already made by `implement-task`'s TDD trio, `fix-draft`, and
`fix-pr` are all valuable on their own terms (fine-grained history, independent of this feature),
and don't need this feature to hook into them to justify existing — they can be squashed later if
ever unwanted, regardless of any event mechanism. Adding special per-skill-internal-iteration
handling to just one event, when nothing else in this feature needs it, was more complexity than
the currently-empty shipped `after-fix` default actually calls for.

_Decision:_ `fixing`/`fixing-pr` get an ordinary `fix` `EVENT_NAME`, exactly like every other
single-`spawn_agent`-dispatching state — `before-fix`/`after-fix-success`/`after-fix-failure`/
`after-fix` all fire once, generically, via `workflow-worker`, wrapping the whole `fix-draft`/
`fix-pr` invocation. Neither skill reads project config or calls `run-event-hooks` internally;
their existing per-issue `commit-changes` loops are entirely unchanged. `workflow-worker` needs no
special-case exclusion for `event="fix"` — the general mechanism handles it like any other event.

_Consequences:_ Simpler implementation, no asymmetry between `fixing`/`fixing-pr` and every other
event-bearing state. A project can still write `after-fix` instructions, but they run once after
the fix cycle completes, not per individual fix. If per-fix granularity is genuinely needed later,
it can be added then — deferred, not designed away.

### New default behaviors: self-assignment, status transitions, and hand-off assignment move from nowhere/an env var into config text

_Context:_ Nothing in the pipeline today assigns a work item to the agent working it or
transitions its status — the epic asks for this at `before-implement` and `before-review`.
Hand-off's reviewer identity is hardcoded behind `$REVIEW_ASSIGNEE_EMAIL`, read by `final-sign-off`
and `work-with-pr`.

_Decision:_ `work-with-pr` is trimmed to bare mechanical operations only (convert PR to ready,
request a review, assign a Jira issue via `work-with-Jira-tasks` — each callable from a
plain-language instruction) and loses its fixed step sequence and the `REVIEW_ASSIGNEE_EMAIL`
lookup entirely; those operations move into `after-hand-off` instructions, run via
`run-event-hooks`. `final-sign-off` itself is **not** eliminated: `HandoffStep`'s descriptor still
dispatches it as `workflow-worker`'s required `<skill>` (the CLI has no "hooks-only, no core skill"
mode), but its own body shrinks to reporting a status result (writing the `Handoff Result` context
section `HandoffStep.handle_results()` reads) — none of the promote/assign/request-review work is
in its own steps anymore. The real sequence at `handoff` becomes: `workflow-worker` runs
`before-hand-off` (empty by default) → invokes `final-sign-off` (now a near-no-op reporting
success) → runs `after-hand-off` (promote PR, assign PR, assign work item — the actual work) →
writes the result.

Rather than designing a generic/project-specific split up front, every instruction the epic names
— including this repo's own literal reviewer identity, `"Assign work item to jodasoft@outlook.com"`
— is scaffolded directly wherever it needs to live (shipped default or this repo's own
`.dev-team/config.yaml`, whichever is simplest to get the event system working end-to-end for an
initial pass) — `before-implement` (assign to self, transition to "In Progress"), `after-hand-off`
(promote PR, assign PR to `jodavis`, assign work item to `jodasoft@outlook.com`), matching the
epic's text exactly. The epic's "transition to In Review" is worded as happening at review time,
but the epic doesn't specify which agent performs it — since `dev-team:reviewer` has no Jira tool
access, that instruction's shipped default lives on `after-create-pr` instead (`creating-pr`
dispatches via `dev-team:developer`, which has full Jira access, and immediately precedes
`reviewing`), not `before-review` — functionally "right before review starts" either way. A later
task in this spec's task breakdown (a human task, not an agent one) reviews what got scaffolded and
moves whatever is genuinely project-specific (like the named reviewer) out to project/personal
config tiers, leaving only the instructions that should actually ship as recommended defaults for
any project in `assets/default-config.yaml`.

_Consequences:_ `update-project-configuration`'s git-repo walkthrough is replaced by an
`instructions:` walkthrough that, among other things, asks who should be assigned as PR/work-item
reviewer at hand-off and writes that literally into `after-hand-off`. No environment variable is
read by the pipeline for this purpose anymore. The generic-vs-project-specific split is deferred to
the follow-up human task rather than designed here — this decision only fixes the mechanism
(literal instruction text, no env var), not the final placement of every instruction.

## Component Breakdown

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `instructions:` config section | Wrapper | New config schema: a map of event name → ordered map of label → plain-language instruction, mergeable per-entry across config tiers | — |
| Event-name-per-state table (extends `dev_team.py`) | Wrapper | `EVENT_NAME` on each `Step`; included as `event` on every emitted descriptor | — |
| `workflow-orchestrate` dispatch prompt (extends `SKILL.md` step 2c) | Wrapper | Passes the descriptor's `event` field through as `--event <item.event>` in the `Agent(...)` prompt template that spawns `workflow-worker` (or `workflow-script`, via `dev-team:script-runner`) for each dispatched item; omits `--event` entirely when `item.event` is absent, the same existing rule already applied to empty `--skill-args`/`--command` | Event-name-per-state table |
| `run-event-hooks` (new skill) | Testable | Given an event name, phase (`before`/`after`), and outcome, reads `get-project-configuration`'s `instructions:` map itself, resolves which key(s) apply (`before-<event>`; or `after-<event>-success`/`after-<event>-failure` by outcome, then unconditionally `after-<event>`), and follows each non-empty value in order using whatever tool/skill fits (git, Jira, GitHub); skips entries whose value is empty/null. Owns the full lookup-and-follow sequence so callers carry no lookup logic of their own. Returns `"completed"`/`"failed"` — a failed instruction doesn't stop the rest from being attempted, but is not swallowed | `work-with-Jira-tasks`, `work-with-GitHub-issues`, `work-with-pr`, `commit-changes`, `create-pr-from-context` (existing) |
| `workflow-worker` (extended) | Orchestrator | Calls `run-event-hooks` before invoking `<skill>` and again after, passing the outcome the second time | `run-event-hooks`, event-name-per-state table |
| `workflow-script` (extended) | Orchestrator | Calls `run-event-hooks` the same way `workflow-worker` does, around its existing single command execution, for the `validating` run_script step; limited to what `dev-team:script-runner`'s Bash-only toolset can follow | `run-event-hooks`, event-name-per-state table |
| `final-sign-off` (trimmed) / `work-with-pr` (trimmed) | Wrapper | `final-sign-off`: near-no-op status report, still the `<skill>` `HandoffStep` dispatches. `work-with-pr`: bare mechanical PR-promotion/review-request/Jira-assignment operations, callable from plain-language instructions; no fixed step sequence, no `REVIEW_ASSIGNEE_EMAIL` | — |
| `update-project-configuration` (extended) | Wrapper | Instructions walkthrough section replacing the old git-repo commit/push/create-pr/promote-pr questions | `instructions:` config section |

## Planned Implementation

### Interfaces

- **Config schema:**
  ```yaml
  instructions:
    before-debug: {}
    after-debug: {}
    before-research: {}
    after-research: {}
    before-implement:
      self-assign: Assign Jira work item to self
      transition: Transition Jira work item to "In Progress"
    after-implement: {}
    before-fix: {}
    after-fix: {}
    before-validate: {}
    after-validate-success:
      push: Push git changes to remote
    after-validate-failure: {}
    before-create-pr:
      ensure-pushed: If there are uncommitted changes, commit and push the branch
    after-create-pr:
      self-assign: Assign Jira work item to self
      transition: Transition Jira work item to "In Review"
    before-review: {}
    after-review: {}
    before-hand-off: {}
    after-hand-off:
      promote: Promote GitHub PR to ready for review
      request-review: Request a GitHub review from <default reviewer name>
      assign-work-item: Assign work item to <default reviewer email>
  ```
  The epic's `"Assign PR to jodavis"` is the same underlying operation as `request-review` —
  GitHub's reviewer-request *is* how a PR gets assigned to someone (`work-with-pr`'s only
  mechanical operations are `convert-to-ready`, `request-review`, and `assign-issue`; there's no
  separate PR-assignment operation). `assign-work-item` is the distinct Jira-side operation
  (`assign-issue`) for the work item itself.
  An event key with no matching pipeline state, or a typo'd name, is simply never looked up — no
  validation is performed against a fixed vocabulary. This fails silently on a typo, accepted as a
  reasonable trade-off since these entries are expected to be written by the `configure` command
  more often than hand-edited. Labels (`self-assign`,
  `push`, `create-pr`, ...) are never interpreted by the hook mechanism itself — they only give a
  more specific config tier something stable to override (see the per-entry-override Key Design
  Decision above). Setting a label's value to `""` or `null` at a higher-precedence tier disables
  that one inherited instruction without touching any other entry in the same event's map — this
  relies entirely on `merge_config.py`'s existing recursive dict-merge; no new merge logic is
  needed.

  **Ordering is guaranteed.** Confirmed by reading `merge_config.py`'s `deep_merge()`: it builds
  `result = dict(base)` then overlays `override`'s keys onto it — Python dict insertion order is a
  language guarantee (not an implementation detail), and `json.dumps`/`json.loads` preserve it too,
  so the order survives parse → merge → JSON output → `run-event-hooks`'s own iteration
  unchanged. One subtlety: overriding an *existing* label (e.g. `promote: ""` to disable it) keeps
  that entry's position from the lower tier, not wherever the override file places it — only a
  genuinely new label a higher tier introduces is appended at the end.

  `after-<event>`, `after-<event>-success`, and `after-<event>-failure` are three independent map
  keys any event may populate (none are shown populated above beyond `after-validate-success`,
  since the shipped defaults don't need the other two yet) — `after-<event>-success`/`-failure`
  run first, whichever matches the outcome, then `after-<event>` always runs regardless.
  PR creation itself stays the `creating-pr` state's fixed job (see Key Design Decisions), not a
  hook instruction a project could omit — `before-create-pr`/`after-create-pr` exist purely so a
  project can layer extra instructions around it. `before-create-pr` ships one safety-net default,
  `ensure-pushed`, in case `after-validate-success`'s `push` didn't run (disabled, or new changes
  appeared since) — belt-and-suspenders so `create-pr-from-context` never opens a PR against a
  branch missing its latest commits. `after-create-pr` ships the self-assign/status-transition
  defaults that would otherwise belong on `before-review` (see the "New default behaviors" decision
  for why: `dev-team:reviewer` has no Jira tool access, so this Jira-scoped work runs here instead,
  via `dev-team:developer`, functionally still "right before review starts").
- **`run-event-hooks(event: str, phase: "before" | "after", outcome: "success" | "failure" | None, context_file: Path) -> "completed" | "failed"`**
  — new skill, not a function; invoked in-session (not as a separate `Agent` spawn) by
  `workflow-worker` and `workflow-script`, twice each (once per phase), passing along the same
  `--context-file` path already given to the caller — the standard `use-context-file`-conventioned
  file every pipeline skill already reads, from which `run-event-hooks` extracts whatever an
  instruction needs to resolve its target (`work_item_id`, `pr_url`, etc.) using the sections
  already written there by earlier pipeline steps, the same way any other skill in this pipeline
  reads context. Owns the entire lookup-and-follow sequence itself, so neither caller does its own
  `get-project-configuration` read or key resolution: for `phase="before"`, reads `before-<event>`
  and follows it; for `phase="after"`, reads `after-<event>-success`/`after-<event>-failure` (by
  `outcome`) and follows it, then unconditionally reads and follows `after-<event>` too. Within any
  single map it looks up, walks it in order, skipping any entry whose value is empty/`null`, and
  follows each remaining instruction with whatever operation fits (`editJiraIssue`,
  `transitionJiraIssue`, `git push`, `create-pr-from-context`, `update_pull_request`, etc.). No
  matching key, or an empty/absent map: no-op for that lookup, contributing nothing toward failure.
  **Failure is not swallowed:** if any individual instruction fails (a Jira/GitHub call errors, or
  no operation plausibly fits an unrecognized instruction), `run-event-hooks` continues attempting
  the remaining instructions in the map (one bad entry shouldn't block the rest) but returns
  `"failed"` overall, with failure details. The caller (`workflow-worker`/`workflow-script`)
  folds that into its own overall return: a `"failed"` hook call makes the wrapping step's own
  result a failure, the same as if `<skill>`/the validation command itself had failed — routing
  through the pipeline's existing `_handle_agent_failure`/troubleshooter escalation, not a silently
  degraded hook. Classified
  `Testable` (skipping empty/null entries, continuing past a failed instruction, and dispatching
  per-instruction is real conditional logic, not a thin passthrough) — but this is agent-skill
  prose making judgment calls about which operation fits a freeform instruction, not a pure
  function, so it can't get a plain `pytest` unit test the way this plugin's other Python scripts
  do.

  **Verification: a scripted fixture harness**, following the same model `resolve-rebase-conflict`
  uses in `_spec_ConcurrentDevelopment.md` — script the fixture setup and the final-state assertion,
  not the reasoning in between, since that reasoning is inherently agent judgment. At minimum,
  cover:
  1. An instructions map containing only the shipped-default Bash-achievable entry (`push`) run
     against a fixture git repo with local-only commits — assert the remote branch receives them.
  2. The same map with `push` overridden to `""` — assert the remote branch is unchanged (the
     skip-empty-value behavior is externally observable, not just internal logic).
  3. An instructions map containing one genuinely new, project-authored instruction outside the
     shipped vocabulary (something with no obvious matching operation) — assert the skill doesn't
     silently no-op it: it must attempt the instruction using whatever tool/skill plausibly fits,
     and report a failure rather than a false success if nothing actually fits.

  Implementers may add more scenarios, but these three are the objective bar — the same posture the
  reference spec's harness took for a similarly judgment-laden mid-operation skill.
- **`workflow-worker` (extended CLI):** gains `--event <name>` (optional — omitted by
  `workflow-orchestrate`'s dispatch prompt, the same way it already omits empty `--skill-args`/
  `--command`, for any descriptor whose `Step` has no `EVENT_NAME`: `signoff`'s three children
  — `review-sign-off`, `researcher-validate`, and the build-check script — all still dispatch via
  `workflow-worker`/`workflow-script` exactly as today, just without an `--event`, since
  `SignoffStep` itself has no `EVENT_NAME` (see the `signoff` decision above); `spec-finding` never
  reaches `workflow-worker` at all, so it doesn't apply here in the first place). With `--event`
  present, calls `run-event-hooks(event, "before", None)` before invoking `<skill>`, and
  `run-event-hooks(event, "after", <skill>'s own success/failure outcome)` after — no lookup logic
  of its own. Either call returning `"failed"` makes `workflow-worker`'s own overall result a
  failure, even if `<skill>` itself succeeded. No event needs special-casing — `fixing`/`fixing-pr`
  (`event="fix"`) are handled exactly like every other single-`spawn_agent` state.
- **`workflow-script` (extended CLI):** gains the same `--event <name>` argument and calls
  `run-event-hooks` the same two ways, around its existing single command execution — computing
  `outcome` from the validation result itself (the same `"Succeeded"`/failure signal
  `ValidateStep.handle_results()` parses), not from its own separate script-ran-without-error
  status. A `"failed"` hook call makes `workflow-script`'s own overall result a failure the same
  way. Follows only instructions `dev-team:script-runner`'s Bash-only toolset can actually perform.
- **`dev_team.py` descriptor (extended):** every `spawn_agent`/`run_script` descriptor gains an
  `"event"` field alongside the existing `"skill"`/`"agent"`/etc.

### Key Classes

- **`ValidateStep` (unchanged in shape)** — still single-phase: returns the `run_script` action,
  then transitions on the next call based on `validate_result`, exactly as today.
  `_commit_and_push()`'s call is **conditionally** deleted from `handle_results()`: it stays for the
  no-validation-script path and is removed for the real-script path. `handle_results()` already
  receives `ctx.validate_result` as a plain string with no other field distinguishing which path
  produced it, so the discriminator is the literal marker substring `get_actions()` already writes
  for the no-script case, `"(no validation script configured for this project)"` — `handle_results()`
  checks for that substring: if present, call `_commit_and_push()` as today; if absent (a real
  script ran), skip it, since `workflow-script` already pushed via `after-validate-success`'s `push`
  entry within its own single invocation of the validation command — not a second pipeline action.
  No new `PipelineContext` field is needed.
- **`CreatePrStep`** — unchanged in shape (still unconditionally dispatches
  `create-pr-from-context` via `dev-team:developer` on the `clean` trigger); gains only the
  ordinary `before-create-pr`/`after-create-pr` hook wrap every other `workflow-worker`-dispatched
  step gets. `before-create-pr`'s shipped default (`ensure-pushed`) runs first, as a safety net —
  belt-and-suspenders against `after-validate-success`'s `push` having been disabled or new changes
  having landed since validation ran. `after-create-pr`'s shipped defaults (self-assign, transition
  to "In Review") run last, using this step's own Jira-capable `dev-team:developer` dispatch —
  see the `before-review` fix in "Event instructions are plain-language maps..." for why they
  don't live on `before-review` itself.
- **`workflow-worker` (extended)** — wraps its existing single `Skill` invocation with a
  before-hook call and an outcome-aware after-hook call (both via `run-event-hooks`), resolved from
  the new `--event` argument.
- **`workflow-script` (extended)** — wraps its existing single command execution the same way,
  resolved from the same new `--event` argument, scoped to Bash-achievable instructions.
- **`update-project-configuration` (extended)** — Step 3's single-setting table row currently
  pointing free-text phrases like "commit/push/PR behavior"/"draft PRs"/"auto-PR" at
  `git-repo.push`/`.create-pr`/`.promote-pr` is repointed at `instructions:`. Step 4's `git-repo`
  walkthrough subsection (today: `user-alias`, `working-branches`, then
  `commit.when`/`push.enabled+.when`/`create-pr.enabled+.draft+.when`/
  `promote-pr.enabled+.when`) is replaced by a new `instructions:` walkthrough subsection: for each
  event, present the current merged instructions (inherited defaults plus anything already set at
  this tier) and let the user add a new labeled instruction, edit one, or disable one (writing
  `label: ""` at the tier being edited) — including asking who should be assigned as PR/work-item
  reviewer at hand-off, written literally into `after-hand-off`. The "no push/PR rights on this
  repo" case from today's `enabled: false` guidance becomes "disable the relevant labeled entries"
  instead of setting a block-level flag.
- **`final-sign-off` (trimmed)** — still the `<skill>` `HandoffStep`'s descriptor dispatches
  (`workflow-worker` requires one); its own body shrinks to reporting success and writing the
  `Handoff Result` context section — no promote/assign/request-review logic of its own remains.
- **`work-with-pr` (trimmed)** — keeps only the mechanical operations (convert-to-ready,
  request-review, assign-issue); no longer reads `REVIEW_ASSIGNEE_EMAIL` or runs a fixed sequence —
  `after-hand-off`'s instructions, followed by `run-event-hooks`, decide which of these operations
  happen and in what order, after `final-sign-off` itself has already returned.
- **`fix-draft` / `fix-pr` (unchanged)** — no changes at all. Their existing per-issue
  `commit-changes` loops (`"Commit each fix separately... one commit per issue"`) stay exactly as
  today; `before-fix`/`after-fix` are handled entirely by `workflow-worker`, generically, wrapping
  the whole invocation.

### Data Flow

1. `dev_team.py` computes the next pipeline step as today. For a `spawn_agent` step, its
   descriptor now includes `"event": "<name>"` from the `EVENT_NAME` table.
2. `workflow-orchestrate` dispatches to `Agent(subagent_type=<item.agent>, prompt="Invoke
   workflow-worker with --context-file ... --event <item.event> --skill <item.skill> ...")`
   exactly as today, with the one new argument passed through.
3. Inside that agent's session, `workflow-worker` calls `run-event-hooks(event, "before", None,
   context_file)`, which does its own `get-project-configuration` read, resolves `before-<event>`,
   and follows it if non-empty (reading whatever it needs — `work_item_id`, etc. — from the same
   context file). `workflow-worker` then invokes `<skill>` as today, capturing its success/failure
   outcome, and calls `run-event-hooks(event, "after", outcome, context_file)` — which resolves and
   follows `after-<event>-success`/`after-<event>-failure` (by `outcome`) then unconditionally
   `after-<event>` — before writing the skill's own output to the context file. If either
   `run-event-hooks` call returned `"failed"`, `workflow-worker`'s own overall result is a failure
   regardless of `<skill>`'s own outcome; otherwise it returns `successful`.
4. For `validating` with a validation script configured: the `run_script` action dispatches to
   `dev-team:script-runner` via `workflow-script` as today, with `event: "validate"` passed
   alongside it. `workflow-script` runs the validation command, determines `outcome` from the
   validation result itself (not its own separate script-ran-without-error status), then calls
   `run-event-hooks` the same two ways — following only what's Bash-achievable (the shipped
   default: `git push` on success). `ValidateStep` transitions to `clean`/`build_failed` based on
   the script's own result, exactly as today; no extra pipeline
   action is inserted. With no validation script configured, none of this happens —
   `ValidateStep` resolves inline inside `dev_team.py` itself, `workflow-script` never runs, and the
   retained hardcoded `_commit_and_push()` fires instead (see Open Questions).
5. On `clean`, `dev_team.py` dispatches `creating-pr` exactly as today — `workflow-worker` runs its
   `before-create-pr` hook (the shipped `ensure-pushed` safety net, plus anything a project added),
   invokes `create-pr-from-context` unconditionally (`dev-team:developer`, full GitHub MCP access),
   then its `after-create-pr` hook (the shipped self-assign/transition-to-"In Review" defaults,
   using this same Jira-capable agent), before transitioning to `reviewing`.
6. At `handoff`, `after-hand-off`'s instructions (followed via the same `workflow-worker` path as
   any other event) perform whatever mix of PR-promotion, reviewer request, and Jira assignment
   the project's config lists — reading the reviewer's actual identity from the instruction text
   itself, not an environment variable.

## Related Features

_(none — this feature is fully self-contained within the dev-team pipeline's config and
orchestration layer)_

## Open Questions

- [ ] A project with `validation.script: null` never triggers `after-validate-success`/
  `after-validate-failure` — `ValidateStep` handles that case entirely inline inside `dev_team.py`
  with no `run_script` dispatch, so there's no hook point at all on that path (it keeps today's
  unconditional `_commit_and_push()`, hardcoded, and nothing else customizable). This matches
  today's behavior exactly (no regression, no new capability either), but is worth confirming is
  an acceptable scope boundary rather than a gap to close in this feature.

## Related Docs

- `_doc_Projects.md` — repository layout
- `plugins/dev-team/skills/get-project-configuration/SKILL.md` — current config schema and the
  `git-repo` orchestration-signals convention this feature replaces
- `plugins/dev-team/skills/get-project-configuration/assets/default-config.yaml` — shipped
  defaults, to be rewritten
- `plugins/dev-team/skills/update-project-configuration/SKILL.md` — configure-command walkthrough;
  see the Key Classes entry above for exactly what changes
- `plugins/dev-team/skills/workflow-orchestrate/SKILL.md` and `scripts/dev_team.py` — the pipeline
  step machine this feature extends
- `plugins/dev-team/skills/workflow-orchestrate/assets/implement-task-plan.md`,
  `fix-issue-plan.md` — their descriptive prose about `handoff`'s behavior needs updating to match
  the `after-hand-off`-driven design (see Responsibilities & Boundaries)
- `plugins/dev-team/skills/workflow-worker/SKILL.md` — the shared per-step wrapper gaining hook
  execution
- `plugins/dev-team/agents/reviewer.md`, `researcher.md`, `debugger.md`, `developer.md` — agent
  tool grants that bound what a given event's shipped/custom instructions can actually do (only
  `developer` has both Jira and GitHub access; see the `before-review`/`after-create-pr` fix)
- `plugins/dev-team/skills/final-sign-off/SKILL.md`, `work-with-pr/SKILL.md` — hand-off steps
  losing `REVIEW_ASSIGNEE_EMAIL`

## Tasks

> **Legend:** 🤖 = agent task · 🧑 = human operator task

---

### [ADR-360: Add `instructions:` config schema, shipped defaults, and implement `run-event-hooks`](https://jodasoft.atlassian.net/browse/ADR-360) 🤖

**Depends on:** — none —

Adds the new `instructions:` config schema (documented in `get-project-configuration/SKILL.md`)
and its shipped defaults to `assets/default-config.yaml`, removing `git-repo.commit`/`.push`/
`.create-pr`/`.promote-pr`; sets this repo's own `.dev-team/config.yaml` override for the real
hand-off reviewer identity; and implements the `run-event-hooks` skill that actually consumes the
new schema, with its scripted fixture-harness verification.

- [ ] `get-project-configuration/SKILL.md` documents just the shape of `instructions:` — a map of
      event name → ordered map of label → instruction — and the basic convention that a label's
      value can be set to `""`/`null` at a more specific tier to disable that one entry, matching
      the brief, convention-level treatment other sections (`work-tracking`, `documentation`) get
      there. The deeper mechanics (ordering guarantee, the three-tier after lookup) belong in
      `run-event-hooks`'s own `SKILL.md` instead — the skill that actually depends on them
- [ ] `assets/default-config.yaml` gains `instructions:` with every `EVENT_NAME` from the
      Key Design Decisions table present as a key (`before-debug`/`after-debug`,
      `before-research`/`after-research`, `before-implement`/`after-implement`,
      `before-fix`/`after-fix`, `before-validate`/`after-validate-success`/
      `after-validate-failure`, `before-create-pr`/`after-create-pr`,
      `before-review`/`after-review`, `before-hand-off`/`after-hand-off`) — populated with the
      shipped defaults exactly as specified (`before-implement`: self-assign, transition to
      "In Progress"; `after-validate-success`: `push`; `before-create-pr`: `ensure-pushed`;
      `after-create-pr`: self-assign, transition to "In Review"; `after-hand-off`: `promote`,
      `request-review`, `assign-work-item`, with placeholder reviewer text) and empty (`{}`) for
      every other key — so a project reading the shipped config sees every hookable point, not
      only the ones with a default
- [ ] `git-repo.commit`/`.push`/`.create-pr`/`.promote-pr` (including `draft`) removed from the
      schema docs and `default-config.yaml`; `git-repo` retains only `user-alias` and
      `working-branches`
- [ ] This repo's own `.dev-team/config.yaml` has its existing `git-repo.commit`/`.push`/
      `.create-pr`/`.promote-pr` blocks removed (dead config once the schema no longer recognizes
      them) and sets `instructions.after-hand-off.request-review`/`.assign-work-item` to the real
      reviewer identity (`jodavis` / `jodasoft@outlook.com`)
- [ ] A quick manual check confirms `merge_config.py` (unmodified) correctly merges a per-entry
      override at this repo's project tier against the shipped default — no code change expected,
      just confirmation the existing recursive dict-merge already does this
- [ ] New skill `run-event-hooks(event, phase, outcome, context_file) -> "completed" | "failed"`
      implemented exactly as specified: resolves `before-<event>` or
      `after-<event>-success`/`after-<event>-failure` + unconditional `after-<event>` depending on
      `phase`/`outcome`; walks each resolved map in order, skipping empty/`null` values; continues
      past a failed instruction but returns `"failed"` overall if any instruction failed
- [ ] `run-event-hooks/SKILL.md` documents the deeper mechanics moved out of
      `get-project-configuration`: the ordering guarantee and its `merge_config.py` basis, and the
      full before/after-success/after-failure/after lookup sequence
- [ ] Scripted fixture harness covering the three minimum scenarios from the spec, using a
      fictional event/label (e.g. `event="fizzle"`) rather than a real pipeline event, so the
      harness proves the generic mechanism works rather than testing today's specific shipped
      defaults — and using a local commit (not a push) as the observable action, so no fixture
      remote is needed:
      1. An instructions map with one commit-producing entry (e.g. `"Commit any uncommitted
         changes"`), run against a fixture git repo with uncommitted changes — a new local commit
         exists afterward
      2. The same map with that entry overridden to `""` — no new commit is created
      3. An instructions map with one genuinely unrecognized instruction (e.g. "Recite three lines
         from Hamlet") — the skill attempts it rather than silently no-op'ing, and reports failure
         rather than a false success since nothing fits
- [ ] All three fixture scenarios pass

### [ADR-361: Wire `--event` through dispatch and extend `workflow-worker`/`workflow-script` with outcome-aware hook execution](https://jodasoft.atlassian.net/browse/ADR-361) 🤖

**Depends on:** ADR-360

Gives every single-`spawn_agent`/`run_script` `Step` in `dev_team.py` a stable `EVENT_NAME`,
threads it through `workflow-orchestrate`'s dispatch prompt as `--event`, and extends both
`workflow-worker` and `workflow-script` to actually call `run-event-hooks` around their existing
single invocation — the end-to-end wiring for both dispatch paths in one PR, since the plumbing
(`EVENT_NAME`) has no independently testable behavior without its two consumers.

- [ ] Every `Step` subclass that dispatches exactly one `spawn_agent`/`run_script` action declares
      `EVENT_NAME` per the spec's table (`debug`, `research`, `implement`, `validate`,
      `create-pr`, `review`, `fix` for both `fixing`/`fixing-pr`, `hand-off`)
- [ ] `signoff` (`SignoffStep`) and `spec-finding` (`FindSpecStep`) correctly have no `EVENT_NAME`
- [ ] Every emitted descriptor includes an `"event"` field when its `Step` has an `EVENT_NAME`,
      absent otherwise
- [ ] `workflow-orchestrate/SKILL.md`'s dispatch prompt template passes `--event <item.event>`
      through to `workflow-worker`/`workflow-script`, omitted entirely when `item.event` is
      absent — matching the existing omission rule already applied to empty `--skill-args`/
      `--command`
- [ ] `workflow-worker` accepts the new optional `--event <name>` argument; when present, calls
      `run-event-hooks(event, "before", None, context_file)` before invoking `<skill>`, and
      `run-event-hooks(event, "after", outcome, context_file)` after, where `outcome` reflects
      `<skill>`'s own success/failure result; when absent, behaves exactly as today
- [ ] `workflow-script` accepts the same `--event <name>` argument and calls `run-event-hooks` the
      same two ways, around its existing single command execution — computing the after-hook
      `outcome` from the validation result itself (the same `"Succeeded"`/failure signal
      `ValidateStep.handle_results()` already parses), independent of its own pre-existing Step 3
      contract (which still returns `successful` to the orchestrator on a build/test failure that
      ran without infrastructure error, unaffected by this change)
- [ ] In both skills, a `run-event-hooks` call returning `"failed"` makes the wrapping skill's own
      overall result a failure, even if `<skill>`/the validation command itself succeeded
- [ ] Testing plan: exercise both dispatch paths directly against ADR-360's `run-event-hooks` and a
      throwaway `instructions:` fixture (not the real shipped defaults) —
      1. A `spawn_agent`-shaped dry run: invoke `workflow-worker` with `--event fizzle` pointed at
         a trivial existing skill and a context file whose `instructions.before-fizzle`/
         `after-fizzle` carry the same kind of commit-producing/disabled/unrecognized entries as
         ADR-360's fixture harness — confirm the before-hook runs first, the skill runs, the
         after-hook runs last, and a hook failure flips `workflow-worker`'s own reported result
      2. The equivalent dry run through `workflow-script` with a trivial command standing in for
         the validation script, confirming `outcome` reflects the command's actual result and not
         `workflow-script`'s own unrelated successful-script-run status
      3. A plain no-`--event` invocation of each, confirming behavior is byte-for-byte identical
         to today (no hook calls, no new output)

### [ADR-362: Make `ValidateStep`'s `_commit_and_push()` conditional on the no-script path](https://jodasoft.atlassian.net/browse/ADR-362) 🤖

**Depends on:** ADR-361

- [ ] `ValidateStep.handle_results()` checks `ctx.validate_result` for the literal marker
      substring `"(no validation script configured for this project)"`
- [ ] If present (no script configured): calls `_commit_and_push()` exactly as today
- [ ] If absent (a real script ran): skips `_commit_and_push()` — `workflow-script` already pushed
      via `after-validate-success`'s `push` entry
- [ ] No new `PipelineContext` field added
- [ ] `SignoffStep`'s separate, unrelated `_commit_and_push()` call site is untouched
- [ ] Testing plan: two dry runs of `ValidateStep` against a fixture `PipelineContext` — one with
      `validation.script: null` (asserts `_commit_and_push()` still fires) and one with a trivial
      real validation command that exits clean (asserts it does not, and that `workflow-script`'s
      own `push` hook from ADR-361 is what pushed instead)

### [ADR-363: Trim `final-sign-off` and `work-with-pr`; remove `REVIEW_ASSIGNEE_EMAIL`](https://jodasoft.atlassian.net/browse/ADR-363) 🤖

**Depends on:** ADR-360, ADR-361

- [ ] `final-sign-off` shrinks to a near-no-op: reports success and writes the `Handoff Result`
      context section; no promote/assign/request-review logic remains in its own steps
- [ ] `final-sign-off/SKILL.md`'s frontmatter `description` (currently: "Converts the PR from draft
      to ready, assigns the Jira issue, and requests a GitHub review") updated to match — it no
      longer does any of that itself
- [ ] `work-with-pr` keeps only its bare mechanical operations (convert-to-ready, request-review,
      assign-issue via `work-with-Jira-tasks`), individually callable from a plain-language
      instruction
- [ ] No reference to `REVIEW_ASSIGNEE_EMAIL` remains in either skill
- [ ] End-to-end scenario:

    ```gherkin
    Scenario: Hand-off promotes the PR and assigns the configured reviewer
      Given a task's pipeline has reached the "handoff" state with an approved PR
      And this repo's project config's after-hand-off instructions name the real reviewer
      When workflow-worker dispatches the handoff step
      Then the PR is converted from draft to ready for review
      And the named reviewer is requested on the PR
      And the Jira work item is assigned to the named reviewer
      And no REVIEW_ASSIGNEE_EMAIL environment variable is read at any point
    ```

### [ADR-364: Rewrite `update-project-configuration`'s git-repo walkthrough as an `instructions:` walkthrough](https://jodasoft.atlassian.net/browse/ADR-364) 🤖

**Depends on:** ADR-360

- [ ] Step 3's single-setting table row for "commit/push/PR behavior"/"draft PRs"/"auto-PR" is
      repointed from `git-repo.push`/`.create-pr`/`.promote-pr` at `instructions:`
- [ ] Step 4's `git-repo` walkthrough subsection no longer asks about
      `commit.when`/`push.enabled+.when`/`create-pr.enabled+.draft+.when`/
      `promote-pr.enabled+.when`
- [ ] A new `instructions:` walkthrough subsection presents each event's current merged
      instructions and lets the user add a new labeled entry, edit one, or disable one
      (`label: ""` at the tier being edited)
- [ ] The walkthrough asks who should be assigned as PR/work-item reviewer at hand-off and writes
      the answer literally into `after-hand-off`
- [ ] The "no push/PR rights on this repo" guidance is rephrased as "disable the relevant labeled
      entries" rather than a block-level `enabled: false`
- [ ] Testing plan: run the `configure` command interactively against a scratch repo, walking
      through adding a new labeled instruction, editing one, and disabling one via `label: ""` —
      confirm each write via `merge_config.py`'s own merged output, matching the "Verifying a
      write" step `update-project-configuration` already documents for every other setting

### [ADR-365: Update stale `handoff` description in workflow-orchestrate plan assets](https://jodasoft.atlassian.net/browse/ADR-365) 🤖

**Depends on:** ADR-363

- [ ] `workflow-orchestrate/assets/implement-task-plan.md`'s prose under the mermaid diagram no
      longer says `final-sign-off` itself "converts the PR from draft to ready for review, assigns
      the Jira issue to the human reviewer, requests their GitHub review, and adds a Jira
      comment" — rewritten to describe the `after-hand-off`-instruction-driven split
- [ ] `fix-issue-plan.md`'s equivalent prose is updated the same way
- [ ] No changes to either file's mermaid diagram or transition table

### [ADR-366: Review scaffolded defaults and split generic vs. project-specific](https://jodasoft.atlassian.net/browse/ADR-366) 🧑

**Depends on:** ADR-360, ADR-364

The reviewer-identity split (placeholder in the shipped default, real identity in this repo's own
config) is already done by ADR-360 — that part needs no further action here. This task's actual
job: review every *other* shipped default instruction's literal wording for whether it's really
generic enough to ship as a recommended default for any project, not just whether the reviewer's
name leaked into it.

- [ ] `self-assign`/`transition` wording (`"Assign Jira work item to self"`, `"Transition Jira
      work item to \"In Progress\"/\"In Review\""`) reviewed specifically for the hardcoded status
      names — `"In Progress"`/`"In Review"` are this project's Jira workflow status names, not
      guaranteed universal across Jira projects (let alone GitHub Issues or another tracker
      entirely). Decide: keep as a reasonable default (these are Jira's own common built-in status
      names), reword more generically (e.g. "transition to the project's in-progress-equivalent
      status"), or move to this repo's own project config alongside the reviewer identity
- [ ] `push`/`ensure-pushed`/`promote`/`request-review`/`assign-work-item` wording reviewed the
      same way — confirmed these describe genuinely tracker/host-agnostic mechanical actions
      (git push, PR promotion, GitHub review request, Jira assignment) with no other
      project-specific assumption baked in
- [ ] Shipped `assets/default-config.yaml` ends this task containing only instructions confirmed
      appropriate as a recommended default for any project; anything reworded or moved is
      reflected in this repo's own `.dev-team/config.yaml` as needed
- [ ] Anything moved or reworded is verified via `merge_config.py` to still resolve correctly
      end-to-end

### [ADR-367: Author design documentation for Workflow Event Hooks](https://jodasoft.atlassian.net/browse/ADR-367) 🤖

**Depends on:** ADR-360, ADR-361, ADR-362, ADR-363, ADR-364, ADR-365, ADR-366

- [ ] `_doc_WorkflowEventHooks.md` written per `write-repo-documentation` conventions, describing
      the shipped `instructions:` mechanism, the event-name-per-state table, and the
      `run-event-hooks` execution model
- [ ] This spec (`_spec_WorkflowEventHooks.md`) left in place afterward, unchanged, per the
      existing convention
