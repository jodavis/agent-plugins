---
name: research-sources
user-invocable: false
description: >
  Use when you are researching a work item by reading existing source code.
  Reads the relevant source files and interfaces to understand existing patterns.
argument-hint: <task context or description>
---

Use this skill when:
- You are researching a work item
- You need to understand existing patterns, interfaces, or utilities in the source code before implementing

## Steps

### 1 — Identify relevant areas

Based on the task description or spec section you have been given, identify which subsystems and source areas the task will create or modify.

### 2 — Find relevant source files

Use `Glob` and `Grep` to locate the relevant files. Focus on:
- Existing interfaces the task must implement or call
- Base classes or abstract types the task will extend
- Utilities and helpers that exist and should be reused rather than reinvented
- Test files for patterns and conventions in the area

### 3 — Read and summarize

Read the relevant source files. For each one, note:
- File path
- What it does
- What patterns or conventions it establishes that this task should follow

Return your findings as prose summarizing the relevant patterns, utilities, and interfaces, with file paths for each.
