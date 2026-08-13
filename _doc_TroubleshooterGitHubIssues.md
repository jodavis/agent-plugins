Summary: The `dev-team:troubleshooter` agent and extended `workflow-troubleshoot` skill that turn
ad hoc pipeline-anomaly workarounds into tracked, deduped GitHub issues — and, only when
machine-tier config authorizes it, into a root-cause fix opened as a draft PR — plus the matching
`workflow-orchestrate`/`concurrent-orchestrate` dispatch changes.

# Troubleshooter GitHub Issues

## Overview

The dev-team pipeline has always been able to escalate an unexpected pipeline condition (a stuck
sign-off cycle, an unrecognized state, repeated agent failures) to `workflow-troubleshoot`, which
diagnoses the problem and edits the failing task's context file to unblock the run. Historically
that fix was ephemeral: nothing recorded that the defect happened, so the same pipeline bug could
recur silently and get re-diagnosed from scratch every time. `workflow-troubleshoot` now searches
for, files, and updates GitHub issues against the plugin's own repo (`jodavis/agent-plugins`)
describing each problem and the workaround applied, so recurring pipeline defects accumulate as a
visible backlog instead of vanishing. When machine-tier config explicitly authorizes it, the same
invocation can also write the underlying code fix and open it as a stacked draft PR.

The skill is now invoked through a dedicated `dev-team:troubleshooter` agent rather than a
generic `claude` subagent, and both orchestrating skills (`workflow-orchestrate` and
`concurrent-orchestrate`) dispatch to it consistently — including for a pipeline condition
neither recognizes at all, which previously stopped and reported to the user with nothing
investigated or logged.

## Responsibilities & Boundaries

- **Owns:** the `dev-team:troubleshooter` agent definition and its tool grants;
  `workflow-troubleshoot`'s issue search/dedup/file/update logic and its `can-fix`/`can-push-fix`
  fix-and-draft-PR flow; the `troubleshooter.can-fix` / `troubleshooter.can-push-fix` config
  schema; the `troubleshooter` GitHub label convention on `jodavis/agent-plugins`; the
  troubleshooter-dispatch prose in both `workflow-orchestrate` and `concurrent-orchestrate`.
- **Does not own:** target-project bug tracking — that stays the `debugger` agent's,
  `investigate-bug`'s, and `/dev-team:fix`'s job; the troubleshooter never files an issue about a
  bug in the project being developed, only about the dev-team plugin's own pipeline logic.
  `dev_team.py`'s trigger-condition thresholds (`consecutive_failures`, `signoff_deadlock`,
  `review_loop`, `unknown_state`) are unchanged — they remain what proactively spawns a
  troubleshooter call from inside the step machine, but most calls this skill actually handles
  don't fit one of those four named buckets. GitHub issue CRUD mechanics stay
  `work-with-GitHub-issues`'s, reused as-is.
- **Integrates with:** `get-project-configuration` (new `troubleshooter:` config keys),
  `work-with-GitHub-issues` (issue search/create/comment), `message-attribution` (attribution
  line on every issue/comment body it writes), `create-pr`'s structured PR body convention
  (reused for the post-`gh stack submit` title/body overwrite, not its create call),
  `github/gh-stack` (branch/PR stacking for a root-cause fix), and both orchestrating skills.

## Key Design Decisions

- **Scope is pipeline/tooling bugs only.** The troubleshooter investigates open-ended rather than
  matching against a fixed list — `dev_team.py`'s 4 named triggers still proactively spawn it, but
  it diagnoses freely rather than dispatching on trigger name. It never files an issue about the
  target project being developed; that stays out of scope entirely.
- **An unrecognized pipeline condition now also routes to the troubleshooter**, instead of
  stopping and reporting to the user immediately. `workflow-orchestrate`'s "matches none of the
  shapes above" branch spawns the troubleshooter with the raw unexpected output as `--problem`;
  only if the troubleshooter itself returns `terminate` does the orchestrator fall back to the
  original stop-and-report behavior.
- **The plugin repo is resolved from `<skill-dir>`, not the pipeline's own CWD** — `git -C
  <skill-dir> rev-parse --show-toplevel` for the filesystem root, and `git -C <skill-dir> remote
  get-url origin` (piped through `get_context_path.py`'s regex slug-extraction logic, not its
  `get_repo_slug()` function, which reads CWD) for the GitHub `owner/repo`. `<skill-dir>` always
  points at the actual plugin checkout in use, so this needs no config.
- **`can-fix` and `can-push-fix` are separate, independent gates**, both defaulting `false`. Issue
  filing/searching is unconditional either way. `can-fix` alone authorizes a local commit and
  merge directly in `<skill-dir>`'s checkout — no push, no PR. Both flags set additionally
  authorize pushing a `gh stack` branch and opening a draft PR. A `can-fix`-only environment gets
  fixes applied immediately with no review step (nobody else can see them); a
  `can-fix`+`can-push-fix` environment gets reviewable PRs but no immediate local unblock — that
  asymmetry is intentional.
- **A root-cause fix auto-opens a draft PR, stacked when concurrent**, via `gh stack view/init/add
  --submit`, then overwriting the resulting PR's title/body via
  `mcp__plugin_github_github__update_pull_request` with `create-pr`'s structured body convention
  plus a final `Closes #<issue-number>` line. It never promotes the PR out of draft or requests
  review itself — that stays a human action.
- **Every non-trivial invocation is logged**, not only ones that produce a fix. A one-off,
  non-reproducible blip with nothing concrete to describe writes nothing (no issue, no comment).
  This applies whether or not `can-fix`/`can-push-fix` are set.
