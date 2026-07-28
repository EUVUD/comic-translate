from __future__ import annotations

import sqlite3
from collections.abc import Callable


STORY_MEMORY_SCHEMA_VERSION = 1
STORY_MEMORY_SCHEMA_VERSION_KEY = "story_memory_schema_version"


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )


def _read_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?",
        (STORY_MEMORY_SCHEMA_VERSION_KEY,),
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid Story Memory schema version") from exc


def _record_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        (STORY_MEMORY_SCHEMA_VERSION_KEY, str(version)),
    )
    conn.execute(
        """
        UPDATE story_memory_metadata
        SET schema_version = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
        """,
        (version,),
    )


def _migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_memory_metadata (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            schema_version INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
            memory_revision INTEGER NOT NULL DEFAULT 0 CHECK (memory_revision >= 0),
            assembler_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO story_memory_metadata(
            id, schema_version, enabled, memory_revision, assembler_version
        ) VALUES(1, 1, 0, 0, 1)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_memory_canon_entries (
            id TEXT PRIMARY KEY,
            source_lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            source_term TEXT NOT NULL,
            normalized_source_term TEXT NOT NULL,
            target_term TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'term',
            behavior TEXT NOT NULL DEFAULT 'preferred'
                CHECK (behavior IN ('preferred', 'forbidden', 'untranslatable')),
            notes TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_memory_briefs (
            id TEXT PRIMARY KEY,
            source_lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_lang, target_lang)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_memory_translation_records (
            id TEXT PRIMARY KEY,
            page_uuid TEXT NOT NULL,
            block_uuid TEXT NOT NULL,
            source_lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            source_text TEXT NOT NULL,
            model_translation TEXT NOT NULL DEFAULT '',
            current_translation TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'draft'
                CHECK (review_status IN ('draft', 'pending', 'approved', 'superseded', 'stale')),
            matched_entry_ids_json TEXT NOT NULL DEFAULT '[]',
            checker_feedback TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_memory_translation_memory (
            id TEXT PRIMARY KEY,
            record_id TEXT REFERENCES story_memory_translation_records(id)
                ON DELETE SET NULL,
            page_uuid TEXT NOT NULL,
            block_uuid TEXT NOT NULL,
            source_lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            source_text TEXT NOT NULL,
            normalized_source_text TEXT NOT NULL,
            target_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'approved'
                CHECK (status IN ('approved', 'superseded')),
            origin TEXT NOT NULL DEFAULT 'page_review',
            is_preferred INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0, 1)),
            supersedes_id TEXT REFERENCES story_memory_translation_memory(id)
                ON DELETE RESTRICT,
            approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_memory_approval_events (
            id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL REFERENCES story_memory_translation_records(id)
                ON DELETE RESTRICT,
            translation_memory_id TEXT REFERENCES story_memory_translation_memory(id)
                ON DELETE SET NULL,
            page_uuid TEXT NOT NULL,
            action TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS story_memory_import_receipts (
            id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_fingerprint TEXT NOT NULL,
            canon_entries_imported INTEGER NOT NULL DEFAULT 0,
            translation_memory_imported INTEGER NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_path, source_fingerprint)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_story_memory_canon_lookup
        ON story_memory_canon_entries(
            source_lang, target_lang, is_active, normalized_source_term
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_story_memory_brief_language
        ON story_memory_briefs(source_lang, target_lang)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_story_memory_record_block
        ON story_memory_translation_records(
            page_uuid, block_uuid, source_lang, target_lang
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_story_memory_translation_lookup
        ON story_memory_translation_memory(
            source_lang, target_lang, status, normalized_source_text
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_story_memory_approval_record
        ON story_memory_approval_events(record_id, created_at)
        """
    )


_MIGRATIONS: tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...] = (
    (1, _migration_001_initial_schema),
)


def initialize_story_memory_schema(conn: sqlite3.Connection) -> int:
    """Apply ordered Story Memory migrations using a nested transaction."""
    _ensure_meta_table(conn)
    current_version = _read_schema_version(conn)
    if current_version > STORY_MEMORY_SCHEMA_VERSION:
        raise ValueError(
            "Project uses a newer Story Memory schema "
            f"({current_version}) than this application supports "
            f"({STORY_MEMORY_SCHEMA_VERSION})"
        )

    for version, migration in _MIGRATIONS:
        if version <= current_version:
            continue

        conn.execute("SAVEPOINT story_memory_schema_migration")
        try:
            migration(conn)
            _record_schema_version(conn, version)
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT story_memory_schema_migration")
            conn.execute("RELEASE SAVEPOINT story_memory_schema_migration")
            raise
        else:
            conn.execute("RELEASE SAVEPOINT story_memory_schema_migration")
        current_version = version

    return current_version
