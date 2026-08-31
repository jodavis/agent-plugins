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

Skip this step if step 1 resolved no `work-item-id` at all — the user just keeps drafting on
whatever branch they're already on, and this runs later instead, from step 6, once a
feature-work-item exists.

Otherwise, establish the feature's own spec branch: a plain git branch, named like a task branch,
that the spec is committed directly onto for as long as the epic is in flight. Base it on whatever
branch is currently checked out, confirming with the user first — a user who wants their epic's
tasks based on something other than `main` checks that branch out themselves before running this
command.

1. Use the `get-project-configuration` skill. Read `git-repo.working-branches.task`,
   `git-repo.user-alias`, and `documentation.dev-specs.name-format`.
2. Build `<feature-prefix>`: substitute `<user-alias>` with `git-repo.user-alias` in
   `git-repo.working-branches.task` (e.g. `dev/<user-alias>/<task-work-item-id>-<slug>`), then
   take the literal prefix up to its next `<placeholder>` (`<task-work-item-id>`) — e.g.
   `dev/claude/`. The branch name substitutes `<work-item-id>-spec` (the feature-work-item's own
   id with a `-spec` suffix) for `<task-work-item-id>` — this is also the branch's real, permanent
   identity: the feature's spec lives directly on it, never on a separate branch merged elsewhere.
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
   it," and pause for confirmation before proceeding, every time this step runs, even resuming a
   session from earlier. If the user says it's not the right one, ask them how they want to
   proceed rather than guessing. Once confirmed:
   ```bash
   git checkout <spec-branch>
   git pull origin <spec-branch>
   ```
   This step is done.
5. **If no match is found**, create one:
   1. Report the currently checked-out branch (`git rev-parse --abbrev-ref HEAD`) to the user and
      ask them to confirm it as the spec branch's base — e.g. "About to create the spec branch for
      `<work-item-id>` off of `<current-branch>` — is that correct, or should I use a different
      branch?" Call the confirmed answer `<base-branch>`.
   2. If this session has already written the spec draft (step 2 has already run — the case when
      this step is running for the first time from step 6, after work items were created), read
      its first `# ` heading and derive a short kebab-case slug from it, matching
      `documentation.dev-specs.name-format`'s own `<slug>` placeholder. Otherwise — the common
      case, since this step usually runs before step 2 drafts anything — omit the slug.
   3. Build `<spec-branch>` from `git-repo.working-branches.task`'s template (sub-step 2 above),
      substituting `<slug>` (if present in the template) with the computed slug, or omitting it
      (and its leading `-`) entirely if none is available. Once created, this name is permanent —
      a later run reuses it as-is via sub-step 3's search, even once a slug becomes available.
   4. Create it from `<base-branch>` and push it immediately, with no other changes:
      ```bash
      git checkout -b <spec-branch> origin/<base-branch>
      git push origin <spec-branch>
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

Skip the rest of this step if no feature-work-item exists at all (the user chose to skip
work-item tracking entirely) — there is nothing to bootstrap a branch for or commit the spec onto.

Otherwise, if this step resolved (or created) a feature-work-item and step 1.5 hasn't already run
this session (step 1 resolved no `work-item-id` at all, so step 1.5 was skipped), run step 1.5's
sub-steps 1–5 now, using that feature-work-item's id as `<work-item-id>`. If step 1.5 already ran
earlier this session, reuse its already-confirmed `<spec-branch>`/`<base-branch>` directly — do
not re-confirm.

Then commit and PR the spec directly onto `<spec-branch>`, using `<spec-path>` — the file step 2
wrote and every step since has been editing — with no need to look it up again:

1. Check whether it's already committed on `<spec-branch>`'s own tree:
   ```bash
   git show origin/<spec-branch>:<spec-path>
   ```
   A zero exit means it's already there — skip to sub-step 3.
2. Otherwise, commit it directly onto `<spec-branch>`:
   ```bash
   git checkout <spec-branch>
   git pull origin <spec-branch>
   ```
   Commit the spec file via the `commit-changes` skill, passing `<work-item-id>` and a short
   description (e.g. "Add feature spec file"). Push it — `commit-changes` never pushes:
   ```bash
   git push origin <spec-branch>
   ```
3. Check whether an open PR already exists for `<spec-branch>`:
   ```bash
   gh pr list --head <spec-branch> --state open
   ```
   If one is found, this step is done. Otherwise, open one via the `create-pr` skill, passing
   `<work-item-id>`, `<spec-branch>` as the working branch, `<base-branch>` as the explicit
   `base`, and a short synthesized description ("Adds/updates the feature's spec file.") in place
   of a task brief — this PR isn't for a task, so there is no per-task brief to pass. This PR
   becomes the base of the first implementation PR. If `<base-branch>` isn't known at this point
   (step 1.5's sub-step 4 path — the spec branch already existed, so no base was ever confirmed),
   ask the user which branch to base the PR against before opening it.
4. Leave `<spec-branch>` checked out:
   ```bash
   git fetch origin
   git checkout <spec-branch>
   git pull origin <spec-branch>
   ```

This guarantees the spec is committed and PR'd by the end of this command even if the user never
staged or committed it themselves while drafting.

### 7 — Update work items

Use the `dev-spec-task-work-items` skill to update project work items with summaries of the finalized design decisions.
