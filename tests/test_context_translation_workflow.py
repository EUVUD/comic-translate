import sqlite3
import tempfile
import unittest
from pathlib import Path

from modules.translation.context.store import ContextTranslationStore
from modules.translation.context.workflow import ContextTranslationWorkflow


class FakeBlock:
    def __init__(self, text, xyxy):
        self.text = text
        self.xyxy = xyxy
        self.translation = ""


class ContextTranslationWorkflowTests(unittest.TestCase):
    def test_translates_page_in_one_call_and_persists_boxes(self):
        calls = []

        def fake_translate(blocks, image, extra_context):
            calls.append([blk.text for blk in blocks])
            for blk in blocks:
                blk.translation = f"tr:{blk.text}"

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "memory.sqlite")
            store = ContextTranslationStore(db_path)
            store.initialize()
            project_id = store.upsert_project("project", "project")
            store.add_glossary_term(project_id, "hello", "bonjour", "greeting")
            workflow = ContextTranslationWorkflow(store, translator_fn=fake_translate)
            blocks = [
                FakeBlock("hello", [0, 0, 10, 10]),
                FakeBlock("world", [0, 12, 10, 22]),
            ]

            workflow.translate_page("project", "/tmp/page.png", blocks, None, "")

            with sqlite3.connect(db_path) as conn:
                step_names = [
                    row[0] for row in conn.execute("SELECT step_name FROM workflow_steps")
                ]
                context_outputs = [
                    row[0]
                    for row in conn.execute(
                        "SELECT output_json FROM workflow_steps WHERE step_name='retrieve_context'"
                    )
                ]
                translations = [
                    row[0] for row in conn.execute("SELECT final_translation FROM translations")
                ]

        self.assertEqual(calls, [["hello", "world"]])
        self.assertEqual([blk.translation for blk in blocks], ["tr:hello", "tr:world"])
        self.assertIn("check_consistency", step_names)
        self.assertIn("save_result", step_names)
        self.assertEqual(translations, ["tr:hello", "tr:world"])
        self.assertTrue(any("bonjour" in value for value in context_outputs))

    def test_context_workflow_uses_custom_translator(self):
        workflow_source = Path(
            "modules/translation/context/workflow.py"
        ).read_text()

        self.assertIn("CustomTranslation", workflow_source)
        self.assertIn('engine.initialize(main_page.settings_page, source_lang, target_lang, "Custom")', workflow_source)
        self.assertNotIn("from modules.translation.processor import Translator", workflow_source)


if __name__ == "__main__":
    unittest.main()
