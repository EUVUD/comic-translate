## ADDED Requirements

### Requirement: Project-scoped Story Memory
The system SHALL maintain Story Memory as project-scoped data containing canon entries, a bounded Story Brief, and approved translation-memory entries separated by source and target language.

#### Scenario: Two projects use different terminology
- **WHEN** two projects contain different preferred translations for the same source term
- **THEN** each project retrieves only its own Story Memory entry

#### Scenario: Language pair changes
- **WHEN** the user translates a project with a different source or target language
- **THEN** the system uses only canon, brief, and translation-memory data applicable to that language pair

### Requirement: Durable project-container persistence
The system SHALL persist Story Memory, its schema version, and stable project, page, block, and entry identifiers inside the `.ctpr` project container.

#### Scenario: Existing project is upgraded
- **WHEN** a project created before Story Memory support is opened
- **THEN** the system initializes the current Story Memory schema without changing existing page content or translation output

#### Scenario: Project is saved as a new file
- **WHEN** the user performs Save As on a project containing Story Memory
- **THEN** the new `.ctpr` contains the same Story Memory and stable identifiers without requiring the original project path

#### Scenario: Text block is deep-copied
- **WHEN** a `TextBlock` is copied by an application workflow that preserves its logical identity
- **THEN** the copy preserves the block identifier used to associate review and memory records

### Requirement: Versioned and constrained storage
The system SHALL apply ordered, idempotent Story Memory schema migrations and SHALL enable SQLite integrity constraints for every repository connection that mutates Story Memory.

#### Scenario: Migration runs more than once
- **WHEN** the same project is opened repeatedly after a Story Memory schema upgrade
- **THEN** the migration completes without duplicating tables, entries, or import records

#### Scenario: Invalid referenced entry is written
- **WHEN** a repository operation attempts to persist a translation-memory row for a nonexistent project identity
- **THEN** the transaction fails without leaving a partial Story Memory update

### Requirement: Canon management
The system SHALL provide a project-level UI for creating, editing, activating, deactivating, and deleting canon entries with source term, preferred translation, category, behavior, notes, and language-pair metadata.

#### Scenario: Preferred character name is created
- **WHEN** the user adds an active preferred canon entry for a character name
- **THEN** the entry is persisted and becomes eligible for matching on later pages in the same language pair

#### Scenario: Forbidden translation is deactivated
- **WHEN** the user deactivates a forbidden canon entry
- **THEN** the entry remains inspectable but is excluded from subsequent context assembly

#### Scenario: Current-page match is inspected
- **WHEN** the user views Story Memory for the current page
- **THEN** the UI shows each matched canon entry and the reason it matched

### Requirement: Story Brief management
The system SHALL provide one user-editable, bounded Story Brief per project language pair and SHALL not automatically append raw prior-page text to it.

#### Scenario: User edits a Story Brief
- **WHEN** the user saves a Story Brief within the configured size limit
- **THEN** the brief becomes eligible for later context assembly for that language pair

#### Scenario: Story Brief exceeds the limit
- **WHEN** the user attempts to save a Story Brief beyond the configured limit
- **THEN** the UI prevents or explicitly confirms truncation and does not silently discard text

### Requirement: Explicit translation approval lifecycle
The system SHALL represent machine translation as `draft`, user-edited translation as `pending`, explicitly reviewed translation as `approved`, and replaced approved translation as `superseded`.

#### Scenario: Machine translation completes
- **WHEN** a translator returns target text for a block
- **THEN** the system records the result as draft and does not make it reusable translation memory

#### Scenario: User edits target text
- **WHEN** the user changes a draft or approved target through the text editor
- **THEN** the current block becomes pending without creating an approved memory entry

#### Scenario: User reviews a page
- **WHEN** the user confirms the page-review action
- **THEN** eligible pending translations are atomically recorded as approved translation memory

#### Scenario: Programmatic or history-driven update occurs
- **WHEN** target text changes because of rendering, cache replay, initialization, undo, or redo
- **THEN** the system does not automatically approve or create reusable translation memory

### Requirement: Approval validation and conflicts
The system SHALL validate page approvals and SHALL expose ambiguous or conflicting approved translations for explicit resolution rather than silently choosing one.

#### Scenario: Empty target is reviewed
- **WHEN** a page review includes a block with empty target text
- **THEN** the system skips that block and reports why it was not approved

#### Scenario: Current block is re-approved
- **WHEN** a changed translation for the same stable block and language pair is approved
- **THEN** the prior approved entry is marked superseded and the new entry becomes current

#### Scenario: Same source has conflicting approved targets
- **WHEN** multiple active approved entries normalize to the same source text and language pair
- **THEN** the system presents them as conflicting suggestions until the user selects a preferred entry or retains both explicitly

### Requirement: Memory revision
The system SHALL maintain a monotonically increasing `memory_revision` and increment it whenever a mutation can change assembled translation context.

#### Scenario: Canon entry changes
- **WHEN** an active canon entry is added, edited, deactivated, or deleted
- **THEN** the project memory revision increases

#### Scenario: Memory is only inspected
- **WHEN** the user reads or filters Story Memory without mutating it
- **THEN** the project memory revision remains unchanged

### Requirement: Conservative legacy sidecar import
The system SHALL provide an idempotent migration path for compatible legacy glossary and explicitly approved translation-memory data while leaving the source sidecar unchanged.

#### Scenario: Eligible sidecar is imported
- **WHEN** a saved project has a matching legacy sidecar that has not previously been imported
- **THEN** compatible glossary and explicitly approved memory rows are imported once and the import fingerprint is recorded

#### Scenario: Scaffold machine result is encountered
- **WHEN** the sidecar contains a machine translation marked final without explicit human approval
- **THEN** the system does not import that translation as approved memory

#### Scenario: Unsaved fallback database is found
- **WHEN** a fallback sidecar cannot be associated unambiguously with one project
- **THEN** the system does not import it automatically

### Requirement: Project-level Story Memory controls
The system SHALL expose Story Memory enablement, canon, Story Brief, translation-memory inspection, conflict status, and current-page matches from a project-scoped panel rather than global account settings.

#### Scenario: Story Memory panel opens
- **WHEN** a project is active and the user opens the Story Memory panel
- **THEN** the panel displays data from that project only

#### Scenario: No project is active
- **WHEN** the user opens the Story Memory area without an active project
- **THEN** mutation controls are disabled and no unrelated project memory is shown
