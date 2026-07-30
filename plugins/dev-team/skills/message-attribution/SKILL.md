---
name: message-attribution
user-invocable: false
description: >
  Use when a skill is about to write a message on the user's behalf — a commit message, PR
  description, PR/review comment, or work-item comment or description. Formats the configured
  "Written by <name>" attribution line, or returns nothing when attribution is unconfigured.
---

Use this skill when:
- You are about to write a commit message, PR description, PR/review comment, or a work-item
  (Jira/GitHub) description or comment, and need to know whether to append an attribution line

## Getting the configured wording

If a context file has already been resolved for the current work item earlier in this task (via
`use-context-file`), read `attribution` from that file's `<!-- section:Project Configuration -->`
section. Otherwise, invoke `get-project-configuration` directly.

Read `attribution.message` from the result.

## Formatting the attribution line

**If `attribution.message` is `null`, absent, or an empty string:** add nothing — the message you
are producing must be byte-for-byte the same as if this skill were never consulted. This is the
shipped default (no project override); do not invent a fallback name.

**Otherwise:** append the text in `attribution-message`, with <name> replaced by your name, as its own
trailing line, separated from the rest of the content by one blank line. For a single-line
message (e.g. a short Jira comment), still place it on its own line rather than appending it
inline to the existing text.

This attribution line is independent of, and additional to, any other attribution mechanism a
message channel already carries on its own (e.g. a `Co-Authored-By:` trailer added by the
surrounding tool harness to git commits) — never remove or replace an existing trailer to make
room for it; add the `attribution.message` line alongside it.

## Out of scope

Slack messages and emails are out of scope: no skill in this plugin sends either today, so there
is nothing to wire attribution into for those channels yet.
