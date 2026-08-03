from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from .project_state_v2 import (
    STORY_MEMORY_PROJECT_UUID_KEY,
    get_project_connection,
)
from .story_memory_types import LanguagePair


_CANON_BEHAVIORS = frozenset({"preferred", "forbidden", "untranslatable"})
_TRANSLATION_MEMORY_STATUSES = frozenset({"approved", "superseded"})


def normalize_story_memory_text(text: str) -> str:
    """Normalize text for local Story Memory lookup without changing display text."""
    if not isinstance(text, str):
        raise TypeError("Story Memory text must be a string")
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _required_label(value: str, field_name: str) -> str:
    return _required_text(value, field_name).strip()


def _optional_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_id(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_label(value, field_name)


def _generated_or_supplied_id(value: str | None, field_name: str) -> str:
    return _optional_id(value, field_name) or str(uuid.uuid4())


def _required_bool(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _required_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


@dataclass(frozen=True, slots=True)
class StoryMemoryMetadata:
    project_uuid: str
    schema_version: int
    enabled: bool
    memory_revision: int
    assembler_version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CanonEntry:
    id: str
    source_lang: str
    target_lang: str
    source_term: str
    normalized_source_term: str
    target_term: str
    category: str
    behavior: str
    notes: str
    is_active: bool
    created_at: str
    updated_at: str

    @property
    def language_pair(self) -> LanguagePair:
        return LanguagePair(self.source_lang, self.target_lang)


@dataclass(frozen=True, slots=True)
class NewCanonEntry:
    language_pair: LanguagePair
    source_term: str
    target_term: str
    category: str = "term"
    behavior: str = "preferred"
    notes: str = ""
    is_active: bool = True
    entry_id: str | None = None


@dataclass(frozen=True, slots=True)
class CanonEntryUpdate:
    language_pair: LanguagePair
    source_term: str
    target_term: str
    category: str = "term"
    behavior: str = "preferred"
    notes: str = ""
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class StoryBrief:
    id: str
    source_lang: str
    target_lang: str
    content: str
    created_at: str
    updated_at: str

    @property
    def language_pair(self) -> LanguagePair:
        return LanguagePair(self.source_lang, self.target_lang)


@dataclass(frozen=True, slots=True)
class NewStoryBrief:
    language_pair: LanguagePair
    content: str
    brief_id: str | None = None


@dataclass(frozen=True, slots=True)
class TranslationRecord:
    id: str
    page_uuid: str
    block_uuid: str
    source_lang: str
    target_lang: str
    source_text: str
    model_translation: str
    current_translation: str
    review_status: str
    matched_entry_ids: tuple[str, ...]
    checker_feedback: str
    created_at: str
    updated_at: str

    @property
    def language_pair(self) -> LanguagePair:
        return LanguagePair(self.source_lang, self.target_lang)


@dataclass(frozen=True, slots=True)
class DraftTranslationRecord:
    language_pair: LanguagePair
    page_uuid: str
    block_uuid: str
    source_text: str
    model_translation: str = ""
    current_translation: str = ""
    matched_entry_ids: tuple[str, ...] = ()
    checker_feedback: str = ""
    record_id: str | None = None


@dataclass(frozen=True, slots=True)
class TranslationMemoryEntry:
    id: str
    record_id: str | None
    page_uuid: str
    block_uuid: str
    source_lang: str
    target_lang: str
    source_text: str
    normalized_source_text: str
    target_text: str
    status: str
    origin: str
    is_preferred: bool
    supersedes_id: str | None
    approved_at: str
    created_at: str
    updated_at: str

    @property
    def language_pair(self) -> LanguagePair:
        return LanguagePair(self.source_lang, self.target_lang)


@dataclass(frozen=True, slots=True)
class NewTranslationMemoryEntry:
    language_pair: LanguagePair
    page_uuid: str
    block_uuid: str
    source_text: str
    target_text: str
    record_id: str | None = None
    status: str = "approved"
    origin: str = "page_review"
    is_preferred: bool = False
    supersedes_id: str | None = None
    entry_id: str | None = None


@dataclass(frozen=True, slots=True)
class ImportReceipt:
    id: str
    source_path: str
    source_fingerprint: str
    canon_entries_imported: int
    translation_memory_imported: int
    imported_at: str


@dataclass(frozen=True, slots=True)
class NewImportReceipt:
    source_path: str
    source_fingerprint: str
    canon_entries_imported: int = 0
    translation_memory_imported: int = 0
    receipt_id: str | None = None


@dataclass(frozen=True, slots=True)
class LegacyEntriesImportResult:
    """Result of one atomic legacy-entry import attempt."""

    receipt: ImportReceipt
    imported: bool


class StoryMemoryRepository:
    """Typed project-local persistence operations for Story Memory.

    The repository deliberately owns no UI or approval policy. It maps typed
    values to the `.ctpr` tables, scopes every retrieval to a complete language
    pair, and keeps each mutation plus its revision update in one savepoint.
    """

    def __init__(self, project_file: str):
        self.project_file = os.path.abspath(_required_text(project_file, "project_file"))

    @classmethod
    def for_project_file(cls, project_file: str) -> "StoryMemoryRepository":
        return cls(project_file)

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        conn, conn_lock = get_project_connection(self.project_file)
        with conn_lock:
            yield conn

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        conn, conn_lock = get_project_connection(self.project_file)
        with conn_lock:
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()
            if foreign_keys is None or int(foreign_keys[0]) != 1:
                raise RuntimeError("Story Memory requires SQLite foreign-key enforcement")

            savepoint = f"story_memory_repository_{uuid.uuid4().hex}"
            conn.execute(f"SAVEPOINT {savepoint}")
            try:
                yield conn
            except BaseException:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            else:
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")

    @staticmethod
    def _metadata_from_row(row: tuple) -> StoryMemoryMetadata:
        return StoryMemoryMetadata(
            project_uuid=str(row[0]),
            schema_version=int(row[1]),
            enabled=bool(row[2]),
            memory_revision=int(row[3]),
            assembler_version=int(row[4]),
            created_at=str(row[5]),
            updated_at=str(row[6]),
        )

    @staticmethod
    def _canon_from_row(row: tuple) -> CanonEntry:
        return CanonEntry(
            id=str(row[0]),
            source_lang=str(row[1]),
            target_lang=str(row[2]),
            source_term=str(row[3]),
            normalized_source_term=str(row[4]),
            target_term=str(row[5]),
            category=str(row[6]),
            behavior=str(row[7]),
            notes=str(row[8]),
            is_active=bool(row[9]),
            created_at=str(row[10]),
            updated_at=str(row[11]),
        )

    @staticmethod
    def _brief_from_row(row: tuple) -> StoryBrief:
        return StoryBrief(
            id=str(row[0]),
            source_lang=str(row[1]),
            target_lang=str(row[2]),
            content=str(row[3]),
            created_at=str(row[4]),
            updated_at=str(row[5]),
        )

    @staticmethod
    def _record_from_row(row: tuple) -> TranslationRecord:
        try:
            parsed_ids = json.loads(row[9])
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed_ids = []
        matched_entry_ids = tuple(value for value in parsed_ids if isinstance(value, str))
        return TranslationRecord(
            id=str(row[0]),
            page_uuid=str(row[1]),
            block_uuid=str(row[2]),
            source_lang=str(row[3]),
            target_lang=str(row[4]),
            source_text=str(row[5]),
            model_translation=str(row[6]),
            current_translation=str(row[7]),
            review_status=str(row[8]),
            matched_entry_ids=matched_entry_ids,
            checker_feedback=str(row[10]),
            created_at=str(row[11]),
            updated_at=str(row[12]),
        )

    @staticmethod
    def _translation_memory_from_row(row: tuple) -> TranslationMemoryEntry:
        return TranslationMemoryEntry(
            id=str(row[0]),
            record_id=str(row[1]) if row[1] is not None else None,
            page_uuid=str(row[2]),
            block_uuid=str(row[3]),
            source_lang=str(row[4]),
            target_lang=str(row[5]),
            source_text=str(row[6]),
            normalized_source_text=str(row[7]),
            target_text=str(row[8]),
            status=str(row[9]),
            origin=str(row[10]),
            is_preferred=bool(row[11]),
            supersedes_id=str(row[12]) if row[12] is not None else None,
            approved_at=str(row[13]),
            created_at=str(row[14]),
            updated_at=str(row[15]),
        )

    @staticmethod
    def _receipt_from_row(row: tuple) -> ImportReceipt:
        return ImportReceipt(
            id=str(row[0]),
            source_path=str(row[1]),
            source_fingerprint=str(row[2]),
            canon_entries_imported=int(row[3]),
            translation_memory_imported=int(row[4]),
            imported_at=str(row[5]),
        )

    def _fetch_metadata(self, conn: sqlite3.Connection) -> StoryMemoryMetadata:
        row = conn.execute(
            """
            SELECT meta.value, metadata.schema_version, metadata.enabled,
                   metadata.memory_revision, metadata.assembler_version,
                   metadata.created_at, metadata.updated_at
            FROM story_memory_metadata AS metadata
            JOIN meta ON meta.key = ?
            WHERE metadata.id = 1
            """,
            (STORY_MEMORY_PROJECT_UUID_KEY,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Story Memory metadata is missing from this project")
        return self._metadata_from_row(row)

    def _fetch_canon(self, conn: sqlite3.Connection, entry_id: str) -> CanonEntry | None:
        row = conn.execute(
            """
            SELECT id, source_lang, target_lang, source_term, normalized_source_term,
                   target_term, category, behavior, notes, is_active, created_at, updated_at
            FROM story_memory_canon_entries WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
        return self._canon_from_row(row) if row is not None else None

    def _fetch_brief(
        self,
        conn: sqlite3.Connection,
        language_pair: LanguagePair,
    ) -> StoryBrief | None:
        row = conn.execute(
            """
            SELECT id, source_lang, target_lang, content, created_at, updated_at
            FROM story_memory_briefs
            WHERE source_lang = ? AND target_lang = ?
            """,
            (language_pair.source_lang, language_pair.target_lang),
        ).fetchone()
        return self._brief_from_row(row) if row is not None else None

    def _fetch_record(
        self,
        conn: sqlite3.Connection,
        record_id: str,
    ) -> TranslationRecord | None:
        row = conn.execute(
            """
            SELECT id, page_uuid, block_uuid, source_lang, target_lang, source_text,
                   model_translation, current_translation, review_status,
                   matched_entry_ids_json, checker_feedback, created_at, updated_at
            FROM story_memory_translation_records WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def _fetch_translation_memory(
        self,
        conn: sqlite3.Connection,
        entry_id: str,
    ) -> TranslationMemoryEntry | None:
        row = conn.execute(
            """
            SELECT id, record_id, page_uuid, block_uuid, source_lang, target_lang,
                   source_text, normalized_source_text, target_text, status, origin,
                   is_preferred, supersedes_id, approved_at, created_at, updated_at
            FROM story_memory_translation_memory WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
        return self._translation_memory_from_row(row) if row is not None else None

    def _fetch_import_receipt(
        self,
        conn: sqlite3.Connection,
        source_path: str,
        source_fingerprint: str,
    ) -> ImportReceipt | None:
        row = conn.execute(
            """
            SELECT id, source_path, source_fingerprint, canon_entries_imported,
                   translation_memory_imported, imported_at
            FROM story_memory_import_receipts
            WHERE source_path = ? AND source_fingerprint = ?
            """,
            (source_path, source_fingerprint),
        ).fetchone()
        return self._receipt_from_row(row) if row is not None else None

    @staticmethod
    def _increment_revision(conn: sqlite3.Connection) -> None:
        cursor = conn.execute(
            """
            UPDATE story_memory_metadata
            SET memory_revision = memory_revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Story Memory metadata is missing from this project")

    @staticmethod
    def _validated_canon_values(
        entry: NewCanonEntry | CanonEntryUpdate,
    ) -> tuple[LanguagePair, str, str, str, str, str, bool]:
        if not isinstance(entry.language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        source_term = _required_text(entry.source_term, "source_term")
        target_term = _required_text(entry.target_term, "target_term")
        category = _required_label(entry.category, "category")
        behavior = _required_label(entry.behavior, "behavior")
        if behavior not in _CANON_BEHAVIORS:
            raise ValueError(f"Unsupported canon behavior: {behavior}")
        notes = _optional_text(entry.notes, "notes")
        is_active = _required_bool(entry.is_active, "is_active")
        return entry.language_pair, source_term, target_term, category, behavior, notes, is_active

    @staticmethod
    def _validated_matched_entry_ids(entry_ids: Iterable[str]) -> tuple[str, ...]:
        if isinstance(entry_ids, str):
            raise TypeError("matched_entry_ids must be an iterable of identifiers")
        values: list[str] = []
        for entry_id in entry_ids:
            value = _required_label(entry_id, "matched_entry_id")
            if value not in values:
                values.append(value)
        return tuple(values)

    @staticmethod
    def _validated_translation_memory_statuses(statuses: Iterable[str]) -> tuple[str, ...]:
        if isinstance(statuses, str):
            raise TypeError("statuses must be an iterable of status strings")
        values: list[str] = []
        for status in statuses:
            value = _required_label(status, "status")
            if value not in _TRANSLATION_MEMORY_STATUSES:
                raise ValueError(f"Unsupported translation-memory status: {value}")
            if value not in values:
                values.append(value)
        if not values:
            raise ValueError("statuses must not be empty")
        return tuple(values)

    @staticmethod
    def _validated_translation_memory_values(
        entry: NewTranslationMemoryEntry,
    ) -> tuple[
        LanguagePair,
        str | None,
        str,
        str,
        str,
        str,
        str,
        str,
        bool,
        str | None,
    ]:
        if not isinstance(entry, NewTranslationMemoryEntry):
            raise TypeError("entry must be a NewTranslationMemoryEntry")
        if not isinstance(entry.language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        record_id = _optional_id(entry.record_id, "record_id")
        page_uuid = _required_label(entry.page_uuid, "page_uuid")
        block_uuid = _required_label(entry.block_uuid, "block_uuid")
        source_text = _required_text(entry.source_text, "source_text")
        target_text = _required_text(entry.target_text, "target_text")
        status = _required_label(entry.status, "status")
        if status not in _TRANSLATION_MEMORY_STATUSES:
            raise ValueError(f"Unsupported translation-memory status: {status}")
        origin = _required_label(entry.origin, "origin")
        is_preferred = _required_bool(entry.is_preferred, "is_preferred")
        supersedes_id = _optional_id(entry.supersedes_id, "supersedes_id")
        return (
            entry.language_pair,
            record_id,
            page_uuid,
            block_uuid,
            source_text,
            target_text,
            status,
            origin,
            is_preferred,
            supersedes_id,
        )

    def get_metadata(self) -> StoryMemoryMetadata:
        with self._read_connection() as conn:
            return self._fetch_metadata(conn)

    def set_enabled(self, enabled: bool) -> StoryMemoryMetadata:
        enabled = _required_bool(enabled, "enabled")
        with self._write_transaction() as conn:
            metadata = self._fetch_metadata(conn)
            if metadata.enabled == enabled:
                return metadata
            conn.execute(
                "UPDATE story_memory_metadata SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (int(enabled),),
            )
            self._increment_revision(conn)
            return self._fetch_metadata(conn)

    def set_assembler_version(self, assembler_version: int) -> StoryMemoryMetadata:
        assembler_version = _required_non_negative_int(assembler_version, "assembler_version")
        if assembler_version == 0:
            raise ValueError("assembler_version must be positive")
        with self._write_transaction() as conn:
            metadata = self._fetch_metadata(conn)
            if metadata.assembler_version == assembler_version:
                return metadata
            conn.execute(
                """
                UPDATE story_memory_metadata
                SET assembler_version = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (assembler_version,),
            )
            self._increment_revision(conn)
            return self._fetch_metadata(conn)

    def get_canon(self, entry_id: str) -> CanonEntry | None:
        entry_id = _required_label(entry_id, "entry_id")
        with self._read_connection() as conn:
            return self._fetch_canon(conn, entry_id)

    def list_canon(
        self,
        language_pair: LanguagePair,
        *,
        active_only: bool = False,
    ) -> list[CanonEntry]:
        if not isinstance(language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        active_only = _required_bool(active_only, "active_only")
        query = """
            SELECT id, source_lang, target_lang, source_term, normalized_source_term,
                   target_term, category, behavior, notes, is_active, created_at, updated_at
            FROM story_memory_canon_entries
            WHERE source_lang = ? AND target_lang = ?
        """
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY id"
        with self._read_connection() as conn:
            rows = conn.execute(
                query,
                (language_pair.source_lang, language_pair.target_lang),
            ).fetchall()
        return [self._canon_from_row(row) for row in rows]

    def create_canon(self, entry: NewCanonEntry) -> CanonEntry:
        if not isinstance(entry, NewCanonEntry):
            raise TypeError("entry must be a NewCanonEntry")
        language_pair, source_term, target_term, category, behavior, notes, is_active = (
            self._validated_canon_values(entry)
        )
        entry_id = _generated_or_supplied_id(entry.entry_id, "entry_id")
        with self._write_transaction() as conn:
            conn.execute(
                """
                INSERT INTO story_memory_canon_entries(
                    id, source_lang, target_lang, source_term, normalized_source_term,
                    target_term, category, behavior, notes, is_active
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    language_pair.source_lang,
                    language_pair.target_lang,
                    source_term,
                    normalize_story_memory_text(source_term),
                    target_term,
                    category,
                    behavior,
                    notes,
                    int(is_active),
                ),
            )
            self._increment_revision(conn)
            created = self._fetch_canon(conn, entry_id)
            if created is None:
                raise RuntimeError("Failed to read the canon entry that was created")
            return created

    def update_canon(self, entry_id: str, update: CanonEntryUpdate) -> CanonEntry:
        entry_id = _required_label(entry_id, "entry_id")
        if not isinstance(update, CanonEntryUpdate):
            raise TypeError("update must be a CanonEntryUpdate")
        language_pair, source_term, target_term, category, behavior, notes, is_active = (
            self._validated_canon_values(update)
        )
        normalized_source_term = normalize_story_memory_text(source_term)
        with self._write_transaction() as conn:
            existing = self._fetch_canon(conn, entry_id)
            if existing is None:
                raise KeyError(f"Unknown canon entry: {entry_id}")
            if (
                existing.source_lang == language_pair.source_lang
                and existing.target_lang == language_pair.target_lang
                and existing.source_term == source_term
                and existing.normalized_source_term == normalized_source_term
                and existing.target_term == target_term
                and existing.category == category
                and existing.behavior == behavior
                and existing.notes == notes
                and existing.is_active == is_active
            ):
                return existing
            conn.execute(
                """
                UPDATE story_memory_canon_entries
                SET source_lang = ?, target_lang = ?, source_term = ?,
                    normalized_source_term = ?, target_term = ?, category = ?,
                    behavior = ?, notes = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    language_pair.source_lang,
                    language_pair.target_lang,
                    source_term,
                    normalized_source_term,
                    target_term,
                    category,
                    behavior,
                    notes,
                    int(is_active),
                    entry_id,
                ),
            )
            self._increment_revision(conn)
            updated = self._fetch_canon(conn, entry_id)
            if updated is None:
                raise RuntimeError("Failed to read the canon entry that was updated")
            return updated

    def set_canon_active(self, entry_id: str, is_active: bool) -> CanonEntry:
        entry_id = _required_label(entry_id, "entry_id")
        is_active = _required_bool(is_active, "is_active")
        with self._write_transaction() as conn:
            existing = self._fetch_canon(conn, entry_id)
            if existing is None:
                raise KeyError(f"Unknown canon entry: {entry_id}")
            if existing.is_active == is_active:
                return existing
            conn.execute(
                """
                UPDATE story_memory_canon_entries
                SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(is_active), entry_id),
            )
            self._increment_revision(conn)
            updated = self._fetch_canon(conn, entry_id)
            if updated is None:
                raise RuntimeError("Failed to read the canon entry that was updated")
            return updated

    def delete_canon(self, entry_id: str) -> bool:
        entry_id = _required_label(entry_id, "entry_id")
        with self._write_transaction() as conn:
            existing = self._fetch_canon(conn, entry_id)
            if existing is None:
                return False
            conn.execute("DELETE FROM story_memory_canon_entries WHERE id = ?", (entry_id,))
            self._increment_revision(conn)
            return True

    def get_brief(self, language_pair: LanguagePair) -> StoryBrief | None:
        if not isinstance(language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        with self._read_connection() as conn:
            return self._fetch_brief(conn, language_pair)

    def upsert_brief(self, brief: NewStoryBrief) -> StoryBrief:
        if not isinstance(brief, NewStoryBrief):
            raise TypeError("brief must be a NewStoryBrief")
        if not isinstance(brief.language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        content = _required_text(brief.content, "content")
        with self._write_transaction() as conn:
            existing = self._fetch_brief(conn, brief.language_pair)
            if existing is not None and existing.content == content:
                return existing
            if existing is None:
                brief_id = _generated_or_supplied_id(brief.brief_id, "brief_id")
                conn.execute(
                    """
                    INSERT INTO story_memory_briefs(id, source_lang, target_lang, content)
                    VALUES(?, ?, ?, ?)
                    """,
                    (
                        brief_id,
                        brief.language_pair.source_lang,
                        brief.language_pair.target_lang,
                        content,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE story_memory_briefs
                    SET content = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (content, existing.id),
                )
            self._increment_revision(conn)
            updated = self._fetch_brief(conn, brief.language_pair)
            if updated is None:
                raise RuntimeError("Failed to read the Story Brief that was saved")
            return updated

    def delete_brief(self, language_pair: LanguagePair) -> bool:
        if not isinstance(language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        with self._write_transaction() as conn:
            existing = self._fetch_brief(conn, language_pair)
            if existing is None:
                return False
            conn.execute("DELETE FROM story_memory_briefs WHERE id = ?", (existing.id,))
            self._increment_revision(conn)
            return True

    def create_draft_record(self, record: DraftTranslationRecord) -> TranslationRecord:
        if not isinstance(record, DraftTranslationRecord):
            raise TypeError("record must be a DraftTranslationRecord")
        if not isinstance(record.language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        record_id = _generated_or_supplied_id(record.record_id, "record_id")
        page_uuid = _required_label(record.page_uuid, "page_uuid")
        block_uuid = _required_label(record.block_uuid, "block_uuid")
        source_text = _required_text(record.source_text, "source_text")
        model_translation = _optional_text(record.model_translation, "model_translation")
        current_translation = _optional_text(record.current_translation, "current_translation")
        checker_feedback = _optional_text(record.checker_feedback, "checker_feedback")
        matched_entry_ids = self._validated_matched_entry_ids(record.matched_entry_ids)
        with self._write_transaction() as conn:
            conn.execute(
                """
                INSERT INTO story_memory_translation_records(
                    id, page_uuid, block_uuid, source_lang, target_lang, source_text,
                    model_translation, current_translation, review_status,
                    matched_entry_ids_json, checker_feedback
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
                """,
                (
                    record_id,
                    page_uuid,
                    block_uuid,
                    record.language_pair.source_lang,
                    record.language_pair.target_lang,
                    source_text,
                    model_translation,
                    current_translation,
                    json.dumps(matched_entry_ids, ensure_ascii=False, separators=(",", ":")),
                    checker_feedback,
                ),
            )
            created = self._fetch_record(conn, record_id)
            if created is None:
                raise RuntimeError("Failed to read the draft translation record that was created")
            return created

    def get_translation_record(self, record_id: str) -> TranslationRecord | None:
        record_id = _required_label(record_id, "record_id")
        with self._read_connection() as conn:
            return self._fetch_record(conn, record_id)

    def list_translation_records(
        self,
        language_pair: LanguagePair,
        *,
        page_uuid: str | None = None,
    ) -> list[TranslationRecord]:
        if not isinstance(language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        page_uuid = _optional_id(page_uuid, "page_uuid")
        query = """
            SELECT id, page_uuid, block_uuid, source_lang, target_lang, source_text,
                   model_translation, current_translation, review_status,
                   matched_entry_ids_json, checker_feedback, created_at, updated_at
            FROM story_memory_translation_records
            WHERE source_lang = ? AND target_lang = ?
        """
        params: list[str] = [language_pair.source_lang, language_pair.target_lang]
        if page_uuid is not None:
            query += " AND page_uuid = ?"
            params.append(page_uuid)
        query += " ORDER BY created_at, id"
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._record_from_row(row) for row in rows]

    def create_translation_memory(
        self,
        entry: NewTranslationMemoryEntry,
    ) -> TranslationMemoryEntry:
        (
            language_pair,
            record_id,
            page_uuid,
            block_uuid,
            source_text,
            target_text,
            status,
            origin,
            is_preferred,
            supersedes_id,
        ) = self._validated_translation_memory_values(entry)
        entry_id = _generated_or_supplied_id(entry.entry_id, "entry_id")
        with self._write_transaction() as conn:
            conn.execute(
                """
                INSERT INTO story_memory_translation_memory(
                    id, record_id, page_uuid, block_uuid, source_lang, target_lang,
                    source_text, normalized_source_text, target_text, status, origin,
                    is_preferred, supersedes_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    record_id,
                    page_uuid,
                    block_uuid,
                    language_pair.source_lang,
                    language_pair.target_lang,
                    source_text,
                    normalize_story_memory_text(source_text),
                    target_text,
                    status,
                    origin,
                    int(is_preferred),
                    supersedes_id,
                ),
            )
            if status == "approved":
                self._increment_revision(conn)
            created = self._fetch_translation_memory(conn, entry_id)
            if created is None:
                raise RuntimeError("Failed to read the translation-memory entry that was created")
            return created

    def import_legacy_entries(
        self,
        *,
        source_path: str,
        source_fingerprint: str,
        canon_entries: Iterable[NewCanonEntry] = (),
        translation_memory_entries: Iterable[NewTranslationMemoryEntry] = (),
    ) -> LegacyEntriesImportResult:
        """Atomically import parsed legacy rows and record their source receipt.

        A receipt is claimed in the same savepoint as every imported row. This
        prevents a failed or repeated migration from creating duplicate canon
        or approved-memory rows.
        """
        source_path = _required_text(source_path, "source_path")
        source_fingerprint = _required_text(source_fingerprint, "source_fingerprint")

        prepared_canons: list[
            tuple[str, LanguagePair, str, str, str, str, str, bool]
        ] = []
        for entry in canon_entries:
            if not isinstance(entry, NewCanonEntry):
                raise TypeError("canon_entries must contain NewCanonEntry values")
            language_pair, source_term, target_term, category, behavior, notes, is_active = (
                self._validated_canon_values(entry)
            )
            prepared_canons.append(
                (
                    _generated_or_supplied_id(entry.entry_id, "entry_id"),
                    language_pair,
                    source_term,
                    target_term,
                    category,
                    behavior,
                    notes,
                    is_active,
                )
            )

        prepared_translation_memory: list[
            tuple[str, LanguagePair, str, str, str, str, bool]
        ] = []
        for entry in translation_memory_entries:
            (
                language_pair,
                record_id,
                page_uuid,
                block_uuid,
                source_text,
                target_text,
                status,
                origin,
                is_preferred,
                supersedes_id,
            ) = self._validated_translation_memory_values(entry)
            if status != "approved":
                raise ValueError("Legacy translation-memory imports must be approved")
            if origin != "legacy_sidecar_import":
                raise ValueError(
                    "Legacy translation-memory imports must use legacy_sidecar_import origin"
                )
            if record_id is not None or supersedes_id is not None:
                raise ValueError(
                    "Legacy translation-memory imports cannot reference project records"
                )
            prepared_translation_memory.append(
                (
                    _generated_or_supplied_id(entry.entry_id, "entry_id"),
                    language_pair,
                    page_uuid,
                    block_uuid,
                    source_text,
                    target_text,
                    is_preferred,
                )
            )

        with self._write_transaction() as conn:
            existing = self._fetch_import_receipt(conn, source_path, source_fingerprint)
            if existing is not None:
                return LegacyEntriesImportResult(existing, imported=False)

            receipt_id = str(uuid.uuid4())
            try:
                conn.execute(
                    """
                    INSERT INTO story_memory_import_receipts(
                        id, source_path, source_fingerprint, canon_entries_imported,
                        translation_memory_imported
                    ) VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        receipt_id,
                        source_path,
                        source_fingerprint,
                        len(prepared_canons),
                        len(prepared_translation_memory),
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self._fetch_import_receipt(conn, source_path, source_fingerprint)
                if existing is not None:
                    return LegacyEntriesImportResult(existing, imported=False)
                raise

            for (
                entry_id,
                language_pair,
                source_term,
                target_term,
                category,
                behavior,
                notes,
                is_active,
            ) in prepared_canons:
                conn.execute(
                    """
                    INSERT INTO story_memory_canon_entries(
                        id, source_lang, target_lang, source_term, normalized_source_term,
                        target_term, category, behavior, notes, is_active
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        language_pair.source_lang,
                        language_pair.target_lang,
                        source_term,
                        normalize_story_memory_text(source_term),
                        target_term,
                        category,
                        behavior,
                        notes,
                        int(is_active),
                    ),
                )

            for (
                entry_id,
                language_pair,
                page_uuid,
                block_uuid,
                source_text,
                target_text,
                is_preferred,
            ) in prepared_translation_memory:
                conn.execute(
                    """
                    INSERT INTO story_memory_translation_memory(
                        id, record_id, page_uuid, block_uuid, source_lang, target_lang,
                        source_text, normalized_source_text, target_text, status, origin,
                        is_preferred, supersedes_id
                    ) VALUES(?, NULL, ?, ?, ?, ?, ?, ?, ?, 'approved',
                             'legacy_sidecar_import', ?, NULL)
                    """,
                    (
                        entry_id,
                        page_uuid,
                        block_uuid,
                        language_pair.source_lang,
                        language_pair.target_lang,
                        source_text,
                        normalize_story_memory_text(source_text),
                        target_text,
                        int(is_preferred),
                    ),
                )

            if prepared_canons or prepared_translation_memory:
                self._increment_revision(conn)

            created = self._fetch_import_receipt(conn, source_path, source_fingerprint)
            if created is None:
                raise RuntimeError("Failed to read the import receipt that was created")
            return LegacyEntriesImportResult(created, imported=True)

    def get_translation_memory(self, entry_id: str) -> TranslationMemoryEntry | None:
        entry_id = _required_label(entry_id, "entry_id")
        with self._read_connection() as conn:
            return self._fetch_translation_memory(conn, entry_id)

    def list_translation_memory(
        self,
        language_pair: LanguagePair,
        *,
        normalized_source_text: str | None = None,
        statuses: Iterable[str] = ("approved",),
    ) -> list[TranslationMemoryEntry]:
        if not isinstance(language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")
        valid_statuses = self._validated_translation_memory_statuses(statuses)
        query = """
            SELECT id, record_id, page_uuid, block_uuid, source_lang, target_lang,
                   source_text, normalized_source_text, target_text, status, origin,
                   is_preferred, supersedes_id, approved_at, created_at, updated_at
            FROM story_memory_translation_memory
            WHERE source_lang = ? AND target_lang = ?
        """
        params: list[str] = [language_pair.source_lang, language_pair.target_lang]
        if normalized_source_text is not None:
            normalized_source_text = normalize_story_memory_text(normalized_source_text)
            query += " AND normalized_source_text = ?"
            params.append(normalized_source_text)
        placeholders = ", ".join("?" for _ in valid_statuses)
        query += f" AND status IN ({placeholders})"
        params.extend(valid_statuses)
        query += " ORDER BY is_preferred DESC, approved_at DESC, id"
        with self._read_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._translation_memory_from_row(row) for row in rows]

    def get_import_receipt(
        self,
        source_path: str,
        source_fingerprint: str,
    ) -> ImportReceipt | None:
        source_path = _required_text(source_path, "source_path")
        source_fingerprint = _required_text(source_fingerprint, "source_fingerprint")
        with self._read_connection() as conn:
            return self._fetch_import_receipt(conn, source_path, source_fingerprint)

    def record_import_receipt(self, receipt: NewImportReceipt) -> ImportReceipt:
        if not isinstance(receipt, NewImportReceipt):
            raise TypeError("receipt must be a NewImportReceipt")
        source_path = _required_text(receipt.source_path, "source_path")
        source_fingerprint = _required_text(receipt.source_fingerprint, "source_fingerprint")
        canon_entries_imported = _required_non_negative_int(
            receipt.canon_entries_imported,
            "canon_entries_imported",
        )
        translation_memory_imported = _required_non_negative_int(
            receipt.translation_memory_imported,
            "translation_memory_imported",
        )
        with self._write_transaction() as conn:
            existing = self._fetch_import_receipt(conn, source_path, source_fingerprint)
            if existing is not None:
                return existing
            receipt_id = _generated_or_supplied_id(receipt.receipt_id, "receipt_id")
            conn.execute(
                """
                INSERT INTO story_memory_import_receipts(
                    id, source_path, source_fingerprint, canon_entries_imported,
                    translation_memory_imported
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    source_path,
                    source_fingerprint,
                    canon_entries_imported,
                    translation_memory_imported,
                ),
            )
            created = self._fetch_import_receipt(conn, source_path, source_fingerprint)
            if created is None:
                raise RuntimeError("Failed to read the import receipt that was created")
            return created
