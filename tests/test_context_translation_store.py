import sqlite3
import tempfile
import unittest
from pathlib import Path

from modules.translation.context.store import (
    ContextTranslationStore,
    resolve_sidecar_db_path,
)


class ContextTranslationStoreTests(unittest.TestCase):
    def test_resolves_project_sidecar_path_and_initializes_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "demo.ctpr"
            db_path = resolve_sidecar_db_path(project_file=str(project))

            self.assertEqual(db_path, str(Path(tmp) / "demo.ctmem.sqlite"))

            store = ContextTranslationStore(db_path)
            store.initialize()

            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }

        self.assertIn("text_boxes", tables)
        self.assertIn("workflow_steps", tables)

    def test_upserts_text_box_and_records_workflow_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "memory.sqlite")
            store = ContextTranslationStore(db_path)
            store.initialize()

            project_id = store.upsert_project("demo", "Demo")
            page_id = store.upsert_page(project_id, "/tmp/page.png", 0)
            box_id = store.upsert_text_box(
                page_id,
                "box-1",
                "hello",
                [1, 2, 30, 40],
            )
            step_id = store.record_workflow_step(
                box_id,
                "retrieve_context",
                {"text": "hello"},
                {"context": []},
                "ok",
            )

        self.assertGreater(project_id, 0)
        self.assertGreater(page_id, 0)
        self.assertGreater(box_id, 0)
        self.assertGreater(step_id, 0)


if __name__ == "__main__":
    unittest.main()
