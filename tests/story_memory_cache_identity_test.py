from __future__ import annotations

import unittest

import numpy as np

from modules.translation.context.models import StoryMemoryCacheIdentity
from pipeline.cache_manager import CacheManager


class StoryMemoryCacheIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache_manager = CacheManager()
        self.image = np.zeros((20, 20, 3), dtype=np.uint8)

    @staticmethod
    def memory_identity(*, revision: int = 3, source_hash: str = "source-a"):
        return StoryMemoryCacheIdentity(
            project_uuid="project-1",
            memory_revision=revision,
            assembler_version=1,
            source_lang="Japanese",
            target_lang="English",
            source_content_hash=source_hash,
            user_context_hash="user-context",
        )

    def test_memory_revision_invalidates_translation_cache_key(self):
        first = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1",
            "Keep dialogue casual.",
            story_memory_identity=self.memory_identity(revision=3),
        )
        changed_memory = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1",
            "Keep dialogue casual.",
            story_memory_identity=self.memory_identity(revision=4),
        )

        self.assertNotEqual(first, changed_memory)

    def test_memory_identity_distinguishes_project_source_and_user_context(self):
        baseline = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1",
            "Keep dialogue casual.",
            story_memory_identity=self.memory_identity(),
        )
        changed_source = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1",
            "Keep dialogue casual.",
            story_memory_identity=self.memory_identity(source_hash="source-b"),
        )
        changed_user_context = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1",
            "Use formal language.",
            story_memory_identity=self.memory_identity(),
        )

        self.assertNotEqual(baseline, changed_source)
        self.assertNotEqual(baseline, changed_user_context)

    def test_disabled_story_memory_preserves_existing_cache_identity(self):
        original = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1",
            "Keep dialogue casual.",
        )
        explicit_disabled = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1",
            "Keep dialogue casual.",
            story_memory_identity=None,
        )

        self.assertEqual(original, explicit_disabled)

    def test_translator_configuration_fingerprint_invalidates_cache_key(self):
        first = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1_config-a",
            "Keep dialogue casual.",
            story_memory_identity=self.memory_identity(),
        )
        changed_configuration = self.cache_manager._get_translation_cache_key(
            self.image,
            "Japanese",
            "English",
            "GPT-4.1_config-b",
            "Keep dialogue casual.",
            story_memory_identity=self.memory_identity(),
        )

        self.assertNotEqual(first, changed_configuration)


if __name__ == "__main__":
    unittest.main()
