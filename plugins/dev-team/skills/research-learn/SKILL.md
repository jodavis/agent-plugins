---
name: research-learn
description: >
  Use when you are researching a work item by learning from external resources.
  Searches for best practices, framework documentation, and technical guidance not covered by local docs.
argument-hint: <topic or framework to research>
---

Use this skill when:
- You are researching a work item
- The task touches a framework, library, or pattern not fully covered by local architecture docs

## Steps

### 1 — Identify topics to research

Based on the task description or spec section you have been given, identify the external topics that need research. Common areas: .NET DI patterns, Blazor component lifecycle, MAUI platform-specific code, ASP.NET minimal API conventions, machine learning patterns, Azure/cloud service APIs.

### 2 — Search for best practices

Use `WebSearch`, `WebFetch`, or Microsoft Learn to look up relevant documentation and best practices:
- `mcp__microsoft-learn__microsoft_docs_search` — search Microsoft docs
- `mcp__microsoft-learn__microsoft_docs_fetch` — fetch a specific Microsoft doc page
- `mcp__microsoft-learn__microsoft_code_sample_search` — find code samples

### 3 — Return findings

Return your findings as prose with source links. Include:
- The recommended approach and why
- Key APIs, types, or conventions to use
- Any constraints or gotchas to be aware of
