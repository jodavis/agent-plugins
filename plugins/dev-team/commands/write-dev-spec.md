---
description: >
  Use when writing a complete new dev spec for a feature or GitHub issue.
  Guides through context gathering, first draft, iterative refinement, task breakdown, readiness review, and work item creation.
argument-hint: <work-item-id | #issue | feature name and description>
---

Use this skill when:
- A user asks to spec a new feature or GitHub issue at the implementation level
- You need to produce a complete _spec_*.md dev spec

You are writing a complete new dev spec, working with the user to refine it, breaking it down into
tasks, and verifying that it is complete.

## Steps

### 1 — Resolve the feature brief

Use the `gather-brief-sources` skill to resolve the argument into a feature brief, from whatever
mix of sources it points to (a tracked work item, pasted notes, a file, a link, or a combination).
A brief with no tracked work item among its sources is fine, as long as at least one source
resolved — `gather-brief-sources` already warns the user and asks them to fix or drop any
individually-referenced source (e.g. a work-item key) that doesn't actually resolve.

Additionally, check for an existing design doc: substitute the resolved `work-item-id` (if any)
into `documentation.specs.search` (from `get-project-configuration`). If a design doc is found,
read it in full and fold it in as the primary source — it already answers the problem/goals/
behavior questions. Record its path for `dev-spec-first-draft`'s `> **Design:**` header line.

If `gather-brief-sources` could not resolve any sources at all, tell the user and stop.

### 1.5 — Bootstrap the spec branch

Skip this step if step 1 resolved no `work-item-id` at all — there is no feature-work-item to
bootstrap a branch for yet; the user just keeps drafting on whatever branch they're already on,
and this happens later instead, in step 6, once (or if) a feature-work-item exists.

Otherwise, bootstrap the feature's own spec branch directly — there is no `ensure-feature-branch`
skill and no mandatory "feature branch" concept to set up first. A feature branch is now entirely
optional and user-driven: if the user wants their epic's tasks based on something other than
`main`, they create and check out that branch themselves *before* running this command — this
step never creates one on their behalf. What this step always does is create (or find) the spec's
own branch and commit the spec onto it, PR'd against whatever branch was active (or confirmed)
when it ran.

1. Use the `get-project-configuration` skill. Read `git-repo.working-branches.task`,
   `git-repo.user-alias`, and `documentation.dev-specs.search`.
2. **The spec branch is named like a task branch, not a special "feature" one** — build it from
   `git-repo.working-branches.task` (e.g. `dev/<user-alias>/<task-work-item-id>-<slug>`),
   substituting `<user-alias>` with `git-repo.user-alias` and `<task-work-item-id>` with
   `<work-item-id>-spec` (the feature-work-item's own id with a `-spec` suffix — this is also the
   branch's real, permanent identity: the feature's spec lives directly on it, not on a separate
   spec-commit branch merged elsewhere). Take the literal prefix of the `<user-alias>`-substituted
   template up to its next `<placeholder>` (`<task-work-item-id>`) — e.g. `dev/claude/` — call
   this `<feature-prefix>`.
3. Search for an existing spec branch for this feature-work-item:
   ```bash
   git fetch origin
   git branch -r --sort=-committerdate | grep -E "<feature-prefix><work-item-id>-spec(-|$)"
   ```
   Anchored the same way `ensure-working-branch` step 4d searches for this same branch — tolerant
   of a missing or different slug, but `<work-item-id>-spec` must end at a `-` or the branch
   name's end.
4. **If one or more matches are found**, take the first line of that sorted output (most recently
   pushed), strip the `origin/` prefix — that is `<spec-branch>`. Report it to the user, e.g.
   "Found existing spec branch `<spec-branch>` already tracking `<work-item-id>` — continuing on
   it," and pause for confirmation before proceeding, every time this step runs (even resuming a
   session from earlier) — a stale or wrong match here would silently redirect the whole drafting
   session onto the wrong branch. If the user says it's not the right one, stop and ask them how
   they want to proceed rather than guessing. Once confirmed:
   ```bash
   git checkout <spec-branch>
   git pull origin <spec-branch>
   ```
   Skip to sub-step 6.
