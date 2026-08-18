# Review Before Posting

> **Status:** Draft
> **Epic:** [ADR-398](https://jodasoft.atlassian.net/browse/ADR-398)
> **Design doc:** none — no existing design doc was found for ADR-398; this spec goes straight
> from the epic to implementation detail.

## Overview

Today, every message the pipeline posts under the user's own identity — Jira/GitHub work-item
comments, PR descriptions, PR review comments — goes out immediately and unattended. That's fine
in a personal repo, where the user reads Claude's PR activity as communication *to* them. In a
team repo, the same activity is communication *to teammates*, posted under the user's own
account, and the user wants to see and approve it before it becomes visible — without losing the
pipeline's ability to run unattended for long stretches.

This feature adds a non-blocking review gate for exactly one class of pipeline output: short
status comments and description updates — whether posted to a tracked Jira/GitHub work item or as
a plain status comment on a PR (e.g. "implementation complete," "PR opened," a review-outcome
summary, a sign-off confirmation). These are always queued instead
of posted immediately, and the user clears the queue in one sitting via a new command, whenever
they choose — batching confirmation rather than interrupting the pipeline for each one. There is
no toggle to configure: since queuing never blocks the pipeline, there's no personal-repo case
that needs to opt out (see Key Design Decisions).

Everything else the pipeline posts — PR creation, the Reviewer's structured review comments,
`fix-pr`'s replies to review threads, commit messages — is left untouched and un-gated. These are
mechanically required for the automated Developer↔Reviewer loop to function at all; blocking them
on a human would stall the pipeline outright, not just add friction. Team-repo isolation for this
category is achieved by a different means entirely, external to this feature: the user points
their local clone's `origin` remote at a personal fork before running the pipeline there, so the
whole implement/review/fix cycle (including PR creation, Copilot review, and CI) runs privately.
Publishing the finished work to the team's real repo, and any further work on that public PR, is
explicitly out of scope here — the user has other, separate tooling planned for that, which this
feature does not need to anticipate.

## Responsibilities & Boundaries

- **Owns:** the pending-post queue format and its storage location; `queue_post.py`, the
  deterministic script that enqueues a proposed post instead of sending it; the new
  `user-approve-posts` skill that owns getting approval for a whole batch of posts (present, edit,
  discuss, attribute, dispatch, clean up); the new `/dev-team:review-posts` command that builds
  that batch from the queue and makes one call; the "reviewed by" attribution line
  `user-approve-posts` applies; the specific extension points inside `run-hook-instructions` (its
  `post-update`-shaped dispatch entries) and `investigate-bug` (its bug-comment step) that call
  `queue_post.py` instead of posting directly; a new `work-with-pr` "post-comment" operation for
  plain PR status comments; adding `Write` to `dev-team:hook-runner`'s tool list (`agents/hook-runner.md`)
  so it can stage content for `queue_post.py` without ever passing it through a shell command
  string.
- **Does not own:** PR creation, the Reviewer's structured PR review, `fix-pr`'s replies to review
  threads, or commit messages — none of these are touched, gated, or even inspected by this
  feature. `dev_team.py`'s state machine and `EVENT_NAME` table — unchanged; no new pipeline state,
  no new hookable event. `work-with-pr`'s existing structured-review and thread-reply mechanics —
  untouched; this feature only adds one new, separate operation alongside them. The fork-based
  isolation workflow for PR content — not built here; it requires no pipeline code (see Key Design
  Decisions), so this spec only documents it as the reason PR-channel content is *otherwise* safe
  to leave un-gated (plain status comments on the PR are still gated — see Key Design Decisions).
  Anything happening to a PR once it's published to the team's real repo — explicitly future,
  separate work per the user.
- **Integrates with:** `run-hook-instructions` (gains a queue-or-post branch for status-comment
  instructions); `investigate-bug` (its step 11 gains the same branch); `work-with-Jira-tasks` /
  `work-with-github-issues` / `work-with-pr` (used unchanged — except `work-with-pr`'s new
  "post-comment" operation — by `/dev-team:review-posts` to actually post an approved entry);
  `message-attribution` (unchanged and orthogonal — the reviewed-by line this feature adds is
  separate from, and additive to, whatever `attribution.message` is configured, exactly as an
  existing `Co-Authored-By` trailer is never displaced by an attribution line today).

## Key Design Decisions

### The gate line is "required for pipeline mechanics," not "which channel"

_Context:_ The obvious first cut — gate everything posted to Jira/GitHub, leave PR content alone
— turns out wrong once you look at what actually posts to a PR. The shipped
`assets/default-config.yaml` currently ships every `post-update` label empty — there is no shipped
default `post-update` text at all today. But this machine's own `~/.dev-team/config.yaml` (a
personal, uncommitted machine-tier override — confirmed by reading it directly) already has real
ones, and they show the pattern this decision has to account for: `after-review`'s reads "Post a
short comment on the PR summarizing the review outcome," `after-signoff-approved`'s reads "Post a
short comment on the PR and the tracked work item confirming sign-off and hand-off" — both post
status summaries to the *PR itself*, separate from the Reviewer's actual structured review
comments and `fix-pr`'s thread replies, which post to the PR too but are load-bearing for the
automated loop.

