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

## Configured behavior

Invoke `get-project-configuration` and read `git-repo` and `documentation`.

### 1 — Check the context file for already-known values

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file.
Note any of these frontmatter fields that are already set: `working_branch`, `base_branch`,
`spec_path`, `parent_work_item`. Skip the corresponding step below for each one found, and use
the recorded value instead of recomputing it.

If `working_branch` is already known, skip straight to step 4.

### 2 — Compute the working branch name

Skip this step if `working_branch` was already known from step 1.

Take `git-repo.working-branches.task`, substituting `<user-alias>` with `git-repo.user-alias`,
`<task-work-item-id>` with the work-item-id, and `<slug>` (if present in the template) with a
short kebab-case slug of the task. Call the result `<working-branch>`. Write it to the context
file's `working_branch` field via `use-context-file`.

### 3 — Determine the base branch

Skip this step if `base_branch` was already known from step 1.

#### 3a — Search the repo for a spec file

Skip this lookup if `spec_path` was already known from step 1. Substitute `<work-item-id>` into
`documentation.specs.search` and run it. If it returns a spec file, read it and write its path to
the context file's `spec_path` field via `use-context-file`.

Then, unless `parent_work_item` was already known from step 1, look in the spec for the parent
feature-work-item: a heading or field naming it, e.g. a heading shaped `<type> <key>` where
`<type>` is `work-tracking.<provider>.feature-work-item.type` (e.g. `Epic` for a Jira project),
or a field labelled `Parent:`. Extract the key (pattern `[A-Z]+-\d+`). That key is the parent
feature-work-item ID.

#### 3b — Query the tracker if no parent feature-work-item ID found

Skip if `parent_work_item` was already known from step 1. If no parent feature-work-item ID was
found in step 3a and `work-item-type` is `jira`: call `mcp__jira__getJiraIssue` with the
`work-item-id`. Look for a `parent` or `epic` field on the returned issue and extract its key
(e.g. `ADR-200`). That key is the parent feature-work-item ID. If the issue has no parent, or the
parent is not an issue key, continue with no parent feature-work-item ID.

If a parent feature-work-item ID was found in step 3a or 3b, write it to the context file's
`parent_work_item` field via `use-context-file`.

#### 3c — Find the feature-work-item branch

If a parent feature-work-item ID is known (from step 1, 3a, or 3b), search remote branches for
it. Take the literal prefix of `git-repo.working-branches.feature` up to its first `<placeholder>`
(e.g. `feature/` from `feature/<feature-work-item-id>-<slug>`) and search for it:

```bash
git fetch origin
git branch -r | grep "<feature-prefix><parent-feature-work-item-id>"
```

Strip the `origin/` prefix from the matching branch name. That is the base branch. If more than
one branch matches, prefer the one most recently pushed.

#### 3d — Fallback: nearest ancestor feature branch

If no parent feature-work-item ID is known and step 3c was not reached, check for the nearest
ancestor branch matching the `<feature-prefix>` from step 3c:

```bash
git branch -r --merged HEAD | grep "<feature-prefix>"
```

Use the closest ancestor matching branch as the base branch.

#### 3e — Fallback or error

If no matching feature branch has been found:
- `work-item-type` is `jira`: stop and report an error — a feature-work-item branch is required
  for Jira-tracked task-work-items.
- Otherwise: use `main` as the base branch.

Once the base branch is determined, write it to the context file's `base_branch` field via
`use-context-file`.

### 4 — Prepare the working branch

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
