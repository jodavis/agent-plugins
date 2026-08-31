---
name: ensure-working-branch
user-invocable: false
description: >
  Ensures the repository is on the correct working branch for a task, creating it if it does not
  yet exist. Use this skill before reading or writing any repository files to confirm the branch
  is ready.
argument-hint: <work-item-id>
---

**Extension point skill** — configure this via `get-project-configuration`'s `git-repo` section
(preferred). Full-file override remains available as an escape hatch: place a `SKILL.md` in
`.claude/skills/ensure-working-branch/` to replace this skill's process entirely.

Use this skill when:
- You are about to write code or modify files and need to be on the correct working branch

Do NOT use this skill when:
- You already know the working branch is checked out and up to date

`task-work-item` / `feature-work-item` — see `get-project-configuration`'s `work-tracking`
section for the definitions used throughout this skill.

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. This skill's own `stack_registration.py` script lives in its sibling
`scripts/` directory (`<skill-dir>/scripts/stack_registration.py`); it in turn imports the Stack
order validator (`validate_stack_order`) and dependency parser (`parse_task_dependencies`), from
the sibling `workflow-orchestrate` skill's `task_dependencies.py`, so no separate `Bash` call to
`task_dependencies.py` is needed here.

**This skill never touches `gh stack`.** A task's working branch is a plain git branch, based
directly on whichever of its own declared dependencies is furthest along the epic's stack (or the
feature branch, if it has none) — never registered into the epic's `gh stack` itself. That
registration is `add-to-pr-stack`'s sole job, and only happens once this task's own PR has been
signed off (see that skill). This is a deliberate split: `gh stack`'s local stack-membership state
is worktree-private (ADR-370 finding #1, `work-with-stacked-prs/SKILL.md`), so registering here —
in whatever fresh per-task worktree `concurrent-orchestrate` spawned this task into — would race
against `monitor-stack`'s own shared-worktree view of the same stack. `add-to-pr-stack` avoids
that entirely by using `gh stack link`, the one operation that doesn't need local tracking state
at all.

## Configured behavior

### 1 — Worktree-freshness check

Run this first, unconditionally, before anything else in this skill — even before step 2's
already-known-values check:

```bash
git status --short
```

Must be empty. If it produces any output, this is a **hard stop**: stop immediately and report
the failure in detail (do not proceed to step 2 or attempt any recovery). This guards against a
confirmed upstream `isolation: "worktree"` bug (Claude Code issues #51596, #37873, #41010) that
can silently reuse a stale worktree/branch on an 8-hex-char ID-prefix collision — a dirty
worktree at this point means it isn't the fresh one this task expects.

(A properly isolated worktree never sees another concurrent session's `.claude/worktrees/`
bookkeeping — that only shows up when this check is run from the main checkout instead. See
`workflow-orchestrate`'s own preflight check, which stops before this skill would ever run in
that situation.)

### 2 — Check the context file for already-known values

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file.
Note any of these frontmatter fields that are already set: `working_branch`, `spec_path`,
`parent_work_item`. Skip the corresponding step below for each one found, and use the recorded
value instead of recomputing it. A pre-populated `base_branch` is never treated as a skip signal
here — step 4 always recomputes the base branch regardless of any `base_branch` already on the
context file.

Also read `git-repo` and `documentation` from the same context file's
`<!-- section:Project Configuration -->` section.

If `working_branch` is already known, this task's branch was already created by a previous run of
this skill — skip straight to step 5, which simply checks it out (this skill's own branch-creation
step is not safely repeatable — running it twice would try to `git checkout -b` an already-
existing branch). Otherwise continue normally through step 3 then step 4.

### 3 — Compute the working branch name

Skip this step if `working_branch` was already known from step 2.

Take `git-repo.working-branches.task`, substituting `<user-alias>` with `git-repo.user-alias`,
`<task-work-item-id>` with the work-item-id, and `<slug>` (if present in the template) with a
short kebab-case slug of the task. Call the result `<working-branch>`. Write it to the context
file's `working_branch` field via `use-context-file`.

### 4 — Determine the base branch

#### 4a — Search the repo for a spec file

Skip this lookup if `spec_path` was already known from step 2. Substitute `<work-item-id>` into
`documentation.dev-specs.search` and run it. If it returns a spec file, read it and write its path
to the context file's `spec_path` field via `use-context-file`.

Then, unless `parent_work_item` was already known from step 2, look in the spec for the parent
feature-work-item: a heading or field naming it, e.g. a heading shaped `<type> <key>` where
`<type>` is `work-tracking.<provider>.feature-work-item.type` (e.g. `Epic` for a Jira project),
or a field labelled `Parent:`. Extract the key (pattern `[A-Z]+-\d+`). That key is the parent
feature-work-item ID.

#### 4c — Query the tracker if no parent feature-work-item ID found

Skip if `parent_work_item` was already known from step 2. If no parent feature-work-item ID was
found in step 4a and `work-item-type` is `jira`: use the `getJiraIssue` operation from
`work-with-Jira-tasks` with the `work-item-id`. Look for a `parent` or `epic` field on the returned issue and extract its key
(e.g. `ADR-200`). That key is the parent feature-work-item ID. If the issue has no parent, or the
parent is not an issue key, continue with no parent feature-work-item ID.

If a parent feature-work-item ID was found in step 4a or 4c, write it to the context file's
`parent_work_item` field via `use-context-file`.

#### 4d — Ensure the epic's feature branch and stack exist (single-task-path bootstrap trigger)

Skip this sub-step and go straight to 4f if no parent feature-work-item ID is known at all
(neither 4a nor 4c found one) — there is no epic to bootstrap.

Otherwise:

1. Take the literal prefix of `git-repo.working-branches.feature` up to its first `<placeholder>`
   (e.g. `feature/` from `feature/<feature-work-item-id>-<slug>`) — call this `<feature-prefix>`.
2. ```bash
   git fetch origin
   git branch -r --sort=-committerdate | grep -E "<feature-prefix><parent-feature-work-item-id>(-|$)"
   ```
   (Anchored the same way `ensure-feature-branch`'s own existence check is — tolerant of a
   missing or different slug, but anchored so the epic id must end at a `-` or the branch name's
   end.)
3. If one or more matches are found, take the first line (most recently pushed), strip the
   `origin/` prefix — that is `<feature-branch>`. Skip to 4e.
4. If no match is found, this epic hasn't been bootstrapped yet — this is the single-task-path
   trigger (when `/implement <key>` dispatches straight here with no `concurrent-orchestrate`
   involved, nothing else is running concurrently, so no coordination is needed to bootstrap it
   directly). Use the `ensure-feature-branch` skill with the parent feature-work-item ID. If it
   does not respond `successful`, stop and report the failure in detail. Once it completes,
   re-run the search in sub-step 2 — it must now find a match; take it as `<feature-branch>`.

Once `<feature-branch>` is known, write it to the context file's `base_branch` field via
`use-context-file`.

#### 4e — Pick this task's base branch from among its own dependencies

Skip this sub-step if 4d fell through to 4f (no epic known) — go straight to 4f for the base
branch.

Also skip this sub-step if `spec_path` is not known at this point (4a found no local spec file,
and the parent feature-work-item ID was discovered only via 4c's Jira fallback). Without a spec
document there is no validated stack order to compute from — treat `<feature-branch>` itself as
this task's base (already written to `base_branch` in 4d) and go straight to step 5.

Otherwise:

1. Run `python3 "<skill-dir>/scripts/stack_registration.py" anchor "<work-item-id>" "<spec_path>"`
   via `Bash`. It prints `{"anchor_task": <task-id-or-null>}` as JSON on success — the one
   declared dependency of this task whose own branch this task should be based on, chosen as
   whichever sorts latest in the epic's document order when this task has more than one declared
   dependency (a linear stack transitively contains everything earlier), or `null` when this task
   has no declared dependencies at all. If the command exits non-zero, it prints a clear
   `Error: ...` message to stderr instead of JSON — stop and report that error in detail.

   Every dependency this can name is guaranteed already `done` — `is_task_eligible`
   (`task_readiness.py`) never lets this task start until all of them are.

2. If `anchor_task` is `null`, `<base-branch>` is `<feature-branch>` (already written in 4d — no
   further write needed). Otherwise, use the `use-context-file` skill with `anchor_task` as an
   explicit work-item-id to read its `working_branch` field — that is `<base-branch>`. Write it to
   this task's own context file's `base_branch` field via `use-context-file` (overwriting the
   `<feature-branch>` placeholder 4d wrote).

This task's branch is **not** registered into the epic's `gh stack` here, and `added_to_stack`
stays unset for the rest of implementation, review, and sign-off — see this skill's own intro.
`add-to-pr-stack` is the sole place that registration happens, once this task's PR is signed off.

#### 4f — Fallback when no epic is known

Reached only when no parent feature-work-item ID could be found at all (neither 4a nor 4c). This
task isn't part of a tracked epic/stack:
- `work-item-type` is `jira`: stop and report an error — a feature-work-item branch is required
  for Jira-tracked task-work-items.
- Otherwise: use `main` as the base branch, write it to the context file's `base_branch` field via
  `use-context-file`.

### 5 — Create and verify the working branch

If `working_branch` was already known from step 2, `<working-branch>` already exists locally from
a previous run of this skill. Just confirm it's current:

```bash
git fetch origin
git checkout <working-branch>
git pull origin <working-branch>
```

Otherwise, create it directly from `<base-branch>` (step 4 always determines one, whether from
4e's dependency-anchor logic or 4f's fallback):

```bash
git fetch origin
git checkout --no-track -b <working-branch> origin/<base-branch>
```

`--no-track` is required here: `git checkout -b <new> origin/<base>` (without it) makes git
auto-configure `<new>`'s upstream as `origin/<base>` — the *base* branch, not `<new>` itself. A
later bare `git push` (e.g. the pipeline's "Push git changes to remote" hook) would then push
straight at that tracked upstream, which is very often a shared/protected branch (a feature
branch, or another task's own working branch used as a dependency base) that rejects direct
pushes — a real, previously-shipped bug (see PR #158's ADR-338 push-rejection incident). With
`--no-track`, `<working-branch>` starts with no upstream configured at all, so the first push
must set it explicitly (`git push -u origin <working-branch>`) — see `run-hook-instructions`'s
push-instruction handling, which does exactly this rather than a bare `git push`.

**Guardrail (closes #126), when a `<feature-branch>` is known** (4d ran — skip this call entirely
in 4f's no-epic case, where there's no feature branch to conflate with): run
`python3 "<skill-dir>/scripts/stack_registration.py" verify "$(git rev-parse --abbrev-ref HEAD)" "<working-branch>" "<feature-branch>"`
via `Bash`. A zero exit confirms HEAD is genuinely `<working-branch>` and not `<feature-branch>`.
A non-zero exit is a **hard stop**: stop immediately, report the mismatch in detail (its stderr
names the branch HEAD is actually on, the expected working branch, and — when this is the exact
conflation bug — the feature branch).

This skill does not push `<working-branch>` itself — with no upstream configured (`--no-track`
above), the first push is left to the pipeline's own later "push changes" hook
(`run-hook-instructions`'s push-instruction handling), the same as this skill's old no-epic
fallback already did.

---

If all steps complete successfully, respond with one word: `successful`

If any step fails, stop and report the failure in detail.
