---
name: work-with-stacked-prs
user-invocable: false
description: >
  Use when you are working with a stack of dependent GitHub PRs via GitHub's `gh stack` CLI
  extension (`github/gh-stack`). Provides the exact command/flags for each operation
  (init, add, submit, sync, view, merge, rebase --continue, checkout, link) and the extension
  preflight check.
---

Use this skill when:
- You need to create, extend, push, sync, inspect, or merge a stack of dependent branches/PRs
- Another skill tells you to use a stacked-PR operation "from `work-with-stacked-prs`"
- You need to run the `github/gh-stack` extension preflight before any stacked-PR work begins

This skill is the **sole owner** of every direct `gh stack` CLI invocation in this feature — no
other skill invokes `gh stack` directly; they all reference this skill's named operations
instead. This isolation is deliberate risk mitigation for a days-old public-preview GitHub CLI
feature (see `_spec_StackedPRs.md`'s "Known upstream risk" decision). The same nine operations
are also exposed as plain Python functions in the sibling `scripts/gh_stack.py` module — both this
skill's prose (for agent-driven calls, including `add-to-pr-stack`'s own `link` call) and
`gh_stack.py` (imported directly by bare scripts like `concurrent_schedule.py`/`stack_pr_poll.py`/
`stack_rebase_continue.py`/`stack_checkout.py`) shell out to the identical underlying commands, so
there is still exactly one place to change if the CLI does.

Every invocation is non-interactive: explicit positional arguments and flags always, the
interactive TUI never — per `github/gh-stack`'s own `skills/gh-stack/SKILL.md` guidance for
agentic use. `--json` output is only available from `view`; `init`/`add`/`submit`/`sync`/`merge`/
`rebase --continue`/`checkout`/`link` have no `--json` support, so their outcome must be read from
exit code and stderr text.

## General guidance

When executing a `gh` or `git` command, never prepend a `cd` to the directory onto the command.
Command safety scanners see this as a risk and prompt for permission, breaking autonomy.

