---
name: commit-changes
user-invocable: false
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

Use the `message-attribution` skill to get the configured attribution line, if any.

```bash
git commit -m "<work-item-id>: <short description of what was implemented>"
```

The message body (optional) can list key decisions if they are non-obvious. If
`message-attribution` returned a line, add it as the final line of the message body, separated
from the rest by a blank line — pass it as an additional `-m` paragraph, e.g.
`git commit -m "<subject>" -m "Written by <name>"`. It is additional to, not a replacement for,
any `Co-Authored-By:` trailer the surrounding tool harness itself adds to commits.

**Do not prefix git commands with `cd <path> &&`.** The working directory is already the repository root. Prepending `cd` triggers an unnecessary permission prompt.

### 3 — Do not push

Do not run `git push`. Pushing is handled by a later pipeline step after validation passes.
