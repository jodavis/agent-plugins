```mermaid
stateDiagram-v2
    [*] --> init
    init --> researching : setup_done
    researching --> implementing : research_done
    implementing --> validating : impl_done
    validating --> fixing : build_failed
    validating --> fixing : tests_failed
    validating --> creating-pr : clean
    creating-pr --> reviewing : pr_created
    reviewing --> handoff : approved
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

The `signoff` state runs three tasks in parallel before making its decision:

1. **`review-sign-off`** — checks that all PR review threads have been resolved and scans
   modified files for new code quality issues (Priority 1–4). Resolves satisfied threads;
   leaves unresolved threads where the developer disagreed and the reviewer is pushing back.
2. **`researcher-validate`** — checks each exit criterion from the spec against the
   actual code and tests. Any `fail` or `partial` result counts as a failure.
3. **Script validation** — runs `validate-build` then (if clean) `validate-tests`.

All three must pass for `signoff` to emit `approved`. Any failure from any task emits
`changes_requested` and routes back to `fixing-pr`, with accumulated failure details.

The `handoff` state runs `final-sign-off` once a PR has been approved — either directly
out of `reviewing` on a clean first pass, or out of `signoff` after a `fixing-pr` cycle.
`final-sign-off` itself only reports that the hand-off point was reached; converting the PR
to ready for review, requesting the human reviewer's GitHub review, and assigning the work
item to them is performed afterward by this event's configured `after-hand-off` instructions.
