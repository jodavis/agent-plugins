```mermaid
stateDiagram-v2
    [*] --> init
    init --> planning : setup_done
    planning --> implementing : ready
    implementing --> validating : impl_done
    validating --> fixing : build_failed
    validating --> fixing : tests_failed
    validating --> creating_pr : clean
    creating_pr --> reviewing : pr_created
    reviewing --> signoff : approved
    reviewing --> fixing_pr : changes_requested
    fixing_pr --> signoff : fix_done
    signoff --> add_to_pr_stack : approved
    signoff --> fixing_pr : changes_requested
    add_to_pr_stack --> done : linked
    fixing --> validating : fix_done
    fixing --> failed : max_retries
    fixing_pr --> failed : max_retries
    done --> [*]
    failed --> [*]
```

The `signoff` state runs three tasks in parallel before making its decision:

1. **`review-sign-off`** — checks that all PR review threads have been resolved and scans
   modified files for new code quality issues (Priority 1–4). Resolves satisfied threads;
   leaves unresolved threads where the developer disagreed and the reviewer is pushing back.
2. **`researcher-validate`** — checks each exit criterion from the spec against the
   actual code and tests. Any `fail` or `partial` result counts as a failure.
3. **Script validation** — runs `validate-build` then (if clean) `validate-tests`.

All three must pass for `signoff` to emit `approved`. Any failure from any task emits
`changes_requested` and routes back to `fixing_pr`, with accumulated failure details.

`reviewing`'s own `approved` trigger routes to `signoff`, never directly to `done` — every
approval, including a clean first pass with no `fixing_pr` cycle, runs the full signoff checks
before the pipeline finishes.

`signoff` carries the `signoff` pipeline event directly — `dev_team.py` resolves this project's
`before-signoff`/`after-signoff-approved` instructions (converting the PR to ready, assigning the
work item, requesting a review, etc.) around `SignoffStep`'s own resolution and dispatches them as
their own pipeline steps, so a project can configure or disable each piece independently without
needing a separate hand-off state or agent turn.

`add_to_pr_stack` runs `add-to-pr-stack` (`gh stack link`) once sign-off approves — the sole place
a task's branch is ever registered into its epic's `gh stack`; `ensure-working-branch` never does
this itself (see that skill's own intro). This is why `concurrent-orchestrate`'s "reached
hand-off" check — the pipeline reaching `done` — is the correct signal for auto-starting
`monitor-stack`: by the time a task's pipeline reaches `done`, its PR is not just open but
actually linked into the stack `monitor-stack` will poll.
