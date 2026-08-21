---
name: ensure-feature-branch
user-invocable: false
description: >
  Bootstraps a feature's branch from `main` — named like a task branch, with `<feature-work-item-
  id>-spec` in place of a task id — and commits and opens a PR for the feature's (possibly
  locally-uncommitted) spec file directly on that same branch, against `main`. Every step
  check-before-act, so the whole skill is safely re-runnable, including calling it before any spec
  draft exists yet (`write-dev-spec`'s own early bootstrap call) as well as after
  (`ensure-working-branch`'s single-task path and `concurrent-orchestrate`, both of which hold
  real MCP/`gh` credentials).
argument-hint: <feature-work-item-id>
---

Use this skill when:
- A feature's branch needs to exist before any task-level work (or spec drafting) can base work
  on it, and the caller already holds real MCP/`gh` credentials (`write-dev-spec`'s early
  bootstrap call, `ensure-working-branch`'s single-task path, or `concurrent-orchestrate`)

Do NOT use this skill when:
- You already know (from context already read this session) that the feature branch exists and
  its spec is committed on that branch — there is nothing left to check

**This skill never touches `gh stack`.** `add-to-pr-stack`'s `link` calls create the epic's stack
from scratch, on GitHub, the first time any task registers into it, so there's no empty-stack
precondition for this skill to set up ahead of time. This also matters because this skill is
routinely invoked from `ensure-working-branch`'s single-task path — i.e. from a task's own
per-task worktree, not the epic's shared one — and `gh stack` operations that rely on local
tracking state (like `init`) are unsafe to run from there (`work-with-stacked-prs/SKILL.md`'s
cross-worktree caveat).

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable.

This skill has no per-task context file to read — it operates on a feature-work-item id, not a
task-work-item id — so it always fetches configuration directly via `get-project-configuration`
rather than reading a context file's `Project Configuration` section.

## Configured behavior

### 1 — Load configuration and compute the feature-branch prefix

Use the `get-project-configuration` skill. Read `git-repo.working-branches.task`,
`git-repo.user-alias`, and `documentation.dev-specs.search`.

**The feature branch is named like a task branch, not a special "feature" one** — build it from
`git-repo.working-branches.task` (e.g. `dev/<user-alias>/<task-work-item-id>-<slug>`),
substituting `<user-alias>` with `git-repo.user-alias` and `<task-work-item-id>` with
`<feature-work-item-id>-spec` (literally the feature-work-item's own id with a `-spec` suffix —
this is also the branch's real, permanent identity: the feature's own spec lives directly on it,
not on a separate spec-commit branch). Take the literal prefix of the `<user-alias>`-substituted
template up to its next `<placeholder>` (`<task-work-item-id>`) — e.g. `dev/claude/` — call this
`<feature-prefix>`.

This mirrors the same tradeoff made for task-branch parsing in `detect_next_stack_event.py`
(ADR-377): rather than reverse-parsing an arbitrary placeholder ordering out of the configured
template, both assume the common real-world shape — a literal prefix, then the id, then an
optional trailing `-<slug>`. Every template this project actually ships (`git-repo`'s default
config and every project override seen so far) follows that shape; generalizing further to
support other placeholder orderings would add real complexity for no known use case, so this is
the deliberate, consistent answer rather than an oversight.

### 2 — Step 1: check whether the feature branch exists; create and push it if not

```bash
git fetch origin
git branch -r | grep -E "<feature-prefix><feature-work-item-id>-spec(-|$)"
```

This is a prefix match — tolerant of a missing or different slug, the same convention
`ensure-working-branch` step 4d already uses to search this same template. The match is anchored
so `<feature-work-item-id>-spec` must end at a `-` or the branch name's end — unlike
`ensure-working-branch` step 4d's unanchored search (which only looks for a base branch to build
on top of), this skill constructs and treats one specific branch as *the* canonical feature
branch for this feature-work-item, so an unanchored match risking a false hit against a
numerically adjacent id (e.g. `ADR-369` matching `dev/claude/ADR-3699-spec`) has bigger
consequences here.

**If one or more matching branches are found:** take the most recently pushed match — plain
`grep` output isn't sorted by push recency, so sort explicitly first:

```bash
git branch -r --sort=-committerdate | grep -E "<feature-prefix><feature-work-item-id>-spec(-|$)"
```

Take the first line of that sorted output, strip the `origin/` prefix, and use it as
`<feature-branch>`. This step is done — skip straight to step 3.

**If no match is found**, this is a fresh feature:

1. Compute a slug: substitute `<feature-work-item-id>` into `documentation.dev-specs.search` and
   run it. If it finds a spec file, read its first `# ` heading and derive a short kebab-case slug
   from it (mirroring `_doc_<slug>.md`/`_spec_<slug>.md` naming). If no spec file is found yet —
   including the common case of this step running before any draft exists, from `write-dev-spec`'s
   own early bootstrap call — omit the slug rather than guessing one.
