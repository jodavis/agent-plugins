---
name: researcher-issue
description: Produce a concise task brief for a GitHub issue, synthesized from the issue body and comments, the relevant architecture docs, and source code. Proposes exit criteria since none are written in the issue.
argument-hint: <Issue-NNN work item ID>
user-invocable: false
---

## Inputs

Work item ID: the first token of `$ARGUMENTS` (e.g. `Issue-444`)

If missing, stop and tell the caller:

> Usage: `/researcher-issue <Issue-NNN>`

## Debug report

A root-cause report from the prior debugging step is embedded below. Use its findings —
confirmed root cause, evidence, ruled-out hypotheses — as supporting context when
proposing exit criteria and identifying affected files. If the section is empty, the
debugging step did not run or produced no output.

$DEBUG_REPORT

---

## Steps

### 1 — Gather issue context

Use `$DEBUG_REPORT` as the primary source of bug context.

If `$DEBUG_REPORT` is empty, derive the issue number by stripping the `Issue-` prefix from
the work item ID (e.g. `Issue-444` → `444`) and fetch issue details:

```bash
gh issue view <number> --comments
```

If the issue is not found, stop and report the error.

Combine whatever context is available (debug report and/or issue title/body/comments) into
a single issue context summary. This is the context you'll pass to the researcher agents
and to the task brief.

### 2 — Spawn parallel researcher agents

Spawn three `dev-team:researcher` agents in parallel. Pass each one the issue context from
step 1.

**Agent 1 — Architecture docs:**
> Use the `find-repo-documentation` skill to discover all architecture docs in the repo. Read the ones relevant to this issue and return a summary of what each says about the areas it will touch.
>
> Issue context:
> `<paste issue context here>`

**Agent 2 — Source code patterns:**
> Use the `research-sources` skill to find and read the source files most relevant to this issue. Focus on existing interfaces, utilities, and patterns the fix should use or extend.
>
> Issue context:
> `<paste issue context here>`

**Agent 3 — External best practices:**
> Use the `research-learn` skill to research any frameworks, libraries, or patterns relevant to this issue that are not fully covered by local docs. Return findings with source links.
>
> Issue context:
> `<paste issue context here>`

Wait for all three agents to complete and collect their output.

### 3 — Write the task brief

Use the `write-task-brief` skill, providing:
- The `work-item-id`
- The issue context from step 1 (in place of a spec section)
- The combined research findings from step 2

The issue contains no formal exit criteria. Instead of copying them verbatim, **propose**
a concrete, checkable list synthesized from the issue description and the context you
gathered. Frame each criterion the same way spec exit criteria are written (observable
behaviour, not implementation detail). Label the section **"Exit criteria (proposed)"**
so the caller knows these are inferred, not authoritative.

Return the task brief as prose.