_Decision:_ The gate applies to *status/summary content*, regardless of which channel it targets —
concretely, any `post-update`-shaped instruction dispatched by `run-hook-instructions` (wherever
one appears: `before-create-pr`, `after-create-pr`, `after-review`, `after-signoff-approved`,
`after-signoff-changes_requested`) and `investigate-bug`'s bug-root-cause comment. Because the
match is on the instruction's plain-language text at dispatch time, not on any specific
project's configured wording, this needs no change to `assets/default-config.yaml` — it works
identically whether the matched instruction came from the (currently empty) shipped default, a
project's own `.dev-team/config.yaml`, or a personal machine-tier override, exactly like this
machine's `~/.dev-team/config.yaml` above. It never applies
to any message *required for the pipeline to keep functioning* — which today means PR creation,
the Reviewer's review-cycle comments, `fix-pr`'s thread replies, and commit messages, dispatched by
entirely separate skills (`create-pr-from-context`, `review`/`review-sign-off`, `fix-pr`,
`commit-changes`) that this feature never touches. This is a principle, not a fixed list: any
future required-for-the-pipeline message, from a custom instruction or a new skill, is exempt the
same way without needing this spec updated. Because `run-hook-instructions` dispatches by reading
each instruction's plain-language text (not by its config label — labels are just merge-override
keys, never semantically interpreted, per `get-project-configuration`), the queue-or-post check is
one more entry in its existing dispatch table, matched the same way every other instruction
already is.

_Consequences:_ An `after-signoff-approved` instruction naming both a PR comment and a tracker
comment produces two separate queued entries, one per channel — `run-hook-instructions` already
reads instruction text and picks the right operation per target, so splitting is no new
capability, just two dispatch-table matches instead of one. A project that writes its own custom
`post-update`-style instruction gets the same gating for free, since the match is on text shape
("post a ... comment/update ..."), not a fixed string.

### A PR-targeted status comment needs its own channel and a new `work-with-pr` operation

_Context:_ The decision above requires gating PR-targeted `post-update` instructions — this
machine's real `after-review`/`after-signoff-changes_requested` examples both post to the PR. But
neither `queue_post.py`'s channel enum nor `user-approve-posts`'s two dispatch targets
(`work-with-Jira-tasks`, `work-with-github-issues`) can address a PR at all. `work-with-pr` is the
skill that talks to PRs, but its only comment-posting capabilities are a full structured review
(inline comments plus a submitted summary) and a reply to an *existing* thread — neither fits
"post one plain, freestanding status comment." GitHub's comment API (and its MCP wrapper,
`mcp__plugin_github_github__add_issue_comment`) treats a PR number identically to an issue number
for commenting purposes — confirmed by `work-with-github-issues`, which already documents this
exact tool (alongside a `gh issue comment` CLI fallback) for plain issue comments.

_Decision:_ Add `pr-comment` to `PostEntry.channel`/`queue_post.py`'s channel enum. Add a new,
separate mechanical operation to `work-with-pr` — "post-comment" — that calls
`mcp__plugin_github_github__add_issue_comment` with the PR's number (the same tool
`work-with-github-issues` already uses, just passing a PR number instead of an issue number),
falling back to `gh pr comment <number> --repo <owner>/<repo> --body <text>` only if that tool is
unavailable — the same fallback pattern `work-with-github-issues` already documents. This is
distinct from the existing structured-review and thread-reply mechanics, which are untouched.
`user-approve-posts` dispatches a `pr-comment`-channel entry through this new operation, and it
calls `message-attribution` first, matching every other posting operation in `work-with-pr`. Since
a PR isn't a Jira/GitHub work item, the field carrying its identifier can't stay named
`work_item_id` — rename it to `target` throughout `PostEntry`/`queue_post.py`: a Jira issue key for
`jira-*` channels, a GitHub issue key for `github-issue-comment`, a PR URL for `pr-comment`.
`run-hook-instructions` already reads `pr_url` from the context file's frontmatter for its existing
hand-off operations (`convert-to-ready`, `request-review`); a `pr-comment`-shaped instruction reads
that same field.

For a work-item-targeted (not PR-targeted) `post-update` instruction, `run-hook-instructions` needs
to also decide `jira-comment` vs. `github-issue-comment` — the instruction wording itself is
tracker-agnostic, and the context file's `work_item_id` field carries no provider tag. This reuses
`identify-project-work-items`'s existing pattern-matching (each configured provider's
`issue-key-pattern`, e.g. `ADR-\d+` for Jira) — the exact same mechanism already used to resolve a
work item's provider anywhere else in this pipeline, not new logic.

_Consequences:_ `work-with-pr` gains one new documented operation; its existing review/reply/
hand-off mechanics are unaffected. The `target` rename touches every place `PostEntry`/
`queue_post.py` are described in this spec, but not their behavior for the two channels that
already worked.

