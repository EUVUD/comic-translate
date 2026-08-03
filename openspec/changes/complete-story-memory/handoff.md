# Story Memory Change Handoff

## Status

Planning is complete. Tasks 1.1 through 2.5 are implemented (12/44); the
remaining work is still apply-ready. Current branch: `feature/story-memory`.
The user-owned `AGENTS.md` guidance update is committed separately; do not
change it while continuing Story Memory work unless asked.

## Completed Work

- Added a pure `ContextAssembler` in
  `modules/translation/context/assembler.py`. It performs local NFKC and
  casefold normalization, removes whitespace only for Chinese, Japanese, and
  Thai aliases, then matches active Canon entries for the exact language pair.
  It retains raw display text, aggregates each matched entry's current-page
  block UUIDs in request order, and orders results by longer normalized term
  followed by stable entry ID without importing Qt, LangGraph, NumPy, or the
  repository implementation.
- Added pure approved translation-memory retrieval to `ContextAssembler`. It
  filters by the exact language pair and `approved` status, re-normalizes raw
  source text with the same language-aware rules as Canon, and requires an
  exact match within each current-page block. It preserves raw display text,
  aggregates matched block UUIDs in page order, and orders candidates by first
  matched block then stable entry ID. Different approved targets for one
  normalized source are all retained and marked as non-binding suggestions;
  stored preferred flags and repository ordering never silently choose one.
- Added immutable `StoryMemoryContextBudget` limits for rendered Story Memory:
  a total character budget plus Brief, Canon, and translation-memory item caps.
  It rejects invalid limits and deliberately excludes the user's existing extra
  translator instructions from truncation.
- Added pure `ContextAssembler.assemble()` to build auditable, distinct user
  instruction, Story Brief, Canon, and approved-example sections without any
  provider, repository, Qt, or LangGraph dependency. It includes only a
  language-pair-matched, non-empty Brief; semantically deduplicates Canon and
  example payloads; truncates only the Brief; and omits lower-priority complete
  entries when the rendered Story Memory budget is exhausted. Conflicting
  translation-memory candidates are budgeted as a whole group, so no prompt
  silently favors one conflicting target over another.
- Added `tests/story_memory_context_assembler_test.py` for Unicode and
  language-aware whitespace behavior, exact language-pair and active filtering,
  per-block provenance, longer-term and stable-ID ordering, word-boundary
  preservation for spaced languages, and prevention of cross-block matches.
- Expanded the assembler tests for approved translation-memory retrieval,
  raw-payload preservation, language/status isolation, exact (not substring or
  cross-block) matching, deterministic conflict suggestions, and harmless
  duplicate targets.
- Expanded context model and assembler tests for immutable budgets, distinct
  rendered sections, Brief language isolation and deterministic truncation,
  semantic deduplication, item limits, preserved user instructions, exclusion
  of unmatched page text, and all-or-nothing conflict-group budgets.
- Added assembly-level boundary tests for complete language-pair isolation,
  active `forbidden` and `untranslatable` Canon behavior, inactive Canon
  exclusion, deterministic Canon and conflicting translation-memory ordering,
  zero and finite memory budgets, preservation of long user instructions, and
  exclusion of raw prior-page history from the rendered context.
- Added framework-independent Story Memory context contracts in
  `modules/translation/context/models.py`. Immutable request, current-page
  source-block, match-reason, entry-provenance, Story Brief, prompt-section,
  and assembled-context values preserve stable IDs, the full language pair,
  original source text, user instructions, and provider-disclosure metadata
  without importing Qt, LangGraph, NumPy, or translator implementations.
- Added a pure `app/projects/story_memory_types.py` home for `LanguagePair`.
  `story_memory_repository` re-exports the same type, so existing callers keep
  their import path while context contracts no longer trigger project parsing or
  PySide imports during lightweight use and test discovery.
- Added `tests/story_memory_context_models_test.py` for immutable request
  identity, duplicate block rejection, match/provenance consistency, sectioned
  disclosure, suggestion flags, and preservation of user extra context.
- Added `tests/story_memory_project_state_test.py`, which creates a legacy v2
  `project_state` fixture and verifies load, current-format save/reopen, and
  save-to-new-file round trips preserve page text, translations, languages, and
  saved LLM extra context.
- Added stable project, page, and `TextBlock` UUIDs. Legacy page/block data
  receives missing IDs during load, project IDs are persisted in `.ctpr` meta,
  and `TextBlock.deep_copy()` preserves logical block identity.
