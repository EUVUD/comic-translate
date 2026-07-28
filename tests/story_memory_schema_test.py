from __future__ import annotations

import sqlite3
import unittest

from app.projects.project_state_v2 import _init_schema
from app.projects.story_memory_schema import (
    STORY_MEMORY_SCHEMA_VERSION,
    STORY_MEMORY_SCHEMA_VERSION_KEY,
    initialize_story_memory_schema,
)


EXPECTED_TABLES = {
    "story_memory_metadata",
    "story_memory_canon_entries",
    "story_memory_briefs",
    "story_memory_translation_records",
    "story_memory_translation_memory",
    "story_memory_approval_events",
    "story_memory_import_receipts",
}


class StoryMemorySchemaTests(unittest.TestCase):
    def test_project_schema_initialization_adds_story_memory_tables(self):
        with sqlite3.connect(":memory:") as conn:
            _init_schema(conn)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue(EXPECTED_TABLES.issubset(tables))
            self.assertEqual(
                conn.execute(
                    "SELECT value FROM meta WHERE key = ?",
                    (STORY_MEMORY_SCHEMA_VERSION_KEY,),
                ).fetchone()[0],
                str(STORY_MEMORY_SCHEMA_VERSION),
            )
            self.assertEqual(
                conn.execute(
                    "SELECT enabled, memory_revision, assembler_version "
                    "FROM story_memory_metadata WHERE id = 1"
                ).fetchone(),
                (0, 0, 1),
            )
            self.assertTrue(
                conn.execute(
                    "PRAGMA foreign_key_list(story_memory_translation_memory)"
                ).fetchall()
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_migrations_are_idempotent_and_keep_existing_page_rows(self):
        with sqlite3.connect(":memory:") as conn:
            conn.execute(
                "CREATE TABLE page_state(page_path TEXT PRIMARY KEY, row_blob BLOB NOT NULL)"
            )
            conn.execute(
                "INSERT INTO page_state(page_path, row_blob) VALUES(?, ?)",
                ("legacy-page.png", b"legacy-row"),
            )

            self.assertEqual(initialize_story_memory_schema(conn), 1)
            self.assertEqual(initialize_story_memory_schema(conn), 1)
            self.assertEqual(
                conn.execute("SELECT row_blob FROM page_state").fetchone()[0],
                b"legacy-row",
            )
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_newer_schema_version_is_rejected_without_schema_mutation(self):
        with sqlite3.connect(":memory:") as conn:
            conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?)",
                (STORY_MEMORY_SCHEMA_VERSION_KEY, str(STORY_MEMORY_SCHEMA_VERSION + 1)),
            )

            with self.assertRaisesRegex(ValueError, "newer Story Memory schema"):
                initialize_story_memory_schema(conn)

            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'story_memory_metadata'"
                ).fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
