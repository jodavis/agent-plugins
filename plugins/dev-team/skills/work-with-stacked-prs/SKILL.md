---
name: work-with-stacked-prs
user-invocable: false
description: Only use when instructed.
---

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
stack (the ongoing `sync`/`view` polling in `monitor-prs`, and anything else that needs the
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
branch `implement` or `monitor-prs` may still consider theirs. Use the
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

Full command syntax, flags, and behavior for each live in `references/operations.md` — only the
operation(s) relevant to what you're doing need reading, not all nine:

| Operation | What it does | Called from |
|---|---|---|
| `init` | Anchors a new stack to a trunk branch | not currently called — kept for CLI completeness |
| `add` | Creates a branch at HEAD, adds it to the stack top | not currently called — kept for CLI completeness |
| `submit` | Pushes and creates/updates PRs for the stack | not currently called — kept for CLI completeness |
| `sync` | Fetches, cascade-rebases, pushes, syncs PR state | not currently called — kept for CLI completeness |
| `rebase --continue` | Resumes the cascade after a conflict | `monitor-prs` step 5 |
| `view` | Reads stack membership/PR links (the only `--json` op) | `monitor-prs`'s poll scripts |
| `merge` | Merges one or more PRs, all-or-nothing | not currently called — kept for CLI completeness |
| `checkout` | Checks out a stack by number/PR/branch | `monitor-prs` step 2 |
| `link` | Creates/updates a stack from branch/PR names — the one op independent of local tracking state | `add-to-pr-stack`, once per task after sign-off |

## `gh_stack.py`

Every operation above is also exposed as a plain Python function in
`scripts/gh_stack.py`, importable directly (no MCP involved) by any bare script:
`init()`, `add()`, `submit()`, `sync()`, `view()`, `merge()`, `rebase_continue()`, `checkout()`,
`link()`, and `check_gh_stack_extension_installed()`. Each function returns `("ok" | "error",
detail)` — for `view`, `detail` is the parsed `--json` dict on success; for the other eight,
`detail` is stdout text on success or stderr text on failure. See the module's own docstring for
the full contract.
