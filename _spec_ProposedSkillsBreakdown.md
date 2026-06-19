Describes how to break down existing commands into reusable skills

Each one comes from part of an existing skill or command, as noted. The ones with (project) next to them contain project-specific knowledge, like how work items and documents are handled in the project, patterns and practices to follow, etc.

The ones with ": Workflow" next to them are steps for a workflow pipeline. 
The ones with ": Command" next to them are commands I want to invoke as a user

Recreate these as skills. Each one should have a clear "use when" statement, and skills that use other skills should start with a summary that includes those exact statements. Examples are included with each skill, but do not need to be used verbatim if stronger language can be written. The point is that the phrasing should be exactly (or nearly-exactly) the same to increase the likelihood that skills will be used.



## identify-work-item (project)
*from `skills/identify-project-work-items`*
- [ ] Use when you need to identify a task-work-item or feature-work-item.
- identify a work-item-id from context, like a prompt or other source
- Describe work item relationships (Epic/Task/Subtask, e.g.)
- Basically, what types of work tracking does this project use, so we can identify them in different projects
- What is a feature-work-item and what is a task-work-item
- Identify the type of work item, then "you are working with a {type} work item" -- hopefully this should loop in the work-with-{type} skill

## work-with-GitHub-issues
## work-with-Jira-tasks
*from various*
- [ ] Use when you are working with a {type}
- Include instructions on how to access information and make changes in the work items (MCP, CLI, etc.)


## spec-task-work-items (project)
*from `spec`*
Use when you are writing a new spec or a new part of an existing spec
- Update Epic and Task descriptions with summaries after a spec is completed

## use-context-file
*from `skills/workflow-setup`, various*
Use when you will read from or write to a workflow context file
- Context file stuff from existing "workflow-setup"
- describe the format of the context file
- Describe how to write or update sections of the context file

## ensure-working-branch (project)
*from `skills/workflow-setup`*
- Based on the working pattern in AdaptiveRemote
- Ensure the context file for active work item
- Determine the base branch and working branch
- Update values in context file
- If working branch does not exist
	- Check out and update base branch
	- etc.

## create-pr
*from `commands/developer-create-pr`* 
Use when creating a new pull request in GitHub
- Rules about how a PR should be created
- Instructions to use `gh` or GitHub MCP

## create-pr-from-context : Workflow
*from `commands/developer-create-pr`*
You are reading from the context file, creating a new pull request in GitHub, and updating the context file.
- Read the context file,
- ensure the correct branch,
- create a PR using create-pr
- Put the PR URL in the context file

## work-with-pr
*from various*
You are working with an existing GitHub PR
- Instructions for working with code reviews and review threads
- Instructions for reading/writing comments
- Instructions for reading checks

## developer-standards (project)
*from `commands`*
- [ ] Use when planning new code, writing code, or reviewing code
- Read CONTRIBUTING.md and CLAUDE.md. Always generate code that complies with .editorconfig

## fix-pr : Workflow
*from `commands/developer-fix`*
Use when fixing build failures, test failures, or addressing code review comments
You are working with an existing GitHub PR, reading from the workflow context file, fixing issues in existing code, and committing changes locally to the repo
- Triage rules
- Do not do a full validation pass--that's someone else's job (only if in pipeline?)
- Commit each fix separately
- Report

## fix-draft : Workflow
*from `commands/developer-fix`*
Use when fixing build failures or test failures
You are reading from the workflow context file, fixing issues in existing code, and committing changes locally to the repo
- Like fix-pr but without the existing GitHub PR

## commit-changes
*from various*
You are committing changes locally to the repo
- Rules for commit comments
- Commands to use
- Don't push

# write-e2e-tests (project)
- gherkin style tests
- Other test guidelines

## missing-test-harness
*new*
Use when you are planning or writing unit, E2E, or API tests
- Use the existing test harnesses in the repo. If a test harness does not exist for a given type of code, don't create one unless explicitly instructed to do so. For example, in a repo that has unit tests in C# and Python, but E2E tests only cover the C# code, when you are writing Python code you do not need to invent an E2E test strategy for Python. If you are writing documentation, you don't have to write any tests for that at all unless there is some kind of documentation testing already in the repo. 

## test-driven-development
*from `commands/developer-implement*`
Use when you are writing new code or fixing issues in existing code
- write E2E tests first
- implement one component at a time
	- write unit tests (they should fail--but for the right reason, not for build break reasons)
	- implement until unit tests pass

## implement-task : Workflow
*from `commands/developer-implement`*
You are reading the workflow context file to find a task brief, writing new code to implement the task brief, and committing changes locally to the repo
- Understand the task
- TDD both E2E and API tests
- Commit incremental changes (after E2E tests written, after each component built, and at the end) with descriptions
- Report results

## code-change-expectations
*from `commands/developer-implemenet` and others*
Use when you are writing new code or fixing issues in existing code
- Always build and test the code you implemented - from developer-fix
- Always write unit tests first (TDD)
- Self-review

## find-repo-documentation (project)
*from various*
- [ ] Use when you need to learn the architecture from documentation in this repo
- file format
- locations
- Search helper

## write-repo-documentation (project)
*from various*
Use when you are drafting or updating architecture documentation in this repo 
- Where to put new documents
- What is expected in new documents
- Document templates

## research-learn
*from `commands/researcher-plan`*
- [ ] Use when you are researching a work item
- Rules from step 4
- Basically, give a list of MCP servers and other references that the researcher can consult on various topics (find some good ones going forward)
- More grounding information sources/patterns

