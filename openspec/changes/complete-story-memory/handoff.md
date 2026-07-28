# Story Memory Change Handoff

## Status

Planning is complete. Tasks 1.1 through 1.7 are implemented (7/44); the
remaining work is still apply-ready. Current branch: `feature/story-memory`.
The user-owned `AGENTS.md` guidance update is committed separately; do not
change it while continuing Story Memory work unless asked.

## Completed Work

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
  deterministic matching and explicit conflict resolution remain tasks 2.3 and
  4.5 rather than being silently selected here.
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

1. Implement task 2.1: define framework-independent Story Memory request,
   match, provenance, and assembled-context models.
2. Keep tasks 1.1 through 1.7 as the compatibility and persistence baseline.
3. Implement one coherent task at a time and verify it before moving to the next task.
4. Update this handoff with test evidence, migration observations, known issues, and the next safe task after each completed implementation increment.
