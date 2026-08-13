# Troubleshooter GitHub Issues

> **Status:** Draft
> **Design:** — none
> **Architecture doc:** `_doc_TroubleshooterGitHubIssues.md` — authored by
> `dev-spec-task-breakdown`'s unconditional final "Author design documentation" task once
> implementation completes; this spec persists afterward for harvesting

## Contents

- [Overview](#overview)
- [Responsibilities & Boundaries](#responsibilities--boundaries)
- [Key Design Decisions](#key-design-decisions)
- [Component Breakdown](#component-breakdown)
- [Planned Implementation](#planned-implementation)
- [Open Questions](#open-questions)
- [Related Docs](#related-docs)

## Overview

The dev-team pipeline already escalates unexpected pipeline states (stuck sign-off cycles,
unknown states, consecutive agent failures) to the `workflow-troubleshoot` skill, invoked ad hoc
as a generic `claude` subagent. It diagnoses the problem and edits the context file to unblock
the run, but that fix is ephemeral — nothing records that the bug happened, so the same pipeline
defect gets silently rediscovered and re-worked-around indefinitely. This feature turns that
skill into a proper `dev-team:troubleshooter` agent that, alongside diagnosing and unblocking the
run, files (or updates) a GitHub issue against the plugin's own repo describing the problem and
the workaround applied, and — only when explicitly authorized via machine-tier config — makes the
underlying code fix itself and opens a draft PR. `workflow-orchestrate` and `concurrent-orchestrate`
both switch to always dispatching this dedicated agent, closing the gap where the latter's vague
fallback language left room for the orchestrator to start investigating problems itself instead of
delegating.

## Responsibilities & Boundaries

- **Owns:** the `dev-team:troubleshooter` agent definition and tool grants; `workflow-troubleshoot`'s
  new GitHub-issue-tracking and fix/draft-PR steps; the `troubleshooter:` config schema
  (`can-fix`, `can-push-fix`); the `troubleshooter` GitHub label convention; the
  troubleshooter-dispatch prose in both `workflow-orchestrate` and `concurrent-orchestrate`.
- **Does not own:** target-project bug tracking (the `debugger` agent, `investigate-bug`,
  `/dev-team:fix` — untouched, out of scope, see Decision 1); `dev_team.py`'s trigger-condition
  thresholds (`consecutive_failures`, `signoff_deadlock`, `review_loop`, `unknown_state` —
  unchanged, still the mechanism that proactively triggers a troubleshooter spawn from inside the
  step machine); GitHub issue CRUD mechanics (`work-with-GitHub-issues`, reused as-is).
- **Integrates with:** `get-project-configuration` (new config keys), `work-with-GitHub-issues`
  (issue search/create/comment), `message-attribution` (attribution line on filed issues/comments,
  per existing convention), `create-pr`'s structured PR body convention (reused, not its create
  call — see the auto-open-PR decision), `gh stack` (the `github/gh-stack` CLI extension, for a
  root-cause fix's branch/PR topology), `workflow-orchestrate` and `concurrent-orchestrate` (both
  now dispatch to this agent).

## Key Design Decisions

### Scope: pipeline/tooling bugs only

_Context:_ The epic describes "during a workflow" without saying what kind of bug. Target-project
bugs already have a dedicated path (`debugger` agent + `/dev-team:fix`).
_Decision:_ The troubleshooter only logs issues for problems in the dev-team plugin itself. It
investigates freely rather than matching against a fixed list of known conditions — `dev_team.py`'s
4 existing trigger conditions are still what proactively spawns it from inside the step machine,
but most problems it's asked to look at won't fit one of those buckets; its job is the same either
way, diagnose and describe whatever is actually wrong. It never files an issue about a bug in the
target project being developed.
_Consequences:_ One clear owner per bug category; no overlapping issue trackers for the same
underlying problem. Diagnosis reads as open-ended investigation (closer to how the `debugger` agent
approaches an app bug) rather than a lookup-table dispatch.

### Unrecognized pipeline conditions also route to the troubleshooter

_Context:_ Today, when `workflow-orchestrate`'s descriptor doesn't match any known shape, it stops
and reports to the user rather than guessing — deliberately cautious, but it means a genuinely novel
problem is reported once and then forgotten; nothing investigates it, works around it, or records
it, so it can recur indefinitely. In practice, most real problems arrive exactly this way rather
than as one of `dev_team.py`'s 4 named triggers.
_Decision:_ That branch now also spawns the troubleshooter — with the raw unexpected output as the
`--problem` description — instead of stopping immediately. The troubleshooter attempts diagnosis
and a workaround the same as for a named trigger; if it can't make sense of it either, it returns
`terminate` and the orchestrator reports to the user exactly as before.
_Consequences:_ No pipeline surprise goes uninvestigated or unlogged. The troubleshooter's
`terminate` path remains the backstop for problems nobody — human or agent — can resolve at that
moment.

### Plugin repo location inferred from `<skill-dir>`

_Context:_ `workflow-orchestrate` runs with its CWD in the target project's repo (its repo slug is
derived from that repo's own git remote) — not the `jodavis/agent-plugins` plugin repo — so the
troubleshooter can't infer where to file issues/read source the way other skills infer the target
project's repo from CWD. But `<skill-dir>` — the base directory `workflow-troubleshoot` itself was
loaded from, an
existing documented convention (see `workflow-orchestrate/SKILL.md`) — always points at the actual
plugin checkout in use, with no config needed.
_Decision:_ The troubleshooter resolves the plugin repo root via
`git -C <skill-dir> rev-parse --show-toplevel`, and derives owner/repo for GitHub calls from that
checkout's `git remote get-url origin` (reusing `get_context_path.py`'s existing slug-extraction
logic). No config key for location.
_Consequences:_ Works in any environment with no setup. It also means issue search/filing has no
location-based on/off switch — see the `can-fix`/`can-push-fix` decision below for the remaining
gates.

### `can-fix` and `can-push-fix` are separate gates

_Context:_ The epic asks who's authorized to let the troubleshooter make code changes — "not for
everyone, but definitely for me." But making a change and pushing it are separately restricted in
practice: a work environment can forbid pushing to a personal repo by policy while a local,
unpushed commit is still fine — and per the "fix happens directly in the checkout" decision, a
local commit in that checkout already unblocks future runs of the plugin, without ever reaching
GitHub.
_Decision:_ Two independent machine-tier flags, both absent/`false` by default. Issue
filing/searching stays unconditional (unaffected by either). `can-fix` authorizes writing the fix
and committing it on a branch in the reserved checkout. `can-push-fix` additionally authorizes
pushing that branch and opening a PR; it has no effect unless `can-fix` is also set. When `can-fix`
is set but `can-push-fix` is not, the troubleshooter merges its fix branch directly into whatever's
checked out in the reserved checkout instead of pushing — safe because nothing else uses that
checkout, and it's what actually satisfies "unblock the workflow" when pushing isn't an option.
_Consequences:_ A `can-fix`-only environment gets fixes applied with no review step at all (nobody
else can see them anyway); a `can-fix` + `can-push-fix` environment gets fixes as reviewable PRs
but not an immediate local unblock — the fix isn't in effect until the PR is reviewed and merged
by a human. This asymmetry is intentional, not an oversight.

### Auto-open a draft PR on a root-cause fix, stacked when concurrent

_Context:_ Epic: "if it made changes, that wouldn't hurt." Separately, concurrent workflows can
trigger multiple troubleshooter fixes in the same reserved checkout close together; each branching
independently off the default branch risks conflicting topologies as they land. Neither `create-pr`
nor `create-pr-from-context` fits directly here — both expect a dev-team `work-item-id`/task
context the troubleshooter doesn't have — and `work-with-pr` has no PR-*creation* operation at all,
only operations on a PR that already exists. `gh stack submit` (confirmed installed:
`github/gh-stack`) creates its own PRs directly and doesn't accept a structured body, so its output
needs a follow-up edit to match this repo's PR body convention.
_Decision:_ When `can-push-fix` is set and a fix is made:
1. Stage the fix and run `gh stack view --json` to check whether a stack already exists in this
   checkout.
2. No stack yet: run `gh stack init` (no branch argument — targets the default branch as trunk,
   creates nothing).
3. Either way: `gh stack add -A -m "<commit message>" troubleshooter/<slug>` — creates the branch on
   top of the current stack tip and commits the staged fix in one step. This is what makes a second
   concurrent fix land on top of the first instead of racing to branch off the same commit.
4. `gh stack submit --auto` (no `--open`) — pushes all branches and creates/updates PRs as drafts
   with auto-generated titles.
5. Re-run `gh stack view --json` (no new tool needed — `gh stack submit` doesn't itself report the
   created PR's number/URL) to find this branch's new PR, then immediately overwrite its title/body
   via `mcp__plugin_github_github__update_pull_request`, reusing `create-pr`'s structured body
   convention (Work item / Changes / Design decisions / Testing completed sections, attribution,
   and a `Closes #<issue-number>` line referencing the issue this fix is for) without going through
   `create-pr`'s own create call, since `gh stack submit` already created the PR.

It never promotes a PR out of draft or requests review itself.
_Consequences:_ Multiple concurrent fixes land as a reviewable, ordered chain of PRs instead of
racing to branch off the same commit, and still read like every other PR this pipeline produces
despite `gh stack`'s own bare auto-generated title. Nothing merges without an explicit human
action — `Closes #<issue-number>` closes the issue automatically once a human merges the PR. Git
operations within the one reserved checkout are still inherently serialized — `gh stack` resolves
branch topology, not two troubleshooter sessions literally committing at the same instant; that
constraint is accepted as a property of using one shared checkout, not solved here.

### Log on every non-trivial invocation, not just when a fix is made

_Context:_ Stated goal: "get to the point where the troubleshooter never needs to be called." A
workaround only unblocks the _current_ run — without a durable record, the same defect recurs
silently, indefinitely.
_Decision:_ Any time the troubleshooter diagnoses a real, describable problem, it searches for and
files/updates an issue with the problem and the workaround applied, regardless of whether
`can-fix` lets it also fix the root cause this time. A one-off transient blip — diagnosis found no
identifiable cause — has nothing to write down and is skipped. The workaround is written under its
own clearly-labeled section in the issue body (not folded into the problem narrative), since it's
the part a future troubleshooter's search step (previous decision) needs to find and reuse
immediately.
_Consequences:_ Issue volume becomes the visible backlog of recurring pipeline pain points;
repeated occurrences accumulate as comments on one issue rather than vanishing as silent
workarounds. This applies whether or not `can-fix`/`can-push-fix` are set — logging never required
either flag.

### Judgment-based dedup against a single `troubleshooter` label

_Context:_ Trigger names are coarse (`consecutive_failures` covers many distinct root causes); a
rigid string-match dedup would either over-merge unrelated bugs or under-merge restatements of the
same bug.
_Decision:_ All troubleshooter-filed issues carry one `troubleshooter` label, pre-created once on
`jodavis/agent-plugins` (already done — not runtime skill logic). Before diagnosing, the
troubleshooter lists open issues, plus issues closed in the last 90 days, under that label and
reads their titles/bodies, using judgment to decide whether any already describes this problem —
recently-closed issues matter because a fix that merged shortly before this occurrence is exactly
the "merged but still recurring" case the linked-PR check below exists for; a fixed date window
(not a count) keeps the search bounded without needing config — not a mechanical trigger-string
match. A match whose documented workaround turns out not to reproduce is
treated as evidence it wasn't actually the same problem: the original issue gets a comment noting
the failure, and a new, separate issue is filed and cross-linked, rather than folding this
occurrence into it.
_Consequences:_ Higher-quality dedup at the cost of being non-deterministic. The fixture harness
for this step verifies the search-and-decide steps happen, not a specific match/no-match verdict
for ambiguous fixture cases. Two issues can end up covering what's later discovered to be the same
underlying bug (linked to each other) rather than one issue accumulating every occurrence — an
accepted tradeoff for treating a failed reused workaround as real evidence rather than noise.

### Fix work happens directly in the checkout the plugin loaded from

_Context:_ A fix only matters if it lands where Claude Code actually reads plugin code from — the
`<skill-dir>`-resolved checkout itself (see previous decision), not an unrelated clone or worktree.
By convention, that checkout is reserved exclusively for troubleshooter fixes: no other development
work happens there, precisely so it's always safe and current for this purpose.
_Decision:_ The troubleshooter makes its fix directly in `<skill-dir>`'s repo root, on a fresh
branch (`troubleshooter/<slug>`) cut from the default branch there — no separate worktree
mechanic.
_Consequences:_ The fix is guaranteed to affect the actual running plugin once it reaches the
checked-out branch there — whether by local merge or by a pushed PR later being pulled, per the
`can-fix`/`can-push-fix` decision. This depends on the reserved-checkout convention holding — if
something else is ever mid-work in that checkout, the troubleshooter's branch creation/checkout
could conflict with it; that tradeoff is accepted deliberately here rather than solved
mechanically.

## Component Breakdown

| Component | Type | Responsibility | Depends on |
| --- | --- | --- | --- |
| `dev-team:troubleshooter` agent (new) | Wrapper | Named, tool-scoped agent (Read/Write/Edit/Bash/Glob/Grep/Skill/GitHub MCP) that invokes `workflow-troubleshoot` and returns exactly what it returns; no logic of its own | `workflow-troubleshoot` (extended) |
| `workflow-troubleshoot` skill (extended) | Testable | Existing diagnosis + fix-strategy logic, plus new config-gated GitHub issue search/file/update and root-cause fix/draft-PR flow | `work-with-GitHub-issues` (existing), `get-project-configuration` (existing), `message-attribution` (existing), `create-pr`'s body convention (existing, reused not called), `gh stack` (external CLI) |
| `troubleshooter:` config section (`can-fix`, `can-push-fix`) | Wrapper | New optional keys read via `get-project-configuration`'s existing merge; no new merge logic | `get-project-configuration` (existing) |
| `workflow-orchestrate` troubleshooter dispatch (modified) | Wrapper | Swaps `subagent_type="claude"` for `subagent_type="dev-team:troubleshooter"` in its existing "Running the troubleshooter agent" section | `dev-team:troubleshooter` agent (this spec) |
| `concurrent-orchestrate` troubleshooter dispatch (new) | Orchestrator | Replaces the vague step 2d "invoke a troubleshooting step" line with an explicit spawn of `dev-team:troubleshooter` and the same continue/terminate/needs_user_input handling `workflow-orchestrate` already has | `dev-team:troubleshooter` agent (this spec) |

Use the `component-taxonomy` skill for the Wrapper/Testable/Orchestrator definitions; agent-skill
prose components here are classified per its "agent-skill prose is the clearest example" note —
verified via a scripted fixture harness, the same pattern `run-event-hooks` and
`resolve-rebase-conflict` already use, not `pytest` unit tests.

## Planned Implementation

### Interfaces

`dev-team:troubleshooter` agent — spawned exactly as `workflow-troubleshoot` is invoked today:

```
Agent(
  subagent_type="dev-team:troubleshooter",
  prompt="""Invoke the `dev-team:workflow-troubleshoot` skill with arguments:
--context-file <context_file>
--problem "<problem_description>"
"""
)
```

Return shape unchanged (`continue` / `needs_user_input` / `terminate`), with an optional
`"issue_url"` field added to any of the three when an issue was filed or updated this call:

```json
{ "action": "continue", "issue_url": "https://github.com/jodavis/agent-plugins/issues/42" }
```

New config keys, read through `get-project-configuration`'s merged output. Both default `false`;
shown here as they'd be set in machine-tier config to opt in:

```yaml
troubleshooter:
  can-fix: true
  can-push-fix: true
```

Absent/false by default — shipped `assets/default-config.yaml` gets a blank `troubleshooter:` key,
mirroring the existing blank `work-tracking:`/`validation:` pattern. Set only in machine-tier
config.

**One-time setup (not runtime skill logic):** create the `troubleshooter` label on
`jodavis/agent-plugins` directly, as part of implementing this feature — the skill assumes the
label already exists rather than checking/creating it on every invocation.

### Key Classes

`workflow-troubleshoot` SKILL.md gains a new first step before its existing "Diagnosis steps", plus
a final step after "Fix strategies" and before "Output":

**Before diagnosing (new):**

1. Resolve two things from `<skill-dir>`: the filesystem repo root, via
   `git -C <skill-dir> rev-parse --show-toplevel` (needed later for any file edit or branch
   operation), and the GitHub `owner/repo`, via `git -C <skill-dir> remote get-url origin` piped
   through `get_context_path.py`'s existing regex slug-extraction (not its `get_repo_slug()`
   function directly, since that runs against CWD rather than an explicit path). List open issues,
   in two separate calls, plus issues closed in the last 90 days, under the `troubleshooter` label.
   Using judgment against each issue's title/body (symptoms, not trigger name), decide whether any
   already describes this
   problem.
2. **Match found, with a documented workaround:** apply it.
   - Works: add an occurrence comment to that issue (confirms the workaround still applies) and
     skip straight to the fix-reuse check (step 4) against that issue.
   - Doesn't work: add a comment to that issue describing the conditions under which it failed —
     evidence this occurrence isn't actually the same root cause despite the symptom match — then
     fall through to fresh diagnosis (existing "Diagnosis steps"/"Fix strategies", unchanged) as if
     no match had been found. The eventual new issue filed in step 3 is cross-linked to this one,
     not merged into it.
3. **Match found, with a linked PR:** check whether it's merged into the default branch already.
   - Merged, but the problem still recurred: note the discrepancy (regression, or a different root
     cause) in a comment and continue with fresh diagnosis.
   - Not merged: keep it as the starting point for this occurrence's own fix (step 4) rather than
     re-deriving one from scratch.
4. **No match** (or the matched workaround failed per step 2): run the existing diagnosis +
   fix-strategy logic unchanged, then file a new issue tagged `troubleshooter` — body has a
   symptoms section (what was actually observed this occurrence, not just the trigger name) and a
   distinct, clearly-labeled workaround section, so a future troubleshooter can both match on
   symptoms and immediately reuse what worked.

**After applying the workaround (new, appended to existing "Fix strategies"):**

1. If `troubleshooter.can-fix` is set and the root cause is concretely fixable: adapt the linked PR
   found during the search above if one applies, otherwise write the fix fresh, directly in
   `<skill-dir>`'s repo root (previous decision — no separate worktree); stage the change. Then:
   - `can-push-fix` also set: `gh stack view --json` to check for an existing stack (`gh stack init`
     first if none), then `gh stack add -A -m "<message>" troubleshooter/<slug>` to branch and
     commit in one step, `gh stack submit --auto` to push and open a draft PR, then overwrite that
     PR's title/body via `mcp__plugin_github_github__update_pull_request` with `create-pr`'s
     structured body (including `Closes #<issue-number>`) referencing the issue — and add the PR
     link plus a description of the change to the issue.
   - `can-push-fix` not set: commit directly on a fresh branch, then merge it into whatever's
     checked out in that checkout — no push, no PR — and add a description of the change to the
     issue.
2. Apply `message-attribution` to any issue/comment body before writing it, per existing
   convention.
3. Include `issue_url` in the returned JSON.

`agents/troubleshooter.md` (new) — modeled directly on `agents/hook-runner.md`: a thin named agent
whose only job is to invoke `workflow-troubleshoot` with the arguments it was given and return
exactly what it returns. Tools: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, `Skill`,
`mcp__plugin_github_github__*`.

`workflow-orchestrate/SKILL.md` — "Running the troubleshooter agent" section: change
`subagent_type="claude"` to `subagent_type="dev-team:troubleshooter"`. Outcome handling
(`continue`/`terminate`/`needs_user_input`) is otherwise unchanged. Step 2c's "matches none of the
shapes above" branch changes from "stop and report in full detail" to "run the troubleshooter agent
(see below) with `problem: <the raw descriptors JSON and why it didn't match>`" — reusing the exact
same outcome handling as every other troubleshooter spawn; only if the troubleshooter itself returns
`terminate` does the orchestrator fall back to reporting in full detail to the user.

`concurrent-orchestrate/SKILL.md` — step 2d's "if something else looks broken ... invoke a
troubleshooting step rather than continuing to poll blindly" is replaced with an explicit block
mirroring `workflow-orchestrate`'s "Running the troubleshooter agent" section, scoped to anomalies
tied to one task: spawn `subagent_type="dev-team:troubleshooter"` with that task's own context
file and a `--problem` description of what looked broken, then handle `continue`/`terminate`/
`needs_user_input` the same way `workflow-orchestrate` does before resuming the poll loop. An
anomaly in `concurrent_schedule.py`'s own scheduling logic — not tied to any one task — is out of
scope here (see Data Flow); step 2d keeps today's stop-and-report behavior for that case.

### Data Flow

1. A problem surfaces one of three ways: `dev_team.py` detects a named trigger condition (unchanged
   logic) on a specific task's context file, an agent/script result for a specific task comes back
   anything other than `successful`, or the orchestrating skill sees a descriptor/condition it
   doesn't recognize at all. In every case it spawns `subagent_type="dev-team:troubleshooter"`
   (previously `"claude"`, and previously not spawned at all for the last case) against that task's
   own context file — `workflow-troubleshoot`'s context-file format (YAML frontmatter + section
   blocks) is incompatible with `concurrent_schedule.py`'s plain-JSON scheduler state file, so
   `concurrent-orchestrate` never passes that file as `--context-file`; an anomaly in the scheduler
   itself, not tied to any one task, stays out of scope for this troubleshooter integration and
   keeps today's stop-and-report behavior.
2. The troubleshooter agent invokes `workflow-troubleshoot --context-file ... --problem ...`.
3. `workflow-troubleshoot` searches the plugin repo's `troubleshooter`-labeled issues first, reuses
   or learns from a match if one fits, then diagnoses fresh and applies a workaround by editing the
   context file, then files/updates an issue describing the problem and workaround — and, if
   `can-fix` is also set and the cause is fixable, makes the fix directly in the plugin checkout,
   either merging it locally or (if `can-push-fix` is also set) pushing it as part of a `gh stack`
   and opening a draft PR linked from the issue.
4. The skill returns `continue`/`needs_user_input`/`terminate` (+ optional `issue_url`) exactly as
   today; the calling orchestrator (`workflow-orchestrate` or `concurrent-orchestrate`) handles the
   outcome identically to its existing logic.

## Open Questions

_(None — every open item from the epic was resolved during drafting.)_

## Related Docs

- `_doc_WorkflowEventHooks.md` — `instructions:`/hook mechanism this feature does not touch, but
  whose config-tier conventions (`troubleshooter:` mirrors `git-repo.user-alias`'s machine-tier
  personal-identity pattern) this design follows
- `_doc_Projects.md` — repository layout
- `_spec_AgentOrchestration.md` — historic spec (ADR-269) that first planned a dedicated
  `troubleshooter` agent; this feature finally implements that agent and extends it
- `_spec_ConcurrentDevelopment.md` — introduced `concurrent-orchestrate`'s current vague
  troubleshooting fallback this feature tightens
- `plugins/dev-team/skills/workflow-troubleshoot/SKILL.md` — skill being extended
- `plugins/dev-team/skills/work-with-GitHub-issues/SKILL.md` — GitHub issue mechanics reused as-is
- `plugins/dev-team/skills/get-project-configuration/SKILL.md` — config schema being extended
- `plugins/dev-team/skills/create-pr/SKILL.md` — structured PR body convention reused for the
  post-`gh stack submit` title/body overwrite
- `plugins/dev-team/skills/work-with-pr/SKILL.md` — confirms it has no PR-creation operation
  (only operations on an already-existing PR), which is why `gh stack`/`create-pr`'s body
  convention are used instead
- `plugins/dev-team/agents/hook-runner.md` — model for the new thin `troubleshooter` agent
- `plugins/dev-team/fixtures/run-hook-instructions/` — fixture-harness pattern to follow for
  testing the new skill-prose logic
- [github/gh-stack](https://github.com/github/gh-stack) — the `gh` CLI extension used for the
  root-cause-fix branch/PR topology; confirmed installed in this environment
  (`gh extension list` → `github/gh-stack`)

## Tasks

### [ADR-383: `dev-team:troubleshooter` agent and `workflow-troubleshoot` GitHub issue tracking](https://jodasoft.atlassian.net/browse/ADR-383) 🤖

**Depends on:** — none —

The whole feature, reviewed as one holistic PR: `agents/troubleshooter.md` (thin wrapper, modeled
on `agents/hook-runner.md`), plus `workflow-troubleshoot` SKILL.md's new "Before diagnosing"
search/dedup/logging step group and its new fix/draft-PR flow appended after "Fix strategies"
(including the `troubleshooter.can-fix` / `troubleshooter.can-push-fix` config keys). The `troubleshooter`
label already exists on `jodavis/agent-plugins` (created ahead of this task).

**Exit criteria:**
- [ ] `agents/troubleshooter.md` exists with `model: sonnet` (matches `debugger`/`researcher`/`reviewer` — open-ended diagnosis, not `hook-runner`/`script-runner`'s mechanical `haiku`) and tools `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, `Skill`, `mcp__plugin_github_github__*`; its role prose matches `hook-runner.md`'s pattern (invoke the one named skill with the given arguments, return exactly what it returns, no independent judgment); `dev-team:troubleshooter` is spawnable as a `subagent_type`
- [ ] `<skill-dir>`-based plugin repo resolution implemented: both the filesystem repo root (`git -C <skill-dir> rev-parse --show-toplevel`) and the GitHub `owner/repo` (`git -C <skill-dir> remote get-url origin`, piped through `get_context_path.py`'s regex slug-extraction logic — not its `get_repo_slug()` function directly, which reads CWD rather than an explicit path)
- [ ] Search-before-diagnosing step order implemented: lists open issues, plus issues closed in the last 90 days, under the `troubleshooter` label and judges a match by symptoms, not trigger name
- [ ] Matched issue with a working workaround: applies it, adds an occurrence comment, skips fresh diagnosis
- [ ] Matched issue with a workaround that fails: adds a comment on the original describing the failure conditions, then runs fresh diagnosis and files a new issue cross-linked to the original
- [ ] Matched issue with a linked PR: checks merged/unmerged status, notes a still-recurring-after-merge discrepancy, and adapts/reuses an unmerged PR as the fix starting point instead of writing one from scratch
- [ ] No match: runs existing diagnosis/fix-strategy logic unchanged, then files a new issue with a symptoms section and a distinct, clearly-labeled workaround section
- [ ] A one-off problem with no identifiable cause writes nothing (no issue filed)
- [ ] `message-attribution` applied to every issue/comment body written
- [ ] `troubleshooter.can-fix` / `troubleshooter.can-push-fix` documented in `get-project-configuration/SKILL.md` and added blank to `assets/default-config.yaml`, both defaulting `false`
- [ ] Neither flag set: no code change is attempted; issue logging is unaffected
- [ ] `can-fix` set, `can-push-fix` not set: fix is committed on a branch in `<skill-dir>`'s repo root, then merged directly into the checked-out branch there — no push, no PR — and the issue gets a description of the change
- [ ] Both flags set: fix branch is added to a shared `gh stack` (`gh stack view --json` to check for an existing stack; `gh stack init` if none; `gh stack add -A -m "<message>" troubleshooter/<slug>` either way), `gh stack submit --auto` pushes and opens a draft PR, and its title/body are immediately overwritten via `mcp__plugin_github_github__update_pull_request` to match `create-pr`'s structured body convention (including `Closes #<issue-number>`) referencing the issue; the issue gets the PR link plus a description of the change
- [ ] `issue_url` included in the skill's returned JSON whenever an issue was filed or updated this call
- [ ] Existing diagnosis/fix-strategy behavior for the 4 named triggers is unchanged (regression check)
- [ ] A dedicated disposable fixture repo (e.g. `jodavis/dev-team-troubleshooter-fixtures`, created once, never `jodavis/agent-plugins`) exists for dry runs, with its own `troubleshooter` label pre-created; `build_fixture.py` under `plugins/dev-team/fixtures/workflow-troubleshoot/` (pattern: `plugins/dev-team/fixtures/run-hook-instructions/`) seeds it per scenario (no-match, reusable-workaround-match, failed-workaround-match, linked-PR-match, no-identifiable-cause, `can-fix`-only local merge, `can-fix`+`can-push-fix` stacked PR) and provides a local throwaway clone standing in for `<skill-dir>`'s resolved checkout
- [ ] Each fixture scenario graded both mechanically (`gh issue list`/`gh api` state, resulting branch/commit state against the fixture repo) and by judgment (the skill's own report describes the right reasoning), same two-tier grading `run-hook-instructions`'s harness uses

### [ADR-384: Orchestrator troubleshooter dispatch (`workflow-orchestrate` + `concurrent-orchestrate`)](https://jodasoft.atlassian.net/browse/ADR-384) 🤖

**Depends on:** ADR-383

Update both orchestrators together so their dispatch behavior stays consistent. In
`workflow-orchestrate/SKILL.md`: swap `subagent_type="claude"` for
`subagent_type="dev-team:troubleshooter"` in "Running the troubleshooter agent", and change step
2c's "matches none of the shapes above" branch from stop-and-report to a troubleshooter spawn
(falling back to stop-and-report only if the troubleshooter itself returns `terminate`). In
`concurrent-orchestrate/SKILL.md`: replace step 2d's "invoke a troubleshooting step rather than
continuing to poll blindly" with an explicit block mirroring `workflow-orchestrate`'s pattern.

**Exit criteria:**
- [ ] All troubleshooter spawns in both files use `subagent_type="dev-team:troubleshooter"`
- [ ] `workflow-orchestrate` step 2c's unrecognized-descriptor branch spawns the troubleshooter with the raw descriptor JSON as `--problem`, falling back to today's stop-and-report only on a `terminate` outcome
- [ ] `concurrent-orchestrate` step 2d's vague fallback line is replaced with an explicit spawn block using the specific task's context file, scoped to anomalies tied to one task; a scheduler-level anomaly not tied to any task keeps today's stop-and-report behavior
- [ ] `continue`/`terminate`/`needs_user_input` handling is identical in shape across both files; poll loop resumes after `continue` in `concurrent-orchestrate`, same as before this change
- [ ] Manual dry run (not a scripted fixture — both are Wrapper/Orchestrator-tier per `component-taxonomy`): seed a scratch context file to force each of the three spawn paths (named trigger, failed result, unrecognized descriptor) through both orchestrators and confirm `dev-team:troubleshooter` is spawned correctly and each outcome is handled as specified

### [ADR-385: Author design documentation](https://jodasoft.atlassian.net/browse/ADR-385) 🤖

**Depends on:** ADR-383, ADR-384

Write `_doc_TroubleshooterGitHubIssues.md` per `write-repo-documentation`, covering the
`dev-team:troubleshooter` agent, the extended `workflow-troubleshoot` flow, the `can-fix`/
`can-push-fix` config gates, and the updated orchestrator dispatch behavior.

**Exit criteria:**
- [ ] `_doc_TroubleshooterGitHubIssues.md` created at the repo root, following `write-repo-documentation`'s expected structure
- [ ] Covers ownership/boundaries, key design decisions, and integration points consistent with the finalized spec
- [ ] Linked from `_doc_Projects.md` if that file's plugin-file table needs updating for the new `agents/troubleshooter.md`
