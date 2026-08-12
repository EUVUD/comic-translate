"""Project-backed Story Memory preparation for one translation request.

This module is deliberately independent of Qt, a translation provider, and the
pipeline.  Callers supply the page identity, OCR blocks, language pair, and
existing user instructions; the service returns the exact context that should
be handed to the normal translator.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import hashlib
from typing import Any

from app.projects.project_state_v2 import is_sqlite_project_file
from app.projects.story_memory_repository import StoryMemoryRepository
from app.projects.story_memory_types import LanguagePair

from .assembler import ContextAssembler
from .models import (
    DEFAULT_STORY_MEMORY_CONTEXT_BUDGET,
    AssembledStoryMemoryContext,
    PreparedTranslationContext,
    StoryMemoryAssemblyRequest,
    StoryMemoryCacheIdentity,
    StoryMemoryContextBudget,
    StoryMemorySourceBlock,
)


RepositoryFactory = Callable[[str], StoryMemoryRepository]


class StoryMemoryRequestContextService:
    """Load, match, and format enabled Story Memory for one project page."""

    def __init__(
        self,
        *,
        repository_factory: RepositoryFactory = StoryMemoryRepository.for_project_file,
        assembler: ContextAssembler | None = None,
        budget: StoryMemoryContextBudget = DEFAULT_STORY_MEMORY_CONTEXT_BUDGET,
    ) -> None:
        if not callable(repository_factory):
            raise TypeError("repository_factory must be callable")
        if assembler is not None and not isinstance(assembler, ContextAssembler):
            raise TypeError("assembler must be a ContextAssembler or None")
        if not isinstance(budget, StoryMemoryContextBudget):
            raise TypeError("budget must be a StoryMemoryContextBudget")

        self._repository_factory = repository_factory
        self._assembler = assembler or ContextAssembler()
        self._budget = budget

    def prepare(
        self,
        *,
        project_file: str | None,
        page_uuid: str,
        blocks: Sequence[Any],
        language_pair: LanguagePair,
        user_extra_context: str,
    ) -> PreparedTranslationContext:
        """Return original instructions unless an enabled saved project is available."""

        if not isinstance(user_extra_context, str):
            raise TypeError("user_extra_context must be a string")
        if not self._has_saved_project(project_file):
            return self._without_story_memory(user_extra_context)

        repository = self._repository_factory(project_file)
        metadata = repository.get_metadata()
        if not metadata.enabled:
            return self._without_story_memory(user_extra_context)

        request = StoryMemoryAssemblyRequest(
            project_uuid=metadata.project_uuid,
            page_uuid=page_uuid,
            language_pair=language_pair,
            source_blocks=self._source_blocks(blocks),
            user_extra_context=user_extra_context,
        )
        assembled = self._assembler.assemble(
            request,
            story_brief=repository.get_brief(language_pair),
            canon_entries=repository.list_canon(language_pair, active_only=True),
            translation_memory_entries=repository.list_translation_memory(language_pair),
            budget=self._budget,
        )
        return PreparedTranslationContext(
            effective_context=assembled.effective_context,
            assembled=assembled,
            cache_identity=StoryMemoryCacheIdentity(
                project_uuid=metadata.project_uuid,
                memory_revision=metadata.memory_revision,
                assembler_version=metadata.assembler_version,
                source_lang=language_pair.source_lang,
                target_lang=language_pair.target_lang,
                source_content_hash=self._hash_source_blocks(request.source_blocks),
                user_context_hash=self._hash_text(user_extra_context),
            ),
            memory_enabled=True,
        )

    @staticmethod
    def _has_saved_project(project_file: str | None) -> bool:
        return isinstance(project_file, str) and bool(project_file) and is_sqlite_project_file(project_file)

    @staticmethod
    def _without_story_memory(user_extra_context: str) -> PreparedTranslationContext:
        return PreparedTranslationContext(
            effective_context=user_extra_context,
            assembled=None,
            cache_identity=None,
            memory_enabled=False,
        )

    @staticmethod
    def _source_blocks(blocks: Sequence[Any]) -> tuple[StoryMemorySourceBlock, ...]:
        if isinstance(blocks, (str, bytes)) or not isinstance(blocks, Sequence):
            raise TypeError("blocks must be a sequence of text blocks")

        source_blocks: list[StoryMemorySourceBlock] = []
        for block in blocks:
            block_uuid = getattr(block, "block_uuid", None)
            source_text = getattr(block, "text", None)
            source_blocks.append(
                StoryMemorySourceBlock(block_uuid=block_uuid, source_text=source_text)
            )
        return tuple(source_blocks)

    @staticmethod
    def _hash_source_blocks(blocks: tuple[StoryMemorySourceBlock, ...]) -> str:
        digest = hashlib.sha256()
        for block in blocks:
            digest.update(block.block_uuid.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(block.source_text.encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()

    @staticmethod
    def _hash_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
