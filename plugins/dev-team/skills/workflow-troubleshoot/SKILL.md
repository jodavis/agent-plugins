---
name: workflow-troubleshoot
user-invocable: false
description: >
  Troubleshooting skill for the dev-team pipeline. Investigates and attempts to fix problems in the pipeline.
argument-hint: --context-file <context_file> --problem "<problem_description>"
---

## Arguments

- `--context-file` — absolute path to the workflow context file
- `--problem` — the trigger name or failure description passed by the orchestrator

## Context file structure

The context file is a Markdown file with YAML frontmatter followed by `<!-- section:<name> -->` blocks
that hold agent output. Frontmatter fields relevant to troubleshooting:

| Field | Description |
|---|---|
| `state` | Current pipeline state (e.g. `implementing`, `reviewing`). Edit this to resume at a different step. |
| `troubleshooter_input` | The user's answer if you previously returned `needs_user_input`. Empty on first call. |
| `pending_agent` | The last agent the pipeline attempted to spawn before failing. |
| `consecutive_failures` | Number of consecutive agent failures. Resets to 0 on success. |
| `signoff_cycle_count` | Number of completed sign-off rounds. |
| `review_cycle_count` | Number of completed review/fix rounds. |

## Known triggers

| Trigger | Meaning | What to look for |
|---|---|---|
| `consecutive_failures` | An agent has failed 3 times in a row | Check `pending_agent` and the section it should have written; look for missing output or error messages |
| `signoff_deadlock` | Sign-off has cycled twice without resolution | Read the `signoff_review` and `signoff_research` sections; determine what is blocking agreement |
| `review_loop` | Review/fix has iterated 3 times without approval | Read `review_notes` and `fix_summary` sections; identify what the reviewer keeps flagging |
| `unknown_state` | Pipeline entered a state with no handler | Check the `state` field; it may be a typo or a state that was removed — set it to a valid state |

## Before diagnosing

This dev-team plugin repo — not the target project a pipeline run happens to be operating on —
is what the rest of this section, and the "Making the fix" section below, both read from and
write to. Resolve it, then search for a previously-filed issue before running any fresh
diagnosis.

1. **Resolve the plugin repo.** `<skill-dir>` is this skill's own base directory — the actual
   plugin checkout Claude Code loaded `workflow-troubleshoot` from (the same convention
   `workflow-orchestrate/SKILL.md` documents). Resolve two things from it:
   - Filesystem repo root: `git -C <skill-dir> rev-parse --show-toplevel`.
   - GitHub `owner/repo`: `git -C <skill-dir> remote get-url origin`, then extract the slug with
     the same three-step regex `get_context_path.py`'s `get_repo_slug()` uses internally — do
     not call that function directly, since it reads the CWD's own git remote rather than an
     explicit path:
     ```python
     slug = re.sub(r"^https?://[^/]+/", "", url)
     slug = re.sub(r"^[^@]+@[^:]+:", "", slug)
     slug = re.sub(r"\.git$", "", slug)
     ```
2. **Search for a match.** Using `work-with-GitHub-issues`, list open issues under the
   `troubleshooter` label, plus issues under that label closed in the last 90 days (two separate
   list/search calls). Read each candidate's title and body. Using judgment — the symptoms
   actually observed this occurrence, not just the `--problem` trigger name — decide whether any
   candidate already describes this problem. A shared trigger name alone (e.g.
   `consecutive_failures` also covers many unrelated root causes) is not a symptom match by
   itself; read into the failing step's own context-file section (same sources "Diagnosis steps"
   below reads) before deciding.
3. **No match found:** proceed to "Diagnosis steps" below exactly as if this were a novel
   problem.
4. **Match found, with a documented workaround** (a labeled "Workaround" section in that issue's
   body): apply it.
   - **It works** — add a comment to that issue noting this occurrence (confirms the workaround
     still applies), then skip "Diagnosis steps"/"Fix strategies" entirely and go straight to
     "Making the fix" below, scoped to this matched issue.
   - **It doesn't work** — add a comment to that issue describing the conditions under which it
     failed this occurrence (evidence this isn't actually the same root cause despite the
     symptom match), then fall through to "Diagnosis steps" below as if no match had been found.
     The new issue filed there (per "No match" in "Fix strategies") must cross-link back to this
     one — reference its number in the new issue's body, and add a follow-up comment on the
     original pointing at the new issue.
