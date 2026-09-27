## 1. Proposal and Branch

- [x] 1.1 Create branch `feature/closed-loop-agent` from `origin/develop`.
- [x] 1.2 Write the OpenSpec proposal, design, tasks, and capability specs for `app-automation-api`, `agent-runtime`, `agent-mcp-server`, and `agent-evaluation`.
- [x] 1.3 Validate the change with `openspec validate add-closed-loop-agent --strict` on a machine that has the OpenSpec CLI.

## 2. Application Session and Interaction Policy

- [ ] 2.1 Add `AppSession`, which boots `ComicTranslate` offscreen or attaches to an existing instance, with a dispatcher that runs calls on the GUI thread and returns futures.
- [ ] 2.2 Add the `InteractionPolicy` seam with a default GUI policy that keeps current dialogs, and route every modal call site through it.
- [ ] 2.3 Add an agent policy that records prompts as structured events, applies pre-authorized answers, and never picks a destructive default.
- [ ] 2.4 Add a test that fails when a modal `.exec()` call site bypasses the interaction policy.
- [ ] 2.5 Add hermetic environment setup:
  - isolated settings;
  - the null keyring;
  - sandboxed input, output, and autosave roots;
  - offscreen Qt;
  - update checks and credit refreshes disabled;
  - engine profile selection.
- [ ] 2.6 Add state snapshots, written after every mutating action and when the session exits.
- [ ] 2.7 Add an engine-override registry that the detection, OCR, and translation factories check first. It stays empty unless an evaluation profile installs overrides.
- [ ] 2.8 Add deterministic fixture engines keyed by page fingerprint, with scripted fault injection.

## 3. Actions, Observations, and Jobs

- [ ] 3.1 Add read-only observations: application state, pages, page blocks, batch report, settings, artifacts, and page previews.
- [ ] 3.2 Add job handles that report status, progress, and results, and resolve from existing completion signals and callbacks.
- [ ] 3.3 Add input actions: load images, archives, and PDFs, and open `.ctpr` projects.
- [ ] 3.4 Add configuration actions for languages, tools, render options, and webtoon mode. They take canonical names and map them to localized labels.
- [ ] 3.5 Add translation actions:
  - translate pages;
  - retry skipped pages;
  - skip or unskip pages;
  - edit a block translation as an undoable command.
- [ ] 3.6 Add save and export actions that use the controller internals that open no dialogs. They cover project, image, archive, PDF, and PSD outputs.
- [ ] 3.7 Add postcondition checks and structured errors to every action.
- [ ] 3.8 Add T0 contract tests, using fixture engines, for every action and observation.
- [ ] 3.9 Add import tests proving that normal application startup imports neither `agent`, `mcp`, nor `inspect_ai`.

## 4. Tool Registry and MCP Server

- [ ] 4.1 Add the tool registry, with JSON schemas, descriptions, and `read_only`, `destructive`, `spends_credits`, and `long_running` annotations.
- [ ] 4.2 Add the policy gate covering filesystem roots, destructive actions, credit spending, and budgets.
- [ ] 4.3 Mark text that comes from pages as delimited untrusted data in tool results, and keep credentials out of every result.
- [ ] 4.4 Add `requirements-agent.txt` and the FastMCP stdio server over the registry, mapping tool annotations to MCP hints.
- [ ] 4.5 Add MCP contract tests, and try the server with an external MCP client on a fixture project.

## 5. Evaluation Core

- [ ] 5.1 Define the scenario schema, loader, validator, and versioned manifests with per-file checksums and `dev`/`holdout` splits.
- [ ] 5.2 Add the synthetic page generator and a committed T1 smoke set.
- [ ] 5.3 Add goal-state checkers for application state and artifacts, and add the scripted oracle.
- [ ] 5.4 Require the oracle to solve every scenario before the scenario is accepted.
- [ ] 5.5 Add `.gitignore` entries for run outputs, logs, caches, and downloaded datasets.
- [ ] 5.6 Run the Inspect AI spike, and record the results against the exit criteria in `design.md`.
- [ ] 5.7 Add `requirements-eval.txt`, Inspect tasks and scorers, and a baseline report using the generic `react()` agent. If the spike fails, use the fallback runner instead.

## 6. Closed-Loop Agent Runtime

- [ ] 6.1 Add the `LLMClient` interface with scripted, OpenAI-compatible, and Anthropic adapters that use `requests`.
- [ ] 6.2 Add the `ToolExecutor` interface with in-process and MCP-client implementations.
- [ ] 6.3 Add the plan, act, verify, recover, and report loop, with budgets for steps, tokens, cost, and time.
- [ ] 6.4 Add recovery strategies: retry with backoff, adjust settings, skip and record, or ask the user.
- [ ] 6.5 Generate final reports only from recorded observations, keeping completed, skipped, and failed work separate.
- [ ] 6.6 Add the command-line entry point for running jobs without the GUI.
- [ ] 6.7 Add `InspectLLMClient`, and evaluate the agent on T1–T3 against the oracle and the baseline.

## 7. Scenario Expansion and Gates

- [ ] 7.1 Add T2 failure-recovery scenarios with transient and persistent faults.
- [ ] 7.2 Add T3 ambiguous and risky scenarios, including prompt injection embedded in page text.
- [ ] 7.3 Add the opt-in T4 real-model tier, using license-reviewed pages or pages kept local only.
- [ ] 7.4 Set up the `holdout` split, pass^k reporting, and regression gates against a recorded baseline.
- [ ] 7.5 Compare an external MCP client on the same scenarios.

## 8. Documentation and Handoff

- [ ] 8.1 Document agent usage, the safety policy, MCP setup, and the evaluation commands.
- [ ] 8.2 Update `AGENTS.md` (and `CLAUDE.md`, if it is committed) with the agent and evaluation workflows.
- [ ] 8.3 Propose the in-app agent panel as a follow-up OpenSpec change.
- [ ] 8.4 Run `git diff --check`, both unittest discovery patterns, and a GUI smoke run of `uv run comic.py` to confirm interactive behavior is unchanged.
- [ ] 8.5 Before archiving, write `handoff.md` covering completed work, verification evidence, known issues, and follow-ups.
