---
name: run-event-hooks
user-invocable: false
description: >
  Use when a pipeline step needs to run the project's configured before/after instructions
  for one pipeline event. Reads the `instructions:` config section itself, resolves which
  key(s) apply for the given event/phase/outcome, and follows each non-empty entry in order
  using whatever existing skill or tool fits.
argument-hint: --event <name> --phase <before|after> [--outcome <success|failure>] --context-file <path>
---

Use this skill when:
- You (`workflow-worker` or `workflow-script`) are about to invoke a pipeline skill and need to
  run that event's `before-<event>` instructions first
- You just finished invoking a pipeline skill and need to run that event's after-instructions
- Anything else that needs to follow a project's configured `instructions:` for one event/phase

Do NOT use this skill when:
- You already know there is no `EVENT_NAME` for the current step (e.g. `spec-finding`,
  `signoff`) — there is nothing to look up

## Arguments

- `--event` — the event name (e.g. `implement`, `signoff`) — matches the `EVENT_NAME` a
  `dev_team.py` `Step` puts on its descriptor's `event` field, without the `before-`/`after-`
  prefix. Note `signoff` here names `HandoffStep`'s event (fired only once `signoff` the pipeline
  state has approved), not the `signoff` state's own three parallel children, which still have no
  `EVENT_NAME` at all — see "Do NOT use this skill when" above.
- `--phase` — `before` or `after`
- `--outcome` — `success` or `failure`; required when `--phase after`, ignored (and normally
  omitted) when `--phase before`, since nothing has run yet to have an outcome at that point
- `--context-file` — absolute path to the workflow context file, the same one already given to
  the calling skill

## What this skill owns

This skill owns the **entire** lookup-and-follow sequence for one event/phase call. Callers
(`workflow-worker`, `workflow-script`) do no lookup of their own — no reading
`get-project-configuration`, no key resolution, no map iteration. They call this skill once per
phase and use only the `completed`/`failed` result it returns.

## Steps

### 1 — Get the project configuration's `instructions:` map

Use the `use-context-file` skill's "Resolving the context file path" and "Reading the context
file" steps with `<context-file>` to read the frontmatter (you'll need `work_item_id`, `pr_url`,
and any other field an instruction turns out to need) and the
`<!-- section:Project Configuration -->` body section.

If that section exists, parse it as JSON and read its `instructions` key directly — do not call
`get-project-configuration` again. If the section is absent (context file predates it, or was
never populated), invoke the `get-project-configuration` skill directly and read `instructions`
from its output instead.

If `instructions` is absent or `null` entirely, every lookup in step 2 is a no-op — skip straight
to step 4 and return `completed` (nothing to do is not a failure).

### 2 — Resolve which key(s) apply

Depending on `<phase>`:

- **`phase=before`:** resolve exactly one key, `before-<event>`.
- **`phase=after`:** resolve two keys, in this fixed order:
  1. `after-<event>-success` if `<outcome>` is `success`, or `after-<event>-failure` if
     `<outcome>` is `failure` — whichever matches the actual outcome, never both.
  2. `after-<event>` — unconditionally, regardless of `<outcome>`.

For each resolved key: if it is absent from `instructions`, or its value is `null`/an empty map
(`{}`), that lookup contributes nothing — move on to the next resolved key (or to step 4 if there
are none left). A typo'd or unrecognized event name is simply never found this way; nothing
validates it against a fixed vocabulary, so treat "not found" as an ordinary no-op, not an error.

### 3 — Follow each map in order

For each resolved key that did produce a non-empty map (in the order step 2 produced them: the
success/failure key before the unconditional `after-<event>` key on the `after` phase), walk its
entries in **map order** — the order `get-project-configuration` returned them in, which is
guaranteed stable end-to-end (see "Ordering guarantee" below).

For each `label: instruction` entry:

- **Skip it** if `instruction` is `""` or `null`/absent — this is how a more specific config tier
  disables one inherited entry without touching its siblings. A skipped entry never counts toward
  failure.
- **Otherwise, follow it.** Read the instruction's plain-language text and decide which existing
  operation actually performs it — see "Dispatching an instruction" below. Attempt that operation.
  - If it succeeds, move on to the next entry.
  - If it fails (the underlying Jira/GitHub/git call itself errors), or if no operation
    plausibly fits the instruction's text at all, record that entry as a failure (a short
    description of what was attempted and why it didn't work) and **still continue** to the next
    entry in the same map — one bad entry never stops the rest of the map from being attempted.