### Isolation for PR content is a usage pattern, not a feature to build

_Context:_ The user considered gating PR content directly, forking the team repo for isolation,
and a from-scratch two-PR pipeline redesign (internal PR on a fork, then a second PR against the
real origin). Working through it: every git/GitHub-touching skill in this pipeline
(`commit-changes`, `create-pr`, `work-with-pr`, the Reviewer, `fix-pr`) already operates against
whatever remote is configured as `origin` — none of them hardcode the team's repo. So pointing a
local clone's `origin` at a personal fork, before ever running the pipeline, isolates the entire
Developer↔Reviewer loop (including Copilot review and CI, since both require a real GitHub PR)
with zero pipeline changes. Publishing the finished branch to the real team repo, and anything
that happens on that PR afterward, is then the user's own manual step, using separate tooling they
already intend to build for that purpose (with its own attribution and verification story) — not
something this pipeline resumes automated work on.

_Decision:_ This spec does not build fork creation, fork sync, or fork-to-origin publishing. It
documents the pattern (point `origin` at a personal fork for team repos) as the reason PR-channel
content needs no gate, and scopes the actual review-before-posting mechanism entirely to the one
channel that can't be isolated this way: comments and description updates on the tracked Jira/
GitHub work item, which always hit the real, shared tracker no matter which git remote is in use.

_Consequences:_ This spec is materially smaller than the two-PR pipeline redesign originally
considered. If fork isolation turns out to be unavailable for a given repo (e.g. org policy
disables forking of private repos), that's a gap in the *user's own setup*, not something this
feature falls back to — no fallback path is built here, since none of this feature's mechanism
depends on the fork pattern existing.

### The queue is non-blocking and lives outside any single worktree

_Context:_ Dev-team subagents (Developer, Reviewer, `dev-team:hook-runner`, `dev-team:debugger`)
have no `AskUserQuestion` access — confirmed for any `Agent`-tool-spawned sub-agent during
`_spec_ConcurrentDevelopment.md`'s own design work. Only the top-level interactive session can ask
the user anything. Separately, `concurrent-orchestrate` can run several tasks at once, each in its
own isolated git worktree (per `_spec_ConcurrentDevelopment.md`) — a queue file living inside one
task's worktree would be invisible to a review pass covering every task at once.

_Decision:_ A subagent that hits a gated post never blocks or asks anything — it calls
`queue_post.py`, which appends a record to `~/.dev-team/<repo-slug>/pending-posts/` (the same
home-directory, repo-slug-keyed location `concurrent_schedule.py` already uses for exactly the
same reason: stable across ephemeral worktrees, shared across concurrently-running tasks), and
reports its dispatch as successful — the pipeline proceeds exactly as if the post had gone out.
Review happens later, entirely on the user's own schedule, via `/dev-team:review-posts` (which
calls `user-approve-posts`) — running from the interactive session, which does have
`AskUserQuestion`.

_Consequences:_ Nothing in the automated pipeline ever waits on this feature. A long,
multi-task overnight run can accumulate dozens of queued posts; the user clears all of them in one
sitting the next morning, regardless of which task or which worktree produced each one.

### The reviewed-by attribution line is fixed, not user-configurable, and separate from `attribution.message`

_Context:_ The epic specifies exact wording: "Written by Claude Code as `<agent-name>` and
reviewed by `<user-name>` before posting," where `<agent-name>` was meant to differentiate
Developer vs. Reviewer vs. other agents. That distinction isn't part of this design: every gated
post goes through the same unified queue/review path regardless of which pipeline step or skill
originated it, so there's no per-origin identity worth preserving in the output.

_Decision:_ Drop `<agent-name>` entirely. The fixed line is `"Written by Claude Code and reviewed
by <user-name> before posting."` `<user-name>` is resolved once per `user-approve-posts` call
(covering every post in that batch) via the tracker's own "current user" identity (Jira's
`atlassianUserInfo`; for a GitHub-only project, `gh api user`), falling back to
`git-repo.user-alias` from config if neither resolves. This line is applied automatically to every
post dispatched through the approval flow — it is not read from or written to
`attribution.message`, and existing `attribution.message` behavior for every other message channel
(commits, PR content, and anything outside this feature's scope) is completely unchanged.

_Consequences:_ No config surface for wording — the line is fixed. If a project wants different
wording later, that's a follow-up, not blocking this spec. No separate attribution wiring is
needed inside `queue_post.py`, `run-hook-instructions`, or `investigate-bug`: both
`work-with-Jira-tasks` and `work-with-github-issues` already call `message-attribution` internally
before posting a comment or description, so any configured `attribution.message` line is applied
automatically the moment `user-approve-posts` dispatches through either of them — the reviewed-by
line composes on top of that, not instead of it.

### `user-approve-posts` owns the entire batch, not just one post at a time

_Context:_ An earlier version of this design split "get one post approved" into its own skill
that `/dev-team:review-posts` would call once per queued entry, threading a
`"posted" | "rejected" | "discuss"` result back so the command could decide whether to delete the
entry's file or defer it to a second pass. That return-value contract gets fragile once "discuss
this" (deferred, revisited one at a time after the first pass) and file-based editing (only
meaningful when a file exists) both need to flow through it — the command ends up re-implementing
bookkeeping (which entries are deferred, which files to delete) that belongs with the approval
logic itself.

