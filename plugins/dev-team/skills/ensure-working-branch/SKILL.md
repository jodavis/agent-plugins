---
name: ensure-working-branch
user-invocable: false
description: >
  Ensures the repository is on the correct working branch for a task, creating it if it does not
  yet exist. Use this skill before reading or writing any repository files to confirm the branch
  is ready.
argument-hint: <work-item-id>
---

**Extension point skill** — projects must override this skill with their branch naming convention.
Place a `SKILL.md` in `.claude/skills/ensure-working-branch/` to define how working branches are
named and created for this repo.

Use this skill when:
- You are about to write code or modify files and need to be on the correct working branch

Do NOT use this skill when:
- You already know the working branch is checked out and up to date

## Default behavior (no project override)

Check the current branch:

```bash
git branch --show-current
```

- If the current branch is `main`, `master`, or another known base branch, warn:

  > You are on `<branch>`. Working branches should not be created directly on this branch.
  > What branch should this work go on?

  Wait for the user's response and check out the branch they specify.

- If the current branch already looks like a feature or task branch, proceed on the current branch.
