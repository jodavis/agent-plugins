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
order validator (`validate_stack_order`, from the sibling `workflow-orchestrate` skill's
`task_dependencies.py`) and `PipelineContext`, so no separate `Bash` call to
`task_dependencies.py` is needed here.

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
`parent_work_item`, `added_to_stack`. Skip the corresponding step below for each one found, and
use the recorded value instead of recomputing it. A pre-populated `base_branch` (e.g. from a
scheduler that hasn't yet been updated to this task's stack-based registration) is never treated
as a skip signal here — stack position, not a stored `base_branch`, determines basing now, so
step 4 always runs its own registration logic regardless of any `base_branch` already on the
context file.

Also read `git-repo` and `documentation` from the same context file's
`<!-- section:Project Configuration -->` section.

If `working_branch` is already known and `added_to_stack` is already `true`, this task's branch
was already fully registered by a previous run (or backfilled by a descendant while this task was
still unstarted) — skip straight to step 5, which simply checks it out. If `working_branch` is
already known but `added_to_stack` is not yet `true`, skip step 3 (the name is already computed)
but still run step 4. Otherwise continue normally through step 3 then step 4.

### 3 — Compute the working branch name

Skip this step if `working_branch` was already known from step 2.

Take `git-repo.working-branches.task`, substituting `<user-alias>` with `git-repo.user-alias`,
`<task-work-item-id>` with the work-item-id, and `<slug>` (if present in the template) with a
short kebab-case slug of the task. Call the result `<working-branch>`. Write it to the context
file's `working_branch` field via `use-context-file`.

### 4 — Determine the base branch and register this task's branch in the stack

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
(neither 4a nor 4c found one) — there is no epic to bootstrap or register into.

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

#### 4e — Register this task's branch in the stack (recursive backfill)

Skip this sub-step if 4d fell through to 4f (no epic known) — there is no stack to register into.

Also skip this sub-step if `spec_path` is not known at this point (4a found no local spec file,
and the parent feature-work-item ID was discovered only via 4c's Jira fallback). Without a spec
document there is no validated stack order to register into — mirror the old step 4b's guard,
which fell through unchanged rather than guessing at an order. In this case, treat
`<feature-branch>` itself as this task's base: write it to the context file's `base_branch` field
via `use-context-file` (it may already be set from 4d) and continue directly to step 5, which
creates `<working-branch>` straight off `<base-branch>` — no `add` call is made here and
`added_to_stack` is left unset.

Run `work-with-stacked-prs`'s Preflight check if it hasn't already run earlier this session —
every sub-step below uses its `add` operation.

1. Run `python3 "<skill-dir>/scripts/stack_registration.py" plan "<work-item-id>" "<spec_path>"`
   via `Bash`. It prints `{"plan": [<task-ids, oldest first, this task last>], "anchor_task":
   <task-id-or-null>}` as JSON on success — `anchor_task` is the already-registered task whose
   branch the first `plan` entry should be based on, or `null` when the first `plan` entry is the
   very first task in the epic's stack order (base off `<feature-branch>` itself instead). If the
   command exits non-zero, it prints a clear `Error: ...` message to stderr instead of JSON —
   stop and report that error in detail.

2. Determine `<base-for-first-entry>`: if `anchor_task` is `null`, it's `<feature-branch>`;
   otherwise use the `use-context-file` skill with `anchor_task` as an explicit work-item-id to
   read its `working_branch` field.

3. For every entry in `plan` **except the last** (these are not-yet-started ancestors needing an
   empty placeholder branch, oldest first):
   a. Check out `<base-for-first-entry>` (or the branch registered for the previous entry in this
      same loop, once one exists).
   b. Compute that entry's own working-branch name from `git-repo.working-branches.task`
      (the same template step 3 uses, substituted with that entry's own task id instead of this
      task's).
   c. Use the `add` operation from `work-with-stacked-prs` (e.g. `gh_stack.py`'s
      `add(branch=<computed-name>)`, or the `gh stack add <computed-name>` CLI form) to create,
      register, and check out that placeholder branch — no commit, no changes, an intentionally
      empty branch. If the operation reports failure (`gh_stack.py`'s `add()` returns
      `("error", detail)`, or the CLI form exits non-zero), stop and report the failure in detail
      — do not proceed to the push in sub-step d.
   d. Push it: `git push -u origin <computed-name>`. If the push fails, stop and report the
      failure in detail.
   e. Only once the push succeeds, use `use-context-file` with that entry's explicit work-item-id
      to write `working_branch: <computed-name>` (if not already set) and `added_to_stack: true`
      to its own context file.

4. For the **last** entry in `plan` (this task itself — always present, since `plan` always ends
   with `<work-item-id>`):
   a. Ensure the branch checked out is the last backfilled placeholder's branch from step 3 (or
      `<base-for-first-entry>` directly, if `plan` had only this one entry — no backfill needed).
   b. Use the `add` operation for `<working-branch>` (this task's own name, computed in step 3),
      exactly as in this section's own sub-step 3.c above. If the operation reports failure, stop
      and report the failure in detail — do not proceed to the guardrail in sub-step c.
   c. **Guardrail (closes #126):** run
      `python3 "<skill-dir>/scripts/stack_registration.py" verify "$(git rev-parse --abbrev-ref HEAD)" "<working-branch>" "<feature-branch>"`
      via `Bash`. A zero exit confirms HEAD is genuinely `<working-branch>` and not
      `<feature-branch>`. A non-zero exit is a **hard stop**: stop immediately, report the
      mismatch in detail (its stderr names the branch HEAD is actually on, the expected working
      branch, and — when this is the exact conflation bug — the feature branch) — do not proceed
      to push or write `added_to_stack`.
   d. Push it: `git push -u origin <working-branch>`. If the push fails, stop and report the
      failure in detail.
   e. Only once the push succeeds, write `added_to_stack: true` to this task's own context file
      via `use-context-file` (`working_branch` was already written in step 3).

#### 4f — Fallback when no epic is known

Reached only when no parent feature-work-item ID could be found at all (neither 4a nor 4c). This
task isn't part of a tracked epic/stack:
- `work-item-type` is `jira`: stop and report an error — a feature-work-item branch is required
  for Jira-tracked task-work-items.
- Otherwise: use `main` as the base branch, write it to the context file's `base_branch` field via
  `use-context-file`. Step 5's fallback branch-creation path applies for this case only.

### 5 — Prepare the working branch

If step 4e registered this task's branch (`added_to_stack` now `true`), or `working_branch` and
`added_to_stack` were already known from step 2, `<working-branch>` already exists locally — the
`add` operation (or a previous run) already checked it out. Just confirm it's current:

```bash
git fetch origin
git checkout <working-branch>
git pull origin <working-branch>
```

If step 4 fell through to 4f instead (no epic known), or 4e was skipped because `spec_path` was
not known, and `<working-branch>` does not yet exist, create it directly from `<base-branch>` —
the cases that were never part of a stack:

```bash
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

---

If all steps complete successfully, respond with one word: `successful`

If any step fails, stop and report the failure in detail.
