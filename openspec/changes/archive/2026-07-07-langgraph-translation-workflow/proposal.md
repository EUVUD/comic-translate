## Why

The current translation flow sends page text to a translator in a mostly opaque one-shot call, which makes cross-page consistency, debugging, and reuse of human corrections difficult. A context-aware workflow is needed so character names, glossary terms, tone, and approved edits can persist across pages.

## What Changes

- Introduce a separate LangGraph-based translation workflow that can run alongside the existing translator path.
- Add project-level translation memory storage using a sidecar SQLite database first, with a repository boundary that can later support PostgreSQL.
- Record per-text-box workflow state, including OCR text, retrieved context, model output, checker feedback, final translation, status, and step traces.
- Support glossary terms, character/style context, previous approved translations, and human-edited translations as retrieval sources.
- Keep the existing translation pipeline intact while exposing the new workflow behind a separate function or flag.
- Defer optional vector retrieval until after the SQL-backed retrieval path is stable.

## Capabilities

### New Capabilities

- `context-aware-translation`: Defines the new inspectable translation workflow, persistent translation memory, glossary/history retrieval, and human edit reuse behavior.

### Modified Capabilities

- None.

## Impact

- Affects `modules/translation/`, `pipeline/`, and future UI/controller integration points for choosing the new workflow.
- Adds a sidecar SQLite persistence layer for translation workflow data.
- Adds a LangGraph dependency or compatibility wrapper for graph execution.
- Requires focused validation of manual translation paths before any batch replacement.
