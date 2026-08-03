"""Deterministic, framework-independent Story Memory context matching."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Protocol

from .models import (
    StoryMemoryAssemblyRequest,
    StoryMemoryEntryKind,
    StoryMemoryMatch,
    StoryMemoryMatchReason,
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
