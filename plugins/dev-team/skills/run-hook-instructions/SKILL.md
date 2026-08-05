---
name: run-hook-instructions
user-invocable: false
description: >
  Use when the hook-runner agent needs to follow an already-resolved list of pipeline hook
  instructions. Takes a bare, ordered list of instruction strings directly — dev_team.py owns
  resolving which config keys apply and in what order — and follows each entry using whatever
  existing skill or tool fits, then reports the result.
argument-hint: --instructions <json-array> --context-file <path>
---

Use this skill when:
- You (`dev-team:hook-runner`) were spawned to run a pipeline's `"hooks"` action and need to
  follow its resolved `instructions` list

Do NOT use this skill when:
- Nothing spawned you for a `"hooks"` action — `dev_team.py` only emits one when this project's
  `instructions:` config actually has a non-empty list for the current before-/after-<event>
  phase; there is no "check if hooks apply" step for any other agent to perform

## Arguments

- `--instructions` — the already-resolved, already-ordered JSON array of plain-language
  instruction strings to follow, exactly as `dev_team.py` computed it. Disabled/empty config
  entries are already filtered out before this list is built, so every entry here is meant to be
  followed. Do not re-resolve, re-filter, or re-order it — just follow it in order.
- `--context-file` — absolute path to the workflow context file. Read-only here: some
  instructions need a value from its frontmatter (`pr_url` to promote a PR, `work_item_id` for a
  Jira call), and some need a body section's content (e.g. the `Implementation Summary` section,
  to summarize the work in a posted comment). Nothing is written back to it — a hook's outcome
  isn't pipeline-relevant context; report it directly in this skill's own return value instead
  (see "Report the result" below).

## What this skill owns

This skill owns only the per-instruction **dispatch** — matching each instruction's
plain-language text to the real operation that performs it, and attempting it. It does not look
up config, resolve which keys apply, or decide ordering; `dev_team.py` already did all of that
before ever spawning the agent that calls this skill.

## Steps

### 1 — Follow each instruction in order

Read `work_item_id`/`pr_url`/any other frontmatter field, or any body section's content, an
instruction turns out to need from `--context-file` (use the `use-context-file` skill's "Reading
the context file" step).

Walk `--instructions`' entries in the order given. For each instruction:

- Read its plain-language text and decide which existing operation actually performs it — see
  "Dispatching an instruction" below. Attempt that operation.
  - If it succeeds, move on to the next entry.
  - If it fails (the underlying Jira/GitHub/git call itself errors), or if no operation
    plausibly fits the instruction's text at all, record that entry as a failure (a short
    description of what was attempted and why it didn't work) and **still continue** to the next
    entry — one bad entry never stops the rest of the list from being attempted.

Never silently no-op an instruction just because it doesn't look like anything in the "Dispatching
an instruction" table — a genuinely unrecognized instruction must still be attempted using
whatever tool/skill plausibly fits its literal text, and only counted as a failure if nothing
actually executed it. Reporting a false success for an instruction nothing actually performed
defeats the entire mechanism.

### 2 — Report the result

This is the only output — never write anything to the context file, and never return
intermediate commentary.

If every entry succeeded (including the trivial case of an empty list), return exactly:

```
successful
```

If at least one entry failed, return a plain, one-line failure description summarizing every
failed entry and why. `workflow-orchestrate` treats this exactly like any other failed dispatch
item's result — logging it and running the troubleshooter — so it does not need any particular
prefix or format beyond being clearly non-`successful`.

## Dispatching an instruction

This table lists the shipped-default instructions and the operation that fits each, plus the
general pattern for anything else:

| Instruction (typical wording) | Operation |
|---|---|
| "Assign Jira work item to self" | `work-with-Jira-tasks`'s `atlassianUserInfo` operation to get the current user, then `editJiraIssue` to set the assignee |
| `Transition Jira work item to "<status>"` | `work-with-Jira-tasks`'s `getTransitionsForJiraIssue` then `transitionJiraIssue` |
| "Push git changes to remote" | Plain `git push` for the current working branch |
| "If there are uncommitted changes, commit and push the branch" | If `git status --porcelain` is non-empty, the `commit-changes` skill, then `git push`; a clean tree is a no-op success, not a failure |
| "Promote GitHub PR to ready for review" | `work-with-pr`'s convert-to-ready operation (`update_pull_request` with `draft=false`) against `pr_url` from the context file |
| `Request a GitHub review from <name>` | `work-with-pr`'s request-review operation (`update_pull_request` with `reviewers=[...]`) |
| `Assign work item to <email>` | `work-with-Jira-tasks`'s `lookupJiraAccountId` (if a GitHub-side assignment is meant, resolve the linked username) then `editJiraIssue` to set the assignee |
| Commit-shaped free text (e.g. "Commit any uncommitted changes") | `commit-changes`, if the working tree actually has uncommitted changes; a clean tree is a no-op success |
| Anything else | Read the instruction literally and pick whichever tool call or skill in this pipeline (Jira, GitHub, git, `work-with-Jira-tasks`, `work-with-GitHub-issues`, `work-with-pr`, `commit-changes`, `create-pr-from-context`) most plausibly performs it, scoped to whatever tools `dev-team:hook-runner` has (see its own agent definition). If genuinely nothing fits, that is a failure for this entry, not a silent skip |

`create-pr-from-context` is never dispatched from here for PR *creation* itself — per the spec,
PR creation stays `creating_pr`'s own fixed, always-fires pipeline job, not something a hook
instruction triggers or skips. `before-create-pr`/`after-create-pr` instructions only layer
*extra* work around it (e.g. `ensure-pushed`).

## Ordering guarantee

`--instructions` arrives already in its final order — `dev_team.py` resolves and merges the
trigger-specific and unconditional lists (see `get-project-configuration/SKILL.md`'s
`instructions` section for the resolution rules) before ever spawning the agent that calls this
skill. This skill's only obligation is to preserve that order while walking entries in step 1,
not to re-derive it.
