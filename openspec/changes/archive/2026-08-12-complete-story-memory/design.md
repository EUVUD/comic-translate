## Context

Comic Translate already has an opt-in context workflow, a sidecar SQLite store, and a LangGraph-shaped service. The current implementation is only a scaffold: memory retrieval returns no translation-memory entries, retrieved context is not added to the translator prompt, consistency checking is a stub, machine output is immediately stored as final, and the path is hard-coded to the Custom translator. Manual, batch, and webtoon translation still use the normal translator path without Story Memory.

The sidecar is keyed by project and temporary page paths and identifies blocks from mutable geometry and OCR text. That makes memory vulnerable to project moves, Save As, temporary extraction paths, OCR corrections, and box adjustments. In contrast, `.ctpr` is already a SQLite project container and is the durable unit copied by project lifecycle operations.

This is a local PySide6 desktop application. The design must preserve existing projects, keep long-running translation work off the GUI thread, avoid account/login dependencies, and avoid sending an entire project history to a translation provider. Research on manga translation supports page-level text plus image context, but does not show a reliable benefit from continually expanding prior-page context; therefore Story Memory supplies a short brief and matched facts rather than raw chapter history. LangGraph documentation also distinguishes thread checkpoints from application-level long-term storage, so graph persistence is not used as the Story Memory database.

References:

- [Context-Informed Machine Translation of Manga](https://aclanthology.org/2025.coling-main.232.pdf)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [XLIFF 2.1](https://docs.oasis-open.org/xliff/xliff-core/v2.1/xliff-core-v2.1.html)

## Goals / Non-Goals

**Goals:**

- Make canon, a short Story Brief, and explicitly approved translations durable project data.
- Feed a bounded, deterministic selection of that data into real direct-LLM translation prompts.
- Use one repository and one context assembler across manual page, multi-page, batch, and webtoon translation.
- Establish a deliberate draft-to-approval lifecycle that cannot be triggered by ordinary typing, undo/redo, rendering, or cached output.
- Preserve `.ctpr` compatibility and keep project moves, Save As, and copies self-contained.
- Keep current translation behavior available when Story Memory is disabled.
- Provide focused tests for data migration, prompt effects, review state, cache identity, and workflow parity.

**Non-Goals:**

- Account/login changes, `user.py`, remote synchronization, team sharing, or a server database.
- Automatic fact extraction, automatic story summarization, or additional LLM calls in the first version.
- Embedding/vector retrieval, semantic search infrastructure, or unbounded chapter-history prompts.
- Replacing the translator abstraction or forcing prompt context into traditional non-LLM engines.
- TMX/XLIFF interchange in the first implementation; the schema keeps enough language and provenance metadata to add it later.

## Decisions

### 1. Store Story Memory inside `.ctpr`

Add versioned relational Story Memory tables to the existing project container rather than extending the sidecar:

- project memory metadata, including a stable project UUID, schema version, enabled flag, assembler version, and monotonically increasing `memory_revision`;
- canon entries with stable UUID, language pair, source term, preferred translation, category, behavior (`preferred`, `forbidden`, or `untranslatable`), notes, status, and timestamps;
- one short Story Brief per language pair with revision metadata;
- translation-memory entries with stable UUIDs, page/block references, source and target text, language pair, status, origin, approval metadata, and optional supersession linkage.

Stable page and block UUIDs are stored with project data. A block UUID becomes part of `TextBlock` serialization and must also be preserved by deep-copy operations. Paths, bounding boxes, and source-text hashes remain useful lookup attributes but are not durable identity.

The project persistence layer owns schema creation and ordered migrations. Repository operations use transactions and enable connection-local SQLite constraints on every opened connection. Story Memory repository code does not query or mutate page blobs directly.

Alternatives considered:

- **Keep the sidecar:** rejected because the sidecar is not reliably renamed, copied, or found with its project and can collide for unsaved projects.
- **Use LangGraph checkpoints:** rejected as the data boundary because checkpoints represent execution/thread state, not durable project canon.
- **Use a new remote database:** rejected because the project is local-first and the change explicitly excludes accounts and cloud storage.

### 2. Import legacy sidecar data conservatively

On first eligible project load, the migration service may detect the legacy `<project>.ctmem.sqlite` file and offer/import only compatible glossary rows and explicitly approved translation-memory rows. Machine translations stored as `final` by the scaffold are not treated as human-approved memory. The import records the source fingerprint and completion marker inside `.ctpr`, never deletes or rewrites the sidecar, and is idempotent.

Unsaved-project fallback databases are not imported automatically because their ownership is ambiguous. They can be handled by a later explicit import tool if needed.

### 3. Separate repository, context assembly, translation, and orchestration

The architecture has four boundaries:

```text
StoryMemoryRepository (.ctpr)
  canon / brief / approved TM / revision
                    |
                    v
ContextAssembler (match / rank / budget / format)
                    |
                    v
Translator / LLMTranslation (effective context + current page)
                    |
                    v
draft -> user edit -> page review -> approved memory
```

`StoryMemoryRepository` provides typed persistence operations and revision updates. `ContextAssembler` is a pure service that receives project identity, source/target languages, current page blocks, and the user's existing extra context. It returns both formatted `effective_context` and structured match metadata for UI/debugging.

The normal `Translator` abstraction remains the only translation-engine boundary. Direct LLM implementations consume `effective_context`; traditional engines continue translating normally and can display relevant memory as non-binding review suggestions.

LangGraph may orchestrate retrieve/translate/check/save when its interrupt, retry, or tracing features are actually used, but graph nodes call the same repository and assembler. The core feature must also work without a separate LangGraph execution path.

### 4. Use bounded deterministic retrieval first

The first assembler uses no embeddings and makes no model call:

1. Normalize current-page source text without discarding original text.
2. Match active canon entries by normalized literal/substring match, preferring longer terms and deterministic UUID order for ties.
3. Retrieve approved translation-memory candidates for the same language pair by normalized exact source match. Conflicting candidates remain suggestions until resolved.
4. Add the Story Brief only when non-empty.
5. Deduplicate entries, preserve explicit user extra context, and truncate Story Memory sections to configured item and character/token budgets.
6. Return only the matched subset and structured provenance.

The prompt format uses distinct sections for user instructions, Story Brief, canon constraints, approved examples, and current-page text. User instructions retain highest precedence. Full previous pages and workflow traces are never appended.

FTS5 trigram candidate retrieval can later expand recall while keeping local storage, followed by deterministic Python ranking. It is deferred until exact-match behavior has correctness and performance benchmarks.

### 5. Make approval explicit and page-scoped

Translation state follows this lifecycle:

```text
machine result: draft
user changes target text: pending
explicit "Review page" action: approved
later approval for the same identity/language pair: prior entry superseded
```

Programmatic text updates, initial rendering, cache replay, undo, and redo never create approved memory. The review action snapshots current source and target text for eligible blocks, records the reviewer action locally, and updates all rows atomically. Empty targets, unchanged OCR-only blocks, and unresolved conflicts are skipped or reported rather than silently approved.

If source text changes after approval, the prior memory remains auditable but no longer attaches to the block as its current approval. If a new approval conflicts with an existing normalized source/language pair, the UI requires the user to select the preferred entry or retain both as suggestions.

### 6. Integrate once at the shared translation boundary

Introduce a request-level context object or equivalent shared helper so every translation entry point obtains the same `effective_context` before invoking an engine. Manual single-page integration is implemented and verified first, followed by manual multi-page, regular batch, visible webtoon, and webtoon batch paths.

The existing Context Translate UI entry is redirected to the shared implementation or retired only after parity is proven. No path instantiates Custom directly. Story Memory is project-level opt-in; when disabled or unavailable, existing translator behavior and user-provided extra context remain unchanged.

Translation cache identity includes project UUID, source/target language, `memory_revision`, assembler version, translator configuration, source content, and user extra context. Any canon, brief, approval, supersession, or conflict-resolution mutation increments `memory_revision`.

### 7. Use a project-scoped management and review UI

Add a Story Memory panel beside other project navigation tools rather than global settings. It provides:

- Story Memory enable/disable state and a bounded Story Brief editor;
- canon table CRUD with category, behavior, languages, translation, notes, and active status;
- translation-memory inspection filtered by language, page, status, and conflict state;
- conflict resolution and supersession visibility;
- the matched subset for the current page, including why each entry matched.

A separate page-review action displays how many blocks will be approved and any skipped/conflicting items before committing. Long-running migration or bulk operations use the application's existing worker/thread patterns; ordinary table edits remain on the GUI thread.

### 8. Keep privacy and diagnostics explicit

Story Memory remains inside the local project unless the user invokes a translator. For direct LLM engines, only the bounded matched subset is sent as part of the translation prompt. The UI states this behavior. Workflow traces are diagnostic data with bounded retention and are not considered reusable Story Memory.

Structured assembler metadata records entry IDs and match reasons without duplicating secrets into unbounded logs. Logging must not emit API keys or full project memory.

## Risks / Trade-offs

- **`.ctpr` compatibility regression** → Add fixture tests for older projects, round-trip tests for new tables/UUIDs, and Save As/copy tests before UI rollout.
- **Stable IDs missing during legacy load** → Assign UUIDs lazily in memory and persist them on the next normal save without changing visual content.
- **Low-quality edits pollute memory** → Require explicit page review; never learn from keystrokes, cache replay, or automatic output.
- **Short comic lines produce ambiguous exact matches** → Treat conflicting TM rows as suggestions and require resolution instead of blindly replacing target text.
- **Prompt growth increases cost or degrades translation** → Enforce deterministic budgets, prefer page context, and never append full history.
- **Different entry points drift** → Use one assembler/helper and add contract tests for every manual, batch, and webtoon call path.
- **Stale cache hides memory changes** → Include revision and assembler version in cache identity.
- **Sidecar import misclassifies machine output** → Import only explicit glossary and approved-memory records; keep the source untouched and report counts.
- **SQLite locking during save/translation** → Use short transactions, existing project save coordination, and no database work on shared long-lived GUI connections.
- **LangGraph dependency shapes the domain model** → Keep repository and lifecycle services framework-independent; graph nodes remain adapters.

## Migration Plan

1. Add stable identifiers, Story Memory schema creation, migration versioning, and backward-compatible project round-trip tests.
2. Add the repository, deterministic assembler, cache revisioning, and legacy sidecar importer behind a project-level disabled-by-default flag.
3. Wire manual single-page translation through the shared context boundary and verify that matched entries alter direct-LLM prompts without additional model calls.
4. Add canon/brief/TM management UI and explicit page review; keep the old context entry available until functional parity is verified.
5. Integrate multi-page, regular batch, visible webtoon, and webtoon batch paths with shared contract tests.
6. Redirect or remove the legacy isolated workflow entry and bound diagnostic trace retention.

Rollback disables Story Memory use while leaving its additional tables and IDs intact. Existing translation continues through the normal path, and the legacy sidecar remains untouched. No downgrade step deletes approved memory.

## Open Questions

- Final UI labels and panel placement should be confirmed during the first UI increment with a screenshot, without changing the domain contract.
- TMX/XLIFF or JSON interchange can be proposed separately after the internal schema and approval semantics stabilize.
- FTS5 candidate retrieval should be added only if exact matching misses materially useful approved entries in a representative comic benchmark.
