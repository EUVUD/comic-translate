from __future__ import annotations

import os
import json
import sqlite3


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, name TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
    "CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, path TEXT NOT NULL, page_index INTEGER, UNIQUE(project_id, path), FOREIGN KEY(project_id) REFERENCES projects(id))",
    "CREATE TABLE IF NOT EXISTS text_boxes (id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL, box_key TEXT NOT NULL, source_text TEXT NOT NULL, bbox_json TEXT, status TEXT DEFAULT 'pending', UNIQUE(page_id, box_key), FOREIGN KEY(page_id) REFERENCES pages(id))",
    "CREATE TABLE IF NOT EXISTS translations (id INTEGER PRIMARY KEY, text_box_id INTEGER NOT NULL, model_translation TEXT, checker_feedback TEXT, final_translation TEXT, status TEXT DEFAULT 'draft', created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(text_box_id) REFERENCES text_boxes(id))",
    "CREATE TABLE IF NOT EXISTS glossary_terms (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, source_term TEXT NOT NULL, target_term TEXT NOT NULL, notes TEXT, FOREIGN KEY(project_id) REFERENCES projects(id))",
    "CREATE TABLE IF NOT EXISTS translation_memory (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, source_text TEXT NOT NULL, target_text TEXT NOT NULL, approved INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(project_id) REFERENCES projects(id))",
    "CREATE TABLE IF NOT EXISTS workflow_steps (id INTEGER PRIMARY KEY, text_box_id INTEGER, step_name TEXT NOT NULL, input_json TEXT, output_json TEXT, status TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(text_box_id) REFERENCES text_boxes(id))",
)


def resolve_sidecar_db_path(
    project_file: str | None = None,
    page_path: str | None = None,
) -> str:
    if project_file:
        base, _ = os.path.splitext(os.path.abspath(project_file))
        return f"{base}.ctmem.sqlite"
    if page_path:
        return os.path.join(
            os.path.dirname(os.path.abspath(page_path)),
            "comic_translate_memory.sqlite",
        )
    raise ValueError("project_file or page_path is required")


class ContextTranslationStore:
    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)

    def connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path)

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for statement in SCHEMA:
                conn.execute(statement)

    def upsert_project(self, key: str, name: str | None = None) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO projects(key, name) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET name=excluded.name",
                (key, name),
            )
            row = conn.execute("SELECT id FROM projects WHERE key = ?", (key,)).fetchone()
            return int(row[0])

    def upsert_page(
        self,
        project_id: int,
        path: str,
        page_index: int | None = None,
    ) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pages(project_id, path, page_index) VALUES(?, ?, ?) "
                "ON CONFLICT(project_id, path) DO UPDATE SET page_index=excluded.page_index",
                (project_id, path, page_index),
            )
            row = conn.execute(
                "SELECT id FROM pages WHERE project_id = ? AND path = ?",
                (project_id, path),
            ).fetchone()
            return int(row[0])

    def upsert_text_box(
        self,
        page_id: int,
        box_key: str,
        source_text: str,
        bbox: list[int] | tuple[int, ...] | None = None,
        status: str = "pending",
    ) -> int:
        bbox_json = json.dumps([int(v) for v in bbox]) if bbox is not None else None
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO text_boxes(page_id, box_key, source_text, bbox_json, status) "
                "VALUES(?, ?, ?, ?, ?) ON CONFLICT(page_id, box_key) DO UPDATE SET "
                "source_text=excluded.source_text, bbox_json=excluded.bbox_json, status=excluded.status",
                (page_id, box_key, source_text, bbox_json, status),
            )
            row = conn.execute(
                "SELECT id FROM text_boxes WHERE page_id = ? AND box_key = ?",
                (page_id, box_key),
            ).fetchone()
            return int(row[0])

    def record_workflow_step(
        self,
        text_box_id: int | None,
        step_name: str,
        input_payload: dict | list | None,
        output_payload: dict | list | None,
        status: str,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO workflow_steps(text_box_id, step_name, input_json, output_json, status) "
                "VALUES(?, ?, ?, ?, ?)",
                (
                    text_box_id,
                    step_name,
                    json.dumps(input_payload, ensure_ascii=False),
                    json.dumps(output_payload, ensure_ascii=False),
                    status,
                ),
            )
            return int(cursor.lastrowid)

    def record_translation(
        self,
        text_box_id: int,
        model_translation: str,
        checker_feedback: str = "",
        final_translation: str | None = None,
        status: str = "draft",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO translations(text_box_id, model_translation, checker_feedback, final_translation, status) "
                "VALUES(?, ?, ?, ?, ?)",
                (
                    text_box_id,
                    model_translation,
                    checker_feedback,
                    final_translation if final_translation is not None else model_translation,
                    status,
                ),
            )
            return int(cursor.lastrowid)

    def add_glossary_term(
        self,
        project_id: int,
        source_term: str,
        target_term: str,
        notes: str = "",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO glossary_terms(project_id, source_term, target_term, notes) "
                "VALUES(?, ?, ?, ?)",
                (project_id, source_term, target_term, notes),
            )
            return int(cursor.lastrowid)

    def find_glossary_terms(self, project_id: int, source_texts: list[str]) -> list[dict]:
        haystack = "\n".join(source_texts).lower()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT source_term, target_term, notes FROM glossary_terms WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        return [
            {"source": source, "target": target, "notes": notes or ""}
            for source, target, notes in rows
            if source and source.lower() in haystack
        ]
