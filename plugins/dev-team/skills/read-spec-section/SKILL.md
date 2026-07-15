---
name: read-spec-section
user-invocable: false
description: >
  Use when you need to read the spec file section for a work item.
  Resolves the context file, ensures the working branch, locates the spec file,
  and extracts the section that describes the given work item.
argument-hint: <work-item-id>
---

Use this skill when:
- You need to read the spec section for a work item before researching or planning it

## Steps

### 1 — Resolve the context file and confirm the working branch

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file,
including its "Confirming the working branch" step — this skill is about to read/write repository
files in the next steps. Extract `spec_path` from the frontmatter.

### 2 — Find the spec file

If `spec_path` is empty or missing from the context file:

Search for the spec file that contains a reference to the `work-item-id`:

```
Glob: _spec_*.md
Grep: <work-item-id> across all matches
```

Use the first file that contains the `work-item-id`. Then write the relative path to the context file:

```
spec_path: <relative-path-to-spec>
```

Use the `use-context-file` skill to update the frontmatter field.

If no spec file is found, stop and report:

> No spec file containing `<work-item-id>` was found. Create or locate the spec file before proceeding.

### 3 — Extract the spec section

Read the spec file. Locate the section that references the `work-item-id` — typically a heading or checkbox item that includes the key. Extract all content from that heading until the next heading at the same level or end of file.

If no section is found, stop and report:

> Task key `<work-item-id>` was not found in `<spec-file>`. Verify the key and spec path are correct.

Return the extracted section as the **task context**.
