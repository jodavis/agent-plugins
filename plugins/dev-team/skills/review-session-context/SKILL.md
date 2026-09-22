---
name: review-session-context
user-invocable: false
description: >
  Use when you will read from or write to a PR review session's local state file
  (.dev-team-review.md). Describes the file's format and how to resolve, initialize,
  read, and update it.
argument-hint: <worktree-or-clone-root | review-context-file-path>
---

Use this skill when:
- You need to locate and read the review-session state file for an in-progress PR review
- You need to write or update a section in that file

`.dev-team-review.md` is a small, worktree/clone-local state file for one in-progress PR review
session. Unlike `use-context-file`'s context file, it is not keyed by a task-work-item ID and
does not live outside the repo — it lives at the root of the review's own isolated worktree or
clone, and its state is meaningless once that worktree/clone is cleaned up. Cleanup (deleting
this file along with the rest of the worktree/clone) is performed elsewhere, by `review-pr`'s own
cleanup step — this skill adds no retention or cleanup logic of its own.

`review-session-context` is this file's sole writer: every other component in the Code Review
Helper feature (evidence gathering, guide generation, the cleanup decision script) passes its
output through this skill rather than writing `.dev-team-review.md` directly.

## Resolving the review context file path

The review context file for a review session lives at:
  `<worktree-or-clone-root>/.dev-team-review.md`

If the argument already points to an existing `.dev-team-review.md` file, it is already the
`<review-context-file>` path. Otherwise, treat the argument as `<worktree-or-clone-root>` and
compute the path from it.

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for
this skill" path shown when this skill was invoked. Resolve it to that literal path; it
is not an environment variable.

```bash
python3 "<skill-dir>/scripts/compute-review-context.py" "<worktree-or-clone-root>"
```

If the script exits non-zero, stop and report the error.

Ensure the file exists (creates it with the documented blank frontmatter if missing):

```bash
python3 "<skill-dir>/scripts/init-review-context.py" "<review-context-file>"
```

If the script exits non-zero, stop and report the error.

## Reading the review context file

Read `<review-context-file>` and extract these YAML frontmatter fields:

| Field | Meaning |
|---|---|
| `repo_scope` | `same-repo` or `cross-repo`, relative to the calling session's own repo |
| `isolation_kind` | `enterworktree` \| `sibling-worktree` \| `scratch-clone` — set by `create-review-worktree`; what `decide_cleanup_action.py` branches on |
| `owner` | Owner/org of the reviewed PR's repo |
| `repo` | Name of the reviewed PR's repo |
| `pr_number` | Resolved PR number |
| `pr_url` | Resolved PR URL |
| `worktree_path` | Absolute path to this review's worktree/clone root |
| `head_ref` | The PR's head ref, checked out in the worktree/clone |
| `guide_path` | Path to the generated `review-guide.md`, once `write-review-guide` runs |
| `work_item_id` | Optional related work-item ID, if the reviewed PR is linked to one |

All fields may be empty until the component that owns that value sets it — this skill only ever
persists what it's given, it never resolves any of these values itself.

## Writing to the review context file

Each named section in the file body uses this sentinel format, identical to
`use-context-file`'s convention:

```
<!-- section:<section-name> -->

<content>
```

**If the sentinel already exists:** use `Edit` to replace all content between the sentinel and the next `<!-- section:` marker or end of file.

**If the sentinel does not exist:** use `Edit` to append the sentinel and content after the last line of the file.

Always use `Edit`, never `Write` — specialist subagents from later deliverables write to this
file concurrently.

### Reserved section names

The initial template documents, but leaves unwritten, three section names reserved for later
deliverables in this feature:

- `Specialist Report` — written by the Specialist Review Report deliverable (AIP-13)
- `Quiz` — written by the Comprehension Quiz deliverable (AIP-15)
- `Publish Log` — written by the Specialist Outcome Tracing deliverable (AIP-17)

Any future component writing one of these sections uses the same sentinel-append/replace
convention documented above.

## Updating frontmatter fields

Use `Edit` to update the existing `field: value` line in the YAML frontmatter block.
