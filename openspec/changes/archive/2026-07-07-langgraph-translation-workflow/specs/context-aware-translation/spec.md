## ADDED Requirements

### Requirement: Opt-in LangGraph translation workflow
The system SHALL provide a separate opt-in page-level translation workflow that translates a page's existing OCR `TextBlock` entries together without removing the current translation pipeline.

#### Scenario: Existing pipeline remains available
- **WHEN** context-aware translation is not enabled for a page
- **THEN** the system uses the existing translation path unchanged

### Requirement: Per-text-box workflow records
The system SHALL persist per-text-box translation records containing OCR text, retrieved context, model translation, checker feedback, final translation, status, and workflow step trace data.

#### Scenario: Text box translated through workflow
- **WHEN** a text box is processed by the context-aware workflow
- **THEN** the sidecar database contains a durable record for the text box and each workflow step

### Requirement: Context retrieval before translation
The system SHALL retrieve relevant glossary terms, character or style context, and approved translation memory before generating the page-level model translation.

#### Scenario: Glossary term matches OCR text
- **WHEN** OCR text contains a stored glossary term
- **THEN** the retrieved context provided to translation includes that glossary entry

### Requirement: Approved human edits become reusable memory
The system SHALL persist approved human-edited translations as translation memory for future context retrieval.

#### Scenario: User approves edited translation
- **WHEN** a user marks an edited translation as approved
- **THEN** later workflow runs can retrieve that edit as prior approved translation context
