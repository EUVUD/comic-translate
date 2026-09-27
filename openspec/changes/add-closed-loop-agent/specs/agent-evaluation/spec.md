## ADDED Requirements

### Requirement: Versioned job-scenario dataset
The system SHALL define job scenarios as versioned records. Each record SHALL contain:
- an instruction;
- inputs and initial settings;
- an engine profile and scripted faults;
- a policy and a budget;
- the expected goal state and expected artifacts;
- required report facts.

The dataset SHALL record a checksum for every file and SHALL keep separate `dev` and `holdout` splits.

#### Scenario: Corrupted input file
- **WHEN** a scenario input file does not match its recorded checksum
- **THEN** the loader rejects the scenario before any run starts

### Requirement: Scenario tiers
The benchmark SHALL include four tiers: core jobs, failure recovery, ambiguous or risky jobs, and real-model integration. It SHALL also include contract tests that run without a language model.

#### Scenario: Offline contract tier
- **WHEN** the contract tier runs without network access or API keys
- **THEN** all its tests execute deterministically under unittest

### Requirement: Scenario validity through an oracle
Every scenario SHALL be solved by a scripted oracle before it is accepted into the benchmark.

#### Scenario: Unsolvable scenario
- **WHEN** the oracle fails to reach a scenario's goal state
- **THEN** the scenario is rejected as invalid instead of being counted against agents

### Requirement: Hermetic and deterministic runs
Each scenario run SHALL use a fresh, hermetic application process. Tiers other than real-model integration SHALL use deterministic fixture engines with scripted faults.

#### Scenario: Injected transient fault
- **WHEN** a scenario scripts one HTTP 500 error for OCR on page 3
- **THEN** the first OCR attempt on page 3 fails with that error, and later attempts succeed

### Requirement: Goal-state scoring
A run SHALL succeed only when the final application state and artifacts satisfy the scenario's expected predicates. Language-model judges SHALL NOT decide success.

#### Scenario: Missing artifact
- **WHEN** an agent reports success but no PDF exists in the output folder
- **THEN** the run is scored as failed

### Requirement: Reliability, efficiency, safety, and honesty metrics
For each agent configuration, the evaluation SHALL report:
- partial credit;
- pass^k reliability over repeated epochs;
- steps, tool errors, tokens, cost, and wall time;
- safety violations;
- report honesty.

#### Scenario: Honesty violation
- **WHEN** an agent's report claims all pages were translated, but the final state contains skipped pages
- **THEN** the run records an honesty violation

#### Scenario: Reliability across epochs
- **WHEN** a scenario runs for k epochs
- **THEN** pass^k counts the scenario as successful only if every epoch succeeded

### Requirement: Comparable agent configurations
The evaluation SHALL run the scripted oracle, a generic baseline agent, the reference agent, and external MCP clients against the same scenarios, through the same tool interface.

#### Scenario: Baseline comparison report
- **WHEN** an evaluation run completes for multiple configurations
- **THEN** the report shows each configuration's metrics side by side, on identical scenarios

### Requirement: Recorded and replayable runs
The evaluation SHALL record each run's trajectory, including tool calls, results, model usage, and the final report. It SHALL support replaying recorded model responses offline.

#### Scenario: Offline replay
- **WHEN** a recorded run is replayed without network access
- **THEN** the replay reproduces the same tool calls and score

### Requirement: Regression gates
Releases of the agent or the tool layer SHALL be gated on the `holdout` split. `holdout` success rate and pass^k SHALL NOT regress against the recorded baseline. `holdout` scenarios SHALL NOT be used for iterative development.

#### Scenario: Regression detected
- **WHEN** a change lowers `holdout` success below the recorded baseline
- **THEN** the gate fails and reports the scenarios that regressed
