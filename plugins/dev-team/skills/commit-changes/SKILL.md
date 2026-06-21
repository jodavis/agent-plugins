---
name: commit-changes
description: >
  Use when committing changes locally to the repo.
  Stages all changes and commits with a descriptive message. Does not push.
argument-hint: <work-item-id> <short description>
---

Use this skill when:
- You are committing changes locally to the repo

## Steps

### 1 — Stage changes

```bash
git add -A
```

### 2 — Commit

```bash
git commit -m "<work-item-id>: <short description of what was implemented>"
```

The message body (optional) can list key decisions if they are non-obvious.

**Do not prefix git commands with `cd <path> &&`.** The working directory is already the repository root. Prepending `cd` triggers an unnecessary permission prompt.

### 3 — Do not push

Do not run `git push`. Pushing is handled by a later pipeline step after validation passes.
