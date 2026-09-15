# `gh stack` Feasibility Spike Findings (ADR-370)

This is the findings note produced by ADR-370, the feasibility spike required by
`_spec_StackedPRs.md`'s "Known upstream risk" decision before any other task in that spec's
breakdown (ADR-371–ADR-378) builds on GitHub's native `gh stack` CLI. Every command below was run
non-interactively (`gh` v2.96.0, `github/gh-stack` extension v0.1.0) against a throwaway private
scratch repo (`jodavis-claude/gh-stack-spike-adr370`) with a real GitHub remote, per the spec's
"scratch repo, real GitHub remote" instruction. The repo is left in place (private, harmless) —
the authenticated token lacks the `delete_repo` scope needed to clean it up automatically; a human
with admin rights on the `jodavis-claude` account can delete it, or it can simply be left as an
inert artifact.

Each section below maps 1:1 to one of the spec's four Open Questions and this task's checklist.

## 1. Cross-worktree `gh stack` state (highest-risk item)

**Spec's Open Question:** does `gh stack`'s local notion of "topmost branch"/stack membership
stay visible and correct from a *different* worktree than the one that last ran `gh stack add`?

**What was done:** Built a two-branch stack (`main` → `feature/stack-a` → `feature/stack-b`) in a
primary clone using `gh stack init main`, `gh stack add feature/stack-a`, `gh stack add
feature/stack-b`. Pushed both branches, then ran `git worktree add ../secondary
feature/stack-a` to create a second, linked worktree of the *same* repository (not a second
`git clone`) — the shape this pipeline actually uses (`workflow-orchestrate` runs each task in
its own worktree of one shared repo). Ran `gh stack view` from the second worktree.

**What was observed:** `gh stack view` from the second worktree reported `current branch
"feature/stack-a" is not part of a stack`, even though the branch genuinely was checked out
correctly there (`git status` / `git branch -vv` both confirm `On branch feature/stack-a`, no
detached HEAD) and the primary worktree's `gh stack view` correctly showed it as part of the
stack. Root cause, confirmed by inspection: gh-stack's local state is a JSON file at
`<repo>/.git/gh-stack` (containing stack membership as branch names, not paths), but it is
written and read relative to `git rev-parse --git-dir` — for a linked worktree, that resolves to
the **worktree-private** directory (`<repo>/.git/worktrees/<name>/`), not the shared common git
directory. `ls <repo>/.git/worktrees/secondary/` confirms no `gh-stack` file exists there at all;
gh-stack never falls back to `--git-common-dir`.

