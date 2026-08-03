"""Deterministic, framework-independent Story Memory context matching."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Protocol

from .models import (
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
)


class CanonEntryLike(Protocol):
    """The persisted canon fields required by the pure matching boundary."""

    id: str
    source_lang: str
    target_lang: str
    source_term: str
    target_term: str
    category: str
    behavior: str
    notes: str
    is_active: bool


class TranslationMemoryEntryLike(Protocol):
    """The persisted translation-memory fields required by pure retrieval."""

    id: str
    source_lang: str
    target_lang: str
    source_text: str
    target_text: str
    status: str


class StoryBriefLike(Protocol):
    """The persisted Story Brief fields required by pure assembly."""

    id: str
    source_lang: str
    target_lang: str
    content: str


_NO_SPACE_LANGUAGE_CODES = frozenset({"ja", "th", "zh"})
_NO_SPACE_LANGUAGE_NAMES = frozenset(
    {
        "chinese",
        "japanese",
        "simplified chinese",
        "thai",
        "traditional chinese",
    }
)


def _required_entry_text(entry: CanonEntryLike, field_name: str) -> str:
    value = getattr(entry, field_name, None)
    if not isinstance(value, str):
        raise TypeError(f"canon entry {field_name} must be a string")
    if field_name != "notes" and not value.strip():
        raise ValueError(f"canon entry {field_name} must not be empty")
    return value


def _entry_is_active(entry: CanonEntryLike) -> bool:
    value = getattr(entry, "is_active", None)
    if not isinstance(value, bool):
        raise TypeError("canon entry is_active must be a bool")
    return value


def _required_translation_memory_text(
    entry: TranslationMemoryEntryLike,
    field_name: str,
) -> str:
    value = getattr(entry, field_name, None)
    if not isinstance(value, str):
        raise TypeError(f"translation-memory entry {field_name} must be a string")
    if not value.strip():
        raise ValueError(f"translation-memory entry {field_name} must not be empty")
    return value


def _required_story_brief_text(entry: StoryBriefLike, field_name: str) -> str:
    value = getattr(entry, field_name, None)
    if not isinstance(value, str):
        raise TypeError(f"Story Brief {field_name} must be a string")
    if not value.strip():
        raise ValueError(f"Story Brief {field_name} must not be empty")
    return value


def _uses_no_space_matching(language: str) -> bool:
    normalized = unicodedata.normalize("NFKC", language).casefold().strip()
    language_code = normalized.split("-", 1)[0]
    return (
        normalized in _NO_SPACE_LANGUAGE_NAMES
        or normalized.startswith(("chinese", "japanese", "thai"))
        or language_code in _NO_SPACE_LANGUAGE_CODES
    )


class ContextAssembler:
    """Pure local matching helpers shared by all Story Memory entry points."""

    @staticmethod
    def normalize_source_text(text: str, source_language: str) -> str:
        """Normalize lookup text while retaining its original display text elsewhere."""

        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not isinstance(source_language, str):
            raise TypeError("source_language must be a string")

        normalized = unicodedata.normalize("NFKC", text).casefold()
        parts = normalized.split()
        if _uses_no_space_matching(source_language):
            return "".join(parts)
        return " ".join(parts)

    @classmethod
    def match_active_canon(
        cls,
        request: StoryMemoryAssemblyRequest,
        canon_entries: Iterable[CanonEntryLike],
    ) -> tuple[StoryMemoryMatch, ...]:
        """Match active, language-scoped canon by normalized literal substring.

        Longer normalized terms take precedence. Equal-length terms are ordered
        by their stable entry ID, and each provenance record retains current-page
        block IDs in the order supplied by the request.
        """

        if not isinstance(request, StoryMemoryAssemblyRequest):
            raise TypeError("request must be a StoryMemoryAssemblyRequest")
        if isinstance(canon_entries, (str, bytes)) or not isinstance(canon_entries, Iterable):
            raise TypeError("canon_entries must be an iterable of canon entries")

        source_language = request.language_pair.source_lang
        normalized_blocks = tuple(
            (
                block.block_uuid,
                cls.normalize_source_text(block.source_text, source_language),
            )
            for block in request.source_blocks
        )
        candidates: list[tuple[int, str, CanonEntryLike, tuple[str, ...]]] = []

        for entry in canon_entries:
            entry_id = _required_entry_text(entry, "id").strip()
            entry_source_language = _required_entry_text(entry, "source_lang")
            entry_target_language = _required_entry_text(entry, "target_lang")
            if not _entry_is_active(entry):
                continue
            if (
                entry_source_language != request.language_pair.source_lang
                or entry_target_language != request.language_pair.target_lang
            ):
                continue

            source_term = _required_entry_text(entry, "source_term")
            normalized_term = cls.normalize_source_text(source_term, source_language)
            if not normalized_term:
                continue
            matching_block_uuids = tuple(
                block_uuid
                for block_uuid, normalized_text in normalized_blocks
                if normalized_term in normalized_text
            )
            if matching_block_uuids:
                candidates.append(
                    (len(normalized_term), entry_id, entry, matching_block_uuids)
                )

        candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
        return tuple(
            StoryMemoryMatch(
                entry_id=entry_id,
                entry_kind=StoryMemoryEntryKind.CANON,
                source_text=_required_entry_text(entry, "source_term"),
                target_text=_required_entry_text(entry, "target_term"),
                category=_required_entry_text(entry, "category"),
                behavior=_required_entry_text(entry, "behavior"),
                notes=_required_entry_text(entry, "notes"),
                provenance=StoryMemoryProvenance(
                    entry_id=entry_id,
                    entry_kind=StoryMemoryEntryKind.CANON,
                    match_reason=StoryMemoryMatchReason.CANON_NORMALIZED_SUBSTRING,
                    source_block_uuids=matching_block_uuids,
                ),
            )
            for _, entry_id, entry, matching_block_uuids in candidates
        )

    @classmethod
    def match_approved_translation_memory(
        cls,
        request: StoryMemoryAssemblyRequest,
        translation_memory_entries: Iterable[TranslationMemoryEntryLike],
    ) -> tuple[StoryMemoryMatch, ...]:
        """Retrieve approved, exact normalized translation-memory candidates.

        Entries remain separate candidates even when their source text is the
        same. When those candidates have different target text, each is marked
        as a non-binding suggestion until an explicit conflict decision exists.
        """

        if not isinstance(request, StoryMemoryAssemblyRequest):
            raise TypeError("request must be a StoryMemoryAssemblyRequest")
        if isinstance(translation_memory_entries, (str, bytes)) or not isinstance(
            translation_memory_entries,
            Iterable,
        ):
            raise TypeError(
                "translation_memory_entries must be an iterable of translation-memory entries"
            )

        source_language = request.language_pair.source_lang
        normalized_blocks = tuple(
            (
                index,
                block.block_uuid,
                cls.normalize_source_text(block.source_text, source_language),
            )
            for index, block in enumerate(request.source_blocks)
        )
        candidates: list[tuple[int, str, str, str, str, tuple[str, ...]]] = []

        for entry in translation_memory_entries:
            entry_id = _required_translation_memory_text(entry, "id").strip()
            entry_source_language = _required_translation_memory_text(entry, "source_lang")
            entry_target_language = _required_translation_memory_text(entry, "target_lang")
            status = _required_translation_memory_text(entry, "status")
            if status != "approved":
                continue
            if (
                entry_source_language != request.language_pair.source_lang
                or entry_target_language != request.language_pair.target_lang
            ):
                continue

            source_text = _required_translation_memory_text(entry, "source_text")
            target_text = _required_translation_memory_text(entry, "target_text")
            normalized_source_text = cls.normalize_source_text(source_text, source_language)
            if not normalized_source_text:
                continue
            matching_blocks = tuple(
                (index, block_uuid)
                for index, block_uuid, normalized_block_text in normalized_blocks
                if normalized_source_text == normalized_block_text
            )
            if matching_blocks:
                candidates.append(
                    (
                        matching_blocks[0][0],
                        entry_id,
                        normalized_source_text,
                        source_text,
                        target_text,
                        tuple(block_uuid for _, block_uuid in matching_blocks),
                    )
                )

        candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
        target_texts_by_source: dict[str, set[str]] = {}
        for _, _, normalized_source_text, _, target_text, _ in candidates:
            target_texts_by_source.setdefault(normalized_source_text, set()).add(target_text)
        conflicting_sources = {
            normalized_source_text
            for normalized_source_text, target_texts in target_texts_by_source.items()
            if len(target_texts) > 1
        }

        return tuple(
            StoryMemoryMatch(
                entry_id=entry_id,
                entry_kind=StoryMemoryEntryKind.TRANSLATION_MEMORY,
                source_text=source_text,
                target_text=target_text,
                provenance=StoryMemoryProvenance(
                    entry_id=entry_id,
                    entry_kind=StoryMemoryEntryKind.TRANSLATION_MEMORY,
                    match_reason=(
                        StoryMemoryMatchReason.TRANSLATION_MEMORY_NORMALIZED_EXACT
                    ),
                    source_block_uuids=matching_block_uuids,
                ),
                is_suggestion=normalized_source_text in conflicting_sources,
            )
            for (
                _,
                entry_id,
                normalized_source_text,
                source_text,
                target_text,
                matching_block_uuids,
            ) in candidates
        )

    @classmethod
    def assemble(
        cls,
        request: StoryMemoryAssemblyRequest,
        *,
        story_brief: StoryBriefLike | None = None,
        canon_entries: Iterable[CanonEntryLike] = (),
        translation_memory_entries: Iterable[TranslationMemoryEntryLike] = (),
        budget: StoryMemoryContextBudget = DEFAULT_STORY_MEMORY_CONTEXT_BUDGET,
    ) -> AssembledStoryMemoryContext:
        """Build bounded, auditable prompt sections without provider calls.

        User instructions remain a separate highest-priority section and are
        never shortened. The configured character limit applies only to the
        rendered Story Memory sections, in brief/canon/example priority order.
        """

        if not isinstance(request, StoryMemoryAssemblyRequest):
            raise TypeError("request must be a StoryMemoryAssemblyRequest")
        if not isinstance(budget, StoryMemoryContextBudget):
            raise TypeError("budget must be a StoryMemoryContextBudget")

        brief = cls._story_brief_context(request, story_brief)
        canon_matches = cls._deduplicate_matches(
            cls.match_active_canon(request, canon_entries),
            lambda match: (
                cls.normalize_source_text(
                    match.source_text,
                    request.language_pair.source_lang,
                ),
                match.target_text,
                match.category,
                match.behavior,
                match.notes,
            ),
        )[: budget.max_canon_items]
        translation_memory_matches = cls._deduplicate_matches(
            cls.match_approved_translation_memory(request, translation_memory_entries),
            lambda match: (
                cls.normalize_source_text(
                    match.source_text,
                    request.language_pair.source_lang,
                ),
                match.target_text,
            ),
        )
        translation_memory_groups = cls._groups_with_item_limit(
            cls._translation_memory_match_groups(
                translation_memory_matches,
                request.language_pair.source_lang,
            ),
            budget.max_translation_memory_items,
        )

        memory_sections: list[str] = []
        selected_brief = cls._append_brief_section(memory_sections, brief, budget)
        selected_canon = cls._append_match_section(
            memory_sections,
            "[Canon constraints]",
            tuple((match,) for match in canon_matches),
            cls._format_canon_match,
            budget,
        )
        selected_translation_memory = cls._append_match_section(
            memory_sections,
            "[Approved translation examples]",
            translation_memory_groups,
            cls._format_translation_memory_match,
            budget,
        )
        sections = StoryMemoryPromptSections(
            user_extra_context=request.user_extra_context,
            story_brief=selected_brief,
            canon_constraints=selected_canon,
            translation_memory_examples=selected_translation_memory,
        )

        rendered_sections: list[str] = []
        if request.user_extra_context:
            rendered_sections.append(
                f"[User instructions]\n{request.user_extra_context}"
            )
        rendered_sections.extend(memory_sections)
        return AssembledStoryMemoryContext(
            request=request,
            effective_context="\n\n".join(rendered_sections),
            sections=sections,
        )

    @staticmethod
    def _deduplicate_matches(
        matches: Iterable[StoryMemoryMatch],
        key_for_match,
    ) -> tuple[StoryMemoryMatch, ...]:
        deduplicated: list[StoryMemoryMatch] = []
        seen_keys: set[object] = set()
        for match in matches:
            key = key_for_match(match)
            if key not in seen_keys:
                seen_keys.add(key)
                deduplicated.append(match)
        return tuple(deduplicated)

    @classmethod
    def _translation_memory_match_groups(
        cls,
        matches: Iterable[StoryMemoryMatch],
        source_language: str,
    ) -> tuple[tuple[StoryMemoryMatch, ...], ...]:
        """Keep every conflicting source group intact for later budget checks."""

        grouped_matches: dict[tuple[str, str], list[StoryMemoryMatch]] = {}
        for match in matches:
            if match.is_suggestion:
                key = (
                    "conflict",
                    cls.normalize_source_text(match.source_text, source_language),
                )
            else:
                key = ("entry", match.entry_id)
            grouped_matches.setdefault(key, []).append(match)
        return tuple(tuple(group) for group in grouped_matches.values())

    @staticmethod
    def _groups_with_item_limit(
        match_groups: Iterable[tuple[StoryMemoryMatch, ...]],
        max_items: int,
    ) -> tuple[tuple[StoryMemoryMatch, ...], ...]:
        selected_groups: list[tuple[StoryMemoryMatch, ...]] = []
        selected_item_count = 0
        for match_group in match_groups:
            if selected_item_count + len(match_group) <= max_items:
                selected_groups.append(match_group)
                selected_item_count += len(match_group)
        return tuple(selected_groups)

    @staticmethod
    def _story_brief_context(
        request: StoryMemoryAssemblyRequest,
        story_brief: StoryBriefLike | None,
    ) -> StoryMemoryBriefContext | None:
        if story_brief is None:
            return None
        brief_id = _required_story_brief_text(story_brief, "id").strip()
        source_language = _required_story_brief_text(story_brief, "source_lang")
        target_language = _required_story_brief_text(story_brief, "target_lang")
        if (
            source_language != request.language_pair.source_lang
            or target_language != request.language_pair.target_lang
        ):
            return None
        content = getattr(story_brief, "content", None)
        if not isinstance(content, str):
            raise TypeError("Story Brief content must be a string")
        if not content.strip():
            return None
        return StoryMemoryBriefContext(
            content=content,
            provenance=StoryMemoryProvenance(
                entry_id=brief_id,
                entry_kind=StoryMemoryEntryKind.STORY_BRIEF,
                match_reason=StoryMemoryMatchReason.STORY_BRIEF_CONFIGURED,
            ),
        )

    @classmethod
    def _append_brief_section(
        cls,
        memory_sections: list[str],
        brief: StoryMemoryBriefContext | None,
        budget: StoryMemoryContextBudget,
    ) -> StoryMemoryBriefContext | None:
        if brief is None:
            return None
        header = "[Story Brief]"
        body_limit = min(
            budget.max_story_brief_characters,
            cls._remaining_section_body_characters(memory_sections, header, budget),
        )
        truncated_content = cls._truncate_text(brief.content, body_limit)
        if not truncated_content:
            return None
        memory_sections.append(f"{header}\n{truncated_content}")
        return StoryMemoryBriefContext(
            content=truncated_content,
            provenance=brief.provenance,
        )

    @classmethod
    def _append_match_section(
        cls,
        memory_sections: list[str],
        header: str,
        match_groups: Iterable[tuple[StoryMemoryMatch, ...]],
        render_match,
        budget: StoryMemoryContextBudget,
    ) -> tuple[StoryMemoryMatch, ...]:
        selected: list[StoryMemoryMatch] = []
        rendered_matches: list[str] = []
        for match_group in match_groups:
            candidate_matches = rendered_matches + [
                render_match(match) for match in match_group
            ]
            candidate_section = f"{header}\n" + "\n".join(candidate_matches)
            if cls._memory_text_fits(memory_sections, candidate_section, budget):
                selected.extend(match_group)
                rendered_matches = candidate_matches
        if rendered_matches:
            memory_sections.append(f"{header}\n" + "\n".join(rendered_matches))
        return tuple(selected)

    @staticmethod
    def _format_canon_match(match: StoryMemoryMatch) -> str:
        details = [f"behavior={match.behavior}", f"category={match.category}"]
        if match.notes:
            details.append(f"notes={match.notes}")
        return f"- {match.source_text} -> {match.target_text} ({'; '.join(details)})"

    @staticmethod
    def _format_translation_memory_match(match: StoryMemoryMatch) -> str:
        conflict_suffix = " [conflicting suggestion]" if match.is_suggestion else ""
        return f"- {match.source_text} -> {match.target_text}{conflict_suffix}"

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        if len(text) <= limit:
            return text
        if limit == 1:
            return "…"
        return f"{text[: limit - 1]}…"

    @staticmethod
    def _remaining_section_body_characters(
        memory_sections: list[str],
        header: str,
        budget: StoryMemoryContextBudget,
    ) -> int:
        rendered_length = len("\n\n".join(memory_sections))
        separator_length = 2 if memory_sections else 0
        return max(
            0,
            budget.max_story_memory_characters
            - rendered_length
            - separator_length
            - len(header)
            - 1,
        )

    @staticmethod
    def _memory_text_fits(
        memory_sections: list[str],
        candidate_section: str,
        budget: StoryMemoryContextBudget,
    ) -> bool:
        rendered_sections = memory_sections + [candidate_section]
        return len("\n\n".join(rendered_sections)) <= budget.max_story_memory_characters