Never silently no-op an instruction just because it doesn't look like anything in the "Dispatching
an instruction" table — a genuinely unrecognized instruction must still be attempted using
whatever tool/skill plausibly fits its literal text, and only counted as a failure if nothing
actually executed it. Reporting a false `completed` for an instruction nothing actually performed
defeats the entire mechanism.

### 4 — Report the result

If every followed entry across every resolved map succeeded (including the trivial case of zero
non-empty maps or zero non-skipped entries), return exactly:

```
completed
```

If at least one entry failed, return:

```
failed: <one-line summary of every failed entry and why>
```

The caller folds a `failed` result into its own overall outcome — the same as if the wrapped
skill/command itself had failed.

## Dispatching an instruction

Labels (`self-assign`, `push`, `promote`, ...) are never interpreted by this skill — only the
instruction text matters. This table lists the shipped-default instructions and the operation
that fits each, plus the general pattern for anything else:

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
| Anything else | Read the instruction literally and pick whichever tool call or skill in this pipeline (Jira, GitHub, git, `work-with-Jira-tasks`, `work-with-GitHub-issues`, `work-with-pr`, `commit-changes`, `create-pr-from-context`) most plausibly performs it, scoped to whatever tools the current agent session actually has (see "Tool scope" below). If genuinely nothing fits, that is a failure for this entry, not a silent skip |

`create-pr-from-context` is never dispatched from here for PR *creation* itself — per the spec,
PR creation stays `creating-pr`'s own fixed, always-fires pipeline job, not something a hook
instruction triggers or skips. `before-create-pr`/`after-create-pr` instructions only layer
*extra* work around it (e.g. `ensure-pushed`).

## Tool scope

This skill runs in-session — invoked directly by whichever agent is already running
`workflow-worker`/`workflow-script` for the current pipeline step, not spawned as a separate
`Agent`. It can only use tools already granted to that session. In practice this means Jira/
GitHub-scoped instructions (`self-assign`, `transition`, `promote`, `request-review`,
`assign-work-item`) only resolve successfully on `dev-team:developer`-dispatched events (which
have both Jira and GitHub MCP access) — this is exactly why the shipped defaults place all such
instructions on `before-implement`/`after-create-pr`/`after-signoff-success` rather than
`before-review` (`dev-team:reviewer` has GitHub-PR tools only, no Jira) or any
`dev-team:researcher`/`dev-team:debugger`-dispatched event (neither Jira nor GitHub PR tools). An
instruction that needs a tool the current session doesn't have is simply another way for step 3's
"no operation plausibly fits" failure case to happen — attempt it, and if the required tool truly
isn't available, record the failure rather than silently skipping it.

## Ordering guarantee

`get-project-configuration`'s underlying `merge_config.py` parses each YAML tier into a Python
dict and merges tiers with `result = dict(base)` then overlays `override`'s keys on top (see
`deep_merge()`). Python dict insertion order is a language guarantee, not an implementation
detail, and `json.dumps`/`json.loads` (the format `merge_config.py` emits and this skill reads)
preserve it too — so the order survives parse → merge → JSON output → this skill's own map
iteration in step 3, unchanged. One subtlety: overriding an *existing* label (e.g. a
`config.local.yaml` setting `promote: ""`) keeps that label's position from the lower tier it
first appeared in; only a genuinely new label a higher tier introduces is appended at the end.
No new merge logic exists anywhere for this — it is a direct consequence of `merge_config.py`'s
existing, unmodified recursive dict-merge, the same mechanism `documentation`/`work-tracking`
already rely on.

## Verification: scripted fixture harness

`run-event-hooks` is classified `Testable` (skipping empty/null entries, continuing past a failed
instruction, and dispatching per-instruction is real conditional logic), but it is agent-skill
prose making judgment calls about which real operation fits a freeform instruction string, not a
pure function — it can't get a plain `pytest` unit test the way this plugin's Python scripts do.
Per `component-taxonomy`, it is verified by whatever mechanism actually fits: a scripted fixture
harness, following the same model `plugins/dev-team/fixtures/resolve-rebase-conflict/` uses —
script the fixture setup and the final-state assertion, not the reasoning in between.

See `plugins/dev-team/fixtures/run-event-hooks/RUN.md` for the fixture contents and the
materialize → run → grade dry-run procedure.
