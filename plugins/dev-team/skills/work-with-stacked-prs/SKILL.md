---
name: work-with-stacked-prs
user-invocable: false
description: >
  Use when you are working with a stack of dependent GitHub PRs via GitHub's `gh stack` CLI
  extension (`github/gh-stack`). Provides the exact command/flags for each operation
  (init, add, submit, sync, view, merge) and the extension preflight check.
---

Use this skill when:
- You need to create, extend, push, sync, inspect, or merge a stack of dependent branches/PRs
- Another skill tells you to use a stacked-PR operation "from `work-with-stacked-prs`"
- You need to run the `github/gh-stack` extension preflight before any stacked-PR work begins

This skill is the **sole owner** of every direct `gh stack` CLI invocation in this feature — no
other skill invokes `gh stack` directly; they all reference this skill's named operations
instead. This isolation is deliberate risk mitigation for a days-old public-preview GitHub CLI
feature (see `_spec_StackedPRs.md`'s "Known upstream risk" decision). The same six operations are
also exposed as plain Python functions in the sibling `scripts/gh_stack.py` module — both this
skill's prose (for agent-driven calls) and `gh_stack.py` (imported directly by bare scripts like
`concurrent_schedule.py`/`stack_pr_poll.py`) shell out to the identical underlying commands, so
there is still exactly one place to change if the CLI does.

Every invocation is non-interactive: explicit positional arguments and flags always, the
interactive TUI never — per `github/gh-stack`'s own `skills/gh-stack/SKILL.md` guidance for
agentic use. `--json` output is only available from `view`; `init`/`add`/`submit`/`sync`/`merge`
have no `--json` support, so their outcome must be read from exit code and stderr text.

## General guidance

When executing a `gh` or `git` command, never prepend a `cd` to the directory onto the command.
Command safety scanners see this as a risk and prompt for permission, breaking autonomy.

**Cross-worktree caveat** (ADR-370 finding #1, `_findings_GhStackSpike.md`): `gh stack`'s local
stack-membership state lives in the worktree-private `.git/worktrees/<name>/gh-stack` file, not
the shared common git directory. It is **not** visible or correct from a different worktree than
the one that last registered the branch. Always run these operations from within the same
worktree that owns the branch/stack in question.

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
   No epic bootstrap or task work proceeds past this point.

This preflight is agent-driven (an `AskUserQuestion`-style interaction), not a pure script — only
the presence check itself (step 1) is scriptable, via `gh_stack.py`.

**Scope boundary for the decline hard-stop (step 3):** this skill and `gh_stack.py` have no
"calling flow" of their own to exercise end-to-end — they are consumed by other skills
(`ensure-feature-branch` in ADR-373, `ensure-working-branch` in ADR-375, and others across the
epic), and it is those callers' own runtime flow that actually halts on a decline. The only piece
of this decision that lives in this task's own scope is the absent/present signal
`check_gh_stack_extension_installed()` returns, which is covered by
`TestCheckGhStackExtensionInstalled`'s `no_extensions_installed`/`gh_extension_list_command_fails`
cases; the hard-stop behavior itself — reporting clearly and halting all further work when the
user declines — is a contract this document states for downstream callers to implement and verify
against their own calling flow when they consume this preflight.

## Operations

### init

Anchors a new stack to a trunk branch (typically the epic's feature branch).

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
  cascade across any remaining downstream branches (this module does not implement that
  follow-up; see `_findings_GhStackSpike.md` section 3).
- `--prune` deletes local branches for merged PRs.
- No `--json` support — read the outcome from exit code and stderr text.

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

## `gh_stack.py`

Every operation above is also exposed as a plain Python function in
`scripts/gh_stack.py`, importable directly (no MCP involved) by any bare script:
`init()`, `add()`, `submit()`, `sync()`, `view()`, `merge()`, and
`check_gh_stack_extension_installed()`. Each function returns `("ok" | "error", detail)` — for
`view`, `detail` is the parsed `--json` dict on success; for the other five, `detail` is stdout
text on success or stderr text on failure. See the module's own docstring for the full contract.
