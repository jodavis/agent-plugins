Summary: The `instructions:` config mechanism and `run-event-hooks` execution model that let a
project attach plain-language before/after instructions to named points in the dev-team pipeline.

# Workflow Event Hooks

## Overview

Project policy that used to live in four action-named `git-repo.commit`/`.push`/`.create-pr`/
`.promote-pr` blocks — none of which `workflow-orchestrate`'s pipeline (`dev_team.py`) actually
read — has been replaced by a single `instructions:` config section: an ordered map, per named
pipeline event, of `label: instruction` pairs written in plain language (e.g.
`push: "Push git changes to remote"`). A new skill, `run-event-hooks`, is the mechanism that
actually executes these maps as part of the automated pipeline, resolving and following the right
instructions before and after each step. `workflow-worker` and `workflow-script` — the two
dispatch wrappers every pipeline step already routes through — call it around their existing
single skill/command invocation. This closes the gap where the old `enabled`/`when` fields were
purely advisory: `push`, PR promotion, and reviewer/work-item assignment are now genuinely
config-driven inside the automated pipeline for the first time.

See `plugins/dev-team/skills/get-project-configuration/SKILL.md`'s `instructions` section for the
schema, and `plugins/dev-team/skills/run-event-hooks/SKILL.md` for the full lookup-and-follow
contract.

## Responsibilities & Boundaries

- **Owns:** the `instructions:` config schema; the `EVENT_NAME` on each single-action
  `dev_team.py` `Step`; the `event` field on emitted descriptors; `run-event-hooks`'s
  lookup-and-follow logic; `workflow-worker`'s and `workflow-script`'s before-/after-hook
  wrapping; the trimmed `final-sign-off` and `work-with-pr` skills; the
  `update-project-configuration` `instructions:` walkthrough.
- **Does not own:** `dev_team.py`'s state machine/transition table or either mermaid workflow
  file — both entirely unchanged, no pipeline state added or removed; per-component commit
  granularity inside `implement-task`/the TDD trio/`fix-draft`/`fix-pr` — unaffected, still one
  commit per component/issue regardless of any event; the Jira/GitHub operations an instruction
  ultimately calls (`work-with-Jira-tasks`, `work-with-GitHub-issues`, `work-with-pr`,
  `commit-changes`, `create-pr-from-context` — all reused as-is, none modified in shape).
- **Integrates with:** `get-project-configuration` (schema source), `merge_config.py` (unmodified
  — its existing recursive dict-merge is what makes per-label overrides work),
  `workflow-orchestrate`'s dispatch prompt (threads `--event` through), and every
  pipeline-spawned agent session (Jira/GitHub tool access bounds what an instruction on that
  event can actually do — see Key Design Decisions).
- **Pipeline-only:** hooks fire only inside the automated `workflow-orchestrate` pipeline. A
  standalone `/dev-team:implement` or manual skill invocation never consults `instructions:` —
  the same scope the old `git-repo` signals had.

## Key Design Decisions

- **Events are plain-language label→instruction maps, not a DSL or bare list**, so
  `merge_config.py`'s existing recursive dict-merge can override or disable one entry
  (`label: ""`/`null`) without a tier having to restate its siblings. See
  `get-project-configuration/SKILL.md`'s `instructions` section and `run-event-hooks/SKILL.md`'s
  "Ordering guarantee".
- **Only a `Step` that dispatches exactly one `spawn_agent`/`run_script` action gets an
  `EVENT_NAME`** — the shape a single before-hook/after-hook pair can wrap. The shipped table:
  `debug`, `research`, `implement`, `validate`, `create-pr`, `review`, `fix` (shared by
  `fixing`/`fixing-pr`), and `signoff` (`HandoffStep`'s event, despite the `handoff` pipeline
  state's own name — see `dev_team.py`'s `HandoffStep` docstring). `spec-finding` (inline) and
  the `signoff` pipeline state (`SignoffStep`, a `ParallelSteps` composite with three
  concurrently-dispatched children and no single agent session to wrap) have no `EVENT_NAME` at
  all.
- **`creating_pr` stays a fixed, always-fires state; only `push` moved into a hook.**
  `CreatePrStep` unconditionally dispatches `create-pr-from-context` exactly as before — PR
  creation itself is never optional, since without a PR the pipeline cannot proceed.
  `before-create-pr`/`after-create-pr` only layer extra instructions (the shipped `ensure-pushed`
  safety net, self-assign/status-transition) around that fixed job; they never gate it.
- **`ValidateStep`'s hardcoded push is now conditional on which validation path ran.** With a
  real validation script configured, `workflow-script` pushes via `after-validate-success`'s
  `push` instruction inside the same invocation that ran the script; `ValidateStep`'s own
  `handle_results()` skips its `_commit_and_push()` call in that case (detected via the literal
  marker substring `"(no validation script configured for this project)"` in
  `ctx.validate_result`). With no validation script configured, `ValidateStep` resolves entirely
  inline inside `dev_team.py` itself (no `run_script` dispatch, so no hook mechanism is
  reachable) and keeps the old hardcoded push.
- **`SignoffStep`'s own push (`"Push first so the reviewer can see the latest commits"`) is
  separate and stays hardcoded** — it isn't `after-validate-success`'s job (that event never
  fires on the `fixing_pr → signoff` path) and isn't `after-fix`'s job either (that already fired
  once, generically, before `signoff` starts); the `signoff` state's three parallel children need
  to see the actual latest commits, so this can't be something a project's config silently omits.