- Added a versioned, savepoint-backed Story Memory schema migration module.
  Version 1 creates metadata, canon, brief, translation record, approved-memory,
  approval-event, and sidecar-import receipt tables plus retrieval indexes.
- Added a typed `StoryMemoryRepository` with immutable language-pair, metadata,
  canon, brief, draft-record, translation-memory, and import-receipt models.
  It reuses the project connection, scopes lookup to both source and target
  languages, and uses short SQLite savepoints for each mutation.
- Configured every project SQLite connection to enable foreign-key enforcement
  before schema initialization or transactions. Context-affecting mutations
  increment `memory_revision` atomically; draft records, reads, no-op updates,
  and import receipts do not.
- Added `tests/story_memory_repository_test.py` for foreign-key enforcement,
  project/language isolation, deterministic normalization, revision behavior,
  idempotent receipts, conflict retention, and rollback on invalid references.
- Save As and recovery saves now carry the source project path through the
  controller into project persistence. SQLite's backup API snapshots the full
  source `.ctpr` before current in-memory page state is written, preserving
  project UUID, Story Memory rows, stable IDs, blobs, and future project tables.
- Save As rebinding now moves lazy blob lookups from the old project container
  to the destination after a successful write and invalidates a replaced target
  cache. Source paths are no longer needed to materialize existing lazy blobs.
- Expanded `tests/story_memory_project_state_test.py` to cover normal save,
  Save As over an unrelated destination, filesystem copy, deletion of the
  source file before reopen, stable page/block IDs, and lazy-blob rebinding.
- Added `app/projects/story_memory_sidecar_import.py` for conservative legacy
  sidecar migration. It resolves only the saved project's
  `<project>.ctmem.sqlite`, opens it with SQLite `mode=ro`, validates the
  legacy table/column shape, matches its project key to the current saved
  `.ctpr`, and hashes the source before recording a receipt.
- Sidecar import requires an explicit `LanguagePair` because the old schema
  does not persist one. It imports compatible glossary rows and only
  `translation_memory.approved = 1` rows; it never derives memory from the
  scaffold's `translations.status = 'final'` machine output. Legacy TM rows
  receive deterministic synthetic page/block UUIDs based on the project UUID,
  sidecar fingerprint, and legacy row ID because their original block identity
  is not durable.
- Added an atomic `StoryMemoryRepository.import_legacy_entries()` operation.
  It claims the source path/fingerprint receipt and inserts all parsed rows in
  one savepoint, increments `memory_revision` once when content changes, and
  rolls back receipt, rows, and revision together on failure or conflict.
- Added sidecar-import tests for project-key isolation, approved-row filtering,
  idempotent repeat imports, incompatible sources, checksum/mtime preservation,
  and atomic rollback of a duplicate-ID import.
- Added migration-safety fixtures using the real legacy
  `ContextTranslationStore`: a scaffold `translations.status = 'final'` row
  remains excluded from approved translation memory while compatible glossary
  data still imports, and a populated `comic_translate_memory.sqlite` fallback
  is neither inspected nor receipted when its saved-project sidecar is absent.
- Created `proposal.md` with the problem statement, scope, capability map, and affected areas.
- Created `design.md` with persistence, identity, retrieval, approval, cache, UI, privacy, migration, and rollback decisions.
- Added the new `story-memory-management` capability specification.
- Added a complete delta specification for the existing `context-aware-translation` capability.
- Created `tasks.md` with dependency-ordered, trackable implementation and verification work.
- Recorded external research supporting bounded page-focused context and a framework-independent long-term memory store.

## Key Decisions

- Story Memory lives inside `.ctpr`; the existing sidecar is a conservative import source, not the durable store.
- Canon, a short Story Brief, and explicitly approved translation memory are distinct data types.
- Stable project, page, and block UUIDs replace paths, geometry, and OCR hashes as durable identity.
- A deterministic `ContextAssembler` supplies only matched, budgeted memory through the normal translator abstraction.
- Machine results are draft, user edits are pending, and only explicit page review creates approved memory.
- Legacy `translation_memory.approved = 1` is the only compatible sidecar
  marker, not durable proof of human review. It may be migrated under the
  legacy compatibility rule, but new Story Memory features must never infer
  approval from it or from `translations.status = 'final'`.
- LangGraph is optional orchestration and does not own Story Memory.
- Account/login behavior and `user.py` are outside the change.

## Verification Status

- After tasks 1.1 and 1.2: `tests.story_memory_project_state_test` passed 3
  tests, and focused `*test.py` discovery passed 7 tests.
