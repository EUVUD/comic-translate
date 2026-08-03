"""Framework-independent contracts for Story Memory context assembly.

These models deliberately contain no Qt, LangGraph, SQLite, or translator
implementation concerns.  They make the data that crosses the repository,
assembler, UI, and translator boundaries explicit and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.projects.story_memory_types import LanguagePair


class StoryMemoryEntryKind(str, Enum):
    """Kinds of durable Story Memory data that can affect a request."""

    CANON = "canon"
    STORY_BRIEF = "story_brief"
    TRANSLATION_MEMORY = "translation_memory"


class StoryMemoryMatchReason(str, Enum):
    """Deterministic reasons an item is eligible for a page context."""

    CANON_NORMALIZED_SUBSTRING = "canon_normalized_substring"
    STORY_BRIEF_CONFIGURED = "story_brief_configured"
    TRANSLATION_MEMORY_NORMALIZED_EXACT = "translation_memory_normalized_exact"


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _optional_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _block_uuids(value: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError("source_block_uuids must be a tuple")
    block_uuids = tuple(
        _required_text(block_uuid, "source_block_uuids item").strip()
        for block_uuid in value
    )
    if len(set(block_uuids)) != len(block_uuids):
        raise ValueError("source_block_uuids must not contain duplicates")
    return block_uuids


@dataclass(frozen=True, slots=True)
class StoryMemorySourceBlock:
    """Current-page OCR source retained with its durable block identity."""

    block_uuid: str
    source_text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_uuid", _required_text(self.block_uuid, "block_uuid").strip())
        object.__setattr__(self, "source_text", _optional_text(self.source_text, "source_text"))


@dataclass(frozen=True, slots=True)
class StoryMemoryAssemblyRequest:
    """All framework-neutral inputs required to assemble one page's context."""

    project_uuid: str
    page_uuid: str
    language_pair: LanguagePair
    source_blocks: tuple[StoryMemorySourceBlock, ...]
    user_extra_context: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_uuid", _required_text(self.project_uuid, "project_uuid").strip())
        object.__setattr__(self, "page_uuid", _required_text(self.page_uuid, "page_uuid").strip())
        if not isinstance(self.language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        if not isinstance(self.source_blocks, tuple):
            raise TypeError("source_blocks must be a tuple")
        if not all(isinstance(block, StoryMemorySourceBlock) for block in self.source_blocks):
            raise TypeError("source_blocks must contain StoryMemorySourceBlock values")
        block_uuids = tuple(block.block_uuid for block in self.source_blocks)
        if len(set(block_uuids)) != len(block_uuids):
            raise ValueError("source_blocks must not contain duplicate block_uuid values")
        object.__setattr__(
            self,
            "user_extra_context",
            _optional_text(self.user_extra_context, "user_extra_context"),
        )


@dataclass(frozen=True, slots=True)
class StoryMemoryProvenance:
    """Why one durable item was selected for the current page."""

    entry_id: str
    entry_kind: StoryMemoryEntryKind
    match_reason: StoryMemoryMatchReason
    source_block_uuids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _required_text(self.entry_id, "entry_id").strip())
        if not isinstance(self.entry_kind, StoryMemoryEntryKind):
            raise TypeError("entry_kind must be a StoryMemoryEntryKind")
        if not isinstance(self.match_reason, StoryMemoryMatchReason):
            raise TypeError("match_reason must be a StoryMemoryMatchReason")
        block_uuids = _block_uuids(self.source_block_uuids)
        object.__setattr__(self, "source_block_uuids", block_uuids)

        expected_reason = {
            StoryMemoryEntryKind.CANON: StoryMemoryMatchReason.CANON_NORMALIZED_SUBSTRING,
            StoryMemoryEntryKind.STORY_BRIEF: StoryMemoryMatchReason.STORY_BRIEF_CONFIGURED,
            StoryMemoryEntryKind.TRANSLATION_MEMORY: (
                StoryMemoryMatchReason.TRANSLATION_MEMORY_NORMALIZED_EXACT
            ),
        }[self.entry_kind]
        if self.match_reason is not expected_reason:
            raise ValueError("match_reason must match entry_kind")
        if self.entry_kind is StoryMemoryEntryKind.STORY_BRIEF:
            if block_uuids:
                raise ValueError("Story Brief provenance must not reference source blocks")
        elif not block_uuids:
            raise ValueError("matched entries must reference at least one source block")