**Recommendation:** `gh stack`'s local stack-membership state is **not** visible or correct
across `git worktree` checkouts of the same repository — this is a hard *refutation* of the
optimistic reading of the Open Question, not just "unconfirmed." Every task's `ensure-working-
branch`/stack-registration step must run `gh stack add`/`gh stack init` from *within the same
worktree* that will subsequently run `gh stack submit`/`sync`/`view` for that branch — a
successor task's worktree cannot simply assume the prior task's `gh stack add` is visible to it.
Any design that reads stack membership from a different worktree than the one that wrote it
(e.g. an orchestrator process checking stack state from a shared/root worktree while individual
tasks run in per-task worktrees) will get a false "not part of a stack" result. This should be
treated as a structural constraint on ADR-371's `work-with-stacked-prs`/`gh_stack.py` design, not
a corner case: any wrapper around `gh stack` needs to either (a) always invoke it from the same
worktree that owns the branch in question, or (b) explicitly re-derive/re-register stack state
per worktree rather than assuming it carries over.

## 2. `gh stack submit` per-entry granularity

**Spec's Open Question:** does `gh stack submit` for a single, newly-added topmost branch submit
only that branch, or the entire stack?

**What was done:** First ran `gh stack submit --auto` against the full three-branch stack
(`feature/stack-a`, `feature/stack-b`, neither yet having a PR) to observe first-submit behavior.
Then added a *third* branch, `feature/stack-c`, on top of the already-submitted stack (so
`feature/stack-a` and `feature/stack-b` already had open PRs, and only `feature/stack-c` was
"newly-added" and PR-less), and ran `gh stack submit --auto` again to isolate the
newly-added-branch case the checklist item describes.

**What was observed:** `gh stack submit --help` itself states the contract plainly: "Every
branch without a PR is included by default" and step 1 of its documented behavior is "Pushes
**all** branches to the remote." The second run confirmed this exactly: the output was `PR #1 for
feature/stack-a is up to date`, `PR #2 for feature/stack-b is up to date`, `✓ Created PR #4 for
feature/stack-c`, and `✓ Pushed and synced 4 branches` (all four branches including `main`, even
though only one branch was new). There is no `--branch`/entry-scoping flag on `submit` at all.

**Recommendation:** confirms the spec's Open Question framing — `submit` is scoped to the
**entire active stack**, not a single entry, with no way to opt out. It always pushes every
branch in the stack and checks/updates every existing PR's base, but it only *creates* new PRs
for entries that don't already have one — so a stack whose lower entries already have real PRs is
safe to resubmit repeatedly (idempotent for those entries) when a new top entry is added. This
directly resolves the `#129`-adjacent design tension: `create-pr-from-context` running `submit`
for "just this task's branch" is not literally possible, but is **effectively safe** to model as
such *so long as the design gates submission on every entry below the new one already being a
real, open PR* (the first of the two fallbacks the spec's Open Question lists) — since submit
will only touch/update those, not recreate or duplicate them. The second fallback (bypassing
`submit` and creating the PR directly from a `view`-sourced base) is not necessary as a primary
path; it should remain a documented alternative only, not required design work, given `submit`'s
observed idempotency for already-PR'd entries.

## 3. `gh stack sync`/`gh stack rebase` conflict mechanics

**Spec's Open Question:** what git state does a `gh stack sync` conflict leave behind (does
`.git/rebase-merge` appear, matching `resolve-rebase-conflict`'s expectation), and does
completing it need a plain `git rebase --continue` or `gh stack rebase --continue`?

**What was done:** Created a genuine conflict by committing a README.md change on
`feature/stack-a` and a *different* conflicting change to the same line on `main`, then attempted
to reconcile them non-interactively (`< /dev/null`, no TTY). `gh stack sync` was tried first;
it detected an unrelated local/remote divergence (the local stack's tracked `main` entry vs. the
GitHub stack object, which never included `main`) and aborted cleanly with no changes and exit
code 0, per its own documented "abort — no changes were made" behavior for non-interactive
divergence. This is a real, useful finding but not the conflict scenario itself, so `gh stack
rebase` was run directly next (the command `sync` delegates cascading-rebase to internally,
per its `--help`), which reached the actual conflict.

**What was observed:**
- `gh stack rebase` reported `⚠ Rebasing feature/stack-a onto main — conflict`, printed
  human-readable conflict-resolution instructions, and exited with **code 3** (non-zero,
  reliably detectable by a script checking exit status).
- `.git/rebase-merge` **was** present (confirmed via `ls`), and `git status` showed the exact
  standard git conflict shape: `interactive rebase in progress; onto <sha>`, `both modified:
  README.md`, with real `<<<<<<<`/`=======`/`>>>>>>>` markers in the file — matching
  `resolve-rebase-conflict`'s existing expectation precisely, not "something else."
- After resolving the conflict and `git add`-ing the file, a **plain** `git rebase --continue`
  succeeded on its own (exit 0, `Successfully rebased and updated refs/heads/feature/stack-a`) —
  the git-level mechanics of a `gh stack`-initiated rebase are fully standard-git and
  `resolve-rebase-conflict`'s existing per-conflict resolution logic needs no change.
- However, that plain continue only completed `feature/stack-a`'s own rebase. The downstream
  branches (`feature/stack-b`, `feature/stack-c`) were left un-rebased — `gh stack view` still
  showed `feature/stack-b` with a drift warning (⚠) afterward. Running `gh stack rebase
  --continue` next (with no conflict remaining to resolve) correctly detected the git-level
  rebase was already done and resumed gh-stack's own **cascade**: `✓ Rebased feature/stack-a onto
  main`, `✓ Rebased feature/stack-b onto feature/stack-a`, `✓ Rebased feature/stack-c onto
  feature/stack-b`, exit 0, `gh stack view` fully clean afterward.

**Recommendation:** both secondary sources referenced in the researcher brief's ambiguity 4 were
partially right and partially wrong — settle it directly rather than leaving the inference to
ADR-378's author. `resolve-rebase-conflict`'s existing plain-git contract (find `.git/rebase-
merge`, resolve conflict markers, `git add`, `git rebase --continue`) **works as-is** and
requires no change for the git-level mechanics of a single conflicted branch within a `gh stack`
rebase. But it is **not sufficient on its own** for a multi-branch stack: after
`resolve-rebase-conflict` completes the currently-conflicted branch, ADR-378's `monitor-stack`
needs an additional stack-aware follow-up step that calls `gh stack rebase --continue` (not a
fresh `sync`) to resume the cascade across the remaining downstream branches — this is the "stack-
aware follow-up rather than a fresh `sync` invocation" the spec's decision already anticipated,
now confirmed as the correct shape. Concretely: `resolve-rebase-conflict` resolves the git-level
conflict and stays unchanged; `monitor-stack` (or whatever ADR-378 designs) must call `gh stack
rebase --continue` immediately afterward as its own next action, and should treat that call's
own non-zero exit / new conflict output the same way (looping back into another
`resolve-rebase-conflict` round if the cascade hits a second conflict further up the stack).

## 4. `gh stack init` idempotency against an already-anchored trunk

**Spec's Open Question:** does re-running `gh stack init` against a trunk that already has a
stack anchored to it error, reset, or silently no-op?

**What was done:** With `main` already initialized as a stack trunk (and branches stacked on top
of it), checked out `main` again and re-ran `gh stack init main`.

**What was observed:** It errored immediately: `✗ current branch "main" is already part of a
stack`, exit code 5. `gh stack view` immediately after confirms the existing stack (all branches,
all PR links) was left completely untouched — no reset, no silent no-op with a changed/duplicated
stack object.

**Recommendation:** confirms the spec's own framing that this "though the spec's own explicit
existence-check already sidesteps needing this to be a no-op" — no design change is required.
`ensure-feature-branch`'s existing check-before-act shape (check whether the branch/stack already
exists before calling `gh stack init`, rather than relying on `init` itself being safe to
re-run) is the only correct approach, and is validated as necessary: calling `gh stack init` on
an already-anchored trunk is a hard error the caller must avoid, not a tolerable idempotent
retry.

## Summary: what changes as a result

| Open Question | Result | Design impact |
|---|---|---|
| Cross-worktree stack state | **Refuted** — not visible across `git worktree` checkouts (state lives in the worktree-private git dir, not the shared common dir) | ADR-371's `gh_stack.py`/`work-with-stacked-prs` must always operate on a branch from within the same worktree that registered it; no cross-worktree read of stack membership is safe |
| `submit` per-entry granularity | **Confirmed against** per-branch scoping — `submit` always touches the whole stack | Design ADR-376/`create-pr-from-context`'s "submit just this task's branch" as "submit the whole stack, relying on submit's observed idempotency for entries that already have a PR" instead — first fallback in the spec's Open Question is the one to implement, not the second |
| `sync`/`rebase` conflict mechanics | **Partially confirmed** — git-level state matches `resolve-rebase-conflict`'s existing expectation exactly, but the multi-branch cascade needs a `gh stack rebase --continue` follow-up `resolve-rebase-conflict` doesn't do today | ADR-378's `monitor-stack` needs a stack-aware follow-up step that calls `gh stack rebase --continue` right after `resolve-rebase-conflict` finishes the currently-conflicted branch, looping back on any further conflict |
| `init` idempotency | **Confirmed as hard error**, not a no-op | No design change — validates `ensure-feature-branch`'s existing check-before-act shape as required, not optional |

All four findings are now resolved with concrete recommendations; none remain "TBD" for
ADR-371–ADR-378 to re-derive independently.