_Decision:_ `user-approve-posts` (named to avoid ambiguity with the `/dev-team:review-posts`
command) takes a **list** of proposed posts and owns the whole batch end to end: presenting,
editing, deferring for discussion, dispatching, and cleaning up each entry's file — nothing is
threaded back through a per-call return value. `/dev-team:review-posts` shrinks to building that
list from the queue directory and making one call. A synchronous caller with a single post to
confirm just passes a list of one — same code path, no special-casing.

Editing is unified around files rather than having two different mechanisms for the queue and
synchronous cases: every entry may carry a `file_path`. A queue-sourced entry's `file_path` is its
own queue file, so the user can open and edit it directly before or during review. An entry with
no `file_path` (the synchronous case) gets one created on demand — the moment the user picks "Edit
and approve," `user-approve-posts` writes the content to a fresh temp file (outside the queue
directory, so it's never mistaken for a pending queue entry) and waits for confirmation before
re-reading it. Either way, "Edit and approve" always means "re-read whatever's at this path now."

"Discuss this" is handled as a two-pass sweep entirely inside `user-approve-posts`: the first pass
batches every entry through `AskUserQuestion` (up to 4 at a time — Approve as-is / Edit and
approve / Discuss this / Reject) and resolves everything except entries marked "Discuss this,"
which are set aside with their file untouched. Once that pass finishes, `user-approve-posts`
revisits each deferred entry one at a time as an open-ended conversation — not another batched
question — until the user reaches approve or reject, then dispatches and cleans up the same way as
any other entry. This isn't a novel UX pattern: `document-discussion` already implements exactly
this shape (resolve entries one at a time, in conversation, until each is settled) for its own
`> **Review:**` comment loop — `user-approve-posts`'s second pass follows the same precedent.

_Consequences:_ `/dev-team:review-posts` carries almost no logic of its own — list the queue,
build the list, make one call, print the summary it gets back. `user-approve-posts` is the only
place approval/edit/discuss/dispatch/cleanup logic lives, so a future interactive caller (see
Related Features) inherits the full behavior — including file-based editing and deferred
discussion — for free, not just the quick-approve path.

## Component Breakdown

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `queue_post.py` (new script) | Testable | Given proposed content, channel, target (work-item key or PR URL), and firing-event context, writes one pending-post record to `~/.dev-team/<repo-slug>/pending-posts/`; deterministic, no MCP/agent judgment. Pipeline path only — never calls `user-approve-posts` itself | — |
| `run-hook-instructions` (extended) | Testable (per its own established fixture harness — see `component-taxonomy`) | Gains one more dispatch-table entry: a `post-update`-shaped instruction always calls `queue_post.py` instead of posting directly | `queue_post.py` |
| `investigate-bug` (extended) | Orchestrator | Its bug-root-cause comment step (step 11) always queues instead of posting directly | `queue_post.py` |
| `user-approve-posts` (new skill) | Orchestrator | Given a list of proposed posts, owns the whole batch: presents each via `AskUserQuestion` (approve-as-is / edit-and-approve / discuss-this / reject), handles file-based editing (queue file or a self-created temp file), defers "discuss this" entries to a one-at-a-time conversational second pass, applies the reviewed-by attribution line, dispatches approved entries, and deletes each entry's file once resolved. Callable directly from any synchronous/interactive context with a list of one, not just from the queue — see Related Features | `work-with-Jira-tasks` (existing), `work-with-github-issues` (existing), `work-with-pr`'s new "post-comment" operation |
| `work-with-pr` "post-comment" operation (new) | Wrapper | Posts one plain, freestanding comment to a PR via `mcp__plugin_github_github__add_issue_comment` (PR number as issue number), falling back to `gh pr comment` — distinct from `work-with-pr`'s existing structured-review and thread-reply mechanics, which are unchanged | — |
| `/dev-team:review-posts` (new command) | Orchestrator | Lists pending posts for the current repo, builds one list of entries (each tagged with its own queue file), and makes a single `user-approve-posts` call; reports the returned summary | `user-approve-posts` |

## Planned Implementation

### Interfaces

