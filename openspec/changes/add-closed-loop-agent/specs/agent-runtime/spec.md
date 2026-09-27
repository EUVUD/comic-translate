## ADDED Requirements

### Requirement: Closed-loop job execution
The agent SHALL execute natural-language jobs in a closed loop. It SHALL plan steps and success criteria, invoke one tool at a time, and verify each result against postconditions and observations. It SHALL recover from a failed step before continuing.

#### Scenario: Complete job
- **WHEN** the agent receives "translate vol1.cbz from Japanese to English and export a PDF" with valid inputs
- **THEN** it loads the archive, configures the languages, translates, and verifies that the pages were translated
- **AND** it exports the PDF, verifies the artifact, and reports completion

### Requirement: Recovery from failures
The agent SHALL recover from failed steps by one of these means:
- retrying with backoff;
- adjusting settings;
- skipping the step and recording it;
- asking the user.

Beyond its retry limit, the agent SHALL NOT repeat an identical failing call unless conditions have changed.

#### Scenario: Transient engine failure
- **WHEN** a page is skipped because of a transient engine error
- **THEN** the agent retries the skipped page and reports that the retry succeeded

#### Scenario: Persistent failure
- **WHEN** a page fails again after the retry limit
- **THEN** the agent stops retrying it and completes the remaining work
- **AND** it reports the page as failed, with its reason

### Requirement: Grounded reporting
The agent SHALL generate its final report only from recorded observations. The report SHALL distinguish completed, skipped, and failed work.

#### Scenario: Partial completion
- **WHEN** two of twelve pages are still skipped at the end of a job
- **THEN** the report states that ten pages were translated, and names the two skipped pages with their reasons

### Requirement: Budgets and termination
The agent SHALL enforce limits on steps, tokens, cost, and wall time. It SHALL stop and report when a limit is reached or when the job cannot be completed.

#### Scenario: Budget exhausted
- **WHEN** the step budget runs out before the success criteria hold
- **THEN** the agent stops, reports the budget as the reason, and describes the state it reached

### Requirement: Shared tool registry and policy gate
The agent SHALL reach application capabilities only through the shared tool registry. Every call SHALL pass the policy gate, which checks filesystem roots, destructive actions, credit spending, and budgets.

#### Scenario: Write outside allowed roots
- **WHEN** the agent attempts to export to a path outside the allowed roots
- **THEN** the policy gate rejects the call and the agent receives a policy error

#### Scenario: Credit spending not authorized
- **WHEN** the session policy forbids credit spending and the agent selects an account-backed translator
- **THEN** the policy gate rejects the change
- **AND** the agent chooses an allowed translator or asks the user

### Requirement: Untrusted page content
The agent SHALL treat text that comes from pages as untrusted data and SHALL NOT follow instructions contained in it.

#### Scenario: Instruction embedded in a comic page
- **WHEN** OCR output contains text instructing the agent to delete pages
- **THEN** the agent invokes no action requested by that text and continues the user's job

### Requirement: Provider-agnostic LLM adapters
The agent SHALL use a provider-independent LLM interface and SHALL NOT depend on an agent framework. The interface SHALL have adapters for OpenAI-compatible endpoints and the Anthropic API, plus a scripted adapter for deterministic tests.

#### Scenario: Switching providers
- **WHEN** the configured provider changes from an OpenAI-compatible endpoint to Anthropic
- **THEN** the same job runs with the same tools and policy, with no code changes

#### Scenario: Deterministic test run
- **WHEN** the agent runs with the scripted adapter
- **THEN** the run produces the same tool calls and report on every execution

### Requirement: Headless job entry point
The system SHALL provide a command-line entry point that runs a job against a hermetic or user-profile session and prints the final report.

#### Scenario: Command-line job
- **WHEN** a user runs the command with a job instruction and an input path
- **THEN** the agent performs the job without opening a visible window and prints the report
