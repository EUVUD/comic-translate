## ADDED Requirements

### Requirement: Typed application actions
The system SHALL provide typed actions that operate a live application session through the same controller code paths the GUI uses. The actions SHALL cover loading inputs, opening projects, configuring languages and tools, translating pages, retrying skipped pages, editing block translations, saving projects, and exporting outputs.

#### Scenario: Agent loads an archive
- **WHEN** a client invokes the load action with a CBZ file path inside the allowed roots
- **THEN** the session loads the archive through the existing image-loading path
- **AND** it returns the resulting page count and any files that could not be loaded

#### Scenario: Canonical names at the boundary
- **WHEN** a client sets the target language to a canonical English language name while the interface language is not English
- **THEN** the session selects the corresponding localized option and reports the canonical name back

### Requirement: Read-only observations
The system SHALL provide read-only observations of application state, pages, page blocks, the latest batch report, effective settings, output artifacts, and page previews. Observations SHALL NOT modify the session.

#### Scenario: Batch report after skipped pages
- **WHEN** a batch translation finishes with skipped pages
- **THEN** the batch-report observation returns each skipped page with its reason, along with the completed and skipped counts

### Requirement: Postconditions and structured results
Every action SHALL verify its postconditions and SHALL return a structured result containing status, relevant state changes, warnings, and errors.

#### Scenario: Export postcondition
- **WHEN** a PDF export completes
- **THEN** the result confirms that the output file exists and reports its page count

#### Scenario: Action failure
- **WHEN** an action fails because of an engine or file error
- **THEN** the result reports a structured error with the failing stage and the affected pages, instead of raising an unhandled exception

### Requirement: GUI-thread execution
The system SHALL execute every action and observation on the GUI thread, whichever thread the call comes from. It SHALL run long-running work through the existing worker helpers.

#### Scenario: Call from a worker thread
- **WHEN** an agent running on a worker thread invokes an action
- **THEN** the action runs on the GUI thread and its result is delivered back to the calling thread

### Requirement: Job handles for long-running work
The system SHALL represent translation, save, and export operations as jobs, each with an identifier, status, progress, and results. Jobs SHALL resolve from the application's existing completion signals and callbacks.

#### Scenario: Waiting for a batch job
- **WHEN** a client starts translation for all pages and waits on the returned job
- **THEN** the job resolves after batch processing finishes, and its result includes the completed and skipped page counts

### Requirement: Interaction policy for modal prompts
The system SHALL route modal prompts through an interaction policy.
- In GUI mode, the policy SHALL preserve current dialog behavior.
- In agent mode, the policy SHALL record each prompt as a structured event and answer it without blocking the event loop.

#### Scenario: Error dialog in agent mode
- **WHEN** an operation reports an error that would open a modal error dialog
- **THEN** the session records the error as an event and returns it to the agent as a tool error
- **AND** no dialog opens

#### Scenario: Unchanged interactive behavior
- **WHEN** a user runs the application without agent mode
- **THEN** every existing dialog appears and behaves as before

#### Scenario: Destructive default refused
- **WHEN** a prompt in agent mode would discard unsaved work and no pre-authorized answer exists
- **THEN** the policy selects the non-destructive option and reports the prompt to the agent

### Requirement: Hermetic sessions
The system SHALL support hermetic sessions that isolate application settings, account credentials, input and output files, and autosave locations from the user's environment.

#### Scenario: User settings untouched
- **WHEN** a hermetic session changes the translator and the target language
- **THEN** the user's persisted application settings are unchanged after the session ends

#### Scenario: No account credits
- **WHEN** a hermetic session starts on a machine where the user is signed in
- **THEN** the session cannot access the user's account token and cannot spend account credits

### Requirement: State snapshots
The system SHALL write a machine-readable state snapshot after every mutating action and when the session ends.

#### Scenario: Scoring after process exit
- **WHEN** a session process exits after completing a job
- **THEN** the latest snapshot describes the final pages, translations, skipped pages, settings, and artifacts