- After task 1.3: schema tests passed 3 tests, project compatibility tests
  passed 3 tests, and focused `*test.py` discovery passed 10 tests.
- After task 1.4: repository tests passed 7 tests; schema plus project
  compatibility tests passed 6 tests; focused `*test.py` discovery passed 17
  tests; and `git diff --check` passed.
- After task 1.5: project persistence tests passed 7 tests; focused `*test.py`
  discovery passed 21 tests; project controller/persistence import smoke checks
  and `git diff --check` passed.
- After task 1.6: focused repository/schema/project/sidecar tests passed 20
  tests; focused `*test.py` discovery passed 24 tests; changed files compiled;
  and `git diff --check` passed.
- After task 1.7: focused repository/schema/project/sidecar tests passed 22
  tests; focused `*test.py` discovery passed 26 tests; the changed test
  compiled; and `git diff --check` passed.
- After task 2.1: `tests.story_memory_context_models_test` passed 5 tests;
  focused `*test.py` discovery passed 31 tests; changed modules compiled; and
  `git diff --check` passed. The new model test also passes when discovery has
  installed the existing partial PySide stub, proving it does not depend on the
  project parser or Qt modules.
- After task 2.2: `tests.story_memory_context_assembler_test` passed 6 tests;
  focused `*test.py` discovery passed 37 tests; changed modules compiled; and
  `git diff --check` passed.
- After task 2.3: `tests.story_memory_context_assembler_test` passed 11 tests;
  focused `*test.py` discovery passed 42 tests; changed modules compiled;
  `git diff --check` and `openspec validate complete-story-memory --strict`
  passed.
- After task 2.4: focused context model and assembler tests passed 24 tests;
  focused `*test.py` discovery passed 50 tests; changed modules compiled;
  `git diff --check` and `openspec validate complete-story-memory --strict`
  passed.
- After task 2.5: the assembler test module passed 22 tests; focused
  `*test.py` discovery passed 55 tests; the changed test compiled; `git diff
  --check` and `openspec validate complete-story-memory --strict` passed.
- `uv run python -m unittest tests.story_memory_project_state_test`: passed (2 tests).
- `uv run python -m unittest discover -s tests -p '*test.py'`: passed (6 tests).
- `openspec status --change complete-story-memory --json`: all required planning artifacts report `done`.
- `git diff --check -- openspec/changes/complete-story-memory`: passed after artifact creation.
- GUI smoke checks have not run yet; production persistence code now has focused compatibility coverage.
- `openspec validate complete-story-memory --strict`: passed.

## Known Issues and Follow-up Concerns

- `unify-langgraph-translation-workflow` remains a separate active change with no artifacts; it must not be implemented as a substitute for this change.
- `.ctpr` migration and lazy page-blob behavior are user-data sensitive and require compatibility fixtures before schema edits.
- The repository retains conflicting approved translation-memory candidates;
  the assembler exposes them as non-binding suggestions and never sends only a
  subset of a conflicting group; explicit preference and retain-both resolution
  remains task 4.5.
- Context assembly now renders a bounded, structured `effective_context`, but
  task 3.2 still must add those sections to the real direct-LLM prompt while
  preserving existing page grouping and image context.
- The first budget is character-based so it remains independent of provider
  tokenizers. Provider-specific token accounting is deliberately deferred until
  the shared translator boundary is introduced.
- Legacy sidecars have no persisted language pair and their path fallback for
  unsaved pages is ambiguous. The importer therefore exposes an explicit,
  saved-project-only service; controller/UI detection and any user confirmation
  remain deferred. It never treats `translations.final_translation` as an
  approval signal.
- High-level draft-to-pending-to-approved lifecycle operations remain deferred
  to section 4, so this repository does not create approval events or bypass
  explicit page review.
- The Save As snapshot path is covered with small fixture projects. Manual GUI
  validation with image-bearing projects remains part of final task 7.4.
- The final UI placement and labels need screenshot review during the UI increment.
- FTS5, embeddings, automatic summaries, and TMX/XLIFF interchange are intentionally deferred.

## Concrete Next Steps

1. Implement task 2.6: add privacy tests proving only matched entries and the
   configured Brief enter `effective_context`, while unmatched memory remains
   local.
2. Keep tasks 1.1 through 1.7 as the compatibility and persistence baseline.
3. Implement one coherent task at a time and verify it before moving to the next task.
4. Update this handoff with test evidence, migration observations, known issues, and the next safe task after each completed implementation increment.
