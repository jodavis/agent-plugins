Summary: Run procedure for the resolve-rebase-conflict skill's dry-run harness — how to
materialize each conflict scenario and grade the skill's output against expected git state.

# resolve-rebase-conflict: skill dry-run harness

This directory is the fixture set and run procedure for verifying `resolve-rebase-conflict`
(`plugins/dev-team/skills/resolve-rebase-conflict/SKILL.md`), a Testable agent-skill-prose
component per `component-taxonomy` — it makes judgment calls resolving conflicting hunks, so it
doesn't fit AAA unit tests. Per the taxonomy, it's verified by "whatever mechanism actually
fits": here, a scripted fixture-scenario harness that builds a real git repo with a real,
deliberate rebase conflict, runs the skill against it, and asserts the resulting git state.

## Fixture contents

| Path | Purpose |
|---|---|
| `build_fixture.py` | Builds one of three named scenarios into a fresh throwaway git working clone, left mid-rebase with a real conflict already in progress — the exact entry state `resolve-rebase-conflict` expects |
| `test_build_fixture.py` | Unit tests confirming each scenario actually produces the conflict (and only the conflict) it claims to, so a dry run always starts from a trustworthy, reproducible state |

There is no checked-in git history here (unlike `fixtures/playbook-harvesting`'s
`commits.json` replay) — each scenario is built fresh, in-process, by calling
`rebase_mechanic.rebase_onto()` itself against two real, diverging branches, following
`workflow-orchestrate/scripts/test_rebase_mechanic.py`'s bare-"origin"-plus-working-clone
construction pattern. That means every dry run exercises the real Rebase mechanic's own
conflict detection, not a hand-crafted stand-in.

## Scenarios

| Name | Files conflicted | Task-brief context given to the skill | Expected outcome |
|---|---|---|---|
| `single-file` | `CHANGELOG.md` (one hunk) | States this task's own changelog entry verbatim | `"resolved"` |
| `multi-file` | `CHANGELOG.md` and `config/settings.json` (one hunk each, same commit) | States the changelog entry, plus the final target value for `max_retries` (5) | `"resolved"` |
| `unresolvable` | `config/retry_policy.json` (one hunk) | States only the *intent* ("adjust the retry backoff multiplier for better resilience") — never a target value | `"unresolved"` |

`multi-file`'s two files conflict from a single replayed commit (both branches touch
`CHANGELOG.md` and `config/settings.json` together) — this is deliberate: git resolves
non-overlapping single-line edits across separate commits automatically, so the scenario needs
both edits landing in the same commit to guarantee both files are conflicted at once.

## Invocation model: on-demand, not CI

Like `fixtures/playbook-harvesting`, this harness is **run by the implementing or validating
agent whenever `resolve-rebase-conflict` is edited** — it is not a CI gate. The judgment-shaped
grading (did the skill correctly decline to guess on `unresolvable`?) isn't deterministic
enough for a reliable automated gate; `test_build_fixture.py` is the part of this harness that
*is* CI-appropriate, and should run in the normal pytest suite alongside everything else in
this repo.

## Step 1 — Materialize a scenario

```bash
python3 plugins/dev-team/fixtures/resolve-rebase-conflict/build_fixture.py \
  single-file /tmp/dry-run/resolve-rebase-conflict/single-file
```

Replace `single-file` with `multi-file` or `unresolvable` for the other two scenarios. Each
invocation is idempotent given a fresh destination directory — always materialize into a
location outside version control (e.g. under `/tmp/dry-run/`), and use a fresh destination
directory per run rather than reusing one from a previous dry run.

The command prints the worktree path, the working/base branch names, the expected outcome, and
the task-brief text to hand the skill as its context argument.

## Step 2 — Run the target skill in a clean session

Start a fresh session with no memory of this harness's authoring context — a validating
subagent blind to why the fixtures look the way they do, so the run exercises the skill's
prose exactly as a first-time reader would. Give it only:

- `resolve-rebase-conflict`'s own `SKILL.md` instructions,
- the materialized worktree path from Step 1, checked out as the session's working directory
  (a rebase is already in progress there — do not run any git command that would abort or
  restart it before invoking the skill),
- the task-brief text Step 1 printed, as the skill's context argument.

Run the skill to completion and record whichever of `"resolved"` / `"unresolved"` it reports.

## Step 3 — Grade the result

### Mechanical checks

Run these against the same worktree path from Step 1, after Step 2 completes:

```bash
# No rebase left in progress.
test -d <worktree>/.git/rebase-merge -o -d <worktree>/.git/rebase-apply
# (expect this to fail — exit non-zero — only for the two "resolved" scenarios)

# Working tree is clean.
git -C <worktree> status --porcelain
# (expect empty output for the two "resolved" scenarios)
```

- **`single-file` / `multi-file`:** the skill must report `"resolved"`, the rebase-in-progress
  check above must fail (no rebase directory), and `git status --porcelain` must be empty.
- **`unresolvable`:** the skill must report `"unresolved"`, the rebase-in-progress check must
  succeed (a rebase directory still exists), and `config/retry_policy.json` must still contain
  its original `<<<<<<<` conflict markers, untouched.

### Judgment-shaped checks

Read the skill's resolution against each scenario's expected final content:

- **`single-file`:** `CHANGELOG.md` contains both the upstream entry ("Add PR event detector")
  and this task's own entry ("Add rebase conflict resolution skill") — neither was dropped.
- **`multi-file`:** same `CHANGELOG.md` check as above, plus `config/settings.json` contains
  `"max_retries": 5` — the brief-stated final target, not the superseded upstream interim value
  (4) and not the working branch's pre-rebase value (5, same by coincidence of this scenario's
  design, so also confirm the skill didn't just default to "ours" — check its stated reasoning
  cites the brief's explicit target rather than a blind conflict-side pick).
- **`unresolvable`:** the skill's report explains *why* it stopped (the brief states intent but
  no target value) rather than picking one of the two candidate values (2.0 or 2.5) or
  inventing a third. A skill that guesses a value and reports `"resolved"` anyway fails this
  scenario even if that guessed value happens to look reasonable — the check is "did it avoid
  guessing," not "did it guess correctly."

## Re-running after a skill edit

1. Re-materialize each scenario (Step 1) into a fresh destination — never reuse a previous
   dry run's worktree.
2. Re-run Steps 2–3 against the edited skill for all three scenarios.
3. If a checklist item now fails, the edit introduced a regression — fix it before merging, the
   same way a failing unit test blocks a merge elsewhere in this repo.

No fixture content changes as part of a routine re-run. Fixtures only change if
`resolve-rebase-conflict`'s own contract changes (e.g. its argument shape), in which case
update `build_fixture.py` and `test_build_fixture.py` together and note it in that change's PR.
