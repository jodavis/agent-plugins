---
name: gather-brief-sources
user-invocable: false
description: >
  Use when resolving a feature brief from a flexible mix of sources — a tracked work item,
  pasted notes, a file, a link, or any combination — rather than a single fixed source type.
argument-hint: <work-item-id | #issue | pasted notes | file path | URL | combination>
---

Use this skill when:
- A command needs a feature or design brief and the input could be a tracked work item, pasted
  notes, a file, a link, or some combination of these — not just a single known source type

## Steps

### 1 — Determine what sources are available

Look at the command argument and conversation context. If nothing indicates a source, ask:

> What should this be based on? An existing work item, pasted notes, a link, a file, or some combination of these?

**PAUSE — wait for the answer** if nothing was evident from the argument or context.

### 2 — Resolve each source

For every source identified, resolve it:

- **Tracked work item reference** (e.g. an issue key, `#42`, or "the epic for X") — use
  `identify-project-work-items` to resolve it to a `work-item-id`/`work-item-type`, then fetch its
  summary and description via the matching `work-with-<provider>` adapter skill (e.g.
  `work-with-Jira-tasks`, `work-with-GitHub-issues`).
- **Pasted text already in the conversation** — use it verbatim; do not re-fetch or paraphrase it away.
- **A local file path** — read it with the `Read` tool.
- **A URL** — fetch plain pages with `WebFetch`. For a Confluence/Jira link, use the matching
  Atlassian MCP tool only if one is connected and authorized in this environment; otherwise ask
  the user to paste the relevant content rather than guessing at page contents you can't fetch.
- **Multiple sources at once** — resolve and gather all of them; do not force a single source to
  "win."

If a specifically-referenced source (e.g. a work-item key the user or brief pointed at) does not
resolve, tell the user it wasn't found and ask them to correct it or confirm dropping it — do not
silently drop it. This is different from simply not having a tracked work item at all, which is
always valid (see step 4).

### 3 — Synthesize the brief

Combine everything gathered into one coherent feature brief. Note which sources contributed —
this becomes the citation list for the document's `> **Source:**` header line and `## Related
Docs` section.

### 4 — Output

Return:

```
brief: <synthesized brief text>
work-item-id: <id, or "— none">
work-item-type: <jira|github|other, or "— none">
sources: <list of source citations>
```

A brief with no tracked work item among its sources (e.g. purely pasted notes) is valid — do not
require one.
