## Making the fix (`can-fix` / `can-push-fix`)

Runs after a workaround has been applied and an issue has been filed or updated — whether via
"Before diagnosing" step 4's reused-workaround path, or via "Diagnosis steps"/"Fix strategies"
above. Read `troubleshooter.can-fix` and `troubleshooter.can-push-fix` through
`get-project-configuration`'s merged output (or the context file's already-resolved
`Project Configuration` section, if present).

1. **Neither flag set:** do not attempt a code change. Issue logging above is unaffected either
   way — this step only gates the fix itself.
2. **`can-fix` set, and the root cause is concretely fixable:** write the fix — adapt the linked
   PR's branch found in "Before diagnosing" step 5 if one applies, otherwise write it fresh —
   directly in `<skill-dir>`'s repo root (the filesystem root resolved in "Before diagnosing" step
   1), on a fresh branch named `troubleshooter/<slug>` cut from the default branch there.
   - **`can-push-fix` not also set:** stage and commit the change on that branch, then merge it
     directly into whatever branch is currently checked out in `<skill-dir>`'s repo root — no
     push, no PR. Add a comment to the issue describing the change (what was fixed and why).
   - **`can-push-fix` also set:** run `work-with-stacked-prs`'s Preflight check first if it
     hasn't already run earlier this session — every step below shells out directly to
     `gh stack`, and this skill may run outside the normal pipeline where that check would
     otherwise already have happened.
     1. `gh stack view --json` (run from `<skill-dir>`'s repo root) to check whether a stack
        already exists in this checkout.
     2. **No stack yet:** run `gh stack init troubleshooter/<slug>` *before* committing —
        confirmed live against `github/gh-stack` v0.1.0: with no branch argument it fails
        non-interactively (`interactive input required; provide branch names as arguments`), but
        given an explicit branch name that doesn't exist yet it creates that branch off the
        trunk, checks it out, and leaves the working tree (including uncommitted changes) as-is.
        Stage and commit the change on that branch now with a normal `git commit`.
     3. **A stack already exists:** leave the change staged but uncommitted, then run
        `gh stack add -A -m "<commit message>" troubleshooter/<slug>` — confirmed this both
        creates the branch on top of the current stack tip and commits the staged fix in one
        step. Do not pre-commit in this case: confirmed a pre-committed change makes
        `gh stack add` fail with `no changes to commit after staging`, leaving the fix stranded
        on the previous branch instead of creating the new one. This is what makes a second
        concurrent fix land on top of the first instead of racing to branch off the same commit.
     4. Either way: `gh stack submit --auto` (no `--open`) — pushes all branches and
        creates/updates PRs as drafts with auto-generated titles (confirmed).
     5. Re-run `gh stack view --json` (no new tool needed — confirmed each branch's entry gains a
        `pr: { number, url, state }` field once `gh stack submit` has run) to find this branch's
        new PR, then immediately overwrite its title and body via
        `mcp__plugin_github_github__update_pull_request`, reusing `create-pr`'s structured body
        convention (Work item / Changes / Design decisions / Testing completed sections) plus a
        final `Closes #<issue-number>` line referencing the issue — without going through
        `create-pr`'s own create call, since `gh stack submit` already created the PR. Never
        promote it out of draft or request review — this skill's job stops at opening the draft
        PR.
     6. Add the PR link plus a description of the change to the issue.
3. Apply the `message-attribution` skill's line to every issue or comment body written anywhere
   in this skill — "Before diagnosing" above, the new-issue/cross-link/matched-issue-update
   bullets in "Fix strategies" above, this section's issue comments, and (per `create-pr`'s own
   structured body convention, reused above) the final line of the PR title/body overwritten via
   `update_pull_request` in the `can-push-fix` sub-step — per existing convention.

