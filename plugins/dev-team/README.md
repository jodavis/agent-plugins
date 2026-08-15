# dev-team plugin

The dev-team plugin provides a pipeline of agents — planner, researcher, developer, reviewer, and
debugger — for implementing work items and fixing bugs. It is designed to work across projects
with different conventions, tools, and workflows.

## Extension point skills

Some pipeline steps require project-specific knowledge: where architecture docs live, where E2E
tests go, how to resolve work item IDs, what branch naming convention to use. Rather than
hardcoding these into the pipeline, the plugin calls **extension point skills** that projects provide.

The plugin includes a generic stub for each extension point. Stubs do the minimum useful thing when
no project override is present — typically examining the existing repo structure or asking the user.
Projects should override the skills that match their conventions and tools.

### How to override

Create a `SKILL.md` in `.claude/skills/<skill-name>/` in your project repo. Claude Code loads your
version in preference to the plugin's stub. You only need to override the skills relevant to your
project.

### Extension point skills

| Skill | Called by | What it does | Stub behavior |
|---|---|---|---|
| `developer-standards` | code-change-expectations, fix-draft, fix-pr, implement-task, review, review-sign-off | Loads code guidelines and quality gates | Reads CONTRIBUTING.md, CLAUDE.md, and all `.editorconfig` rules |
| `find-repo-documentation` | investigate-bug, plan-task, researcher-dev-spec-review, researcher-design-review, review, dev-spec-first-draft, design-first-draft | Discovers and reads architecture docs relevant to the task | Searches `docs/`, `doc/`, and root-level Markdown files |
| `write-repo-documentation` | write-design-spec flow, write-dev-spec flow | Establishes doc naming, file location, and required sections | Follows existing doc conventions in the repo |
| `identify-project-work-items` | investigate-bug, plan-task, review, and others | Resolves work-item-id and work-item-type from user input | Asks the user what work item to work on |
| `ensure-working-branch` | investigate-bug, read-dev-spec-section, read-task-brief | Ensures the correct working branch is checked out | Warns if on main/master; asks which branch to use |
| `dev-spec-task-work-items` | write-dev-spec | Updates project work items after a dev spec is finalized | Skips with a message (no tracker configured) |
| `design-work-items` | write-design-spec | Updates the source work item after a design doc is finalized | Skips with a message (no tracker configured, or no source item) |
| `write-e2e-test` | investigate-bug | Establishes E2E test framework, file locations, and conventions | Finds the existing test directory and follows observed patterns |

### Authoring an override

Each skill override is a complete, self-contained `SKILL.md` — it replaces the stub entirely.
Write it as you would any skill: YAML frontmatter with `name` and `description`, then instructions
for the agent. See the stub files in `plugins/dev-team/skills/` for the expected structure.

Example: a project using Jira with the prefix `MYPROJ-` would override
`identify-project-work-items` to define that pattern, rather than relying on the stub to ask the
user every time.
