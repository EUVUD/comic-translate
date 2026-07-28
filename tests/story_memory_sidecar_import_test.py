from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.projects.project_state_v2 import close_cached_connection
from app.projects.story_memory_repository import LanguagePair, StoryMemoryRepository
from app.projects.story_memory_sidecar_import import import_legacy_sidecar
from modules.translation.context.store import (
    ContextTranslationStore,
    resolve_sidecar_db_path,
)


_LEGACY_SCHEMA = """
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    name TEXT
);
CREATE TABLE glossary_terms (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    notes TEXT
);
CREATE TABLE translation_memory (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    target_text TEXT NOT NULL,
    approved INTEGER DEFAULT 1
);
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StoryMemorySidecarImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.project_path = Path(self._temporary_directory.name) / "story.ctpr"
        self.repository = StoryMemoryRepository.for_project_file(str(self.project_path))
        self.repository.get_metadata()
        self.language_pair = LanguagePair("Japanese", "English")
        self.sidecar_path = Path(
            resolve_sidecar_db_path(project_file=str(self.project_path))
        )

    def tearDown(self) -> None:
        close_cached_connection(str(self.project_path))
        self._temporary_directory.cleanup()

    def write_legacy_sidecar(self) -> None:
        with sqlite3.connect(self.sidecar_path) as conn:
            conn.executescript(_LEGACY_SCHEMA)
            conn.execute(
                "INSERT INTO projects(id, key, name) VALUES(?, ?, ?)",
                (1, str(self.project_path), "Current project"),
            )
            conn.execute(
                "INSERT INTO projects(id, key, name) VALUES(?, ?, ?)",
                (2, str(self.project_path.with_name("other.ctpr")), "Other project"),
            )
            conn.executemany(
                """
                INSERT INTO glossary_terms(project_id, source_term, target_term, notes)
                VALUES(?, ?, ?, ?)
                """,
                [
                    (1, "太郎", "Taro", "Main character"),
                    (1, "花子", "Hanako", None),
                    (2, "太郎", "Wrong project", "Must not import"),
                ],
            )
            conn.executemany(
                """
                INSERT INTO translation_memory(
                    project_id, source_text, target_text, approved
                ) VALUES(?, ?, ?, ?)
                """,
                [
                    (1, "太郎です", "I am Taro.", 1),
                    (1, "花子です", "I am Hanako.", 0),
                    (2, "太郎です", "Wrong project", 1),
                ],
            )

    def test_imports_matching_glossary_and_approved_memory_once_without_writing_source(self):
        self.write_legacy_sidecar()
        fingerprint_before = _sha256(self.sidecar_path)
        mtime_before = os.stat(self.sidecar_path).st_mtime_ns

        imported = import_legacy_sidecar(self.repository, self.language_pair)

        self.assertEqual(imported.status, "imported")
        self.assertEqual(imported.source_fingerprint, fingerprint_before)
        self.assertEqual(imported.canon_entries_imported, 2)
        self.assertEqual(imported.translation_memory_imported, 1)
        self.assertIsNotNone(imported.receipt)
        self.assertEqual(
            {
                (entry.source_term, entry.target_term, entry.category, entry.notes)
                for entry in self.repository.list_canon(self.language_pair)
            },
            {
                ("太郎", "Taro", "legacy_glossary", "Main character"),
                ("花子", "Hanako", "legacy_glossary", ""),
            },
        )
        memory_entries = self.repository.list_translation_memory(self.language_pair)
        self.assertEqual(
            [(entry.source_text, entry.target_text, entry.origin) for entry in memory_entries],
            [("太郎です", "I am Taro.", "legacy_sidecar_import")],
        )
        self.assertEqual(self.repository.get_metadata().memory_revision, 1)
        self.assertEqual(_sha256(self.sidecar_path), fingerprint_before)
        self.assertEqual(os.stat(self.sidecar_path).st_mtime_ns, mtime_before)

        repeated = import_legacy_sidecar(self.repository, self.language_pair)

        self.assertEqual(repeated.status, "already_imported")
        self.assertEqual(repeated.receipt, imported.receipt)
        self.assertEqual(len(self.repository.list_canon(self.language_pair)), 2)
        self.assertEqual(len(self.repository.list_translation_memory(self.language_pair)), 1)
        self.assertEqual(self.repository.get_metadata().memory_revision, 1)
        self.assertEqual(_sha256(self.sidecar_path), fingerprint_before)

    def test_incompatible_sidecar_is_not_receipted_or_mutated(self):
        with sqlite3.connect(self.sidecar_path) as conn:
            conn.execute("CREATE TABLE projects(id INTEGER PRIMARY KEY, key TEXT NOT NULL)")
            conn.execute("INSERT INTO projects(id, key) VALUES(?, ?)", (1, str(self.project_path)))
        fingerprint_before = _sha256(self.sidecar_path)

        result = import_legacy_sidecar(self.repository, self.language_pair)

        self.assertEqual(result.status, "incompatible_sidecar")
        self.assertIsNone(
            self.repository.get_import_receipt(
                os.path.realpath(self.sidecar_path),
                fingerprint_before,
            )
        )
        self.assertEqual(self.repository.get_metadata().memory_revision, 0)
        self.assertEqual(_sha256(self.sidecar_path), fingerprint_before)

    def test_scaffold_final_translation_is_not_imported_as_approved_memory(self):
        store = ContextTranslationStore(str(self.sidecar_path))
        store.initialize()
        project_id = store.upsert_project(str(self.project_path), "Current project")
        page_id = store.upsert_page(project_id, "legacy-page.png")
        text_box_id = store.upsert_text_box(page_id, "box-1", "太郎です")
        store.add_glossary_term(project_id, "太郎", "Taro", "Main character")
        store.record_translation(
            text_box_id,
            "I am Taro.",
            final_translation="I am Taro.",
            status="final",
        )
        fingerprint_before = _sha256(self.sidecar_path)
        mtime_before = os.stat(self.sidecar_path).st_mtime_ns

        result = import_legacy_sidecar(self.repository, self.language_pair)

        self.assertEqual(result.status, "imported")
        self.assertEqual(result.canon_entries_imported, 1)
        self.assertEqual(result.translation_memory_imported, 0)
        self.assertIsNotNone(result.receipt)
        self.assertEqual(result.receipt.translation_memory_imported, 0)
        self.assertEqual(
            [
                (entry.source_term, entry.target_term)
                for entry in self.repository.list_canon(self.language_pair)
            ],
            [("太郎", "Taro")],
        )
        self.assertEqual(self.repository.list_translation_memory(self.language_pair), [])
        self.assertEqual(self.repository.get_metadata().memory_revision, 1)
        self.assertEqual(_sha256(self.sidecar_path), fingerprint_before)
        self.assertEqual(os.stat(self.sidecar_path).st_mtime_ns, mtime_before)

    def test_ambiguous_unsaved_fallback_sidecar_is_not_auto_imported(self):
        first_page_path = Path(self._temporary_directory.name) / "page-one.png"
        second_page_path = Path(self._temporary_directory.name) / "page-two.png"
        fallback_path = Path(resolve_sidecar_db_path(page_path=str(first_page_path)))
        self.assertEqual(
            fallback_path,
            Path(resolve_sidecar_db_path(page_path=str(second_page_path))),
        )
        self.assertFalse(self.sidecar_path.exists())

        store = ContextTranslationStore(str(fallback_path))
        store.initialize()
        project_id = store.upsert_project(str(self.project_path), "Ambiguous fallback")
        store.add_glossary_term(project_id, "太郎", "Taro")
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO translation_memory(project_id, source_text, target_text, approved)
                VALUES(?, ?, ?, ?)
                """,
                (project_id, "太郎です", "I am Taro.", 1),
            )
        fingerprint_before = _sha256(fallback_path)
        mtime_before = os.stat(fallback_path).st_mtime_ns

        result = import_legacy_sidecar(self.repository, self.language_pair)

        self.assertEqual(result.status, "sidecar_not_found")
        self.assertEqual(result.sidecar_path, os.path.realpath(self.sidecar_path))
        self.assertIsNone(result.source_fingerprint)
        self.assertIsNone(result.receipt)
        self.assertEqual(result.canon_entries_imported, 0)
        self.assertEqual(result.translation_memory_imported, 0)
        self.assertEqual(self.repository.list_canon(self.language_pair), [])
        self.assertEqual(self.repository.list_translation_memory(self.language_pair), [])
        self.assertEqual(self.repository.get_metadata().memory_revision, 0)
        self.assertIsNone(
            self.repository.get_import_receipt(
                os.path.realpath(fallback_path),
                fingerprint_before,
            )
        )
        self.assertFalse(self.sidecar_path.exists())
        self.assertEqual(_sha256(fallback_path), fingerprint_before)
        self.assertEqual(os.stat(fallback_path).st_mtime_ns, mtime_before)


if __name__ == "__main__":
    unittest.main()