5. **If no match is found**, this is a fresh feature spec:
   1. Report the currently checked-out branch (`git rev-parse --abbrev-ref HEAD`) to the user and
      ask them to confirm it as the spec branch's base — e.g. "About to create the spec branch for
      `<work-item-id>` off of `<current-branch>` — is that correct, or should I use a different
      branch?" This confirmation is what "a feature branch is not required, but the user creates
      one first if they want one" means in practice: if the user already checked out a branch of
      their own before running this command, confirming here is what picks it up as the base;
      otherwise this ordinarily confirms `main`. Call the confirmed answer `<base-branch>`.
   2. Compute a slug: substitute `<work-item-id>` into `documentation.dev-specs.search` and run
      it. If it finds a spec file, read its first `# ` heading and derive a short kebab-case slug
      from it (mirroring `_doc_<slug>.md`/`_spec_<slug>.md` naming). If no spec file is found yet
      — the common case, since this step usually runs before any draft exists — omit the slug
      rather than guessing one.
   3. Build `<spec-branch>` from `git-repo.working-branches.task`'s template (sub-step 2 above),
      substituting `<slug>` (if present in the template) with the computed slug, or omitting it
      (and its leading `-`) entirely if none is available yet. Once created, this name is
      permanent: a later run that *does* find a spec (and so could compute a slug) still finds
      this same branch via sub-step 3's search and never renames it.
   4. Create it from `<base-branch>` and push it immediately, with no other changes:
      ```bash
      git checkout -b <spec-branch> origin/<base-branch>
      git push origin <spec-branch>
      ```
6. Substitute `<work-item-id>` into `documentation.dev-specs.search` and run it to find the
   feature's spec file(s) locally. Call the result `<spec-path>` (if any).

   **If no spec file is found locally at all, skip straight to sub-step 8** (there may still be an
   open PR to check for, from a prior run that committed the spec some other way).

   **If a spec file is found**, check whether it's already present in `<spec-branch>`'s own tree —
   not merely tracked somewhere in this worktree's own history:
   ```bash
   git show origin/<spec-branch>:<spec-path>
   ```
   A zero exit means the spec is already committed on the spec branch — skip to sub-step 8. A
   nonzero exit means it isn't there yet, regardless of whether it's tracked elsewhere in this
   worktree — proceed to sub-step 7.
7. Commit and push the spec directly onto `<spec-branch>`:
   1. Ensure `<spec-branch>` is checked out and current:
      ```bash
      git checkout <spec-branch>
      git pull origin <spec-branch>
      ```
   2. Commit the spec file via the `commit-changes` skill, passing `<work-item-id>` and a short
      description (e.g. "Add feature spec file").
   3. Push it — `commit-changes` never pushes:
      ```bash
      git push origin <spec-branch>
      ```
8. Check whether an open PR already exists for `<spec-branch>`:
   ```bash
   gh pr list --head <spec-branch> --state open
   ```
   If one is found, this step is done. Otherwise, open one via the `create-pr` skill, passing
   `<work-item-id>`, `<spec-branch>` as the working branch, `<base-branch>` as the explicit
   `base`, and a short synthesized description ("Adds/updates the feature's spec file.") in place
   of a task brief — this PR isn't for a task, so there is no per-task brief to pass. This PR will
   eventually become the base of the first implementation PR. If `<base-branch>` isn't known at
   this point (sub-step 4's resume path, when this branch was pushed by an earlier run that never
   got as far as opening a PR), ask the user which branch to base the PR against before opening it.
9. Leave `<spec-branch>` checked out, regardless of which path above got here:
   ```bash
   git fetch origin
   git checkout <spec-branch>
   git pull origin <spec-branch>
   ```

### 2 — Write the first draft

Use the `dev-spec-first-draft` skill with the feature brief (and design doc, if found) to gather
context from docs, source code, and the user, and write the draft spec file.

**PAUSE — wait for the user to review the draft.**

### 3 — Refine the spec

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 4 — Task breakdown

Use the `dev-spec-task-breakdown` skill to draft the spec's task breakdown and pause for user
approval.

### 5 — Readiness review

Use the `document-readiness-review` skill on the spec file with `researcher-dev-spec-review` to
verify the full spec — design content and task breakdown together — is implementation-ready and
complete.

### 6 — Create tracked work items

Use the `dev-spec-create-work-items` skill to create tracked work items for the approved tasks
(and any related features), link task dependencies in the tracker, and update the spec with the
assigned keys.

If this step resolved (or created) a feature-work-item — whether or not step 1.5 already ran for
it — repeat step 1.5 in full, now with that feature-work-item's id as `<work-item-id>` if step 1
didn't already resolve one. This guarantees the spec is committed and PR'd by the end of this
command even if the user never staged/committed it themselves while drafting, and every one of its
sub-steps is check-before-act, so it's a no-op if step 1.5 already left everything in order. If
step 1.5 already ran (and its branch/base-branch confirmation already happened) earlier in this
same session, skip re-confirming and reuse `<spec-branch>`/`<base-branch>` directly — only ask
again if this is the first time step 1.5's logic runs this session (step 1 resolved no
`work-item-id` at all, so step 1.5 itself was skipped). Skip this entirely if no feature-work-item
exists at all (the user chose to skip work-item tracking entirely) — there is nothing to bootstrap
a branch for.

### 7 — Update work items

Use the `dev-spec-task-work-items` skill to update project work items with summaries of the finalized design decisions.
