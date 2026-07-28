from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from app.projects.project_state_v2 import close_cached_connection, get_project_connection
from app.projects.story_memory_repository import (
    CanonEntryUpdate,
    DraftTranslationRecord,
    LanguagePair,
    NewCanonEntry,
    NewImportReceipt,
    NewStoryBrief,
    NewTranslationMemoryEntry,
    StoryMemoryRepository,
)


class StoryMemoryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._project_paths: list[Path] = []

    def tearDown(self) -> None:
        for project_path in self._project_paths:
            close_cached_connection(str(project_path))
        self._temporary_directory.cleanup()

    def make_repository(self, name: str = "story-memory.ctpr") -> StoryMemoryRepository:
        project_path = Path(self._temporary_directory.name) / name
        self._project_paths.append(project_path)
        return StoryMemoryRepository.for_project_file(str(project_path))

    @staticmethod
    def make_uuid() -> str:
        return str(uuid.uuid4())

    def test_repository_initializes_project_metadata_and_foreign_keys(self):
        repository = self.make_repository()

        metadata = repository.get_metadata()
        self.assertEqual(str(uuid.UUID(metadata.project_uuid)), metadata.project_uuid)
        self.assertFalse(metadata.enabled)
        self.assertEqual(metadata.memory_revision, 0)

        conn, conn_lock = get_project_connection(repository.project_file)
        with conn_lock:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_canon_and_brief_round_trip_are_scoped_to_full_language_pair(self):
        repository = self.make_repository()
        japanese_to_english = LanguagePair("Japanese", "English")
        japanese_to_chinese = LanguagePair("Japanese", "Chinese")

        english_canon = repository.create_canon(
            NewCanonEntry(japanese_to_english, "太郎", "Taro")
        )
        chinese_canon = repository.create_canon(
            NewCanonEntry(japanese_to_chinese, "太郎", "太郎")
        )
        english_brief = repository.upsert_brief(
            NewStoryBrief(japanese_to_english, "A school comedy.")
        )
        chinese_brief = repository.upsert_brief(
            NewStoryBrief(japanese_to_chinese, "校园喜剧。")
        )

        self.assertEqual(
            [entry.id for entry in repository.list_canon(japanese_to_english)],
            [english_canon.id],
        )
        self.assertEqual(
            [entry.id for entry in repository.list_canon(japanese_to_chinese)],
            [chinese_canon.id],
        )
        self.assertEqual(repository.get_brief(japanese_to_english), english_brief)
        self.assertEqual(repository.get_brief(japanese_to_chinese), chinese_brief)
        self.assertEqual(repository.list_canon(LanguagePair("Korean", "English")), [])
        self.assertIsNone(repository.get_brief(LanguagePair("Korean", "English")))

    def test_context_affecting_mutations_increment_revision_once(self):
        repository = self.make_repository()
        language_pair = LanguagePair("Japanese", "English")

        canon = repository.create_canon(
            NewCanonEntry(language_pair, "太郎", "Taro", notes="lead")
        )
        self.assertEqual(repository.get_metadata().memory_revision, 1)

        repository.update_canon(
            canon.id,
            CanonEntryUpdate(language_pair, "太郎", "Taro", notes="lead"),
        )
        self.assertEqual(repository.get_metadata().memory_revision, 1)

        repository.update_canon(
            canon.id,
            CanonEntryUpdate(language_pair, "太郎", "Taro", notes="main character"),
        )
        self.assertEqual(repository.get_metadata().memory_revision, 2)

        repository.upsert_brief(NewStoryBrief(language_pair, "A school comedy."))
        self.assertEqual(repository.get_metadata().memory_revision, 3)

        repository.create_draft_record(
            DraftTranslationRecord(
                language_pair,
                self.make_uuid(),
                self.make_uuid(),
                "太郎だ",
                model_translation="It's Taro.",
                current_translation="It's Taro.",
                matched_entry_ids=(canon.id,),
            )
        )
        self.assertEqual(repository.get_metadata().memory_revision, 3)

        repository.set_enabled(True)
        self.assertEqual(repository.get_metadata().memory_revision, 4)

        repository.list_canon(language_pair)
        repository.get_brief(language_pair)
        self.assertEqual(repository.get_metadata().memory_revision, 4)

    def test_invalid_translation_memory_reference_rolls_back_row_and_revision(self):
        repository = self.make_repository()
        language_pair = LanguagePair("Japanese", "English")

        with self.assertRaises(sqlite3.IntegrityError):
            repository.create_translation_memory(
                NewTranslationMemoryEntry(
                    language_pair,
                    self.make_uuid(),
                    self.make_uuid(),
                    "太郎",
                    "Taro",
                    record_id=self.make_uuid(),
                )
            )

        self.assertEqual(repository.list_translation_memory(language_pair), [])
        self.assertEqual(repository.get_metadata().memory_revision, 0)

    def test_failed_canon_insert_rolls_back_the_revision(self):
        repository = self.make_repository()
        language_pair = LanguagePair("Japanese", "English")
        entry_id = self.make_uuid()
        repository.create_canon(
            NewCanonEntry(language_pair, "太郎", "Taro", entry_id=entry_id)
        )
        revision_before_failure = repository.get_metadata().memory_revision

        with self.assertRaises(sqlite3.IntegrityError):
            repository.create_canon(
                NewCanonEntry(language_pair, "花子", "Hanako", entry_id=entry_id)
            )

        self.assertEqual(repository.get_metadata().memory_revision, revision_before_failure)
        self.assertEqual(len(repository.list_canon(language_pair)), 1)

    def test_translation_memory_lookup_is_pair_scoped_and_keeps_conflicts(self):
        repository = self.make_repository()
        japanese_to_english = LanguagePair("Japanese", "English")
        japanese_to_chinese = LanguagePair("Japanese", "Chinese")

        first = repository.create_translation_memory(
            NewTranslationMemoryEntry(
                japanese_to_english,
                self.make_uuid(),
                self.make_uuid(),
                " 太郎　",
                "Taro",
            )
        )
        second = repository.create_translation_memory(
            NewTranslationMemoryEntry(
                japanese_to_english,
                self.make_uuid(),
                self.make_uuid(),
                "太郎",
                "Tarou",
            )
        )
        repository.create_translation_memory(
            NewTranslationMemoryEntry(
                japanese_to_chinese,
                self.make_uuid(),
                self.make_uuid(),
                "太郎",
                "太郎",
            )
        )

        english_matches = repository.list_translation_memory(
            japanese_to_english,
            normalized_source_text="太郎",
        )
        self.assertEqual({entry.id for entry in english_matches}, {first.id, second.id})
        self.assertEqual({entry.target_text for entry in english_matches}, {"Taro", "Tarou"})
        self.assertEqual(
            [entry.target_text for entry in repository.list_translation_memory(japanese_to_chinese)],
            ["太郎"],
        )

    def test_import_receipt_is_idempotent_and_does_not_change_revision(self):
        repository = self.make_repository()
        receipt = repository.record_import_receipt(
            NewImportReceipt("/tmp/legacy.ctmem.sqlite", "fixture-fingerprint", 3, 2)
        )
        repeated = repository.record_import_receipt(
            NewImportReceipt("/tmp/legacy.ctmem.sqlite", "fixture-fingerprint", 99, 99)
        )

        self.assertEqual(repeated, receipt)
        self.assertEqual(receipt.canon_entries_imported, 3)
        self.assertEqual(receipt.translation_memory_imported, 2)
        self.assertEqual(repository.get_metadata().memory_revision, 0)

    def test_legacy_entry_import_is_atomic_idempotent_and_increments_revision_once(self):
        repository = self.make_repository()
        language_pair = LanguagePair("Japanese", "English")
        source_path = "/tmp/legacy.ctmem.sqlite"
        failed_fingerprint = "failed-import"
        duplicate_id = self.make_uuid()

        with self.assertRaises(sqlite3.IntegrityError):
            repository.import_legacy_entries(
                source_path=source_path,
                source_fingerprint=failed_fingerprint,
                canon_entries=(
                    NewCanonEntry(language_pair, "太郎", "Taro", entry_id=duplicate_id),
                    NewCanonEntry(language_pair, "花子", "Hanako", entry_id=duplicate_id),
                ),
            )

        self.assertEqual(repository.list_canon(language_pair), [])
        self.assertIsNone(repository.get_import_receipt(source_path, failed_fingerprint))
        self.assertEqual(repository.get_metadata().memory_revision, 0)

        imported = repository.import_legacy_entries(
            source_path=source_path,
            source_fingerprint="successful-import",
            canon_entries=(NewCanonEntry(language_pair, "太郎", "Taro"),),
            translation_memory_entries=(
                NewTranslationMemoryEntry(
                    language_pair,
                    self.make_uuid(),
                    self.make_uuid(),
                    "太郎です",
                    "I am Taro.",
                    origin="legacy_sidecar_import",
                ),
            ),
        )

        self.assertTrue(imported.imported)
        self.assertEqual(imported.receipt.canon_entries_imported, 1)
        self.assertEqual(imported.receipt.translation_memory_imported, 1)
        self.assertEqual(repository.get_metadata().memory_revision, 1)

        repeated = repository.import_legacy_entries(
            source_path=source_path,
            source_fingerprint="successful-import",
            canon_entries=(NewCanonEntry(language_pair, "花子", "Hanako"),),
        )

        self.assertFalse(repeated.imported)
        self.assertEqual(repeated.receipt, imported.receipt)
        self.assertEqual(len(repository.list_canon(language_pair)), 1)
        self.assertEqual(len(repository.list_translation_memory(language_pair)), 1)
        self.assertEqual(repository.get_metadata().memory_revision, 1)


if __name__ == "__main__":
    unittest.main()
