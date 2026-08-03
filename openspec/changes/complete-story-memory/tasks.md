## 1. Persistence Foundation

- [x] 1.1 Add focused legacy `.ctpr` load and round-trip fixtures that establish the compatibility baseline before changing project storage.
- [x] 1.2 Add stable project, page, and block UUIDs, preserve block identity through serialization and `TextBlock.deep_copy()`, and test lazy assignment for legacy projects.
- [x] 1.3 Add ordered Story Memory schema migrations and relational tables for metadata, canon, briefs, translation memory, approvals, and import records inside `.ctpr`.
- [x] 1.4 Implement typed Story Memory repository operations with short transactions, per-connection foreign-key enforcement, language-pair scoping, and revision increments.
- [x] 1.5 Verify open, save, Save As, copy, and reopen preserve Story Memory and stable identifiers without depending on source or temporary page paths.
- [x] 1.6 Implement an idempotent legacy sidecar importer that copies only compatible glossary and explicitly approved memory rows, records a fingerprint, and never mutates the sidecar.
- [x] 1.7 Add migration tests proving scaffold machine results and ambiguous unsaved fallback databases are not auto-approved or auto-imported.

## 2. Deterministic Context Assembly

- [x] 2.1 Define framework-independent Story Memory request, match, provenance, and assembled-context models.
- [x] 2.2 Implement language-aware normalization and deterministic active-canon matching with longer-term priority and stable tie ordering.
- [x] 2.3 Implement approved translation-memory retrieval by normalized exact source and language pair, returning conflicting candidates as suggestions.
- [x] 2.4 Implement Story Brief inclusion, deduplication, item/size budgets, deterministic truncation, and distinct prompt sections that preserve user extra context.
- [x] 2.5 Add assembler tests for language isolation, inactive entries, forbidden/untranslatable behavior, conflicts, ordering, budgets, and exclusion of raw prior-page history.
- [ ] 2.6 Add privacy tests proving only matched entries and the configured brief enter `effective_context`, with unmatched memory retained locally.

## 3. Shared Translation and Cache Boundary

- [ ] 3.1 Introduce one shared request-context helper that loads project memory and assembles `effective_context` before invoking the normal `Translator` abstraction.
- [ ] 3.2 Update direct `LLMTranslation` prompt construction to consume structured Story Memory sections while preserving current-page grouping, image context, and user instruction precedence.
- [ ] 3.3 Keep traditional translators operational without prompt injection and expose matched Story Memory as non-binding review suggestions.
- [ ] 3.4 Remove the context workflow's hard-coded Custom translator construction and make any LangGraph nodes adapters over the shared repository, assembler, and translator boundary.
- [ ] 3.5 Extend translation cache identity with project UUID, memory revision, assembler version, language pair, source content, translator configuration, and user extra context.
- [ ] 3.6 Add tests proving matched memory changes the actual direct-LLM prompt, disabled memory preserves current behavior, cache revisions invalidate stale output, and retrieval adds no provider call.

## 4. Draft, Review, and Approval Lifecycle

- [ ] 4.1 Persist machine translation results as draft records associated with stable page/block identifiers and structured match metadata.
- [ ] 4.2 Mark genuine user target edits as pending while distinguishing initialization, rendering, cached updates, undo, and redo from approval-producing actions.
- [ ] 4.3 Implement an atomic page-review service that validates eligible blocks, reports skipped rows, and creates approved memory only after explicit confirmation.
- [ ] 4.4 Implement re-approval supersession, source-text-change handling, and auditable provenance without deleting historical approved rows.
- [ ] 4.5 Implement conflict detection and explicit preference/retain-both resolution for equal normalized source and language pairs.
- [ ] 4.6 Add lifecycle tests covering draft, pending, approved, superseded, empty target, changed OCR source, undo/redo, programmatic updates, and rollback on transaction failure.

## 5. Project-Level Story Memory UI

- [ ] 5.1 Add a project navigation entry and Story Memory panel shell with correct active-project and no-project states.
- [ ] 5.2 Add enablement and bounded Story Brief controls with explicit over-limit validation.
- [ ] 5.3 Add canon table create/edit/activate/deactivate/delete flows for terms, translations, category, behavior, notes, and language pair.
- [ ] 5.4 Add translation-memory inspection with page, language, status, conflict, provenance, and supersession filters.
- [ ] 5.5 Add current-page match and provider-disclosure previews that explain why each canon or memory entry matched.
- [ ] 5.6 Add a page-review action with pre-commit counts, skipped/conflicting details, confirmation, and completion feedback.
- [ ] 5.7 Add focused UI/controller tests and capture a manual screenshot or recording of canon editing, match preview, and page approval.

## 6. Translation Workflow Parity

- [ ] 6.1 Route manual single-page translation through the shared Story Memory boundary and verify it first with memory enabled and disabled.
- [ ] 6.2 Route manual multi-page and regular batch translation through the same boundary without changing worker/thread behavior.
- [ ] 6.3 Route visible-webtoon and webtoon-batch translation through the same boundary without changing page ordering or rendering behavior.
- [ ] 6.4 Redirect the legacy Context Translate action to the shared implementation or remove it only after manual-path parity is demonstrated.
- [ ] 6.5 Add contract tests that exercise identical memory assembly across manual page, multi-page, regular batch, visible webtoon, and webtoon batch entry points.
- [ ] 6.6 Smoke test at least one supported direct LLM configuration and one traditional translator path without modifying account/login or `user.py`.

## 7. Diagnostics, Documentation, and Final Verification

- [ ] 7.1 Bound workflow diagnostic retention and verify cleanup never removes canon, briefs, approvals, or current translation state.
- [ ] 7.2 Document Story Memory enablement, local persistence, provider disclosure, review semantics, sidecar migration, and disabled behavior in user-facing project documentation.
- [ ] 7.3 Run `git diff --check`, all focused Story Memory tests, both repository test-discovery naming patterns, and targeted import smoke checks.
- [ ] 7.4 Manually open a legacy project, save it normally and with Save As, reopen both files, and verify pages plus Story Memory round-trip correctly.
- [ ] 7.5 Smoke run `uv run comic.py` and exercise manual, batch, webtoon, Story Memory management, and explicit page-review workflows.
- [ ] 7.6 Update `handoff.md` with completed work, verification evidence, known issues, migration notes, and concrete follow-up options before verification/archive.
