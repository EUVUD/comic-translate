## Context

Comic Translate currently keeps translation state in `TextBlock` objects and page `image_states`, then calls a translator engine from manual and batch pipeline paths. Project persistence already uses SQLite inside `.ctpr`, but that database is a project container with msgpack page blobs rather than an inspectable translation-memory schema. The first step should add a parallel workflow path and avoid changing default rendering, inpainting, or project-file compatibility.

## Goals / Non-Goals

**Goals:**
- Add a small LangGraph-backed workflow boundary for page-level translation.
- Store workflow data in a sidecar SQLite database next to the project or source images.
- Preserve the existing translator path and expose the new workflow behind a separate function or flag.
- Make each workflow step inspectable and durable enough for later debugging and human-edit reuse.

**Non-Goals:**
- Replace batch translation in the first implementation step.
- Add vector retrieval, PostgreSQL, or pgvector immediately.
- Build full UI management for glossary or translation memory in this change.

## Decisions

- Use sidecar SQLite first. This keeps `.ctpr` compatibility safe and gives us relational tables for `projects`, `pages`, `text_boxes`, `translations`, `glossary_terms`, `translation_memory`, and `workflow_steps`.
- Add a repository/service layer instead of querying SQLite from graph nodes. This keeps LangGraph nodes small and leaves room for PostgreSQL later.
- Run the initial graph per page, translating all page text boxes together so correlated dialogue stays in scope and API call count remains close to the current pipeline.
- Route only an opt-in/manual function through the new workflow first. Existing `TranslationHandler.translate_image` and batch paths remain usable while the new path matures.

## Risks / Trade-offs

- Checker or rewrite nodes could add calls later -> start with one page-level translation call and non-LLM consistency checks where possible.
- LangGraph may not be installed in existing environments -> add dependency explicitly and keep imports localized.
- Sidecar DB path selection can be confusing -> centralize path resolution and document it.
- Human edits may not map cleanly back to boxes after geometry changes -> key records by page path plus stable geometry/source-text fingerprint.
