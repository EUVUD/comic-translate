## Why

Every job in Comic Translate still needs a person to drive the GUI and interpret what it shows: loading inputs, choosing languages and tools, running translation, checking skipped pages, retrying, saving, and exporting. No AI can operate the application programmatically and verify the results. No agent closes the loop between acting and checking outcomes. No benchmark measures whether such an agent completes jobs correctly, recovers from failures, and reports honestly.

This change sets the architecture for three things:
- a closed-loop agent that operates the app from natural-language jobs;
- an MCP interface that lets external AI clients use the same capabilities;
- an evaluation framework, with a dataset of job scenarios, that measures both.

## What Changes

- Add an App Action and Observation API that operates a live `ComicTranslate` instance. It provides typed actions with postcondition checks, job handles for long-running work, state snapshots, dispatch onto the GUI thread, and an interaction policy that turns blocking modal prompts into structured events when running in agent mode.
- Add a tool registry shared by every agent client. It holds JSON schemas and safety annotations (read-only, destructive, spends credits, long-running), and every call passes through a policy gate.
- Add a closed-loop agent runtime built from scratch, with no agent framework or LangGraph dependency.
  - The loop is: plan → act → verify → recover → report.
  - LLM adapters are provider-agnostic: OpenAI-compatible and Anthropic, plus a scripted adapter for tests.
  - Budgets cap each run, and the final report is built only from recorded observations.
- Add a thin MCP stdio server that exposes the same tool registry to external AI clients.
- Add an evaluation framework with these parts:
  - a versioned job-scenario dataset with four tiers: core jobs, failure recovery, ambiguous or risky jobs, and real-model integration;
  - a fresh, isolated app environment for each scenario;
  - deterministic fixture engines with fault injection;
  - checkers that compare the final state against the expected goal state;
  - a scripted oracle that proves each scenario is solvable;
  - Inspect AI as the run and log layer for tiers that call a model.
- Add a command-line entry point for running agent jobs without the GUI. An in-app agent panel is deferred to a follow-up change.
- Keep normal GUI behavior unchanged. The new dependencies (`mcp`, `inspect-ai`) are optional and are never imported during normal application startup.

## Capabilities

### New Capabilities

- `app-automation-api`: Typed, verifiable actions and observations over a live application session, executed on the GUI thread. Includes job handles, state snapshots, the interaction policy, and hermetic environments.
- `agent-runtime`: The closed-loop agent built from scratch, with its tool registry and policy gate, LLM adapters, budgets, recovery behavior, reports grounded in observations, and the command-line entry point.
- `agent-mcp-server`: The MCP stdio server that exposes the shared tool registry to external AI clients under the same safety policy.
- `agent-evaluation`: The job-scenario dataset, fixture engines and fault injection, goal-state scoring, reliability and safety metrics, runners, and regression gates.

### Modified Capabilities

- None. `context-aware-translation` behavior is reused unchanged: translation started by the agent goes through the existing translation paths, and therefore through the Story Memory context boundary.

## Impact

- New top-level packages `agent/` and `evals/`, and new unittest modules under `tests/` that follow the `*_test.py` naming convention.
- Small seams in existing code:
  - Modal prompt call sites consult an injected interaction policy. These are in `app/ui/messages.py`, `app/ui/main_window/builders/nav.py`, `controller.py`, `app/controllers/projects.py`, the startup screen, and the settings dialogs.
  - The detection, OCR, and translation factories consult an engine-override registry that only evaluation profiles populate.
- Optional dependency files `requirements-agent.txt` (`mcp`) and `requirements-eval.txt` (`inspect-ai`). The base `requirements.txt` is unchanged.
- Evaluation runs never touch the user's settings, keyring, account credits, or autosave folders.
- `.gitignore` gains entries for evaluation run outputs, logs, caches, and downloaded datasets when the evaluation milestone begins.
- No change to `.ctpr` project format, account/login behavior, or server-side APIs.
