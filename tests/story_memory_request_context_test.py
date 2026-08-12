from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from app.projects.project_state_v2 import close_cached_connection
from app.projects.story_memory_repository import (
    LanguagePair,
    NewCanonEntry,
    NewStoryBrief,
    NewTranslationMemoryEntry,
    StoryMemoryRepository,
)
from modules.translation.context.request_context import StoryMemoryRequestContextService


@dataclass(frozen=True, slots=True)
class _Block:
    block_uuid: str
    text: str


class StoryMemoryRequestContextServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._project_path = Path(self._temporary_directory.name) / "story-memory.ctpr"
        self.repository = StoryMemoryRepository.for_project_file(str(self._project_path))
        self.language_pair = LanguagePair("Japanese", "English")
        self.blocks = (_Block("block-1", "太郎が来た"),)

    def tearDown(self) -> None:
        close_cached_connection(str(self._project_path))
        self._temporary_directory.cleanup()

    def prepare(self, project_file: str | None = None):
        return StoryMemoryRequestContextService().prepare(
            project_file=str(self._project_path) if project_file is None else project_file,
            page_uuid="page-1",
            blocks=self.blocks,
            language_pair=self.language_pair,
            user_extra_context="Keep dialogue casual.",
        )

    def test_enabled_project_discloses_only_matched_memory(self):
        self.repository.set_enabled(True)
        self.repository.create_canon(NewCanonEntry(self.language_pair, "太郎", "Taro"))
        self.repository.create_canon(
            NewCanonEntry(
                self.language_pair,
                "花子",
                "Hanako",
                notes="Private note that must remain local.",
            )
        )
        self.repository.upsert_brief(NewStoryBrief(self.language_pair, "A school comedy."))
        self.repository.create_translation_memory(
            NewTranslationMemoryEntry(
                self.language_pair,
                "prior-page",
                "prior-block",
                "太郎が来た",
                "Taro arrived.",
            )
        )
        self.repository.create_translation_memory(
            NewTranslationMemoryEntry(
                self.language_pair,
                "prior-page",
                "unmatched-block",
                "花子が来た",
                "Hanako arrived.",
            )
        )

        prepared = self.prepare()

        self.assertTrue(prepared.memory_enabled)
        self.assertIsNotNone(prepared.assembled)
        self.assertIsNotNone(prepared.cache_identity)
        self.assertIn("[User instructions]", prepared.effective_context)
        self.assertIn("Keep dialogue casual.", prepared.effective_context)
        self.assertIn("A school comedy.", prepared.effective_context)
        self.assertIn("太郎 -> Taro", prepared.effective_context)
        self.assertIn("太郎が来た -> Taro arrived.", prepared.effective_context)
        self.assertNotIn("花子", prepared.effective_context)
        self.assertNotIn("Hanako", prepared.effective_context)
        self.assertNotIn("Private note", prepared.effective_context)

    def test_disabled_or_missing_project_preserves_original_context(self):
        disabled = self.prepare()
        missing = self.prepare(project_file=str(self._project_path.with_name("missing.ctpr")))

        for prepared in (disabled, missing):
            self.assertFalse(prepared.memory_enabled)
            self.assertIsNone(prepared.assembled)
            self.assertIsNone(prepared.cache_identity)
            self.assertEqual(prepared.effective_context, "Keep dialogue casual.")

    def test_memory_revision_invalidates_the_context_cache_identity(self):
        self.repository.set_enabled(True)
        self.repository.create_canon(NewCanonEntry(self.language_pair, "太郎", "Taro"))
        first = self.prepare()

        self.repository.create_canon(
            NewCanonEntry(self.language_pair, "花子", "Hanako")
        )
        second = self.prepare()

        self.assertEqual(first.effective_context, second.effective_context)
        self.assertNotEqual(first.cache_identity, second.cache_identity)
        self.assertLess(
            first.cache_identity.memory_revision,
            second.cache_identity.memory_revision,
        )


if __name__ == "__main__":
    unittest.main()