**Cross-worktree caveat** (ADR-370 finding #1, `_findings_GhStackSpike.md`): `gh stack`'s local
stack-membership state lives in the worktree-private `.git/worktrees/<name>/gh-stack` file, not
the shared common git directory. It is **not** visible or correct from a different worktree than
the one that last registered the branch. Always run `init`/`add`/`submit`/`sync`/`view`/`merge`/
`rebase --continue`/`checkout` from within the same worktree that owns the branch/stack in
question.

**Concurrent workers, concretely:** this repo's usual pattern gives each task its own fresh
`isolation: "worktree"` — that pattern is unsafe for the eight local-tracking `gh stack`
operations above. Per the spike's recommendation, every one of those operations for one feature's
stack (the ongoing `sync`/`view` polling in `monitor-stack`, and anything else that needs the
local `gh-stack` tracking state) must run from **one shared worktree per feature**, never from a
task's own per-task worktree — a second task calling one of these operations from a different
worktree would get a false "not part of a stack" result instead of seeing the first task's own
registration.

**`link` is the one exception.** It "does not rely on gh-stack local tracking state" (per
`gh stack link --help`) — it operates purely against GitHub, resolving branch names/PR numbers/
PR URLs directly through the API, and can create or extend a stack without ever running `init`/
`add` first. `link` is therefore the only operation callers may run from a task's own per-task
worktree: a task's working branch is a plain git branch, unrelated to `gh stack`, until it's PR'd
and signed off (see `ensure-working-branch`'s own intro) — `add-to-pr-stack` calls `link` once,
after sign-off, from whichever worktree the task's own pipeline is already running in. No caller
needs to route a `link` call back through the feature's shared worktree.

**Ad hoc/manual use** (a human, or any process outside the automated pipeline, wanting to read,
run, or test a stacked PR's code): never check out a stack member branch directly from whatever
checkout you happen to already be sitting in — that's a third, uncoordinated location touching a
branch `implement` or `monitor-stack` may still consider theirs. Use the
`checkout-stack-pr-for-review` skill instead; it creates a disposable local branch off the PR's
own tip rather than touching the shared branch itself.

## Preflight check

Before any stacked-PR operation runs for the first time in a session, verify the extension:

1. Run `gh extension list` and confirm it includes a line whose second (tab-separated) field is
   literally `github/gh-stack` — not some other, unrelated extension that happens to share the
   `stack` command name. `gh_stack.py`'s `check_gh_stack_extension_installed()` function performs
   this exact check and returns `True`/`False`, so a caller with access to `gh_stack.py` can call
   it directly instead of parsing the output itself.
2. If it is **not** installed, use `AskUserQuestion` to offer to install it now (this repo's Auto
   Mode convention: ask only when a human decision is genuinely needed, since installing a new
   `gh` extension is not something to do silently). If the user accepts, run
   `gh extension install github/gh-stack` and re-run step 1 to confirm.
3. If the user **declines** the install offer, hard-stop: report clearly that stacked-PR work
   cannot proceed without `github/gh-stack`, and stop — there is no fallback stacked-PR mechanism.
   No feature bootstrap or task work proceeds past this point.

This preflight is agent-driven (an `AskUserQuestion`-style interaction), not a pure script — only
the presence check itself (step 1) is scriptable, via `gh_stack.py`.

**Scope boundary for the decline hard-stop (step 3):** this skill and `gh_stack.py` have no
"calling flow" of their own to exercise end-to-end — they are consumed by other skills
(`write-dev-spec`'s own step 1.5 in ADR-373, `ensure-working-branch` in ADR-375, and others across
the feature), and it is those callers' own runtime flow that actually halts on a decline. The only
piece of this decision that lives in this task's own scope is the absent/present signal
`check_gh_stack_extension_installed()` returns, which is covered by
`TestCheckGhStackExtensionInstalled`'s `no_extensions_installed`/`gh_extension_list_command_fails`
cases; the hard-stop behavior itself — reporting clearly and halting all further work when the
user declines — is a contract this document states for downstream callers to implement and verify
against their own calling flow when they consume this preflight.

## Operations

### init

Anchors a new stack to a trunk branch (typically the feature's own branch).

```
gh stack init [branches...] [-b/--base <branch>]
```

- Adopts existing branches or creates missing ones; the first branch is based on the trunk, each
  subsequent branch on the previous one.
- `-b/--base <branch>` specifies a non-default trunk branch (defaults to the repo's default
  branch).
- **Hard error (exit 5)** if the target trunk is already anchored to a stack — confirmed directly
  by ADR-370. Never treat this as idempotent or a no-op; callers must check whether a stack is
  already anchored (e.g. via `view`) before calling `init`.
- **Not currently called by any skill in this feature** — `link` (below) creates a stack from
  scratch itself the first time any task registers into it, so nothing needs to pre-anchor an
  empty one ahead of time. Kept here for CLI completeness and for a project that wants to pre-seed
  a stack manually.

### add

Creates a new branch at HEAD, adds it to the top of the stack, and checks it out.

```
gh stack add [branch] [-A|-u] [-m <message>]
```

- `-A` stages all changes (including untracked files); `-u` stages tracked-file changes only.
- `-m <message>` creates a commit with that message; if omitted while `-A`/`-u` is used, an
  editor opens for the commit message (do not rely on this in non-interactive use — always pass
  `-m` explicitly).
- If no branch name is given and `-m` is provided, the branch name is auto-generated from the
  commit message.
- **Does not push** — push the new branch separately after `add` succeeds.
- **Not currently called by any skill in this feature** — task-branch registration is done via
  `add-to-pr-stack`'s `link` call instead (see this skill's Concurrent workers note above for
  why). Kept here for CLI completeness.

### submit

Pushes and creates/updates PRs for the stack.

```
gh stack submit [--auto] [--open] [--remote <name>]
```

- **Confirmed by ADR-370: always scoped to the entire stack.** No per-branch flag exists — every
  branch without a PR is included, every branch is pushed, and existing PRs' base branches are
  updated. It only *creates* new PRs for branches that don't already have one, so it is safe to
  resubmit repeatedly (idempotent for already-PR'd entries) when a new top entry is added.
- `--auto` is **required for non-interactive use** — skips the interactive editor and uses
  auto-generated PR titles.
- Omit `--open` to default new PRs to draft; pass `--open` to mark new and existing PRs ready for
  review.
- `--remote <name>` overrides the auto-detected remote.
- **Not currently called by any skill in this feature** — PRs are created directly via `create-pr`
  against an explicit `base_branch`, and registered into the stack later via `link`. Kept here for
  CLI completeness.

### sync

Fetches, cascade-rebases the stack, pushes, and syncs PR state.

```
gh stack sync [--prune] [--remote <name>]
```

- Performs, in order: fetch → reconcile local/remote stack membership → fast-forward trunk →
  cascade-rebase stack branches → push all branches (`--force-with-lease --atomic`) → sync PR
  state → link open PRs into a stack object on GitHub.
- **Aborts cleanly, with no changes and exit 0, on non-interactive divergence** (confirmed by
  ADR-370) — a clean exit does not always mean something changed.
- On a genuine rebase conflict, exits non-zero — **confirmed as exit code 3 for `gh stack rebase`
  run standalone** in ADR-370's spike; `sync` delegates its own cascade-rebase step to `rebase`
  internally (per `gh stack sync --help`), so the same exit code is *inferred*, not directly
  observed, when the conflict is reached via `sync`'s cascade rather than a standalone `rebase`
  call (see `_findings_GhStackSpike.md` section 3 — the spike's own `sync` attempt hit an
  unrelated non-interactive-divergence abort with exit 0 before `rebase` was run directly).
  `.git/rebase-merge` is left in place with standard git conflict markers — `resolve-rebase-
  conflict`'s existing plain-git contract handles the currently-conflicted branch unchanged, but
  a multi-branch stack needs a follow-up `gh stack rebase --continue` call afterward to resume the
  cascade across any remaining downstream branches — see the `rebase --continue` operation below,
  which `monitor-stack` calls for exactly this (see `_findings_GhStackSpike.md` section 3).
- `--prune` deletes local branches for merged PRs.
- No `--json` support — read the outcome from exit code and stderr text.

### rebase --continue

Resumes gh-stack's own cascading rebase across the remaining downstream branches after the
currently-conflicted branch's own git-level rebase has already been completed via a plain
`git rebase --continue` (`resolve-rebase-conflict`'s unchanged contract).

```
gh stack rebase --continue
```

- Per ADR-370's spike (`_findings_GhStackSpike.md` section 3): a plain `git rebase --continue`
  only finishes the currently-conflicted branch's own rebase — downstream branches are left
  un-rebased (shown as a drift warning in `gh stack view`) until this call specifically resumes
  the cascade. A fresh `sync` call is **not** an equivalent substitute for this step.
- Exit 0 means the whole cascade reached a clean state. A further non-zero exit (confirmed exit
  code 3 in the spike, matching `sync`'s own conflict exit code) means the cascade hit another
  conflict higher in the stack — `.git/rebase-merge` is left in place again, with the same
  standard git conflict shape as the first conflict; callers should loop back into another
  conflict-resolution round exactly as they do for the first one.
- No `--json` support — read the outcome from exit code and stderr text.
- `monitor-stack`'s step 5 calls this (via `stack_rebase_continue.py`) immediately after
  `resolve-rebase-conflict` reports `"resolved"`, before returning to the poll loop.

### view

Reads current stack membership, branch ordering, and each entry's PR link.

```
gh stack view [--json] [--short]
```

- **The only operation that supports `--json`.** Returns `trunk`, `currentBranch`, and
  `branches[]` (each with `name`, `head`, `base`, `isCurrent`, `isMerged`, `isQueued`,
  `needsRebase`, and an optional `pr` object).
- Does **not** carry review-comment or CI-check state — only stack/PR-link membership.
- `--short` gives a compact one-line-per-branch view (not needed when parsing `--json`).

### merge

Merges one or more PRs in the stack, all-or-nothing.

```
gh stack merge [<stack-number>|<pr-number>] [-y/--yes] [--merge|--squash|--rebase|--merge-method <method>]
```

- With no argument, merges the stack for the current branch. A bare number is a stack number
  first, then a PR number.
- All members up to and including the chosen PR merge in a single all-or-nothing operation — if
  any PR can't merge, none are.
- `-y/--yes` is **required for non-interactive use** — merges without prompting, using the
  last-used merge method unless `--merge-method <method>` (`merge`, `squash`, or `rebase`) is
  given.
- No `--json` support — read the outcome from exit code and stderr text.

### checkout

Checks out a stack by stack number, PR number, PR URL, or branch name.

```
gh stack checkout [<stack-number>|<pr-number>|<pr-url>|<branch>]
```

- A bare number is tried first as a stack number, then a locally tracked PR number, then a PR
  number whose stack is discovered from GitHub, and finally a branch name.
- **A PR number or PR URL not yet tracked locally is discovered from the GitHub API, its branches
  fetched, and the stack set up locally** — this is the one form of `checkout` that can bootstrap
  `gh stack` awareness into a worktree that never ran `init`/`add` for this stack itself (needed
  because `gh stack`'s local stack-membership state is worktree-private — ADR-370 finding #1). A
  branch name, by contrast, only resolves against stacks already tracked locally.
- With no argument, opens an interactive picker — never use this form non-interactively.
- No `--json` support — read the outcome from exit code and stderr text.
- `monitor-stack`'s step 2 calls this (via `stack_checkout.py`, passing a PR number) to land its
  own freshly spawned worktree on a real stack member instead of the trunk, which `gh-stack`
  doesn't consider a member.

### link

Creates or updates a stack on GitHub purely from branch names, PR numbers, or PR URLs — the one
operation that does **not** rely on local `gh-stack` tracking state (see the cross-worktree
caveat above).

```
gh stack link <stack-number | branch-or-pr> <branch-or-pr> [<branch-or-pr>...] [--base <branch>] [--open] [--remote <name>]
```

- Arguments are given in stack order, bottom to top. Each is a branch name, PR number, or PR URL.
  A branch argument without an open PR is pushed and a new PR created automatically, with correct
  base-branch chaining; an argument that already has an open PR just reuses it.
- If none of the arguments are already in a stack, a new one is created; if some already are, the
  existing stack is extended to include the rest — **existing PRs are never removed.**
- **Shortcut for growing an existing stack:** pass its stack number (shown in the GitHub stack UI)
  as the first argument — the rest are appended to its top, and any already in that stack are
  skipped.
- `--base <branch>` sets the base branch for the bottom of a *new* stack (defaults to the repo's
  default branch) — irrelevant when growing an existing stack via the stack-number shortcut.
- Omit `--open` to leave newly-created PRs as drafts; pass it to mark new and existing PRs ready
  for review. `--remote <name>` overrides the auto-detected remote.
- No `--json` support — read the outcome from exit code and stderr text.
- `add-to-pr-stack` calls this (via `gh_stack.py`'s `link()`) once per task, right after sign-off,
  passing just the task's immediate dependency (or the feature branch, for the epic's first task)
  and the task's own already-open PR — never the whole stack — since `link` only needs enough
  context to place one new entry correctly, and running it from the task's own per-task worktree
  needs no shared-worktree routing at all.

## `gh_stack.py`

Every operation above is also exposed as a plain Python function in
`scripts/gh_stack.py`, importable directly (no MCP involved) by any bare script:
`init()`, `add()`, `submit()`, `sync()`, `view()`, `merge()`, `rebase_continue()`, `checkout()`,
`link()`, and `check_gh_stack_extension_installed()`. Each function returns `("ok" | "error",
detail)` — for `view`, `detail` is the parsed `--json` dict on success; for the other eight,
`detail` is stdout text on success or stderr text on failure. See the module's own docstring for
the full contract.