- **`queue_post.py`** (lives at
  `plugins/dev-team/skills/run-hook-instructions/scripts/queue_post.py`), invoked as
  `queue_post.py --target <key-or-pr-url> --channel <channel> --content-file <path> --event-context <event>`
  (`repo_slug` is never a caller-supplied argument — see below):
  `channel: Literal["jira-comment", "jira-description", "github-issue-comment", "pr-comment"]`.
  `--content-file` takes a path, not the content itself, to avoid ever putting arbitrary (possibly
  adversarial-looking) multi-line comment text into a shell command string. The calling skill first
  uses the `Write` tool — not `Bash` — to place the content into a scratch file (never
  shell-interpreted), then invokes `queue_post.py` via `Bash` with only that fixed path as an
  argument. Writes a YAML file at `~/.dev-team/<repo-slug>/pending-posts/<id>.yaml` (`<id>` a
  timestamp-prefixed random suffix, so concurrent writers from different tasks/worktrees never
  collide — no locking needed) with fields `target`, `channel`, `content` (read from
  `content_file`), `event_context`, `created_at`. `repo_slug` is derived internally by calling
  `get_repo_slug()` (imported from `workflow-orchestrate/scripts/get_context_path.py`, via the same
  relative-`sys.path` pattern `concurrent_schedule.py` already uses to import it) — never a
  parameter, so callers never need to compute or pass it. The home-directory root
  (`~/.dev-team/`) honors the `DEV_TEAM_STATE_DIR` env var override, the same mechanism
  `concurrent_schedule.py`'s own `_state_dir()` already uses, so tests never write into a real
  machine's `~/.dev-team/`.
- **`run-hook-instructions` dispatch table addition:** an instruction matching the existing
  `post-update` shape (free text along the lines of "post a \[short\] comment/update on the
  PR/tracked work item...") always composes the content exactly as it would have for immediate
  posting (same context-file reads as today — e.g. the `Implementation Summary` section, or
  `pr_url` from frontmatter when the instruction targets the PR), writes it to a scratch file with
  `Write`, then calls `queue_post.py` (at its own `scripts/queue_post.py`, same directory) via
  `Bash` with `--target <key-or-pr-url>`, `--channel <channel>`, `--content-file <path>`, and
  `--event-context` set to the context file's own `state` field (its current pipeline state, e.g.
  `creating_pr`/`reviewing`/`signoff` — not an `--event` flag, which `run-hook-instructions` never
  receives; its only arguments are `--instructions`/`--context-file`, confirmed against its own
  SKILL.md, so this needs no new plumbing through `dev_team.py` or `workflow-orchestrate`'s dispatch
  prompt). `--channel` for a work-item-targeted instruction is resolved the same way
  `identify-project-work-items` already resolves a work item's provider — matching the context
  file's `work_item_id` against each configured provider's `issue-key-pattern` — not new logic.
  Then reports this entry successful without posting. Requires `Write` on `dev-team:hook-runner`'s
  tool list (`agents/hook-runner.md`), which it doesn't have today — every invocation of
  `run-hook-instructions` goes through that subagent.
- **`investigate-bug` step 11 addition:** the same always-queue behavior, `event_context="debug"`,
  in place of the existing direct `work-with-GitHub-issues` comment call. Reaches `queue_post.py`
  via `<skill-dir>/../run-hook-instructions/scripts/queue_post.py` — the same relative-path
  convention `dev-spec-create-work-items` already uses to reach `task_dependencies.py` in
  `workflow-orchestrate`'s `scripts/` directory.
