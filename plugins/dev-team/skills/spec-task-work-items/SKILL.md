---
name: spec-task-work-items
description: >
  Use when you are writing a new spec or a new part of an existing spec.
  Updates the Jira epic and task descriptions with summaries after the spec is finalized.
argument-hint: <epic-key> <spec-path>
---

Use this skill when:
- You are writing a new spec or a new part of an existing spec
- The spec is finalized and Jira work items need to reflect the decisions

## Steps

### 1 — Update the Jira epic description

Use the `work-with-Jira-tasks` skill to update the Jira epic's description with a concise summary of the finalized design decisions from the spec:

- Replace the original description (which typically contains early design thoughts) with a brief overview and a bulleted list of the key decisions and their outcomes
- Include a link to the spec file in the repo

### 2 — Update task descriptions

For each Jira task created from the spec, update its description to reflect the finalized content:

- One-paragraph overview of what the task implements
- Bulleted list of key decisions and their outcomes relevant to this task
- Reference to the spec section: `See spec: <relative path>`

Replace initial notes or placeholders entirely — do not append.