2. Build `<feature-branch>` from `git-repo.working-branches.task`'s template, substituting
   `<user-alias>` with `git-repo.user-alias`, `<task-work-item-id>` with
   `<feature-work-item-id>-spec`, and `<slug>` (if present in the template) with the computed
   slug, if any — omit the slug and its leading `-` entirely if none is available yet. Once
   created, this name is permanent: a later call that *does* find a spec (and so could compute a
   slug) still finds this same branch via step 2's own search above and never renames it.
3. Create it from `origin/main` and push it immediately, with no other changes:
   ```bash
   git checkout -b <feature-branch> origin/main
   git push origin <feature-branch>
   ```

### 3 — Step 2: check for a locally-uncommitted feature spec; commit it directly on the feature
branch, and PR that branch against `main`, if needed

There is no separate spec-commit branch — `<feature-branch>` **is** the spec's own branch (see
step 1); the spec is committed directly on it, and updated there directly for as long as the
epic is in flight (drafting, review, and any later edits alike). Any task working branch that
forks from it later picks up whatever is on it at that time, same as basing on any other branch.

Substitute `<feature-work-item-id>` into `documentation.dev-specs.search` and run it to find the
feature's spec file(s) locally. Call the result `<spec-path>` (if any).

**If no spec file is found locally at all, skip straight to sub-step 4** (there may still be an
open PR to check for, from a prior run that committed the spec some other way).

**If a spec file is found**, check whether it's already present in `<feature-branch>`'s own tree
— not merely tracked somewhere in this worktree's own history, which is a different question:

```bash
git show origin/<feature-branch>:<spec-path>
```

A zero exit means the spec is already committed on the feature branch — skip to sub-step 4. A
nonzero exit means it isn't there yet, regardless of whether it's tracked elsewhere in this
worktree — proceed:

1. Ensure `<feature-branch>` is checked out and current:
   ```bash
   git checkout <feature-branch>
   git pull origin <feature-branch>
   ```
2. Commit the spec file via the `commit-changes` skill, passing `<feature-work-item-id>` and a
   short description (e.g. "Add feature spec file") — directly on `<feature-branch>`.
3. Push it — `commit-changes` never pushes:
   ```bash
   git push origin <feature-branch>
   ```
4. Check whether an open PR already exists for `<feature-branch>` against `main`:
   ```bash
   gh pr list --head <feature-branch> --base main --state open
   ```
   If one is found, this step is done. Otherwise, open one via the existing `create-pr` skill,
   passing `<feature-work-item-id>`, `<feature-branch>` as the working branch, `main` as the
   explicit `base`, and a short synthesized description ("Adds/updates the feature's spec file.")
   in place of a task brief — this PR isn't for a task, so there is no per-task brief to pass.

### 4 — Leave `<feature-branch>` checked out

Unconditionally check out `<feature-branch>` at the end of this skill, regardless of which path
through steps 2 and 3 got here — step 2's "match found" branch and step 3's two skip branches
("no spec file found locally" and "spec already committed on the feature branch") never perform a
checkout themselves, so this step cannot assume one already happened, and a caller chaining
straight into more work against `<feature-branch>` shouldn't have to re-check it out itself:

```bash
git fetch origin
git checkout <feature-branch>
git pull origin <feature-branch>
```

---

If every step completes — whether it acted or skipped because its own check found nothing left
to do — respond with one word: `successful`

If any step fails, stop and report the failure in detail.
