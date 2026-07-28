from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from modules.translation.context.store import resolve_sidecar_db_path

from .project_state_v2 import is_sqlite_project_file
from .story_memory_repository import (
    ImportReceipt,
    LanguagePair,
    NewCanonEntry,
    NewTranslationMemoryEntry,
    StoryMemoryRepository,
)


_LEGACY_PROJECT_COLUMNS = frozenset({"id", "key"})
_LEGACY_GLOSSARY_COLUMNS = frozenset(
    {"id", "project_id", "source_term", "target_term"}
)
_LEGACY_TRANSLATION_MEMORY_COLUMNS = frozenset(
    {"id", "project_id", "source_text", "target_text", "approved"}
)


@dataclass(frozen=True, slots=True)
class LegacySidecarImportResult:
    """The observable result of a conservative legacy-sidecar migration."""

    status: str
    sidecar_path: str
    source_fingerprint: str | None = None
    receipt: ImportReceipt | None = None
    canon_entries_imported: int = 0
    translation_memory_imported: int = 0


def _canonical_path(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _file_fingerprint(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> frozenset[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return frozenset(str(row[1]) for row in rows)


def _legacy_project_ids(
    conn: sqlite3.Connection,
    project_file: str,
) -> tuple[int, ...]:
    expected_key = _canonical_path(project_file)
    project_ids: list[int] = []
    for project_id, key in conn.execute("SELECT id, key FROM projects").fetchall():
        if not isinstance(key, str) or key == "unsaved-project":
            continue
        if _canonical_path(key) == expected_key:
            project_ids.append(int(project_id))
    return tuple(project_ids)


def _nonempty_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _project_rows_query(project_ids: tuple[int, ...], query: str) -> tuple[str, list[int]]:
    placeholders = ", ".join("?" for _ in project_ids)
    return query.format(project_ids=placeholders), list(project_ids)


def _read_legacy_glossary(
    conn: sqlite3.Connection,
    project_ids: tuple[int, ...],
    has_notes: bool,
    language_pair: LanguagePair,
) -> list[NewCanonEntry]:
    notes_expression = "notes" if has_notes else "''"
    query, parameters = _project_rows_query(
        project_ids,
        f"""
        SELECT source_term, target_term, {notes_expression}
        FROM glossary_terms
        WHERE project_id IN ({{project_ids}})
        ORDER BY id
        """,
    )
    entries: list[NewCanonEntry] = []
    for source_term, target_term, notes in conn.execute(query, parameters).fetchall():
        source_text = _nonempty_text(source_term)
        target_text = _nonempty_text(target_term)
        if source_text is None or target_text is None:
            continue
        entries.append(
            NewCanonEntry(
                language_pair,
                source_text,
                target_text,
                category="legacy_glossary",
                behavior="preferred",
                notes=notes if isinstance(notes, str) else "",
            )
        )
    return entries


def _legacy_provenance_uuid(
    project_uuid: str,
    fingerprint: str,
    legacy_row_id: object,
    kind: str,
) -> str:
    namespace = uuid.UUID(project_uuid)
    return str(
        uuid.uuid5(
            namespace,
            f"legacy-sidecar:{fingerprint}:{legacy_row_id}:{kind}",
        )
    )


def _read_legacy_translation_memory(
    conn: sqlite3.Connection,
    project_ids: tuple[int, ...],
    language_pair: LanguagePair,
    project_uuid: str,
    fingerprint: str,
) -> list[NewTranslationMemoryEntry]:
    query, parameters = _project_rows_query(
        project_ids,
        """
        SELECT id, source_text, target_text, approved
        FROM translation_memory
        WHERE project_id IN ({project_ids})
        ORDER BY id
        """,
    )
    entries: list[NewTranslationMemoryEntry] = []
    for legacy_id, source_text, target_text, approved in conn.execute(query, parameters).fetchall():
        if not isinstance(approved, int) or approved != 1:
            continue
        source = _nonempty_text(source_text)
        target = _nonempty_text(target_text)
        if source is None or target is None:
            continue
        entries.append(
            NewTranslationMemoryEntry(
                language_pair,
                _legacy_provenance_uuid(project_uuid, fingerprint, legacy_id, "page"),
                _legacy_provenance_uuid(project_uuid, fingerprint, legacy_id, "block"),
                source,
                target,
                origin="legacy_sidecar_import",
            )
        )
    return entries


def import_legacy_sidecar(
    repository: StoryMemoryRepository,
    language_pair: LanguagePair,
) -> LegacySidecarImportResult:
    """Import one saved project's legacy sidecar without changing the source.

    The legacy database has no language metadata, so the caller must provide
    the intended language pair. This function intentionally resolves only the
    saved-project sidecar path and never probes the ambiguous unsaved fallback.
    """
    if not isinstance(repository, StoryMemoryRepository):
        raise TypeError("repository must be a StoryMemoryRepository")
    if not isinstance(language_pair, LanguagePair):
        raise TypeError("language_pair must be a LanguagePair")

    project_file = _canonical_path(repository.project_file)
    sidecar_path = _canonical_path(resolve_sidecar_db_path(project_file=project_file))
    if not is_sqlite_project_file(project_file):
        return LegacySidecarImportResult("ineligible_project", sidecar_path)
    if not os.path.isfile(sidecar_path):
        return LegacySidecarImportResult("sidecar_not_found", sidecar_path)

    fingerprint = _file_fingerprint(sidecar_path)
    existing_receipt = repository.get_import_receipt(sidecar_path, fingerprint)
    if existing_receipt is not None:
        return LegacySidecarImportResult(
            "already_imported",
            sidecar_path,
            fingerprint,
            existing_receipt,
            existing_receipt.canon_entries_imported,
            existing_receipt.translation_memory_imported,
        )

    try:
        source_uri = Path(sidecar_path).as_uri() + "?mode=ro"
        source_conn = sqlite3.connect(source_uri, uri=True)
        try:
            table_names = {
                str(row[0])
                for row in source_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "projects" not in table_names:
                return LegacySidecarImportResult("incompatible_sidecar", sidecar_path, fingerprint)

            project_columns = _table_columns(source_conn, "projects")
            if not _LEGACY_PROJECT_COLUMNS.issubset(project_columns):
                return LegacySidecarImportResult("incompatible_sidecar", sidecar_path, fingerprint)

            project_ids = _legacy_project_ids(source_conn, project_file)
            if not project_ids:
                return LegacySidecarImportResult("unmatched_project", sidecar_path, fingerprint)

            glossary_columns = (
                _table_columns(source_conn, "glossary_terms")
                if "glossary_terms" in table_names
                else frozenset()
            )
            memory_columns = (
                _table_columns(source_conn, "translation_memory")
                if "translation_memory" in table_names
                else frozenset()
            )
            glossary_is_compatible = _LEGACY_GLOSSARY_COLUMNS.issubset(glossary_columns)
            memory_is_compatible = _LEGACY_TRANSLATION_MEMORY_COLUMNS.issubset(memory_columns)
            if not glossary_is_compatible and not memory_is_compatible:
                return LegacySidecarImportResult("incompatible_sidecar", sidecar_path, fingerprint)

            canon_entries = (
                _read_legacy_glossary(
                    source_conn,
                    project_ids,
                    "notes" in glossary_columns,
                    language_pair,
                )
                if glossary_is_compatible
                else []
            )
            translation_memory_entries = (
                _read_legacy_translation_memory(
                    source_conn,
                    project_ids,
                    language_pair,
                    repository.get_metadata().project_uuid,
                    fingerprint,
                )
                if memory_is_compatible
                else []
            )
        finally:
            source_conn.close()
        if _file_fingerprint(sidecar_path) != fingerprint:
            return LegacySidecarImportResult("sidecar_changed", sidecar_path, fingerprint)
    except (OSError, sqlite3.DatabaseError, ValueError):
        return LegacySidecarImportResult("incompatible_sidecar", sidecar_path, fingerprint)

    imported = repository.import_legacy_entries(
        source_path=sidecar_path,
        source_fingerprint=fingerprint,
        canon_entries=canon_entries,
        translation_memory_entries=translation_memory_entries,
    )
    status = "imported" if imported.imported else "already_imported"
    return LegacySidecarImportResult(
        status,
        sidecar_path,
        fingerprint,
        imported.receipt,
        imported.receipt.canon_entries_imported,
        imported.receipt.translation_memory_imported,
    )
