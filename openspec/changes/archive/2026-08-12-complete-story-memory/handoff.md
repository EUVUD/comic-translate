# Story Memory follow-up handoff

## Intent

The delivered Story Memory MWE is being archived.  Do not reopen this change
for the remaining product work; create focused follow-up OpenSpec changes so
approval lifecycle, management UI, and acceptance work can evolve separately.

The user has validated that a manually maintained Story Brief is useful as a
translation rule.  Preserve the existing model: project-scoped, language-pair
scoped, bounded, and manually edited.

## Delivered baseline

- The MWE is implemented by commits `1c4a092`, `d0e9d8d`, and `1726d38` on
  `feature/story-memory`.
- It persists Story Memory in the active `.ctpr`, exposes an enablement and
  Story Brief dialog, and injects matched bounded memory through normal LLM
  translation paths.  See `design.md`, `tasks.md`, and the delta specs in this
  archived change for the detailed contract.
- Custom API use is intentionally account-independent when its local API key,
  endpoint, and model are configured.  The localized “自定义” label is also
  normalized before validation; see `modules/utils/pipeline_config.py` and the
  two authentication-fix commits above.
- Latest verified baseline before archive: `uv run --locked python -m unittest
  discover -s tests -p '*_test.py'` (77 tests) and `uv run --locked python -m
  unittest discover -s tests -p 'test_*.py'` (7 tests).

## Recommended follow-up changes

1. `story-memory-approval-lifecycle`
   - Carry tasks 4.1–4.6: draft, pending, explicit page review, approved and
     superseded records, conflict resolution, and lifecycle tests.
2. `story-memory-management-ui`
   - Carry tasks 5.1 and 5.3–5.7: project panel, Canon CRUD, translation
     memory browsing, provider-disclosure preview, page-review UI, and visual
     verification.
3. `story-memory-translation-contracts`
   - Carry tasks 3.2–3.4 and 6.5–6.6: structured prompt boundary refinement,
     review suggestions for traditional translators, legacy LangGraph adapter
     work, uniform route contracts, and real-provider smoke coverage.
4. `story-memory-operations-and-acceptance`
   - Carry tasks 7.1–7.5: diagnostic retention, user documentation, legacy
     project Save/Save As validation, and end-to-end GUI acceptance.

Keep each change independently reviewable.  Do not automatically convert
machine output into reusable memory; only an explicit human-review flow may do
that.

## Spec and migration notes

- The old delta specs are deliberately **not synced** into `openspec/specs/`.
  They describe the broader product scope above, much of which is not yet
  implemented.  Each follow-up change should create a narrow delta spec from
  its own accepted scope.
- `.ctpr` storage, stable project/page/block IDs, and legacy sidecar import are
  user-data-sensitive.  Read `design.md` and existing persistence tests before
  changing them.
- The normal translation paths—not the legacy `.ctmem.sqlite` sidecar—are the
  authoritative Story Memory route.

## Read first

- `openspec/changes/archive/2026-08-12-complete-story-memory/design.md`
- `openspec/changes/archive/2026-08-12-complete-story-memory/tasks.md`
- `openspec/changes/archive/2026-08-12-complete-story-memory/specs/`
- `modules/translation/context/request_context.py`
- `pipeline/story_memory_context.py`
- `app/ui/story_memory_dialog.py`
- `tests/story_memory_*_test.py`

## Suggested skills

- `openspec-new-change` to create each follow-up change.
- `openspec-explore` before deciding approval and conflict UX.
- `openspec-apply-change` for implementation within a chosen follow-up.
- `search-first` for new integrations or dependencies.
- `solid` for test-first implementation and boundary design.
- `openspec-verify-change` before archiving any follow-up change.
