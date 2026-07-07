## 1. Branch and Dependency Setup

- [x] 1.1 Create or switch to branch `feature/langgraph-translation-workflow`.
- [x] 1.2 Add the minimal LangGraph dependency entry and keep imports localized to the new workflow module.
- [x] 1.3 Confirm the existing app still imports without invoking LangGraph on startup.

## 2. Sidecar Persistence

- [x] 2.1 Add a small sidecar SQLite path resolver for translation workflow data.
- [x] 2.2 Add schema initialization for `projects`, `pages`, `text_boxes`, `translations`, `glossary_terms`, `translation_memory`, and `workflow_steps`.
- [x] 2.3 Add repository methods for upserting page/text-box rows and recording workflow steps.

## 3. LangGraph Workflow

- [x] 3.1 Add a context-aware workflow service with nodes `retrieve_context`, `translate_page`, `check_consistency`, and `save_result`.
- [x] 3.2 Reuse the existing `Translator` engine inside `translate_page` so all page text boxes are translated in one scoped call.
- [x] 3.3 Store retrieved context, page model output, checker feedback, final translations, and status for each processed text box.

## 4. Opt-in Pipeline Integration

- [x] 4.1 Add a separate pipeline method that translates current OCR `TextBlock` entries through the new workflow.
- [x] 4.2 Keep existing manual and batch translation behavior unchanged unless the new method is explicitly called.
- [x] 4.3 Document the new workflow entry point and sidecar database behavior.

## 5. Verification

- [x] 5.1 Run focused import checks for the new modules.
- [x] 5.2 Smoke test the old translation path remains callable.
- [x] 5.3 Smoke test the new workflow on a small synthetic `TextBlock` list with a temporary sidecar database.
