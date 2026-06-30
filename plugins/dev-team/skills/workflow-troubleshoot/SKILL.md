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

## Diagnosis steps

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
