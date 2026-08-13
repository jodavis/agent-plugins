Summary: Run procedure for the workflow-troubleshoot skill's dry-run harness — how to
materialize each of the seven scenarios against the disposable fixture repo and grade the
skill's output against expected GitHub issue/PR/branch state.

# workflow-troubleshoot: skill dry-run harness

This directory is the fixture set and run procedure for verifying `workflow-troubleshoot`
(`plugins/dev-team/skills/workflow-troubleshoot/SKILL.md`), a Testable agent-skill-prose
component per `component-taxonomy` — it makes judgment calls (symptom-based issue dedup,
whether a root cause is "concretely fixable," whether a workaround actually resolved the
problem) that don't fit AAA unit tests. Per the taxonomy, it's verified by "whatever mechanism
actually fits": here, a scripted fixture-scenario harness that seeds real GitHub issue/PR/branch
state on a disposable repo and a local clone standing in for `<skill-dir>`'s resolved checkout,
runs the skill against it, and grades the resulting GitHub/git state plus the skill's own
reasoning — the same two-tier (mechanical + judgment) grading `run-hook-instructions`'s harness
uses.

## The disposable fixture repo

All seven scenarios run against `jodavis-claude/dev-team-troubleshooter-fixtures` — never
`jodavis/agent-plugins`. It was created once, ahead of authoring this harness, with its own
`troubleshooter` label pre-created (mirroring the label on `jodavis/agent-plugins`).

**Deviation from the spec's example name:** the spec's exit criteria used
`jodavis/dev-team-troubleshooter-fixtures` as an example. The account this harness runs under
(`jodavis-claude`) has no permission to create a repo inside the `jodavis` *user* namespace —
GitHub only allows creating a repo "for" another account when that account is an org, and
`jodavis` is a personal user account, not an org. The repo was created under `jodavis-claude`
instead; every command below and every command `build_fixture.py` runs targets that repo via
its `FIXTURE_REPO` constant.

Every issue, branch, and PR in this repo is throwaway scenario state created by
`build_fixture.py` and may be reset or deleted at any time. Nothing in it is real project work.

## Fixture contents

| Path | Purpose |
|---|---|
| `build_fixture.py` | Builds one of seven named scenarios: a local clone of the disposable repo standing in for `<skill-dir>`'s resolved checkout, a throwaway context file (carrying a `Project Configuration` section with the scenario's `troubleshooter.can-fix`/`can-push-fix` flags), and — for the match/fix scenarios — real seeded issues, branches, and PRs on the disposable repo |
| `test_build_fixture.py` | Unit tests confirming each scenario builder issues the right `git`/`gh` commands and returns the fixture state it claims to, with `subprocess.run` mocked so the suite runs hermetically in this repo's normal pytest suite |

## Scenarios

| Name | Seeded GitHub state | Context file | Expected skill behavior |
|---|---|---|---|
| `no-match` | One `troubleshooter`-labeled issue describing an unrelated problem | `consecutive_failures` trigger, `pending_agent: implement` | Diagnose fresh; file a new, distinct issue |
| `reusable-workaround-match` | One issue with Symptoms/Workaround sections matching this occurrence exactly | Same symptoms as the seeded issue | Apply the documented workaround; add an occurrence comment; file no new issue |
| `failed-workaround-match` | One issue whose Workaround addresses a different root cause than this occurrence's real problem | Same trigger name, different real symptom (stuck review cycle, not stuck implement) | Comment on the original describing the failure; diagnose fresh; file a new issue cross-linked to the original |
| `linked-pr-match` | One issue linking an unmerged PR against the disposable repo | `signoff_deadlock` trigger matching the issue's symptoms | Recognize the PR as unmerged; treat its branch as the fix starting point; update the matched issue (not a new one) with the freshly-found workaround |
| `no-identifiable-cause` | Nothing seeded | A vague, one-off, non-reproducible blip | Write nothing — no new issue, no comment |
| `can-fix-only-local-merge` | Nothing seeded; a concretely-fixable bug committed locally in the checkout (`tools/greet.py`) | `validate_failed`, `troubleshooter.can-fix: true`, `can-push-fix: false` | Fix the bug, commit on `troubleshooter/<slug>`, merge it locally into the checked-out branch — no push, no PR; file an issue describing the change |
| `can-fix-can-push-fix-stacked-pr` | Nothing seeded; a different concretely-fixable bug committed locally (`tools/farewell.py`) | `validate_failed`, both flags `true` | Fix the bug, add it to a `gh stack` on `troubleshooter/<slug>`, submit the stack (push + open draft PR), overwrite the PR's title/body to match `create-pr`'s structured body convention including `Closes #<issue-number>`; file an issue with the PR link |

## Invocation model: on-demand, not CI

Like `fixtures/run-hook-instructions`, this harness is **run by the implementing or validating
agent whenever `workflow-troubleshoot` is edited** — it is not a CI gate. `test_build_fixture.py`
is the part of this harness that *is* CI-appropriate (hermetic, no network) and runs in the
normal pytest suite; materializing a scenario and actually running `workflow-troubleshoot`
against it requires `gh auth` and network access to the disposable repo, and is not run
automatically.

## Step 1 — Materialize a scenario

