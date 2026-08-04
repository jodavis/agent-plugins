---
name: ensure-feature-branch
user-invocable: false
description: >
  Bootstraps an epic's feature branch from `main`, commits and opens a PR for the epic's
  (possibly locally-uncommitted) spec file against that branch, and initializes the epic's
  `gh stack` — every step check-before-act so the whole skill is safely re-runnable. Invoked by
  `ensure-working-branch`'s single-task path and by `concurrent-orchestrate`, both of which hold
  real MCP/`gh` credentials.
argument-hint: <epic-id>
---

**Extension point skill** — configure this via `get-project-configuration`'s `git-repo` and
`documentation` sections (preferred). Full-file override remains available as an escape hatch:
place a `SKILL.md` in `.claude/skills/ensure-feature-branch/` to replace this skill's process
entirely.

Use this skill when:
- An epic's feature branch, committed spec, and anchored `gh stack` need to exist before any
  task-level work can register into that stack, and the caller already holds real MCP/`gh`
  credentials (`ensure-working-branch`'s single-task path, or `concurrent-orchestrate`)

Do NOT use this skill when:
- You already know (from context already read this session) that the epic's feature branch
  exists, its spec is committed on that branch, and a stack is already anchored to it — there is
  nothing left to check

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable.

This skill has no per-task context file to read — it operates on an epic id, not a
task-work-item id — so it always fetches configuration directly via `get-project-configuration`
rather than reading a context file's `Project Configuration` section.

## Configured behavior

### 1 — Load configuration and compute the feature-branch prefix

Use the `get-project-configuration` skill. Read `git-repo.working-branches.feature` and
`documentation.dev-specs.search`.

Take the literal prefix of `git-repo.working-branches.feature`
(`feature/<feature-work-item-id>-<slug>`) up to its first `<placeholder>` — `feature/` — call
this `<feature-prefix>`.

### 2 — Step 1: check whether the feature branch exists; create and push it if not

```bash
git fetch origin
git branch -r | grep "<feature-prefix><epic-id>"
```

This is a prefix match — tolerant of a missing or different slug, the same convention
`ensure-working-branch` step 4d already uses to search this same template. Some of this repo's
real feature branches predate any slug convention and have none at all, so an exact-name match
would miss them.

**If one or more matching branches are found:** take the most recently pushed match, strip the
`origin/` prefix, and use it as `<feature-branch>`. This step is done — skip straight to step 3.

**If no match is found**, this is a fresh epic:

1. Compute a slug: substitute `<epic-id>` into `documentation.dev-specs.search` and run it. If it
   finds a spec file, read its first `# ` heading and derive a short kebab-case slug from it
   (mirroring `_doc_<slug>.md`/`_spec_<slug>.md` naming). If no spec file is found yet, omit the
   slug — build `<feature-branch>` as `feature/<epic-id>` with no trailing `-<slug>` rather than
   guessing one.
2. Build `<feature-branch>` from `git-repo.working-branches.feature`'s template, substituting
   `<epic-id>` for `<feature-work-item-id>` and the computed slug (if any) for `<slug>`.
3. Create it from `origin/main` and push it immediately, with no other changes:
   ```bash
   git checkout -b <feature-branch> origin/main
   git push origin <feature-branch>
   ```

### 3 — Step 2: check for a locally-uncommitted epic spec; commit and PR it if found

Substitute `<epic-id>` into `documentation.dev-specs.search` and run it to find the epic's spec
file(s) locally. Call the result `<spec-path>` (if any).

**If no spec file is found locally at all, skip the rest of this step.**

**If a spec file is found**, check whether it's already present in `<feature-branch>`'s own tree
— not merely tracked somewhere in this worktree's own history, which is a different question:

```bash
git show origin/<feature-branch>:<spec-path>
```

A zero exit means the spec is already committed on the feature branch — skip the rest of this
step. A nonzero exit means it isn't there yet, regardless of whether it's tracked elsewhere in
this worktree — proceed:

1. Check whether the dedicated spec-commit branch already exists on the remote (a second run
   after a first run already opened the PR, but before that PR merged, must not duplicate it):
   ```bash
   git ls-remote --heads origin docs/<epic-id>-spec
   ```
   If it already exists, skip the rest of this step — a prior run already committed the spec and
   opened its PR.
2. Otherwise, check out `<feature-branch>` and create the dedicated branch from it:
   ```bash
   git checkout <feature-branch>
   git checkout -b docs/<epic-id>-spec
   ```
3. Commit the spec file via the `commit-changes` skill, passing `<epic-id>` and a short
   description (e.g. "Add epic spec file").
4. Push the new branch — `commit-changes` never pushes, and this PR is opened directly, not
   through the normal validate-then-push pipeline step:
   ```bash
   git push -u origin docs/<epic-id>-spec
   ```
5. Open a PR against the feature branch via the existing `create-pr` skill, passing
   `<epic-id>`, `docs/<epic-id>-spec` as the working branch, `<feature-branch>` as the explicit
   `base` (unchanged `create-pr` behavior), and a short synthesized description ("Adds the
   epic's spec file.") in place of a task brief — this PR isn't for a task, so there is no
   per-task brief to pass.
6. Check `<feature-branch>` back out, leaving the working tree positioned there for step 4.

### 4 — Step 3: check whether a stack is already anchored to this trunk; init it if not

With `<feature-branch>` checked out locally, run `work-with-stacked-prs`'s Preflight check if it
hasn't already run earlier this session.

Use `work-with-stacked-prs`'s `view` operation (`gh_stack.py`'s `view()`, or the `gh stack view
--json` CLI form) to check current stack membership.

**If `view` returns `"ok"` and its `trunk` field equals `<feature-branch>`**, a stack is already
anchored to this trunk — skip `init` entirely; this step is a no-op.

**Otherwise** (an `"error"` result — e.g. "not part of a stack" — or an `"ok"` result whose
`trunk` doesn't match `<feature-branch>`), run the `init` operation with `<feature-branch>` as
the trunk:

```bash
gh stack init --base <feature-branch>
```

(or `gh_stack.py`'s `init(base=<feature-branch>)`). Per ADR-370's confirmed finding, `init`
against an already-anchored trunk is a hard error (exit 5), not an idempotent no-op — this is
exactly why this step's `view` check must run first and must never be skipped.

---

If every step completes — whether it acted or skipped because its own check found nothing left
to do — respond with one word: `successful`

If any step fails, stop and report the failure in detail.