- **`fixing`/`fixing-pr` share one `fix` event, fired once per invocation** — no per-commit hook
  granularity was added; the existing per-issue `commit-changes` loops inside
  `fix-draft`/`fix-pr` are unrelated and unchanged.
- **Reviewer/work-item-assignment identity is literal instruction text, not an environment
  variable.** `REVIEW_ASSIGNEE_EMAIL` is gone; `final-sign-off` shrinks to a near-no-op status
  report (`HandoffStep` still dispatches it as `workflow-worker`'s required `<skill>`), and the
  actual promote/assign/request-review work happens afterward as `after-signoff-success`
  instructions, executed by `run-event-hooks` calling `work-with-pr`'s three bare mechanical
  operations (`convert-to-ready`, `request-review`, `assign-issue`).
- **Shipped defaults vs. project-specific identity are split across config tiers**, not baked
  into one file: `assets/default-config.yaml` ships only instructions confirmed generic for any
  project (e.g. `push`, `ensure-pushed`); this repo's own reviewer identity (`jodavis` /
  `jodasoft@outlook.com`) lives in the machine-tier `~/.dev-team/config.yaml`, merged in via
  `merge_config.py`'s existing tier order — not committed to the repo.
- **A Jira/Atlassian-routed instruction gets one authentication-recovery retry, owned by
  `work-with-Jira-tasks` itself, not duplicated in `run-event-hooks`.** If the underlying MCP
  call reports that authentication needs to be established or refreshed — observed with
  Cursor's Atlassian MCP connector — `work-with-Jira-tasks` performs the environment's recovery
  step (`mcp_auth`) and retries the same call exactly once before reporting failure to its
  caller. `run-event-hooks`'s dispatch loop (step 3) does not re-implement this: a
  `work-with-Jira-tasks` operation that still fails after its own retry surfaces as an ordinary
  failed entry under the existing record-failure-and-continue contract. Git/GitHub instructions
  never route through `work-with-Jira-tasks`, so they are unaffected. `work-with-Jira-tasks` also
  documents a fallback `GetMcpTools`/`CallMcpTool` discovery path and a third tool-name prefix
  (`mcp__plugin-atlassian-atlassian__*`) for environments where `ToolSearch` doesn't surface
  individually-named Jira tools.

## Key Classes / Interfaces

- **`run-event-hooks(event, phase, outcome, context_file) -> "completed" | "failed"`**
  (`plugins/dev-team/skills/run-event-hooks/SKILL.md`) — owns the entire lookup-and-follow
  sequence for one event/phase call: `before-<event>` for `phase=before`;
  `after-<event>-success`/`after-<event>-failure` (by `outcome`) then unconditionally
  `after-<event>` for `phase=after`. Skips empty/`null` entries; continues past a failed
  instruction but reports `"failed"` overall if any instruction failed. Verified by a scripted
  fixture harness (`plugins/dev-team/fixtures/run-event-hooks/`), not `pytest` unit tests, since
  dispatching an instruction is agent judgment, not a pure function.
- **`Step.EVENT_NAME`** (`dev_team.py`) — class attribute on each pipeline `Step`; `None` means
  no hookable event. Included as the `"event"` field on every emitted descriptor in
  `_do_get_actions_and_exit`.
- **`workflow-worker`/`workflow-script`'s `--event <name>` argument** — optional; when present,
  each wraps its existing single skill/command invocation with a `run-event-hooks` call before
  and after, computing `outcome` independently (`workflow-worker`: whether `<skill>` completed
  and wrote output; `workflow-script`: whether the validation result itself starts with
  `"Succeeded"`, not its own separate script-ran-without-error status). A `"failed"` hook result
  makes the wrapping step's own overall result a failure, even if the wrapped skill/command
  succeeded.
- **`work-with-pr`'s mechanical operations** (`convert-to-ready`, `request-review`,
  `assign-issue`) — each independently callable from a plain-language instruction; no fixed
  sequence, no environment variable lookup.

## Data Flow

1. `dev_team.py` computes the next step. A `Step` with an `EVENT_NAME` gets that name stamped
   onto its descriptor's `"event"` field by `_do_get_actions_and_exit`.
2. `workflow-orchestrate`'s dispatch prompt passes `--event <item.event>` through to
   `workflow-worker` (`spawn_agent` actions) or `workflow-script` (`run_script` actions), omitted
   when `item.event` is absent — the same rule already applied to empty `--skill-args`/
   `--command`.
3. Inside that agent session, the wrapper calls `run-event-hooks(event, "before", None,
   context_file)`, invokes `<skill>`/the command as before, writes its output, then calls
   `run-event-hooks(event, "after", outcome, context_file)`. Both hook calls read the merged
   `instructions:` map from the context file's own `Project Configuration` section (or
   `get-project-configuration` directly, if absent) and follow each non-empty instruction with
   whatever Jira/GitHub/git operation fits.
4. At `validating`, a real validation script's `after-validate-success` `push` instruction is
   what pushes now — `ValidateStep`'s own hardcoded push only fires when no script is configured.
   At `creating_pr`, `before-create-pr`/`after-create-pr` hooks wrap the still-unconditional
   `create-pr-from-context` dispatch. At `handoff`, `after-signoff-success` (fired under
   `HandoffStep`'s `EVENT_NAME = "signoff"`) drives PR promotion, review request, and work-item
   assignment — all via `work-with-pr`'s mechanical operations, none of it inside
   `final-sign-off` itself anymore.
