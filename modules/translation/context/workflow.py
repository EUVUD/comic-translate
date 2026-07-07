from __future__ import annotations

import hashlib
import json


def _block_key(block) -> str:
    bbox = getattr(block, "xyxy", None)
    text = getattr(block, "text", "") or ""
    coords = [int(v) for v in bbox] if bbox is not None else []
    raw = json.dumps({"bbox": coords, "text": text}, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class ContextTranslationWorkflow:
    def __init__(self, store, translator_fn):
        self.store = store
        self.translator_fn = translator_fn

    @classmethod
    def from_existing_translator(cls, store, main_page, source_lang, target_lang):
        def translate(blocks, image, extra_context):
            from modules.translation.llm.custom import CustomTranslation

            engine = CustomTranslation()
            engine.initialize(main_page.settings_page, source_lang, target_lang, "Custom")
            engine.translate(
                blocks,
                image,
                extra_context,
            )

        return cls(store, translate)

    def compile_graph(self):
        from langgraph.graph import END, StateGraph

        graph = StateGraph(dict)
        graph.add_node("retrieve_context", lambda state: state)
        graph.add_node("translate_page", lambda state: state)
        graph.add_node("check_consistency", lambda state: state)
        graph.add_node("save_result", lambda state: state)
        graph.set_entry_point("retrieve_context")
        graph.add_edge("retrieve_context", "translate_page")
        graph.add_edge("translate_page", "check_consistency")
        graph.add_edge("check_consistency", "save_result")
        graph.add_edge("save_result", END)
        return graph.compile()

    def retrieve_context(self, project_id, blocks):
        source_texts = [getattr(block, "text", "") or "" for block in blocks]
        return {
            "glossary": self.store.find_glossary_terms(project_id, source_texts),
            "memory": [],
            "text_count": len(blocks),
        }

    def check_consistency(self, blocks, context):
        return {
            "status": "ok",
            "feedback": "",
            "checked": len(blocks),
            "context_items": len(context.get("glossary", [])) + len(context.get("memory", [])),
        }

    def save_result(self, box_ids, blocks, feedback):
        for box_id, block in zip(box_ids, blocks):
            final = getattr(block, "translation", "") or ""
            self.store.record_translation(box_id, final, feedback.get("feedback", ""), final, "final")
            self.store.record_workflow_step(
                box_id,
                "save_result",
                {"translation": final},
                {"status": "final"},
                "ok",
            )

    def translate_page(self, project_key, page_path, blocks, image, extra_context):
        project_id = self.store.upsert_project(project_key, project_key)
        page_id = self.store.upsert_page(project_id, page_path)
        box_ids = [
            self.store.upsert_text_box(page_id, _block_key(block), block.text, block.xyxy)
            for block in blocks
        ]
        context = self.retrieve_context(project_id, blocks)
        for box_id in box_ids:
            self.store.record_workflow_step(box_id, "retrieve_context", {}, context, "ok")
        self.translator_fn(blocks, image, extra_context)
        feedback = self.check_consistency(blocks, context)
        for box_id in box_ids:
            self.store.record_workflow_step(box_id, "check_consistency", {}, feedback, "ok")
        self.save_result(box_ids, blocks, feedback)
        return blocks


def translate_blocks_with_context(
    db_path,
    project_key,
    page_path,
    main_page,
    source_lang,
    target_lang,
    blocks,
    image,
    extra_context,
):
    from modules.translation.context.store import ContextTranslationStore

    store = ContextTranslationStore(db_path)
    store.initialize()
    workflow = ContextTranslationWorkflow.from_existing_translator(
        store,
        main_page,
        source_lang,
        target_lang,
    )
    return workflow.translate_page(project_key, page_path, blocks, image, extra_context)
