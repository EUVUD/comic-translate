from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from app.projects.story_memory_types import LanguagePair
from modules.translation.context.models import (
    AssembledStoryMemoryContext,
    DEFAULT_STORY_MEMORY_CONTEXT_BUDGET,
    StoryMemoryAssemblyRequest,
    StoryMemoryBriefContext,
    StoryMemoryContextBudget,
    StoryMemoryEntryKind,
    StoryMemoryMatch,
    StoryMemoryMatchReason,
    StoryMemoryPromptSections,
    StoryMemoryProvenance,
    StoryMemorySourceBlock,
)


class StoryMemoryContextModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.language_pair = LanguagePair("Japanese", "English")
        self.request = StoryMemoryAssemblyRequest(
            project_uuid="project-uuid",
            page_uuid="page-uuid",
            language_pair=self.language_pair,
            source_blocks=(
                StoryMemorySourceBlock("block-1", "太郎が来た"),
                StoryMemorySourceBlock("block-2", "花子も来た"),
            ),
            user_extra_context="Keep dialogue casual.",
        )

    def test_request_keeps_stable_identities_and_original_extra_context(self):
        self.assertEqual(self.request.project_uuid, "project-uuid")
        self.assertEqual(self.request.page_uuid, "page-uuid")
        self.assertEqual(
            [block.source_text for block in self.request.source_blocks],
            ["太郎が来た", "花子も来た"],
        )
        self.assertEqual(self.request.user_extra_context, "Keep dialogue casual.")
        with self.assertRaises(FrozenInstanceError):
            self.request.page_uuid = "other-page"

    def test_request_rejects_duplicate_stable_block_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate block_uuid"):
            StoryMemoryAssemblyRequest(
                project_uuid="project-uuid",
                page_uuid="page-uuid",
                language_pair=self.language_pair,
                source_blocks=(
                    StoryMemorySourceBlock("block-1", "first"),
                    StoryMemorySourceBlock("block-1", "second"),
                ),
            )

    def test_context_budget_has_immutable_defaults(self):
        budget = StoryMemoryContextBudget()

        self.assertEqual(budget, DEFAULT_STORY_MEMORY_CONTEXT_BUDGET)
        self.assertEqual(budget.max_story_memory_characters, 4000)
        self.assertEqual(budget.max_story_brief_characters, 1200)
        self.assertEqual(budget.max_canon_items, 20)
        self.assertEqual(budget.max_translation_memory_items, 10)
        with self.assertRaises(FrozenInstanceError):
            budget.max_canon_items = 1

    def test_context_budget_rejects_bool_non_int_and_negative_limits(self):
        for field_name, invalid_value, exception_type in (
            ("max_story_memory_characters", True, TypeError),
            ("max_story_brief_characters", 1.5, TypeError),
            ("max_canon_items", "20", TypeError),
            ("max_translation_memory_items", -1, ValueError),
        ):
            with self.subTest(field_name=field_name, invalid_value=invalid_value):
                with self.assertRaises(exception_type):
                    StoryMemoryContextBudget(**{field_name: invalid_value})

    def test_match_requires_consistent_provenance(self):
        provenance = StoryMemoryProvenance(
            entry_id="canon-1",
            entry_kind=StoryMemoryEntryKind.CANON,
            match_reason=StoryMemoryMatchReason.CANON_NORMALIZED_SUBSTRING,
            source_block_uuids=("block-1",),
        )
        match = StoryMemoryMatch(
            entry_id="canon-1",
            entry_kind=StoryMemoryEntryKind.CANON,
            source_text="太郎",
            target_text="Taro",
            category="character",
            behavior="preferred",
            provenance=provenance,
        )

        self.assertEqual(match.provenance.source_block_uuids, ("block-1",))
        with self.assertRaisesRegex(ValueError, "same entry"):
            StoryMemoryMatch(
                entry_id="canon-2",
                entry_kind=StoryMemoryEntryKind.CANON,
                source_text="太郎",
                target_text="Taro",
                provenance=provenance,
            )

    def test_assembled_context_keeps_sections_and_auditable_disclosure(self):
        brief = StoryMemoryBriefContext(
            content="A school comedy.",
            provenance=StoryMemoryProvenance(
                entry_id="brief-1",
                entry_kind=StoryMemoryEntryKind.STORY_BRIEF,
                match_reason=StoryMemoryMatchReason.STORY_BRIEF_CONFIGURED,
            ),
        )
        canon_match = StoryMemoryMatch(
            entry_id="canon-1",
            entry_kind=StoryMemoryEntryKind.CANON,
            source_text="太郎",
            target_text="Taro",
            provenance=StoryMemoryProvenance(
                entry_id="canon-1",
                entry_kind=StoryMemoryEntryKind.CANON,
                match_reason=StoryMemoryMatchReason.CANON_NORMALIZED_SUBSTRING,
                source_block_uuids=("block-1",),
            ),
        )
        memory_match = StoryMemoryMatch(
            entry_id="memory-1",
            entry_kind=StoryMemoryEntryKind.TRANSLATION_MEMORY,
            source_text="花子も来た",
            target_text="Hanako came too.",
            provenance=StoryMemoryProvenance(
                entry_id="memory-1",
                entry_kind=StoryMemoryEntryKind.TRANSLATION_MEMORY,
                match_reason=StoryMemoryMatchReason.TRANSLATION_MEMORY_NORMALIZED_EXACT,
                source_block_uuids=("block-2",),
            ),
            is_suggestion=True,
        )
        sections = StoryMemoryPromptSections(
            user_extra_context=self.request.user_extra_context,
            story_brief=brief,
            canon_constraints=(canon_match,),
            translation_memory_examples=(memory_match,),
        )
        context = AssembledStoryMemoryContext(
            request=self.request,
            effective_context="[User instructions]\nKeep dialogue casual.",
            sections=sections,
        )

        self.assertEqual([match.entry_id for match in context.matches], ["canon-1", "memory-1"])
        self.assertEqual(
            [provenance.entry_id for provenance in context.provenance],
            ["brief-1", "canon-1", "memory-1"],
        )
        self.assertTrue(context.matches[1].is_suggestion)

    def test_assembled_context_rejects_dropped_user_context(self):
        with self.assertRaisesRegex(ValueError, "preserve request.user_extra_context"):
            AssembledStoryMemoryContext(
                request=self.request,
                effective_context="",
                sections=StoryMemoryPromptSections(user_extra_context="Different instructions."),
            )


if __name__ == "__main__":
    unittest.main()
