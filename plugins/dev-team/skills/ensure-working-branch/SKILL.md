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
environment variable. The Task readiness checker's scripts (`task_readiness.py`,
`task_dependencies.py`) live in the sibling `workflow-orchestrate` skill's `scripts/` directory,
so they are invoked as `<skill-dir>/../workflow-orchestrate/scripts/<script>.py` — still anchored
to `<skill-dir>`, never to an assumed repo-root CWD.

## Configured behavior

### 1 — Worktree-freshness check

Run this first, unconditionally, before anything else in this skill — even before step 2's
already-known-values check:

```bash
git stash list
git status --short
```

Both must be empty. If either produces any output, this is a **hard stop**: stop immediately and
report the failure in detail (do not proceed to step 2 or attempt any recovery). This guards
against a confirmed upstream `isolation: "worktree"` bug (Claude Code issues #51596, #37873,
#41010) that can silently reuse a stale worktree/branch on an 8-hex-char ID-prefix collision — a
dirty worktree at this point means it isn't the fresh one this task expects.

### 2 — Check the context file for already-known values

Invoke `get-project-configuration` and read `git-repo` and `documentation`.

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file.
Note any of these frontmatter fields that are already set: `working_branch`, `base_branch`,
`spec_path`, `parent_work_item`. Skip the corresponding step below for each one found, and use
the recorded value instead of recomputing it.

If `working_branch` is already known, skip straight to step 5.

### 3 — Compute the working branch name

Skip this step if `working_branch` was already known from step 2.

Take `git-repo.working-branches.task`, substituting `<user-alias>` with `git-repo.user-alias`,
`<task-work-item-id>` with the work-item-id, and `<slug>` (if present in the template) with a
short kebab-case slug of the task. Call the result `<working-branch>`. Write it to the context
file's `working_branch` field via `use-context-file`.

### 4 — Determine the base branch

Skip this step if `base_branch` was already known from step 2 — including the case where the
context file has it explicitly set (a scheduler-spawned task may pre-populate it; a plain
`/implement <key>` run never has it pre-populated, so this step always runs for that case).

#### 4a — Search the repo for a spec file

Skip this lookup if `spec_path` was already known from step 2. Substitute `<work-item-id>` into
`documentation.specs.search` and run it. If it returns a spec file, read it and write its path to
the context file's `spec_path` field via `use-context-file`.

Then, unless `parent_work_item` was already known from step 2, look in the spec for the parent
feature-work-item: a heading or field naming it, e.g. a heading shaped `<type> <key>` where
`<type>` is `work-tracking.<provider>.feature-work-item.type` (e.g. `Epic` for a Jira project),
or a field labelled `Parent:`. Extract the key (pattern `[A-Z]+-\d+`). That key is the parent
feature-work-item ID.

#### 4b — Dependency-aware base branch

This is the only dependency-aware step in the pipeline itself — no rebasing happens here or
anywhere else mid-pipeline; it only decides which base branch this task's own working branch
should start from.

Skip this sub-step entirely (fall through to 4c unchanged) if no `spec_path` is known at this
point (neither pre-populated nor found in 4a) — without a spec there is nothing to read this
task's own dependencies from.

Otherwise:

1. Read this task's own dependency ids: invoke
   `<skill-dir>/../workflow-orchestrate/scripts/task_dependencies.py "<spec_path>"` via `Bash`.
   It prints the whole spec's `{task_key: [dependency_ids]}` graph as JSON on success. Look up
   this task's own work-item-id key in that graph — that list is this task's own dependency ids
   (an empty list if the task declares `— none —` or has no `Depends on:` line at all).

2. If that list is empty, skip the rest of this sub-step and fall through to 4c unchanged (no
   dependencies means nothing for this step to override).

3. Otherwise, invoke
   `<skill-dir>/../workflow-orchestrate/scripts/task_readiness.py "<work-item-id>" "<dep1>,<dep2>,..."`
   via `Bash`, passing this task's own dependency ids as a comma-separated list. It prints
   `{"status": "eligible" | "waiting" | "blocked", "base_branch": <branch-name-or-null>}` as JSON
   on success.

4. If `status` is `"eligible"` and `base_branch` is a real (non-null) branch name: write it to
   the context file's `base_branch` field via `use-context-file`, then skip the rest of step 4
   entirely (4c–4f) and proceed straight to step 5.

5. If `status` is `"eligible"` and `base_branch` is `null`: no override is needed (every
   dependency is already done) — fall through to 4c and let the existing feature-branch lookup
   run unchanged.

6. If `status` is `"waiting"` or `"blocked"`: this task's dependencies are not yet ready to start
   from. Stop and report the failure in detail (name the task, its dependency ids, and the
   returned status) — do not fall back to the feature-branch lookup, since that would silently
   start this task's working branch without the dependency it actually needs.

#### 4c — Query the tracker if no parent feature-work-item ID found

Skip if `parent_work_item` was already known from step 2. If no parent feature-work-item ID was
found in step 4a and `work-item-type` is `jira`: use the `getJiraIssue` operation from
`work-with-Jira-tasks` with the `work-item-id`. Look for a `parent` or `epic` field on the returned issue and extract its key
(e.g. `ADR-200`). That key is the parent feature-work-item ID. If the issue has no parent, or the
parent is not an issue key, continue with no parent feature-work-item ID.

If a parent feature-work-item ID was found in step 4a or 4c, write it to the context file's
`parent_work_item` field via `use-context-file`.

#### 4d — Find the feature-work-item branch

If a parent feature-work-item ID is known (from step 2, 4a, or 4c), search remote branches for
it. Take the literal prefix of `git-repo.working-branches.feature` up to its first `<placeholder>`
(e.g. `feature/` from `feature/<feature-work-item-id>-<slug>`) and search for it:

```bash
git fetch origin
git branch -r | grep "<feature-prefix><parent-feature-work-item-id>"
```

Strip the `origin/` prefix from the matching branch name. That is the base branch. If more than
one branch matches, prefer the one most recently pushed.

#### 4e — Fallback: nearest ancestor feature branch

If no parent feature-work-item ID is known and step 4d was not reached, check for the nearest
ancestor branch matching the `<feature-prefix>` from step 4d:

```bash
git branch -r --merged HEAD | grep "<feature-prefix>"
```

Use the closest ancestor matching branch as the base branch.

#### 4f — Fallback or error

If no matching feature branch has been found:
- `work-item-type` is `jira`: stop and report an error — a feature-work-item branch is required
  for Jira-tracked task-work-items.
- Otherwise: use `main` as the base branch.

Once the base branch is determined, write it to the context file's `base_branch` field via
`use-context-file`.

### 5 — Prepare the working branch

Fetch the latest state from the remote:

```bash
git fetch origin
```

If `<working-branch>` already exists locally or on the remote, check it out and pull:

```bash
git checkout <working-branch>
git pull origin <working-branch>
```

If it does not yet exist, create it from the base branch:

```bash
git checkout -b <working-branch> origin/<base-branch>
```

---

If all steps complete successfully, respond with one word: `successful`

If any step fails, stop and report the failure in detail.
