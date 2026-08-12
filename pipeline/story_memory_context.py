"""Pipeline adapter for optional project Story Memory.

The repository-facing service intentionally knows nothing about Qt or the
application's page state.  This adapter owns the small amount of orchestration
needed by translation workers: resolving a saved page identity, handling
``Auto`` source language safely, and falling back to the user's existing
instructions when Story Memory is unavailable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from app.projects.story_memory_types import LanguagePair
from modules.translation.context.assembler import ContextAssembler
from modules.translation.context.models import (
    DEFAULT_STORY_MEMORY_CONTEXT_BUDGET,
    PreparedTranslationContext,
    StoryMemoryAssemblyRequest,
    StoryMemorySourceBlock,
)
from modules.utils.language_utils import resolve_auto_source_language

if TYPE_CHECKING:
    from modules.translation.context.request_context import StoryMemoryRequestContextService


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _CanonMatchAdapter:
    """Expose an already-disclosed canon match to the pure assembler."""

    id: str
    source_lang: str
    target_lang: str
    source_term: str
    target_term: str
    category: str
    behavior: str
    notes: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class _TranslationMemoryMatchAdapter:
    """Expose an already-disclosed approved example to the pure assembler."""

    id: str
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    status: str = "approved"


@dataclass(frozen=True, slots=True)
class _StoryBriefAdapter:
    """Expose a previously selected Story Brief to the pure assembler."""

    id: str
    source_lang: str
    target_lang: str
    content: str


def translator_supports_context(translator: Any) -> bool:
    """Return whether a translator accepts image plus prompt context.

    ``Translator`` exposes ``supports_context`` for both direct LLM engines and
    account-backed LLM proxies.  The fallback keeps lightweight test doubles
    and external translator adapters compatible with the original flag.
    """

    return bool(
        getattr(
            translator,
            "supports_context",
            getattr(translator, "is_llm_engine", False),
        )
    )


def without_story_memory(user_extra_context: str) -> PreparedTranslationContext:
    """Create the no-op result used when optional Story Memory cannot apply."""

    return PreparedTranslationContext(
        effective_context=user_extra_context,
        assembled=None,
        cache_identity=None,
        memory_enabled=False,
    )


def prepare_story_memory_context(
    main_page: Any,
    *,
    page_path: str | None,
    page_uuid: str | None,
    blocks: Sequence[Any],
    source_lang: str,
    target_lang: str,
    user_extra_context: str,
    service: StoryMemoryRequestContextService | None = None,
) -> PreparedTranslationContext:
    """Resolve provider-safe context for one normal translation request.

    Story Memory is an optional enhancement.  A missing durable page identity,
    an unsaved project, a malformed local database, or unavailable source
    language must not prevent the existing translation pipeline from running.
    Details are retained in the log for diagnosis while the caller receives the
    original user instructions unchanged.
    """

    if not isinstance(user_extra_context, str):
        raise TypeError("user_extra_context must be a string")
    if not isinstance(page_uuid, str) or not page_uuid.strip():
        return without_story_memory(user_extra_context)
    if not isinstance(source_lang, str) or not isinstance(target_lang, str):
        return without_story_memory(user_extra_context)

    resolved_source_lang = resolve_auto_source_language(list(blocks), source_lang)
    if resolved_source_lang == "Auto" or not target_lang.strip():
        return without_story_memory(user_extra_context)

    try:
        language_pair = LanguagePair(resolved_source_lang, target_lang)
        if service is None:
            from modules.translation.context.request_context import (
                StoryMemoryRequestContextService,
            )

            context_service = StoryMemoryRequestContextService()
        else:
            context_service = service
        return context_service.prepare(
            project_file=getattr(main_page, "project_file", None),
            page_uuid=page_uuid,
            blocks=blocks,
            language_pair=language_pair,
            user_extra_context=user_extra_context,
        )
    except Exception:
        logger.warning(
            "Story Memory preparation failed for page %r; using normal translation context.",
            page_path,
            exc_info=True,
        )
        return without_story_memory(user_extra_context)


def combine_story_memory_contexts(
    user_extra_context: str,
    prepared_contexts: Iterable[PreparedTranslationContext],
) -> str:
    """Combine local page contexts for one cross-page visible-webtoon request.

    The visible-webtoon translator still makes one provider request.  Its blocks
    can span physical pages, so each physical page is assembled independently
    and their bounded local sections are combined here.  User instructions are
    deliberately rendered exactly once and remain first.
    """

    assembled_contexts = [
        prepared.assembled
        for prepared in prepared_contexts
        if prepared.memory_enabled and prepared.assembled is not None
    ]
    if not assembled_contexts:
        return user_extra_context

    first = assembled_contexts[0]
    request = first.request
    source_blocks: dict[str, StoryMemorySourceBlock] = {}
    canon_entries: dict[str, _CanonMatchAdapter] = {}
    translation_memory_entries: dict[str, _TranslationMemoryMatchAdapter] = {}
    story_brief = None

    for assembled in assembled_contexts:
        candidate_request = assembled.request
        if (
            candidate_request.project_uuid != request.project_uuid
            or candidate_request.language_pair != request.language_pair
        ):
            logger.warning(
                "Skipped cross-project or cross-language Story Memory while combining a visible webtoon request."
            )
            continue

        for block in candidate_request.source_blocks:
            source_blocks.setdefault(block.block_uuid, block)

        sections = assembled.sections
        if story_brief is None and sections.story_brief is not None:
            brief = sections.story_brief
            story_brief = _StoryBriefAdapter(
                id=brief.provenance.entry_id,
                source_lang=request.language_pair.source_lang,
                target_lang=request.language_pair.target_lang,
                content=brief.content,
            )

        for match in sections.canon_constraints:
            canon_entries.setdefault(
                match.entry_id,
                _CanonMatchAdapter(
                    id=match.entry_id,
                    source_lang=request.language_pair.source_lang,
                    target_lang=request.language_pair.target_lang,
                    source_term=match.source_text,
                    target_term=match.target_text,
                    category=match.category,
                    behavior=match.behavior,
                    notes=match.notes,
                ),
            )
        for match in sections.translation_memory_examples:
            translation_memory_entries.setdefault(
                match.entry_id,
                _TranslationMemoryMatchAdapter(
                    id=match.entry_id,
                    source_lang=request.language_pair.source_lang,
                    target_lang=request.language_pair.target_lang,
                    source_text=match.source_text,
                    target_text=match.target_text,
                ),
            )

    if not source_blocks:
        return user_extra_context

    combined_request = StoryMemoryAssemblyRequest(
        project_uuid=request.project_uuid,
        page_uuid=request.page_uuid,
        language_pair=request.language_pair,
        source_blocks=tuple(source_blocks.values()),
        user_extra_context=user_extra_context,
    )
    return ContextAssembler.assemble(
        combined_request,
        story_brief=story_brief,
        canon_entries=canon_entries.values(),
        translation_memory_entries=translation_memory_entries.values(),
        budget=DEFAULT_STORY_MEMORY_CONTEXT_BUDGET,
    ).effective_context
