---
name: ensure-feature-branch
user-invocable: false
description: >
  Bootstraps a feature's branch from `main`, commits and opens a PR for the feature's (possibly
  locally-uncommitted) spec file against that branch, and initializes the feature's `gh stack` —
  every step check-before-act so the whole skill is safely re-runnable. Invoked by
  `ensure-working-branch`'s single-task path and by `concurrent-orchestrate`, both of which hold
  real MCP/`gh` credentials.
argument-hint: <feature-work-item-id>
---

Use this skill when:
- A feature's branch, committed spec, and anchored `gh stack` need to exist before any
  task-level work can register into that stack, and the caller already holds real MCP/`gh`
  credentials (`ensure-working-branch`'s single-task path, or `concurrent-orchestrate`)

Do NOT use this skill when:
- You already know (from context already read this session) that the feature branch
  exists, its spec is committed on that branch, and a stack is already anchored to it — there is
  nothing left to check

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable.

This skill has no per-task context file to read — it operates on a feature-work-item id, not a
task-work-item id — so it always fetches configuration directly via `get-project-configuration`
rather than reading a context file's `Project Configuration` section.

## Configured behavior

### 1 — Load configuration and compute the feature-branch prefix

Use the `get-project-configuration` skill. Read `git-repo.working-branches.feature` and
`documentation.dev-specs.search`.

Take the literal prefix of `git-repo.working-branches.feature`
(`feature/<feature-work-item-id>-<slug>`) up to its first `<placeholder>` — `feature/` — call
this `<feature-prefix>`.

This mirrors the same tradeoff made for task-branch parsing in `detect_next_stack_event.py`
(ADR-377): rather than reverse-parsing an arbitrary placeholder ordering out of the configured
template, both assume the common real-world shape — a literal prefix (or, for task branches, an
id-shaped token), then the id, then an optional trailing `-<slug>`. Every template this project
actually ships (`git-repo`'s default config and every project override seen so far) follows that
shape; generalizing further to support other placeholder orderings would add real complexity for
no known use case, so this is the deliberate, consistent answer on both sides rather than an
oversight.

### 2 — Step 1: check whether the feature branch exists; create and push it if not

```bash
git fetch origin
git branch -r | grep -E "<feature-prefix><feature-work-item-id>(-|$)"
```

This is a prefix match — tolerant of a missing or different slug, the same convention
`ensure-working-branch` step 4d already uses to search this same template. Some of this repo's
real feature branches predate any slug convention and have none at all, so an exact-name match
would miss them. The match is anchored so `<feature-work-item-id>` must end at a `-` or the
branch name's end — unlike `ensure-working-branch` step 4d's unanchored search (which only looks
for a base branch to build on top of), this skill constructs and treats one specific branch as
*the* canonical feature branch for this feature-work-item, so an unanchored match risking a false
hit against a numerically adjacent id (e.g. `ADR-369` matching `feature/ADR-3699-...`) has bigger
consequences here.

**If one or more matching branches are found:** take the most recently pushed match — plain
`grep` output isn't sorted by push recency, so sort explicitly first:

```bash
git branch -r --sort=-committerdate | grep -E "<feature-prefix><feature-work-item-id>(-|$)"
```

Take the first line of that sorted output, strip the `origin/` prefix, and use it as
`<feature-branch>`. This step is done — skip straight to step 3.

**If no match is found**, this is a fresh feature:

1. Compute a slug: substitute `<feature-work-item-id>` into `documentation.dev-specs.search` and
   run it. If it finds a spec file, read its first `# ` heading and derive a short kebab-case slug
   from it (mirroring `_doc_<slug>.md`/`_spec_<slug>.md` naming). If no spec file is found yet,
   omit the slug — build `<feature-branch>` as `feature/<feature-work-item-id>` with no trailing
   `-<slug>` rather than guessing one.
2. Build `<feature-branch>` from `git-repo.working-branches.feature`'s template, substituting
   `<feature-work-item-id>` for the placeholder of the same name and the computed slug (if any)
   for `<slug>`.
3. Create it from `origin/main` and push it immediately, with no other changes:
   ```bash
   git checkout -b <feature-branch> origin/main
   git push origin <feature-branch>
   ```
   **Do not open a PR for `<feature-branch>` itself.** It is the stack's trunk, not a stacked
   entry — only the spec-doc branch (step 2 below) and each task's own branch ever PR *against*
   it.

### 3 — Step 2: check for a locally-uncommitted feature spec; commit and PR it if found

Substitute `<feature-work-item-id>` into `documentation.dev-specs.search` and run it to find the
feature's spec file(s) locally. Call the result `<spec-path>` (if any).

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
   git ls-remote --heads origin docs/<feature-work-item-id>-spec
   ```
   If it exists, don't assume its PR was actually opened — a prior run could have pushed the
   branch and then crashed or failed before reaching the `create-pr` call. Also check whether an
   open PR already targets `<feature-branch>` from that branch:
   ```bash
   gh pr list --head docs/<feature-work-item-id>-spec --base <feature-branch> --state open
   ```
   If that also finds an open PR, skip the rest of this step — a prior run already committed the
   spec and opened its PR. If the branch exists but no open PR is found, skip straight to
   sub-step 5 below and open the PR against the existing branch (no need to recommit or re-push).
2. Otherwise, check out `<feature-branch>` and create the dedicated branch from it:
   ```bash
   git checkout <feature-branch>
   git checkout -b docs/<feature-work-item-id>-spec
   ```
3. Commit the spec file via the `commit-changes` skill, passing `<feature-work-item-id>` and a
   short description (e.g. "Add feature spec file").
4. Push the new branch — `commit-changes` never pushes, and this PR is opened directly, not
   through the normal validate-then-push pipeline step:
   ```bash
   git push -u origin docs/<feature-work-item-id>-spec
   ```
5. Open a PR against the feature branch via the existing `create-pr` skill, passing
   `<feature-work-item-id>`, `docs/<feature-work-item-id>-spec` as the working branch,
   `<feature-branch>` as the explicit `base` (unchanged `create-pr` behavior), and a short
   synthesized description ("Adds the feature's spec file.") in place of a task brief — this PR
   isn't for a task, so there is no per-task brief to pass.
6. Check `<feature-branch>` back out, leaving the working tree positioned there for step 4.

### 4 — Step 3: check whether a stack is already anchored to this trunk; init it if not

Unconditionally check out `<feature-branch>` at the start of this step, regardless of which path
through steps 2 and 3 got here — step 2's "match found" branch and step 3's two skip branches
("no spec file found locally" and "spec already committed on the feature branch") never perform a
checkout themselves, so this step cannot assume one already happened:

```bash
git fetch origin
git checkout <feature-branch>
git pull origin <feature-branch>
```

With `<feature-branch>` now checked out locally, run `work-with-stacked-prs`'s Preflight check if
it hasn't already run earlier this session.

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
