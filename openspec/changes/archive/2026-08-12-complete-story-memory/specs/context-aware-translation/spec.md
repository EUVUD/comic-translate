## MODIFIED Requirements

### Requirement: Opt-in LangGraph translation workflow
The system SHALL provide project-level opt-in Story Memory through the normal translation boundary for manual page, manual multi-page, regular batch, visible webtoon, and webtoon batch workflows without removing the current translation behavior. LangGraph MAY orchestrate a workflow but SHALL NOT be required to persist or retrieve Story Memory.

#### Scenario: Existing pipeline remains available
- **WHEN** Story Memory is disabled or unavailable for a project
- **THEN** the system uses the existing translation behavior with the user's original extra context

#### Scenario: Story Memory is enabled for manual translation
- **WHEN** the user translates an OCR-complete page with Story Memory enabled
- **THEN** the normal translator path receives assembled Story Memory context for that page

#### Scenario: Story Memory is enabled for batch translation
- **WHEN** regular batch or webtoon batch translation processes pages with Story Memory enabled
- **THEN** each page uses the same context-assembly contract as manual translation

#### Scenario: LangGraph orchestration is not invoked
- **WHEN** a supported translation path calls the normal translator without starting a graph
- **THEN** enabled Story Memory still affects that translation

### Requirement: Per-text-box workflow records
The system SHALL persist per-text-box translation state inside the `.ctpr` project container using stable project, page, and block identifiers. Records SHALL include source text, matched Story Memory entry identifiers, model translation, optional checker feedback, current target, review status, and bounded diagnostic trace references.

#### Scenario: Text box is translated through a supported workflow
- **WHEN** a text box is processed with Story Memory enabled
- **THEN** the project contains a durable draft record associated with the stable block identifier and matched context metadata

#### Scenario: Diagnostic retention limit is reached
- **WHEN** workflow diagnostics exceed the configured retention limit
- **THEN** the system removes or compacts the oldest trace data without deleting canon, Story Brief, or approved translation memory

### Requirement: Context retrieval before translation
The system SHALL retrieve applicable canon, the bounded Story Brief, and relevant approved translation memory before a direct-LLM translation call, assemble them deterministically within a configured budget, and include the resulting `effective_context` in the actual model prompt.

#### Scenario: Glossary term matches OCR text
- **WHEN** current-page OCR text contains an active canon source term for the selected language pair
- **THEN** the prompt includes that canon entry and the structured match result identifies why it was selected

#### Scenario: Approved source text matches
- **WHEN** current-page source text has an approved exact normalized translation-memory match for the selected language pair
- **THEN** the approved source-target pair is supplied as a translation example

#### Scenario: Context exceeds the budget
- **WHEN** all applicable Story Memory entries cannot fit within the configured context budget
- **THEN** the assembler deterministically selects the highest-priority entries and does not append raw full-page history

#### Scenario: User extra context is present
- **WHEN** the user supplied translator instructions in the existing extra-context field
- **THEN** those instructions are preserved as a distinct highest-priority section of `effective_context`

#### Scenario: Traditional translator is selected
- **WHEN** the active translator cannot consume LLM prompt context
- **THEN** translation still runs and matched Story Memory is available as non-binding review suggestions

### Requirement: Approved human edits become reusable memory
The system SHALL make only explicitly page-reviewed human translations reusable as approved translation memory and SHALL preserve their language pair, provenance, stable block association, and supersession state.

#### Scenario: User approves edited translation
- **WHEN** the user confirms page review for an eligible pending translation
- **THEN** later workflow runs can retrieve that approved edit for the same language pair

#### Scenario: User types without reviewing
- **WHEN** the user edits a translation but does not confirm page review
- **THEN** later workflow runs do not retrieve that pending edit as approved memory

#### Scenario: Approved source changes
- **WHEN** OCR source text changes after its translation was approved
- **THEN** the prior entry remains auditable but is not treated as the current approval for that block

## ADDED Requirements

### Requirement: Shared translator abstraction
The system SHALL assemble Story Memory before invoking the existing translator abstraction and SHALL NOT hard-code the Custom translator or any account-backed translator.

#### Scenario: Direct LLM translator is selected
- **WHEN** the selected translator is any supported direct LLM implementation
- **THEN** the implementation receives the same structured Story Memory sections through the shared translator boundary

#### Scenario: Translation engine changes
- **WHEN** the user switches between supported direct LLM translators
- **THEN** Story Memory behavior does not depend on a Custom-only workflow class

### Requirement: No additional model call for retrieval
The first Story Memory implementation SHALL perform context matching, ranking, budgeting, and formatting locally without making an additional LLM or embedding request.

#### Scenario: Context is assembled
- **WHEN** Story Memory is enabled for a page
- **THEN** the number of translation-provider calls is not increased solely to retrieve or summarize Story Memory

### Requirement: Memory-aware translation cache
The system SHALL include project identity, `memory_revision`, assembler version, source and target language, source content, translator configuration, and user extra context in cached translation identity.

#### Scenario: Story Memory changes
- **WHEN** a context-affecting Story Memory mutation increments `memory_revision`
- **THEN** a subsequent translation does not reuse output cached under the prior revision

#### Scenario: Story Memory is unchanged
- **WHEN** all cache identity inputs remain unchanged
- **THEN** the existing translation cache remains eligible for reuse

### Requirement: Bounded provider disclosure
The system SHALL send only the assembled matched Story Memory subset to a direct LLM provider and SHALL keep unmatched canon, unrelated language pairs, full translation-memory history, and workflow traces local.

#### Scenario: Page matches one canon entry
- **WHEN** a project contains many canon and translation-memory entries but the current page matches only one active canon entry
- **THEN** only that matched entry and any configured Story Brief are included in Story Memory prompt sections

#### Scenario: User inspects disclosure
- **WHEN** the UI displays current-page Story Memory matches
- **THEN** the user can identify which entries are eligible to be sent with the next direct-LLM translation

### Requirement: Current-page context remains primary
The system SHALL preserve the translator's current-page text grouping and available image context while adding Story Memory, and SHALL NOT replace them with unbounded prior-page text.

#### Scenario: Page is translated with visual context support
- **WHEN** the selected translator accepts the current page image
- **THEN** the page image and grouped current-page text remain available alongside bounded Story Memory

#### Scenario: Project contains many prior pages
- **WHEN** Story Memory is assembled late in a long project
- **THEN** raw text from all prior pages is not appended to the translation prompt
