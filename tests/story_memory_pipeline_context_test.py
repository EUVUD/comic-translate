from __future__ import annotations

from dataclasses import dataclass
import sys
import unittest

# A lightweight import test can leave a partial Qt stub in sys.modules.  This
# pipeline adapter imports the real language helpers, so restore real Qt when
# tests share one interpreter.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from app.projects.story_memory_types import LanguagePair
from modules.translation.context.assembler import ContextAssembler
from modules.translation.context.models import (
    DEFAULT_STORY_MEMORY_CONTEXT_BUDGET,
    PreparedTranslationContext,
    StoryMemoryAssemblyRequest,
    StoryMemorySourceBlock,
)
from pipeline.story_memory_context import combine_story_memory_contexts


@dataclass(frozen=True, slots=True)
class _Canon:
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
class _Brief:
    id: str
    source_lang: str
    target_lang: str
    content: str


def _prepared_context(
    *,
    page_uuid: str,
    block_uuid: str,
    source_text: str,
    canon_entries: list[_Canon],
    brief: str = "A school comedy.",
) -> PreparedTranslationContext:
    pair = LanguagePair("Japanese", "English")
    request = StoryMemoryAssemblyRequest(
        project_uuid="project-1",
        page_uuid=page_uuid,
        language_pair=pair,
        source_blocks=(StoryMemorySourceBlock(block_uuid, source_text),),
    )
    assembled = ContextAssembler.assemble(
        request,
        story_brief=_Brief("brief-1", "Japanese", "English", brief),
        canon_entries=canon_entries,
    )
    return PreparedTranslationContext(
        effective_context=assembled.effective_context,
        assembled=assembled,
        cache_identity=None,
        memory_enabled=True,
    )


class VisibleWebtoonStoryMemoryContextTests(unittest.TestCase):
    def test_combines_cross_page_matches_once_with_one_story_brief(self):
        first = _prepared_context(
            page_uuid="page-1",
            block_uuid="block-1",
            source_text="太郎が来た",
            canon_entries=[_Canon("canon-taro", "Japanese", "English", "太郎", "Taro")],
        )
        second = _prepared_context(
            page_uuid="page-2",
            block_uuid="block-2",
            source_text="花子が来た",
            canon_entries=[_Canon("canon-hanako", "Japanese", "English", "花子", "Hanako")],
        )

        effective_context = combine_story_memory_contexts(
            "Keep dialogue casual.",
            [first, second],
        )

        self.assertEqual(effective_context.count("[User instructions]"), 1)
        self.assertEqual(effective_context.count("[Story Brief]"), 1)
        self.assertIn("太郎 -> Taro", effective_context)
        self.assertIn("花子 -> Hanako", effective_context)

    def test_cross_page_context_respects_one_global_story_memory_budget(self):
        first_terms = [
            _Canon(
                f"first-{index:02d}",
                "Japanese",
                "English",
                f"一{index:02d}",
                "A" * 260,
            )
            for index in range(20)
        ]
        second_terms = [
            _Canon(
                f"second-{index:02d}",
                "Japanese",
                "English",
                f"二{index:02d}",
                "B" * 260,
            )
            for index in range(20)
        ]
        first = _prepared_context(
            page_uuid="page-1",
            block_uuid="block-1",
            source_text=" ".join(entry.source_term for entry in first_terms),
            canon_entries=first_terms,
            brief="C" * 600,
        )
        second = _prepared_context(
            page_uuid="page-2",
            block_uuid="block-2",
            source_text=" ".join(entry.source_term for entry in second_terms),
            canon_entries=second_terms,
            brief="C" * 600,
        )
        user_context = "Keep dialogue casual."

        effective_context = combine_story_memory_contexts(
            user_context,
            [first, second],
        )

        user_section = f"[User instructions]\n{user_context}\n\n"
        self.assertTrue(effective_context.startswith(user_section))
        self.assertLessEqual(
            len(effective_context[len(user_section) :]),
            DEFAULT_STORY_MEMORY_CONTEXT_BUDGET.max_story_memory_characters,
        )


if __name__ == "__main__":
    unittest.main()