5. **Match found, with a linked PR** (referenced in the issue body or comments): check whether it
   has merged into the plugin repo's default branch. Neither case here files a new issue — the
   fresh workaround found in "Diagnosis steps"/"Fix strategies" below gets added to *this*
   matched issue (a comment describing it, reopening the issue first if a merge auto-closed it),
   never a new one, since the search step already found the right issue for this occurrence.
   - **Merged, but the problem still recurred** — add a comment noting the discrepancy (a
     regression, or a distinct root cause that happens to share symptoms), then fall through to
     "Diagnosis steps" below.
   - **Not merged** — keep that PR's branch as the starting point for this occurrence's own fix in
     "Making the fix" below, instead of writing one from scratch. Still run "Diagnosis steps"
     first if step 4's workaround check doesn't apply or didn't work, to find the workaround to
     record on the matched issue.

## Diagnosis steps

Reached directly from "Before diagnosing" step 3 (no match), or by falling through from step 4
(workaround failed) or step 5 (merged but recurring, or not merged and no workaround to try
first).

1. Read the context file. Check `troubleshooter_input` — if non-empty, the user has answered a question
   from a prior call; use that answer to decide what to do next.
2. Identify the trigger from `--problem` and note any relevant counter fields.
3. Read the `<!-- section:... -->` blocks for the failing step to see what the agent produced (or failed to produce).
4. If needed, read plugin source files in the dev-team plugin directory to understand what a step expects.

## Fix strategies

- **Wrong or corrupted state** — edit the `state` frontmatter field to a valid pipeline state, then return `continue`.
- **Counter deadlock** — diagnose the root cause; if fixable, edit the relevant context section to break the cycle
  and reset the counter to `0`; return `continue`.
- **Needs a user decision** — return `needs_user_input` with a single focused question; the orchestrator will
  relay it to the user, write the answer to `troubleshooter_input`, and re-invoke this skill.
- **Cannot fix** — return `terminate` with a clear problem description and recommendation.
- **No identifiable cause** — a genuinely one-off, non-reproducible blip with nothing concrete to
  describe: apply no workaround, write nothing (no issue, no comment — see "Log on every
  non-trivial invocation" below), and return `continue` or `terminate` per whichever of the above
  actually applies to unblocking this run.
- **No prior match at all ("Before diagnosing" step 3), and a real problem was diagnosed:** once
  a workaround from the strategies above has been applied, file a new issue tagged
  `troubleshooter`. Body has two distinct, clearly-labeled sections: a **Symptoms** section (what
  was actually observed this occurrence — the real evidence, not just the `--problem` trigger
  name) and a **Workaround** section (exactly what fixed it this time), so a future
  troubleshooter's search step can both match on symptoms and immediately reuse what worked.
- **A failed-workaround match ("Before diagnosing" step 4), and a real problem was diagnosed:**
  file a new issue the same way as "No prior match" above, but cross-link it to the original —
  reference the original issue's number in the new issue's body, and add a follow-up comment on
  the original pointing at the new issue.
- **A linked-PR match with no reusable workaround ("Before diagnosing" step 5), and a real
  problem was diagnosed:** do not file a new issue — the search step already found the right
  issue for this occurrence. Add the freshly-found workaround to *that* matched issue as a
  comment (with the same Symptoms/Workaround structure as a new issue's body would have),
  reopening it first if a merged-but-recurring PR had auto-closed it.

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
   - **`can-push-fix` also set:**
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

## Output

Return a JSON object — exactly one of these three shapes:

```json
{ "action": "continue" }
```
You applied a fix. The orchestrator resumes from whatever `state` is now set in the context file.

```json
{ "action": "needs_user_input", "question": "<one specific question for the user>" }
```
You need the user to make a decision. The orchestrator asks the question, writes the answer to
`troubleshooter_input`, and re-invokes this skill.

```json
{ "action": "terminate", "reason": "<clear description of the problem and your recommendation>" }
```
You could not fix the issue. The orchestrator reports the reason to the user and stops.

Add an `"issue_url"` field to whichever of the three shapes above applies whenever an issue was
filed or updated this call (a fresh issue, a reused-workaround occurrence comment, a
failed-workaround comment plus new issue, or a fix description/PR link added to an existing
issue):

```json
{ "action": "continue", "issue_url": "https://github.com/jodavis/agent-plugins/issues/42" }
```

Omit the field entirely on a call that wrote nothing to GitHub — the "no identifiable cause"
case in "Fix strategies" above.