```bash
python3 plugins/dev-team/fixtures/workflow-troubleshoot/build_fixture.py \
  no-match /tmp/dry-run/workflow-troubleshoot/no-match
```

Replace `no-match` with any other scenario name from the table above. Requires `gh auth login`
with write access to `jodavis-claude/dev-team-troubleshooter-fixtures` (issues, PRs, and, for
the `can-fix-can-push-fix-stacked-pr` scenario, the `github/gh-stack` extension). Each
invocation mutates real state on the disposable repo (a new issue, and for `linked-pr-match` a
new branch/PR too) — always materialize into a fresh destination directory outside version
control, and expect the disposable repo's issue/PR history to accumulate across runs; it is
disposable by design.

The command prints the checkout path, the context file path, the `--problem` string, this
scenario's `can-fix`/`can-push-fix` flags, any seeded issue number/URL, the flags the harness
expects the skill to satisfy, and a one-line description of the scenario's intent.

## Step 2 — Run the target skill in a clean session

Start a fresh session with no memory of this harness's authoring context — a validating
subagent blind to why the fixtures look the way they do, so the run exercises the skill's prose
exactly as a first-time reader would. Give it:

- `workflow-troubleshoot`'s own `SKILL.md` instructions,
- an explicit instruction that the materialized `checkout` path from Step 1 stands in for
  `<skill-dir>`'s resolved checkout throughout — wherever the skill's prose says `<skill-dir>`,
  substitute that checkout path,
- the `--context-file <context_file path from Step 1> --problem "<problem string from Step 1>"`
  arguments.

Run the skill to completion and record its returned JSON and its own narrative report of what
it found and did.

## Step 3 — Grade the result

### Mechanical checks

Run these against the disposable repo and the materialized checkout, after Step 2 completes:

```bash
# Issue state on the disposable repo.
gh issue list --repo jodavis-claude/dev-team-troubleshooter-fixtures --label troubleshooter --state all --json number,title,state,body,comments

# PR state (linked-pr-match and can-fix-can-push-fix-stacked-pr only).
gh pr list --repo jodavis-claude/dev-team-troubleshooter-fixtures --state all --json number,title,body,isDraft,headRefName

# Local git state in the checkout (can-fix-only-local-merge and can-fix-can-push-fix-stacked-pr).
git -C <checkout> log --oneline -5
git -C <checkout> status --porcelain
```

- **`no-match`:** a new issue exists distinct from the seeded one, tagged `troubleshooter`, with
  separate Symptoms/Workaround sections. Skill's returned `issue_url` points at the new issue.
- **`reusable-workaround-match`:** no new issue exists; the seeded issue has a new comment; the
  skill's returned `issue_url` points at the seeded issue.
- **`failed-workaround-match`:** the seeded issue has a new comment describing the failure; a
  new, separate issue exists that references the seeded issue's number.
- **`linked-pr-match`:** the seeded PR is still open (unmerged); the seeded issue has a new
  comment with the freshly-found workaround; no new issue was filed.
- **`no-identifiable-cause`:** issue list on the disposable repo is unchanged from before Step 2.
- **`can-fix-only-local-merge`:** `tools/greet.py` no longer contains the bug; `git log` shows a
  local commit/merge on top of the fixture's seed commit; `git status --porcelain` shows nothing
  pushed anywhere (no remote branch created); a new issue describes the change.
- **`can-fix-can-push-fix-stacked-pr`:** `gh pr list` shows a new draft PR whose head branch is
  `troubleshooter/<slug>`, whose title/body follow `create-pr`'s structured convention, and
  whose body contains `Closes #<issue-number>` referencing the new issue filed for this
  occurrence.

### Judgment-shaped checks

Read the skill's own report against each scenario's expectation:

- **`no-match`:** the report explains *why* the seeded unrelated issue didn't match (different
  symptoms), not just that it searched.
- **`reusable-workaround-match` / `linked-pr-match`:** the report explains the match was found
  by comparing symptoms, not just the shared trigger name.
- **`failed-workaround-match`:** the report explains why the matched issue's workaround didn't
  fit this occurrence's real problem, despite the shared trigger name.
- **`no-identifiable-cause`:** the report explains that nothing concrete was found to describe,
  rather than silently doing nothing without saying why. A report that writes an issue anyway
  fails this scenario.
- **`can-fix-only-local-merge` / `can-fix-can-push-fix-stacked-pr`:** the report describes the
  actual root cause fixed (not just "fixed it"), and correctly states whether it pushed or
  merged locally, matching the scenario's flags.

## Re-running after a skill edit

1. Re-materialize each scenario (Step 1) into a fresh destination — never reuse a previous dry
   run's checkout, and expect a new issue/branch/PR to be created on the disposable repo each
   time.
2. Re-run Steps 2–3 against the edited skill for all seven scenarios.
3. If a checklist item now fails, the edit introduced a regression — fix it before merging, the
   same way a failing unit test blocks a merge elsewhere in this repo.

No fixture content changes as part of a routine re-run. Fixtures only change if
`workflow-troubleshoot`'s own contract changes (e.g. its argument shape, or the `Project
Configuration` section's expected shape), in which case update `build_fixture.py` and
`test_build_fixture.py` together and note it in that change's PR.
