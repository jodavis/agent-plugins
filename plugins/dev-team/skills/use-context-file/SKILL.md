---
name: use-context-file
user-invocable: false
description: >
  Use when you will read from or write to a workflow context file.
  Describes the context file format and how to resolve, initialize, read, and update it.
argument-hint: <work-item-id | context-file-path>
---

Use this skill when:
- You need to locate and read the context file for a work item
- You need to write or update a section in the context file

## Resolving the context file path

The context file for a work item lives at:
  `<DEV_TEAM_STATE_DIR or ~/.dev-team>/<repo-slug>/<work-item-id>.md`

If the argument ends in `.md` or points to an existing file, it is already the `<context-file>` path. Derive the `<work-item-id>` from the filename stem (e.g. `PROJ-228.md` → `PROJ-228`).

Otherwise, treat the argument as a `<work-item-id>` and compute the context file path:

```bash
python "$SKILL_DIR/scripts/compute-context-file.py" "<work-item-id>"
```

If the script exits non-zero, stop and report the error.

Ensure the file exists (creates it with default frontmatter if missing):

```bash
python "$SKILL_DIR/scripts/init-context-file.py" "<work-item-id>" "<context-file>"
```

If the script exits non-zero, stop and report the error.

## Reading the context file

Read `<context-file>` and extract these YAML frontmatter fields:

| Field | Meaning |
|---|---|
| `work_item_id` | The work item actively being worked on |
| `spec_path` | Repo-relative path to the spec file (may be empty) |
| `working_branch` | The working branch for this task-work-item (may be empty) |
| `base_branch` | Base branch this task-work-item's working branch was created from (may be empty) |
| `parent_work_item` | The parent feature-work-item ID, if one was found (may be empty) |
| `pr_url` | URL of the GitHub PR (may be empty) |
| `state` | Current workflow state |

Fields marked "may be empty" are not guaranteed to be set — a caller that needs one and finds it
empty must compute it itself (see e.g. `ensure-working-branch`) rather than assuming a default.

## Writing to the context file

Each named section in the context file body uses this sentinel format:

```
<!-- section:<section-name> -->

<content>
```

**If the sentinel already exists:** use `Edit` to replace all content between the sentinel and the next `<!-- section:` marker or end of file.

**If the sentinel does not exist:** use `Edit` to append the sentinel and content after the last line of the file.

Always use `Edit`, never `Write` — concurrent agents may share this file.

## Updating frontmatter fields

Use `Edit` to update the existing `field: value` line in the YAML frontmatter block.