- **`user-approve-posts`:**
  `user_approve_posts(posts: list[PostEntry]) -> {"posted": int, "rejected": int}`, where
  `PostEntry = {content: str, channel: Literal["jira-comment", "jira-description", "github-issue-comment", "pr-comment"], target: str, file_path: Path | None}`
  (`target`: a Jira issue key, GitHub issue key, or PR URL, matching `channel`).
  `posts` is passed as a JSON-array argument, the same convention `run-hook-instructions` already
  uses for its own `--instructions <json-array>` argument — the only established pattern in this
  repo for threading a typed list into a skill invocation. `channel` intentionally has no
  `github-issue-description` entry alongside `jira-description`, even though
  `work-with-github-issues` supports issue-body updates — no dispatch source this spec covers ever
  needs it; add it if a future one does.
  Resolves `<user-name>` once for the whole call (tracker's current-user identity, falling back to
  `git-repo.user-alias`). **First pass:** walks `posts` in batches of up to 4 via `AskUserQuestion`,
  each with four options — "Approve as-is," "Edit and approve," "Discuss this," "Reject." "Edit and
  approve": if `file_path` is set, re-reads that file's current content (the user may have edited
  it directly, before or during review); if unset, writes the content to a fresh temp file under
  `~/.dev-team/<repo-slug>/user-approve-posts-tmp/`, reports the path, and waits for the user to
  confirm before re-reading it. "Discuss this" sets the entry aside (its file, if any, untouched)
  instead of resolving it now. Every other outcome resolves immediately: approved (as-is or
  edited) → dispatch per `channel` (`work-with-Jira-tasks` for `jira-*`, `work-with-github-issues`
  for `github-issue-comment`, `work-with-pr`'s new "post-comment" operation for `pr-comment`), with
  `"Written by Claude Code and reviewed by <user-name> before posting"` appended as its own line;
  rejected → discard. Either way, delete whatever file that entry was using (its supplied
  `file_path`, or a self-created temp file), if any. **Second pass:** once every non-deferred entry
  is resolved, revisit each "Discuss this" entry one at a time as an open-ended conversation — not
  another batched question — answering the user's questions and incorporating feedback until it
  reaches approve or reject, then resolves exactly as above. Returns final `posted`/`rejected`
  counts once every entry (immediate or deferred) is resolved.
- **`/dev-team:review-posts`:** reads every file under `~/.dev-team/<repo-slug>/pending-posts/`
  for the current repo, oldest first, and builds one `list[PostEntry]` — each entry's `file_path`
  set to its own queue file. Makes a single `user_approve_posts(posts)` call and prints the
  returned summary (posted count, rejected count). Owns no approval, editing, or cleanup logic of
  its own — `user-approve-posts` deletes each entry's file as it resolves it.

### Key Classes

- **`queue_post.py`** (new script at `run-hook-instructions/scripts/queue_post.py`, reached by
  `investigate-bug` via the same relative-path convention `dev-spec-create-work-items` uses for
  `task_dependencies.py`) — the only component with real logic worth unit-testing directly:
  unique-id generation (collision-free under concurrent callers), YAML record shape, and the
  content-file contract. Verified with `pytest`, matching this repo's existing convention for its
  Python scripts.
- **`run-hook-instructions`** (extended) — the queue-or-post branch is one more row in its existing
  "Dispatching an instruction" table; no change to its ordering guarantee, its record-failure-and-
  continue contract, or anything about non-`post-update` instructions.
- **`investigate-bug`** (extended) — step 11 only; every other step unchanged.
- **`user-approve-posts`** (new skill) — the sole owner of the approve/edit/discuss/reject/
  attribute/dispatch/cleanup sequence for a batch of posts. Takes a list directly, with no
  queue/file dependency of its own beyond the optional `file_path` on each entry, so it's equally
  usable for a single interactive confirmation (a list of one) or the full queue.
- **`/dev-team:review-posts`** (new command, parallel to `/watch-pr`) — the only new user-invocable
  entry point this feature adds. Never spawned by the automated pipeline; always initiated by the
  user. Builds the queue's contents into one list and makes a single `user-approve-posts` call;
  owns no approval logic itself.

### Data Flow

1. During an automated pipeline run (`workflow-orchestrate`, `concurrent-orchestrate`, or the
   `debug`/`fix` pipeline), a step reaches a `post-update`-shaped hook instruction or
   `investigate-bug`'s bug-comment step.
2. The dispatching skill composes the content it would have posted, writes it to a scratch file
   with `Write`, and calls `queue_post.py` (via `Bash`, `--content-file <path>`), which writes one
   record under `~/.dev-team/<repo-slug>/pending-posts/`. The dispatching skill reports success and
   the pipeline continues without waiting.
3. This repeats across however many tasks/events fire while the user is away — the queue directory
   accumulates entries from every task and worktree for this repo.
4. Whenever the user chooses, they run `/dev-team:review-posts` from their interactive session. It
   lists every pending queue file, oldest first, and builds one list of entries — each tagged with
   its own queue file as `file_path` — then makes a single `user-approve-posts` call with the whole
   list.
5. `user-approve-posts` resolves `<user-name>` once for the call, then walks the list in batches of
   up to 4 via `AskUserQuestion` (Approve as-is / Edit and approve / Discuss this / Reject). "Edit
   and approve" re-reads the entry's queue file after the user edits it directly. Every outcome but
   "Discuss this" resolves immediately: an approval (as-is or edited) dispatches through
   `work-with-Jira-tasks`, `work-with-github-issues`, or `work-with-pr`'s new "post-comment"
   operation, per `channel`, with the fixed reviewed-by line appended; either way (approved or
   rejected) the entry's queue file is deleted.
6. "Discuss this" entries are set aside, file untouched, during that first pass. Once every other
   entry is resolved, `user-approve-posts` revisits each deferred entry one at a time as an
   open-ended conversation — not another batched question — until it reaches approve or reject,
   then resolves it exactly as above.
7. `user-approve-posts` returns final posted/rejected counts once every entry is resolved;
   `/dev-team:review-posts` reports them and exits — the pipeline resumes (or already has been
   running) fully unattended until the next batch accumulates.

## Related Features

| Feature | Scope |
|------|-------|
| (this feature) | Non-blocking review/approval queue for status comments and description updates posted to a tracked Jira/GitHub work item — always on, no config toggle |
| [ADR-399: `user-approve-posts` reuse in interactive flows](https://jodasoft.atlassian.net/browse/ADR-399) | `user-approve-posts` takes a list, so a synchronous, content-generating flow (e.g. `dev-spec-create-work-items`, `dev-spec-task-work-items`) could call it directly with a list of one for its own confirmation, skipping the queue entirely and still getting file-based editing and "discuss this" for free. Not wired into any interactive skill by this spec; the split into `queue-post`/`user-approve-posts` exists so that future integration costs nothing beyond one call site |
| Possible future opt-out/short-circuit | If always-queuing turns out to be annoying in practice (e.g. for low-stakes personal-repo pings), a way to skip the queue could be added later — explicitly deferred, not built here |

## Open Questions

None outstanding.

## Tasks

> **Legend:** 🤖 = agent task · 🧑 = human operator task

---

### [ADR-400: `queue_post.py` pending-post queue script](https://jodasoft.atlassian.net/browse/ADR-400) 🤖

**Depends on:** — none —

New deterministic script that writes one pending-post record to the repo-slug-keyed,
home-directory queue directory, given a content-file path.

**Exit criteria:**
- [ ] Lives at `plugins/dev-team/skills/run-hook-instructions/scripts/queue_post.py`
- [ ] Accepts `--target <key-or-pr-url>`, `--channel <jira-comment|jira-description|github-issue-comment|pr-comment>`,
      `--content-file <path>`, `--event-context <event>` — no CLI content argument and no stdin, so
      arbitrary comment text never passes through a shell command string
- [ ] Writes a YAML file to `~/.dev-team/<repo-slug>/pending-posts/<id>.yaml` with fields `target`,
      `channel`, `content` (read from `content_file`), `event_context`, `created_at`
- [ ] `<id>` generation is collision-free under concurrent callers (timestamp-prefixed random
      suffix), verified by a test that invokes it many times in quick succession
- [ ] `repo_slug` is derived internally via `get_repo_slug()` (imported from
      `workflow-orchestrate/scripts/get_context_path.py`, same relative-`sys.path` pattern
      `concurrent_schedule.py` uses) — never a CLI argument
- [ ] The `~/.dev-team/` root honors the `DEV_TEAM_STATE_DIR` env var override (same mechanism as
      `concurrent_schedule.py`'s `_state_dir()`), and `pytest` coverage uses it so tests never write
      into a real machine's `~/.dev-team/`
- [ ] `pytest` coverage for id-uniqueness, record shape, and the content-file contract
- [ ] No existing YAML-writing utility or third-party YAML dependency exists in this repo to reuse
      (`merge_config.py`'s `parse_yaml` only reads, including literal `|` block scalars for
      multi-line values — `queue_post.py` writes matching literal-block-scalar YAML by hand for its
      `content` field, not by adding a new dependency)

---

### [ADR-401: Wire pipeline dispatchers to the queue](https://jodasoft.atlassian.net/browse/ADR-401) 🤖

**Depends on:** ADR-400

Extend `run-hook-instructions`'s dispatch table and `investigate-bug`'s step 11 so status-comment
content is always queued via `queue_post.py` instead of posted directly, without touching anything
required for the pipeline's own mechanics.

Per `component-taxonomy`, `run-hook-instructions` is already established as a **Testable**
agent-skill-prose component, verified by its own scripted fixture harness
(`plugins/dev-team/fixtures/run-hook-instructions/`) rather than AAA unit tests — see this task's
last exit criterion.

**Exit criteria:**
- [ ] `agents/hook-runner.md` gains `Write` on its tool list (alongside its existing `Read`,
      `Bash`, `Skill`, Jira/GitHub MCP globs), matching the precedent already set by
      `agents/debugger.md` — required because every invocation of `run-hook-instructions` goes
      through `dev-team:hook-runner`, and it needs `Write` to stage content for `queue_post.py`
- [ ] `run-hook-instructions` recognizes `post-update`-shaped instruction text (matched on text
      shape, e.g. "post a \[short\] comment/update on the PR/tracked work item...") wherever it
      appears — `before-create-pr`, `after-create-pr`, `after-review`, `after-signoff-approved`,
      `after-signoff-changes_requested` — writes the composed content to a scratch file with
      `Write`, and calls `queue_post.py` (`scripts/queue_post.py` in its own skill directory) via
      `Bash` with `--target <key-or-pr-url>` (from context-file frontmatter — `pr_url` for a
      PR-targeted instruction, the tracked work-item id otherwise), `--channel <channel>`,
      `--content-file <path>`, and `--event-context` set to the context file's own `state` field
      (not an `--event` flag — `run-hook-instructions` only ever receives `--instructions`/
      `--context-file`, confirmed against its own SKILL.md, so no plumbing changes to `dev_team.py`
      or `workflow-orchestrate` are needed), reporting the entry successful without posting. This
      requires no change to `assets/default-config.yaml` (every `post-update` label ships empty
      today) — the match fires on whatever instruction text a project's own config tiers actually
      supply, exercised in practice today by this machine's own `~/.dev-team/config.yaml`
- [ ] For a work-item-targeted (not PR-targeted) instruction, `--channel jira-comment` vs.
      `github-issue-comment` is resolved by matching the context file's `work_item_id` against each
      configured provider's `issue-key-pattern`, the same mechanism `identify-project-work-items`
      already uses
- [ ] A synthetic instruction naming both a PR comment and a tracker comment in one line (matching
      the shape of this machine's own `after-signoff-approved` `post-update` instruction) produces
      two separate queued entries — one `channel: pr-comment` with `target` set to `pr_url`, one
      `channel: jira-comment`/`github-issue-comment` with `target` set to the work-item id
- [ ] `investigate-bug` step 11 queues its bug-root-cause comment the same way, with
      `event_context="debug"`, instead of calling `work-with-GitHub-issues` directly
- [ ] PR creation, the Reviewer's structured review comments, `fix-pr`'s thread replies, and
      commit messages are entirely untouched — verified by confirming `create-pr-from-context`,
      `review`/`review-sign-off`, `fix-pr`, and `commit-changes` are not modified by this task
- [ ] A custom project-authored `post-update`-style instruction (synthetic, not from any shipped
      or machine config) is matched and queued the same way, confirming the match is on text
      shape, not a fixed string
- [ ] `plugins/dev-team/fixtures/run-hook-instructions/` gains a new scenario covering the
      `post-update` dispatch entry, with `build_fixture.py`/`test_build_fixture.py` updated per
      the harness's own documented convention ("fixtures only change if `run-hook-instructions`'s
      own contract changes"). Unlike the harness's existing scenarios, which grade on git-repo
      state, this one has no git-observable action — it grades on the written
      `pending-posts/*.yaml` file instead, with `DEV_TEAM_STATE_DIR` pointed at a scratch directory
      so the dry run never touches a real machine's `~/.dev-team/`

---

### [ADR-402: `user-approve-posts` skill](https://jodasoft.atlassian.net/browse/ADR-402) 🤖

**Depends on:** — none —

New skill implementing the full batch approve/edit/discuss/reject/attribute/dispatch/cleanup flow
for a list of proposed posts. Also adds `work-with-pr`'s new "post-comment" operation, which this
skill is the sole caller of.

**Exit criteria:**
- [ ] `work-with-pr` gains a new "post-comment" operation, documented alongside its existing
      "Posting a review" and "Hand-off operations" sections: given a PR URL and body text, calls
      `mcp__plugin_github_github__add_issue_comment` with the PR's number (the same tool
      `work-with-github-issues` already uses for plain issue comments — GitHub treats a PR number
      as an issue number for commenting), falling back to `gh pr comment <pullNumber> --repo
      <owner>/<repo> --body <text>` only if that tool is unavailable, matching
      `work-with-github-issues`'s own documented fallback pattern. Calls `message-attribution`
      first, matching every other posting operation in this skill. Its existing structured-review
      and thread-reply mechanics are unmodified
- [ ] `user_approve_posts(posts: list[PostEntry]) -> {"posted": int, "rejected": int}` accepts
      `PostEntry = {content, channel: jira-comment|jira-description|github-issue-comment|pr-comment, target, file_path: Path | None}`
      (`target` is a Jira issue key, GitHub issue key, or PR URL, matching `channel`)
- [ ] Resolves `<user-name>` once per call (tracker's current-user identity, falling back to
      `git-repo.user-alias`)
- [ ] First pass batches entries through `AskUserQuestion` up to 4 at a time, each offering
      "Approve as-is," "Edit and approve," "Discuss this," "Reject"
- [ ] "Edit and approve" re-reads `file_path`'s current content when set; when unset, writes a
      fresh temp file under `~/.dev-team/<repo-slug>/user-approve-posts-tmp/` (never inside
      `pending-posts/`), reports the path, and waits for confirmation before re-reading it
- [ ] "Discuss this" entries are set aside with their file untouched instead of resolving
      immediately
- [ ] Every approved entry (as-is or edited) dispatches per `channel` — `work-with-Jira-tasks` for
      `jira-*`, `work-with-github-issues` for `github-issue-comment`, `work-with-pr`'s new
      "post-comment" operation for `pr-comment` — with `"Written by Claude Code and reviewed by
      <user-name> before posting"` appended as its own line
- [ ] Whichever file an entry used (caller-supplied `file_path` or a self-created temp file) is
      deleted the moment that entry resolves, posted or rejected
- [ ] Second pass revisits every deferred "Discuss this" entry one at a time as an open-ended
      conversation (not another batched `AskUserQuestion` call) until it reaches approve or reject
- [ ] Returns final `posted`/`rejected` counts once every entry, immediate or deferred, is resolved
- [ ] A list of one behaves identically to any other list — no queue/file dependency beyond the
      optional `file_path` on that one entry

---

### [ADR-403: `/dev-team:review-posts` command](https://jodasoft.atlassian.net/browse/ADR-403) 🤖

**Depends on:** ADR-400, ADR-402

New user-invocable command that lists the pending-posts queue and makes a single
`user-approve-posts` call over the whole batch.

**Exit criteria:**
- [ ] Lists every file under `~/.dev-team/<repo-slug>/pending-posts/` for the current repo, oldest
      first
- [ ] Builds one `list[PostEntry]`, each entry's `file_path` set to its own queue file
- [ ] Makes exactly one `user_approve_posts(posts)` call for the whole list — no per-entry looping
      in the command itself
- [ ] Prints the returned summary (posted count, rejected count)
- [ ] Running it with an empty queue reports that cleanly rather than erroring
- [ ] Never invoked by the automated pipeline — confirmed no `dev_team.py` state or hook dispatches
      it