## research-sources
*from `commands/resarcher-plan`*
- [ ] Use when you are researching a work item
- Rules from step 3
- Use documentation and source files to understand existing patterns
- Understand where the work item fits in

## write-task-brief
*from `commands/researcher-plan`*
- [ ] Use when you are writing a task brief for a work item
- Rules from step 4 about what should go into a task brief

## plan : Workflow
*from `commands/researcher-plan`*
- [ ] Use when making a plan to implement a task-work-item
You need to identify a task-work-item and learn the architecture from documentation in this repo, then you are researching the work item and writing a task brief for the work item *(or maybe don't mention the research specifically if we're going to spawn Researcher agents)*
- Spawn researcher agents to gather information from various sources
- Create a task brief 

## researcher-spec-review : Workflow
*from `commands/researcher-spec-review`*
- Review each task as if you were going to research it as a task
- If there are any "open questions", ask them
- If you make decisions that aren't in the spec, suggest adding them to the spec

## researcher-sign-off : Workflow
*from `commands/researcher-sign-off`*
- Evaluate exit criteria

## spec : Command
*from `commands/spec`*
You are writing a complete new spec, working with the user to refine the spec, breaking down the spec into tasks, and verifying that the spec is complete.  
- Given some source of input (feature-work-item-id, draft document, prose description)
- write a first draft
- Pause and wait for the user
- discuss with the user
- Spawn Researcher to do readiness review on design
- Task breakdown
- Pause and wait for the user
- discuss with the user
- Spawn Researcher to do readiness review on task breakdown
- Include a template for the spec to follow
	- add that the spec must include a reference to the feature-work-item, if there is one

## add-to-spec : Command
*from `commands/add-to-spec`*
You are writing a new part of an existing spec, working with the user to refine the spec, breaking down the spec into tasks, and verifying that the spec is complete.  
- Given some source of input (task-work-item-id, draft document, prose description)
- write a first draft
- Pause and wait for the user
- discuss with the user
- Spawn Researcher to do readiness review on design
- Task breakdown (break down into multiple tasks, if necessary)
- Pause and wait for the user
- discuss with the user
- Spawn Researcher to do readiness review on task breakdown

## spec-first-draft
*from `commands/spec`*
Use when writing a first draft of a complete new spec or a new part of an existing spec
- Gather information about
- Spawn one or more Researchers to `research-learn` about topics in the spec, summarize alternatives, make recommendations, find links to documentation, etc.
- Ask the user clarifying questions until you have enough information to write a first draft
	- What is expected in the draft (template)
 
## spec-discussion
*from `commands/spec`*
Use when working with the user to refine a spec.
- Find `**REVIEW:**` comments in the spec
- Do Phase 3 from `commands/spec`

## spec-task-breakdown
*from `commands/spec`*
Use when breaking down a spec into tasks
- Phase 5
- Scope: an appropriate amount of work for an agent to handle in one session
- Separate human-required tasks (configuration, etc.) from agent tasks (coding, writing documents)

## spec-readiness-review
*from `commands/spec`*
Use when verifying a spec is complete
- Phase 4, but on a specific part of the document (either the design/decision content or the task breakdown)

## investigate-bug
*from `commands/debugger-investigate`*
You are identifying a work item to fix, reading architecture documentation in this repo, writing E2E tests or unit tests to reproduce the issue, and providing analysis of the root cause 
- Ensure issue is found
- Everything from the existing skill, except specifics about writing tests

## write-e2e-test (project)
*from `commands/debugger-investigate`, others*
Use when you are writing E2E tests
- Collected guidance from across the tools

## review : Workflow
*from `commands/reviewer-review`*
You are working with an existing PR, reading from a workflow context file, learning the architecture from documents in this repo, reviewing code changes, and creating a PR review
- read the task brief and exit criteria
- read relevant reference material
- Review the code (don't create a pending review, it doesn't show up until it's posted anyway)
- Create a review on GitHub
- Write output

## review-sign-off
*from `commands/review-sign-off`*
You are working with an existing PR, reading from a workflow context file, learning the architecture from documents in this repo, reviewing code changes, and creating a PR review
- read the latest updates in the context file
- read existing comments and replies on review threads
- Review the code that has changed (don't create a pending review, it doesn't show up until it's posted anyway)
- Scan modified files for new issues
- Submit sign off

## final-sign-off : Workflow
*from `commands/review-sign-off`*
You are working with an existing PR and modifying a task-work-item
- Break out step 7a from review-sign-off into a separate step. This hand-off is happening after the reviewer signs off, but not waiting for other parallel sign-offs.

## review-guidelines
*from `commands/reviewer-review`*
Use when you are reviewing code changes
- Priority guidelines from step 6

## identify-project-work-item
**Deprecated**

## workflow-orchestration
Use when you are orchestrating a dev-team workflow pipeline
You need to identify a task-work-item, then you are orchestrating a team of sub agents
- Minor change: argument should be interpreted by the rules

## workflow-setup
**Deprecated**

## workflow-worker
You are performing a requested skill as part of a workflow pipeline, writing the results to the workflow context file
- No real changes, just adding the reference to other skills so the context file is referenced

## commands/implement : Command
You are identifying a task-work-item and orchestrating a dev-team workflow pipeline
- No other changes, just the reference to workflow-orchestration and work item skills

## commands/fix : Command
You are identifying a task-work-item and orchestrating a dev-team workflow pipeline
- No other changes, just the reference to workflow-orchestration and work item skills

Still to do:
- [ ] Which things belong in agents?
- [ ] Which agent things belong in skills?
- [ ] Which CONTRIBUTING.md things belong in either?