- **Dedup is judgment-based against a single `troubleshooter` label**, pre-created on
  `jodavis/agent-plugins`. The skill lists open issues plus issues closed in the last 90 days
  under that label and judges a match by symptoms actually observed, not by trigger name — a
  fixed date window keeps the search bounded without needing config. A matched workaround that
  fails to reproduce is treated as evidence of a different root cause: the original issue gets a
  comment describing the failure, and a new issue is filed and cross-linked rather than folded in.
- **Fix work happens directly in the checkout `<skill-dir>` resolves to** — no separate worktree.
  That checkout is a reserved convention: no other development work happens there, so it is always
  safe and current for a troubleshooter fix.
- **Both orchestrators dispatch `subagent_type="dev-team:troubleshooter"`** (previously the
  generic `"claude"`), with identical `continue`/`terminate`/`needs_user_input` handling in both
  `workflow-orchestrate` and `concurrent-orchestrate`. `concurrent-orchestrate`'s dispatch is
  scoped to anomalies tied to one task's own context file; a scheduler-level anomaly not tied to
  any task keeps its prior stop-and-report behavior, since `concurrent_schedule.py`'s plain-JSON
  scheduler state file is incompatible with `workflow-troubleshoot`'s YAML-frontmatter context-file
  format.
- **Verified by a scripted dry-run fixture harness, not `pytest` unit tests**, since the skill's
  core logic (symptom-based dedup, whether a root cause is "concretely fixable," whether a
  workaround actually resolved the problem) is judgment, not a pure function —
  `plugins/dev-team/fixtures/workflow-troubleshoot/` (`build_fixture.py`, `test_build_fixture.py`,
  `RUN.md`) covers all seven scenarios (no-match, reusable-workaround-match,
  failed-workaround-match, linked-pr-match, no-identifiable-cause, `can-fix`-only local merge,
  `can-fix`+`can-push-fix` stacked PR) against a disposable fixture repo. `RUN.md` documents why
  that repo ended up under a different namespace than the spec's original example name — GitHub
  does not allow creating a repo "for" another account unless that account is an org.

## Key Classes / Interfaces

- **`agents/troubleshooter.md`** (`plugins/dev-team/agents/troubleshooter.md`) — thin wrapper
  agent, `model: sonnet`, tools `Read`/`Write`/`Edit`/`Bash`/`Glob`/`Grep`/`Skill`/
  `mcp__plugin_github_github__*`. Modeled directly on `agents/hook-runner.md`'s pattern: invoke
  the one named skill with the arguments it was given, return exactly what it returns, no
  independent judgment of its own.
- **`workflow-troubleshoot`** (`plugins/dev-team/skills/workflow-troubleshoot/SKILL.md`) — the
  skill the agent invokes. Gains a "Before diagnosing" step group ahead of its existing
  "Diagnosis steps": resolves the plugin repo from `<skill-dir>`, then searches
  `troubleshooter`-labeled issues (open, plus closed in the last 90 days) for a symptom match
  before running fresh diagnosis. Gains a "Making the fix" step group after its existing "Fix
  strategies", gated on `troubleshooter.can-fix`/`can-push-fix`. Returns the same
  `continue`/`needs_user_input`/`terminate` JSON shape as before, with an optional `issue_url`
  field added whenever an issue was filed or updated on that call.
- **`troubleshooter.can-fix` / `troubleshooter.can-push-fix`** (documented in
  `plugins/dev-team/skills/get-project-configuration/SKILL.md`, shipped blank in
  `plugins/dev-team/skills/get-project-configuration/assets/default-config.yaml`) — the two
  independent authorization booleans, read through `get-project-configuration`'s existing merge.
  Set only in machine-tier config, never project-tier, since authorizing automated code changes is
  a personal decision.
- **`workflow-orchestrate`'s troubleshooter dispatch**
  (`plugins/dev-team/skills/workflow-orchestrate/SKILL.md`, "Running the troubleshooter agent")
  — spawns `dev-team:troubleshooter` on a named trigger, a non-`successful` step result, or an
  unrecognized descriptor shape, and handles the three outcomes.
- **`concurrent-orchestrate`'s troubleshooter dispatch**
  (`plugins/dev-team/skills/concurrent-orchestrate/SKILL.md`, "Running the troubleshooter agent")
  — the same dispatch and outcome handling, scoped to per-task anomalies noticed while polling.

## Data Flow

1. A problem surfaces one of three ways: `dev_team.py` detects one of its 4 existing named
   trigger conditions on a task's context file, an agent/script result for a task comes back
   anything other than `successful`, or the orchestrating skill sees a descriptor it doesn't
   recognize at all. Each case spawns `subagent_type="dev-team:troubleshooter"` against that
   task's own context file.
2. The troubleshooter agent invokes `workflow-troubleshoot --context-file ... --problem ...`.
3. `workflow-troubleshoot` resolves the plugin repo from `<skill-dir>` and searches its
   `troubleshooter`-labeled issues first. A symptom match with a working workaround short-circuits
   straight to applying it and commenting on the existing issue; otherwise it runs its existing
   diagnosis/fix-strategy logic, applies a workaround by editing the context file, and files or
   updates an issue describing the problem and the workaround. If `troubleshooter.can-fix` is also
   set and the root cause is concretely fixable, it writes the fix directly in `<skill-dir>`'s
   checkout, either merging it locally (`can-fix` only) or pushing it as part of a `gh stack` and
   opening a draft PR linked from the issue (`can-fix` + `can-push-fix`).
4. The skill returns `continue` / `needs_user_input` / `terminate` (plus an optional `issue_url`)
   exactly as before this feature; the calling orchestrator handles the outcome identically to its
   existing logic — resuming the loop, relaying a question to the user, or stopping and reporting.
