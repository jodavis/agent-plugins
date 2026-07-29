```mermaid
stateDiagram-v2
    [*] --> init
    init --> debugging : start
    debugging --> researching : debug_done
    debugging --> failed : reproduction_failed
    researching --> implementing : research_done
    implementing --> validating : impl_done
    validating --> fixing : build_failed
    validating --> fixing : tests_failed
    validating --> creating-pr : clean
    creating-pr --> reviewing : pr_created
    reviewing --> signoff : approved
    reviewing --> fixing-pr : changes_requested
    fixing-pr --> signoff : fix_done
    signoff --> handoff : approved
    signoff --> fixing-pr : changes_requested
    fixing --> validating : fix_done
    fixing --> failed : max_retries
    fixing-pr --> failed : max_retries
    handoff --> done : handoff_done
    done --> [*]
    failed --> [*]
```

The `debugging` state runs `investigate-bug` against the GitHub issue before the
researcher sees it. It reproduces the reported behaviour, investigates the root cause,
and commits a failing repro test and any diagnostic logging to the feature branch. Its
output — a structured root-cause report — is passed to the researcher as additional
context when writing the task brief. If the bug cannot be reproduced the pipeline fails
immediately with `reproduction_failed`.

The `signoff` state runs three tasks in parallel before making its decision:

1. **`review-sign-off`** — checks that all PR review threads have been resolved and scans
   modified files for new code quality issues (Priority 1–4). Resolves satisfied threads;
   leaves unresolved threads where the developer disagreed and the reviewer is pushing back.
2. **`researcher-validate`** — checks each exit criterion proposed by the researcher against
   the actual code and tests. Any `fail` or `partial` result counts as a failure.
3. **Script validation** — runs `validate-build` then (if clean) `validate-tests`.

All three must pass for `signoff` to emit `approved`. Any failure from any task emits
`changes_requested` and routes back to `fixing-pr`, with accumulated failure details.

`reviewing`'s own `approved` trigger routes to `signoff`, never directly to `handoff` — every
approval, including a clean first pass with no `fixing-pr` cycle, runs the full signoff checks
before any hand-off work happens.

The `handoff` state is reached only out of `signoff`'s own `approved` trigger. It runs
`final-sign-off`, a near-no-op agent turn whose only job is to report that the hand-off point
was reached — it does not itself convert the PR to ready, assign the Jira issue, or request a
review. That work is performed by this pipeline event's `after-signoff-success` instructions
(run generically by `run-event-hooks`, wrapped around this dispatch by `workflow-worker`), so a
project can configure or disable each piece independently.
