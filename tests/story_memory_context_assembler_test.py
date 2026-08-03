from __future__ import annotations

from dataclasses import dataclass
import unittest

from app.projects.story_memory_types import LanguagePair
from modules.translation.context.assembler import ContextAssembler
from modules.translation.context.models import (
    StoryMemoryAssemblyRequest,
    StoryMemorySourceBlock,
)


@dataclass(frozen=True, slots=True)
class _CanonEntry:
    id: str
    source_lang: str
    target_lang: str
    source_term: str
    target_term: str
    category: str = "term"
    behavior: str = "preferred"
    notes: str = ""
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class _TranslationMemoryEntry:
    id: str
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    status: str = "approved"
    is_preferred: bool = False


class ContextAssemblerTests(unittest.TestCase):
    def make_request(
        self,
        *,
        language_pair: LanguagePair | None = None,
        source_blocks: tuple[StoryMemorySourceBlock, ...] | None = None,
    ) -> StoryMemoryAssemblyRequest:
        blocks = source_blocks
        if blocks is None:
            blocks = (
                StoryMemorySourceBlock("block-1", "太郎が来た"),
                StoryMemorySourceBlock("block-2", "太郎と花子"),
            )
        return StoryMemoryAssemblyRequest(
            project_uuid="project-uuid",
            page_uuid="page-uuid",
            language_pair=language_pair or LanguagePair("Japanese", "English"),
            source_blocks=blocks,
        )

    def test_normalization_is_unicode_and_language_aware(self):
        self.assertEqual(
            ContextAssembler.normalize_source_text(" ＴＡＲＯ\tStraße ", "English"),
            "taro strasse",
        )
        self.assertEqual(
            ContextAssembler.normalize_source_text(" 太　郎 \n", "Japanese"),
            "太郎",
        )
        self.assertEqual(
            ContextAssembler.normalize_source_text("太 郎", "ja"),
            "太郎",
        )
        self.assertEqual(
            ContextAssembler.normalize_source_text("太 郎", "zh-CN"),
            "太郎",
        )

    def test_matches_only_active_entries_for_the_exact_language_pair(self):
        request = self.make_request()
        entries = (
            _CanonEntry("match", "Japanese", "English", "太郎", "Taro"),
            _CanonEntry("inactive", "Japanese", "English", "花子", "Hanako", is_active=False),
            _CanonEntry("wrong-target", "Japanese", "Chinese", "太郎", "太郎"),
            _CanonEntry("wrong-source", "Korean", "English", "太郎", "Taro"),
        )

        matches = ContextAssembler.match_active_canon(request, entries)

        self.assertEqual([match.entry_id for match in matches], ["match"])
        self.assertEqual(matches[0].source_text, "太郎")
        self.assertEqual(matches[0].target_text, "Taro")
        self.assertEqual(matches[0].provenance.source_block_uuids, ("block-1", "block-2"))

    def test_matches_multiple_blocks_and_orders_by_length_then_stable_id(self):
        request = self.make_request(
            source_blocks=(
                StoryMemorySourceBlock("block-1", "太郎が来た"),
                StoryMemorySourceBlock("block-2", "太郎太郎が笑う"),
            )
        )
        entries = (
            _CanonEntry("z-short", "Japanese", "English", "太郎", "Taro"),
            _CanonEntry("b-long", "Japanese", "English", "太郎太郎", "Taro Taro"),
            _CanonEntry("a-long", "Japanese", "English", "太郎太郎", "Taro Taro"),
        )

        matches = ContextAssembler.match_active_canon(request, entries)

        self.assertEqual([match.entry_id for match in matches], ["a-long", "b-long", "z-short"])
        self.assertEqual(matches[0].provenance.source_block_uuids, ("block-2",))
        self.assertEqual(matches[2].provenance.source_block_uuids, ("block-1", "block-2"))

    def test_spaced_languages_collapse_whitespace_without_removing_word_boundaries(self):
        request = self.make_request(
            language_pair=LanguagePair("English", "Japanese"),
            source_blocks=(
                StoryMemorySourceBlock("block-1", "NewYork"),
                StoryMemorySourceBlock("block-2", "new\n  york"),
            ),
        )
        entries = (_CanonEntry("new-york", "English", "Japanese", "New York", "ニューヨーク"),)

        matches = ContextAssembler.match_active_canon(request, entries)

        self.assertEqual([match.entry_id for match in matches], ["new-york"])
        self.assertEqual(matches[0].provenance.source_block_uuids, ("block-2",))

    def test_canon_terms_do_not_match_across_independent_blocks(self):
        request = self.make_request(
            source_blocks=(
                StoryMemorySourceBlock("block-1", "太"),
                StoryMemorySourceBlock("block-2", "郎"),
            )
        )
        entries = (_CanonEntry("taro", "Japanese", "English", "太郎", "Taro"),)

        self.assertEqual(ContextAssembler.match_active_canon(request, entries), ())

    def test_empty_page_source_has_no_canon_matches(self):
        request = self.make_request(source_blocks=())
        entries = (_CanonEntry("match", "Japanese", "English", "太郎", "Taro"),)

        self.assertEqual(ContextAssembler.match_active_canon(request, entries), ())

    def test_retrieves_approved_exact_matches_and_preserves_raw_payload(self):
        request = self.make_request(
            source_blocks=(
                StoryMemorySourceBlock("block-1", "太 郎"),
                StoryMemorySourceBlock("block-2", "太郎"),
            )
        )
        entries = (
            _TranslationMemoryEntry(
                "taro",
                "Japanese",
                "English",
                " 太 郎 ",
                "Taro",
            ),
        )

        matches = ContextAssembler.match_approved_translation_memory(request, entries)

        self.assertEqual([match.entry_id for match in matches], ["taro"])
        self.assertEqual(matches[0].source_text, " 太 郎 ")
        self.assertEqual(matches[0].target_text, "Taro")
        self.assertEqual(matches[0].provenance.source_block_uuids, ("block-1", "block-2"))
        self.assertFalse(matches[0].is_suggestion)

    def test_translation_memory_requires_approved_exact_language_pair(self):
        request = self.make_request()
        entries = (
            _TranslationMemoryEntry("match", "Japanese", "English", "太郎が来た", "Taro arrived"),
            _TranslationMemoryEntry(
                "superseded",
                "Japanese",
                "English",
                "太郎が来た",
                "Old Taro arrived",
                status="superseded",
            ),
            _TranslationMemoryEntry(
                "pending",
                "Japanese",
                "English",
                "太郎が来た",
                "Pending Taro arrived",
                status="pending",
            ),
            _TranslationMemoryEntry(
                "wrong-target",
                "Japanese",
                "Chinese",
                "太郎が来た",
                "太郎来了",
            ),
            _TranslationMemoryEntry(
                "wrong-source",
                "Korean",
                "English",
                "太郎が来た",
                "Taro arrived",
            ),
        )

        matches = ContextAssembler.match_approved_translation_memory(request, entries)

        self.assertEqual([match.entry_id for match in matches], ["match"])

    def test_translation_memory_does_not_match_substrings_or_across_blocks(self):
        request = self.make_request(
            source_blocks=(
                StoryMemorySourceBlock("block-1", "太郎が来た"),
                StoryMemorySourceBlock("block-2", "太"),
                StoryMemorySourceBlock("block-3", "郎"),
            )
        )
        entries = (_TranslationMemoryEntry("taro", "Japanese", "English", "太郎", "Taro"),)

        self.assertEqual(
            ContextAssembler.match_approved_translation_memory(request, entries),
            (),
        )

    def test_conflicting_translation_memory_candidates_are_stable_suggestions(self):
        request = self.make_request(
            source_blocks=(StoryMemorySourceBlock("block-1", "太郎が来た"),)
        )
        entries = (
            _TranslationMemoryEntry(
                "z-taro",
                "Japanese",
                "English",
                "太郎が来た",
                "Taro arrived",
                is_preferred=True,
            ),
            _TranslationMemoryEntry(
                "a-taro",
                "Japanese",
                "English",
                "太郎が来た",
                "Taro has arrived",
            ),
        )

        matches = ContextAssembler.match_approved_translation_memory(request, entries)

        self.assertEqual([match.entry_id for match in matches], ["a-taro", "z-taro"])
        self.assertTrue(all(match.is_suggestion for match in matches))
        self.assertEqual(
            [match.target_text for match in matches],
            ["Taro has arrived", "Taro arrived"],
        )

    def test_duplicate_translation_memory_targets_are_not_conflicts(self):
        request = self.make_request(
            source_blocks=(StoryMemorySourceBlock("block-1", "太郎が来た"),)
        )
        entries = (
            _TranslationMemoryEntry(
                "a-taro",
                "Japanese",
                "English",
                "太郎が来た",
                "Taro arrived",
            ),
            _TranslationMemoryEntry(
                "b-taro",
                "Japanese",
                "English",
                "太郎が来た",
                "Taro arrived",
            ),
        )

        matches = ContextAssembler.match_approved_translation_memory(request, entries)

        self.assertEqual([match.entry_id for match in matches], ["a-taro", "b-taro"])
        self.assertTrue(all(not match.is_suggestion for match in matches))


if __name__ == "__main__":
    unittest.main()
