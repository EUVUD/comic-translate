## Why

The existing context-aware translation scaffold records some workflow data, but retrieved memory does not reach translator prompts, approved edits are not captured, and sidecar storage is not stable across project moves or Save As. Comic Translate needs a local, project-scoped Story Memory that consistently preserves names, terminology, story context, and approved human choices across pages and translation workflows.

## What Changes

- Add a project-level Story Memory containing canon/glossary entries, a short Story Brief, and approved translation-memory entries scoped by source and target language.
- Persist Story Memory inside the `.ctpr` project container with schema versioning, stable identifiers, migration support, and lifecycle-safe Save As/copy behavior.
- Add a bounded, deterministic context assembler that selects only glossary matches, a short brief, and relevant approved translations, then supplies that context to the normal translator abstraction without an extra model call.
- Integrate Story Memory with manual page, multi-page, regular batch, and webtoon translation paths for direct LLM translators; keep non-LLM translators functional and expose applicable memory as review suggestions rather than prompt context.
- Add a project-level Story Memory panel for editing canon and the Story Brief, inspecting translation memory, and resolving conflicting or superseded entries.
- Add an explicit page-review action so machine output remains draft, user edits become pending, and only reviewed translations become reusable approved memory.
- Include `memory_revision` in translation cache identity so changes to Story Memory cannot reuse stale cached output.
- Replace the hard-coded Custom translator dependency in the context workflow with the existing translator interfaces. LangGraph remains an optional orchestration detail rather than the Story Memory storage boundary.
- Keep account/login behavior, `user.py`, cloud synchronization, and server-backed memory outside this change.

## Capabilities

### New Capabilities

- `story-memory-management`: Project-local creation, persistence, review, approval, conflict handling, and UI management of canon, Story Brief, and approved translation memory.

### Modified Capabilities

- `context-aware-translation`: Make retrieved Story Memory affect real translation prompts and apply consistently across supported manual, batch, and webtoon workflows instead of remaining an isolated sidecar scaffold.

## Impact

- Project persistence: `app/projects/project_state_v2.py`, project save/load/Save As flows, and backward-compatible `.ctpr` schema migration.
- Translation data: stable page/block identity and `TextBlock` serialization/deep-copy behavior.
- Translation orchestration: `modules/translation/context/`, normal `Translator`/`LLMTranslation` paths, manual and batch controllers, and webtoon batch processing.
- User interface: a project-scoped Story Memory panel and an explicit page-review/approval action.
- Caching and privacy: memory-aware cache invalidation and prompt assembly that sends only the matched project subset to the configured translator.
- Tests: persistence compatibility, retrieval and prompt effects, approval lifecycle, cache invalidation, and parity across translation entry points.
- No new account, login, remote database, embedding, or cloud-service dependency is introduced.