@dataclass(frozen=True, slots=True)
class StoryMemoryMatch:
    """One matched canon or approved translation-memory item.

    The payload is deliberately a transport value rather than a repository row:
    callers can display it, format it, and record it without inheriting storage
    or framework dependencies.
    """

    entry_id: str
    entry_kind: StoryMemoryEntryKind
    source_text: str
    target_text: str
    provenance: StoryMemoryProvenance
    category: str = ""
    behavior: str = ""
    notes: str = ""
    is_suggestion: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _required_text(self.entry_id, "entry_id").strip())
        if self.entry_kind not in {
            StoryMemoryEntryKind.CANON,
            StoryMemoryEntryKind.TRANSLATION_MEMORY,
        }:
            raise ValueError("StoryMemoryMatch only supports canon or translation-memory entries")
        object.__setattr__(self, "source_text", _required_text(self.source_text, "source_text"))
        object.__setattr__(self, "target_text", _required_text(self.target_text, "target_text"))
        if not isinstance(self.provenance, StoryMemoryProvenance):
            raise TypeError("provenance must be a StoryMemoryProvenance")
        if (
            self.provenance.entry_id != self.entry_id
            or self.provenance.entry_kind is not self.entry_kind
        ):
            raise ValueError("provenance must identify the same entry as the match")
        object.__setattr__(self, "category", _optional_text(self.category, "category"))
        object.__setattr__(self, "behavior", _optional_text(self.behavior, "behavior"))
        object.__setattr__(self, "notes", _optional_text(self.notes, "notes"))
        if not isinstance(self.is_suggestion, bool):
            raise TypeError("is_suggestion must be a bool")


@dataclass(frozen=True, slots=True)
class StoryMemoryBriefContext:
    """The configured brief and its disclosure provenance, if included."""

    content: str
    provenance: StoryMemoryProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", _required_text(self.content, "content"))
        if not isinstance(self.provenance, StoryMemoryProvenance):
            raise TypeError("provenance must be a StoryMemoryProvenance")
        if self.provenance.entry_kind is not StoryMemoryEntryKind.STORY_BRIEF:
            raise ValueError("Story Brief context requires Story Brief provenance")


@dataclass(frozen=True, slots=True)
class StoryMemoryPromptSections:
    """Structured sections used to build an effective translator context."""

    user_extra_context: str
    story_brief: StoryMemoryBriefContext | None = None
    canon_constraints: tuple[StoryMemoryMatch, ...] = ()
    translation_memory_examples: tuple[StoryMemoryMatch, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "user_extra_context",
            _optional_text(self.user_extra_context, "user_extra_context"),
        )
        if self.story_brief is not None and not isinstance(self.story_brief, StoryMemoryBriefContext):
            raise TypeError("story_brief must be a StoryMemoryBriefContext or None")
        self._validate_matches(self.canon_constraints, StoryMemoryEntryKind.CANON, "canon_constraints")
        self._validate_matches(
            self.translation_memory_examples,
            StoryMemoryEntryKind.TRANSLATION_MEMORY,
            "translation_memory_examples",
        )

    @staticmethod
    def _validate_matches(
        matches: tuple[StoryMemoryMatch, ...],
        expected_kind: StoryMemoryEntryKind,
        field_name: str,
    ) -> None:
        if not isinstance(matches, tuple):
            raise TypeError(f"{field_name} must be a tuple")
        if not all(isinstance(match, StoryMemoryMatch) for match in matches):
            raise TypeError(f"{field_name} must contain StoryMemoryMatch values")
        if any(match.entry_kind is not expected_kind for match in matches):
            raise ValueError(f"{field_name} contains an entry of the wrong kind")


@dataclass(frozen=True, slots=True)
class AssembledStoryMemoryContext:
    """The bounded, auditable context passed across the translator boundary."""

    request: StoryMemoryAssemblyRequest
    effective_context: str
    sections: StoryMemoryPromptSections

    def __post_init__(self) -> None:
        if not isinstance(self.request, StoryMemoryAssemblyRequest):
            raise TypeError("request must be a StoryMemoryAssemblyRequest")
        object.__setattr__(
            self,
            "effective_context",
            _optional_text(self.effective_context, "effective_context"),
        )
        if not isinstance(self.sections, StoryMemoryPromptSections):
            raise TypeError("sections must be a StoryMemoryPromptSections")
        if self.sections.user_extra_context != self.request.user_extra_context:
            raise ValueError("sections must preserve request.user_extra_context")

    @property
    def matches(self) -> tuple[StoryMemoryMatch, ...]:
        """Selected canon and TM rows in their prompt-section order."""

        return self.sections.canon_constraints + self.sections.translation_memory_examples

    @property
    def provenance(self) -> tuple[StoryMemoryProvenance, ...]:
        """Disclosure metadata for every selected Story Memory item."""

        brief_provenance = ()
        if self.sections.story_brief is not None:
            brief_provenance = (self.sections.story_brief.provenance,)
        return brief_provenance + tuple(match.provenance for match in self.matches)
