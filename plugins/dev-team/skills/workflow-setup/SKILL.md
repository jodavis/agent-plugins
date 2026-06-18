---
name: workflow-setup
description: >
  **Ensures the working repository and task context file are in a clean, ready-to-work state before any sub-agent reads or writes files.**
  Use this skill **before reading or writing files** in the repository or when information will be read or written in the context file.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You are about to read or write repository files
- AND you need to ensure the repository is in a clean, synchronized state
- OR you need to ensure there is a context file to write to

Do NOT use this skill when:
- A context file is already provided with all the required information
- You are an orchestrator agent coordinating sub-agents

## Arguments

- First argument — either a **work-item-id** (e.g. `ADR-123`, `Issue-444`) or a **context file path** (e.g. `~/.dev-team/org/repo/ADR-123.md`). Required.
  - A context file path is recognised when the argument ends in `.md` or points to an existing file.
  - When a context file path is given, the work-item-id is derived from the filename stem (e.g. `ADR-123.md` → `ADR-123`).

## Determining work-item-type

Derive `work-item-type` from the `work-item-id` pattern (see `identify-project-work-items`):

| work-item-id pattern | work-item-type |
|---|---|
| `ADR-\d+` (Jira key) | `jira` |
| `Issue-\d+` (GitHub issue) | `github` |

## Steps

### 1 — Resolve work-item-id and context file path

Determine both `<work-item-id>` and `<context-file>` from the first argument:

If the first argument is a valid path with a `.md` extension, then that is the `<context-file>`.
The `<work-item-id>` is the file name of the context file (without the extension).

Otherwise, the first argument is the `<work-item-id>` and the context file path is
computed with the following command:

```bash
python "$SKILL_DIR/scripts/compute-context-file.py" "<work-item-id>"
```

If the script exits non-zero, stop and report the error.

Once `<work-item-id>` and `<context-file>` are resolved (from either branch), ensure the
file exists by running:

```bash
python "$SKILL_DIR/scripts/init-context-file.py" "<work-item-id>" "<context-file>"
```

If the script exits non-zero, stop and report the error.

### 2 — Read the context file

Read `<context-file>` and extract these YAML frontmatter fields:

- `work_item_id` — the work item that is actively being worked on
- `spec_path` — relative path from the repo root to the spec file (may be empty)
- `base_branch` — the base branch for this task (may be empty)

The working branch is always `dev/claude/<work-item-id>`. Compute it from the ID.

### 3 — Find the spec file

**Skip this step if `spec_path` is already populated.**

```bash
python "$SKILL_DIR/scripts/find-spec-file.py" "<work-item-id>" "<context-file>"
```

The script searches the repository for `_spec_*.md` files whose text contains the work
item ID, writes the relative path into the `spec_path` frontmatter field, and prints that
path to stdout.

If the script exits non-zero:
- If `work-item-type` is `jira-task`: **stop and report failure** — a spec file is
  required for Jira tasks.
- Otherwise: continue; the base branch will default to `main` in step 4.

### 4 — Determine the base branch

**Skip this step if `base_branch` is already set in the context file.**

#### 4a — Search the spec file for an Epic ID

If a spec file was found in step 3, read it. Look for a Jira key (pattern `[A-Z]+-\d+`)
that appears in a heading or field labelled `Epic:`, `Parent:`, or `Epic ID:`. This is
the Epic ID.

#### 4b — Query Jira if no Epic ID found in spec

If no Epic ID was found in 4a and `work-item-type` is `jira-task`:

Call `mcp__08e9ccd3-4093-4425-adec-d98ea766a759__getJiraIssue` with the `work-item-id`.
Look for a `parent` or `epic` field on the returned issue object and extract its key (e.g.
`ADR-200`). This is the Epic ID. If the issue has no parent or the parent is not a Jira
key, proceed with no Epic ID.

#### 4c — Find the epic feature branch

If an Epic ID was found in 4a or 4b, search remote branches for it:

```bash
git fetch origin
git branch -r | grep "feature/<epic-id>"
```

Use the first matching branch, stripping the `origin/` prefix (e.g.
`feature/ADR-200-infrastructure`). 

#### 4d — Fallback: nearest ancestor feature branch

If no Epic ID was found and step 4c was not reached, check for the nearest ancestor
`feature/*` remote branch:

```bash
git branch -r --merged HEAD | grep "feature/"
```

Use the closest ancestor `feature/*` branch.

#### 4e — Fallback: use `main` for non-Jira work items

If no `feature/*` branch has been found for the base branch, and the work-item-id is a Jira work item, stop and report an error to the user. For other work item types, the base branch is `main`.

#### 4f — Write base branch to context file

After resolving the base branch, write it to the frontmatter of the context file.

### 5 — Prepare the working branch

```bash
python "$SKILL_DIR/scripts/prepare-working-branch.py" "<context-file>"
```

If the script exits non-zero or reports an error in its output, stop and report the failure output as the failure reason.

If the script output does not indicate that the current branch is now `working_branch`, or the pull from the remote tracking branch failed, stop and report that the branch is not ready.


---

If all steps complete successfully, respond with one word: `successful`

If any step fails, stop and report the failure in detail.
