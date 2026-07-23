---
name: resolve-rebase-conflict
user-invocable: false
description: >
  Use when a rebase has been left in progress with conflicts and the task's own brief/spec
  context is available to resolve them. Reads each conflicted file's hunks, resolves what the
  task context makes unambiguous, stages them, and drives `git rebase --continue` to
  completion. Reports "resolved" or "unresolved"; never runs `git push` or `git rebase
  --abort` itself.
argument-hint: <task-brief-or-spec-context>
---

Use this skill when:
- You (the Developer agent) have been invoked in the current worktree after the Rebase
  mechanic (`rebase_onto()`) already detected a conflict and left the rebase in progress —
  `rebase_onto()` itself has already exited; this skill does not call it and does not re-enter
  it
- You have the task's own brief/spec section available as context for what the working
  branch's changes were meant to accomplish

Do NOT use this skill when:
- No rebase is currently in progress in this worktree — there is nothing to resolve
- You need to start or retry a rebase from scratch — that is `rebase_onto()`'s job, not this
  skill's

You are working entirely inside a rebase already left mid-flight with conflicts. You never
call `rebase_onto()`, and you never run `git push` or `git rebase --abort` yourself — those
decisions belong to the caller (`dev-team:watch-pr`), made from whichever of `"resolved"` or
`"unresolved"` you report at the end.

## Steps

### 1 — Confirm a rebase is in progress

```bash
git status
```

Confirm the output names a rebase in progress (or check directly:
`test -d .git/rebase-merge || test -d .git/rebase-apply`). If neither is true, stop — there is
nothing for this skill to do.

### 2 — Enumerate every conflicted file up front

```bash
git status --porcelain=v1
```

Lines whose two-letter status code is one of `UU`, `AA`, `DD`, `AU`, `UA`, `UD`, or `DU` name a
file git could not auto-merge for the commit currently being replayed. Read the full list
before resolving anything. This matters for step 4's "stop at the first unresolvable conflict"
rule — you need to know the whole set of files touched by this one conflicting commit before
you can be sure none of them hides a conflict you can't confidently resolve.

### 3 — Read each conflicted file's regions

For each conflicted file, read it and find every conflict region. This repo does not set
`merge.conflictStyle`, so expect plain two-way markers, not `diff3`'s three-way `|||||||`
merge-base section:

```
<<<<<<< HEAD
<current branch's content — the commit already applied onto the new base>
=======
<incoming content — the working branch's own commit being replayed>
>>>>>>> <commit-ish>
```

There is no git subcommand that enumerates conflict regions structurally within a file — read
the markers directly.

### 4 — Resolve each region using the task's own context, or stop

For every conflict region, in every conflicted file from step 2:

- Read both sides, plus enough surrounding lines to understand each side's intent.
- Cross-reference the task's brief/spec context (this skill's argument) for what the working
  branch's own side was trying to accomplish. Most conflicts here are a genuine textual merge —
  keep the unrelated part of the other side's change, and layer this task's own specific,
  brief-stated intent on top of it — not a blind, wholesale "ours" or "theirs" choice.
- **Only resolve a region when the brief/spec context makes the correct final content
  unambiguous.** Concretely: the brief must state, or make directly inferable, either (a) the
  specific final value/content this task's own side was introducing (so it can be reapplied on
  top of the other side's still-relevant, superseded-but-known change), or (b) that both sides'
  content should simply be kept together (e.g. two independent additions to the same list). If
  arriving at the correct result would mean guessing at a value, a priority between two
  equally-plausible edits, or an intent the brief never states — even for just one region in
  one file — stop immediately:
  - Do not `git add` the file you were resolving, or any other conflicted file, even ones
    already fully resolved in this pass.
  - Do not partially edit any other still-conflicted file.
  - Leave every conflict marker exactly as found, and the rebase exactly as it was left.
  - Go straight to step 6 and report `"unresolved"`.
- If confidently resolvable, edit the file to the correct final content and remove the
  conflict markers for that region.

### 5 — Stage and continue

Only once every file from step 2 has had every one of its conflict regions resolved with
confidence:

```bash
git add <each resolved file>
GIT_EDITOR=true git rebase --continue
```

`GIT_EDITOR=true` avoids blocking on an interactive commit-message editor — the replayed
commit's own message carries forward unless the rebase specifically demands a new one.

- If `git rebase --continue` reports the next commit in the sequence also conflicts, return to
  step 2 and repeat for that commit's newly-conflicted files.
- If it reports the rebase is complete (e.g. "Successfully rebased and updated ..."), go to
  step 6.

### 6 — Report the result

- **The rebase reports complete and `git status` shows a clean working tree with no rebase in
  progress:** return `"resolved"`.
- **Step 4 stopped on a conflict that couldn't be resolved with confidence, or a rebase is
  still in progress for any other reason:** return `"unresolved"`.

Either way, stop here. Do not run `git rebase --abort` or `git push` — the caller
(`dev-team:watch-pr`) runs `git rebase --abort` on `"unresolved"` to return to a clean
pre-rebase state, and `git push --force-with-lease` on `"resolved"`; neither is this skill's
responsibility.
