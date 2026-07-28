from __future__ import annotations

import sqlite3
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

import msgpack
import numpy as np

# Existing lightweight tests install a partial PySide6 stub in sys.modules.
# This persistence test exercises the real project parser, so restore PySide6
# before importing application modules when test discovery runs in one process.
sys.modules.pop("PySide6.QtCore", None)
sys.modules.pop("PySide6", None)

from app.projects.parsers import ProjectEncoder
from app.projects.project_state_v2 import (
    _init_schema,
    close_cached_connection,
    ensure_lazy_blob_materialized,
    load_state_from_proj_file_v2,
    register_lazy_blob_path,
    remap_project_file_path,
    save_state_to_proj_file_v2,
)
from app.projects.story_memory_repository import (
    DraftTranslationRecord,
    LanguagePair,
    NewCanonEntry,
    NewImportReceipt,
    NewStoryBrief,
    NewTranslationMemoryEntry,
    StoryMemoryRepository,
)
from modules.utils.textblock import TextBlock


class _SettingsPage:
    def __init__(self, extra_context: str):
        self._extra_context = extra_context

    def get_llm_settings(self):
        return {"extra_context": self._extra_context}


def _project_shell(temp_dir: str, extra_context: str = ""):
    return SimpleNamespace(
        temp_dir=temp_dir,
        image_data={},
        in_memory_history={},
        image_history={},
        current_history_index={},
        image_files=[],
        image_states={},
        image_patches={},
        curr_img_idx=0,
        displayed_images=set(),
        loaded_images=[],
        settings_page=_SettingsPage(extra_context),
        webtoon_mode=False,
        image_viewer=SimpleNamespace(webtoon_view_state={}),
    )


def _write_legacy_project(path: Path) -> None:
    block = TextBlock(
        text_bbox=np.array([1, 2, 30, 40]),
        text="legacy source",
        translation="legacy target",
    )
    state = {
        "current_image_index": 0,
        "original_image_files": [],
        "current_history_index": {},
        "displayed_images": [],
        "loaded_images": [],
        "llm_extra_context": "legacy instruction",
        "webtoon_mode": False,
        "webtoon_view_state": {},
        "unique_images": {},
        "image_states": {
            "legacy-page.png": {
                "blk_list": [block],
                "source_lang": "Japanese",
                "target_lang": "English",
            }
        },
        "image_patches": {},
    }
    payload = msgpack.packb(state, default=ProjectEncoder().encode, use_bin_type=True)

    with sqlite3.connect(path) as conn:
        _init_schema(conn)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?)",
            ("project_format_version", "2"),
        )
        conn.execute(
            "INSERT INTO project_state(id, state_blob) VALUES(1, ?)",
            (sqlite3.Binary(payload),),
        )


_STORY_MEMORY_PAIR = LanguagePair("Japanese", "English")
_IMPORT_SOURCE_PATH = "/fixtures/legacy.ctmem.sqlite"
_IMPORT_FINGERPRINT = "legacy-sidecar-fixture"


def _story_memory_snapshot(project_path: Path) -> dict:
    repository = StoryMemoryRepository.for_project_file(str(project_path))
    metadata = repository.get_metadata()
    brief = repository.get_brief(_STORY_MEMORY_PAIR)
    receipt = repository.get_import_receipt(_IMPORT_SOURCE_PATH, _IMPORT_FINGERPRINT)
    if brief is None or receipt is None:
        raise AssertionError("Expected the seeded Story Memory data to be present")

    return {
        "metadata": (
            metadata.project_uuid,
            metadata.enabled,
            metadata.memory_revision,
            metadata.assembler_version,
        ),
        "canon": [
            (
                entry.id,
                entry.source_lang,
                entry.target_lang,
                entry.source_term,
                entry.normalized_source_term,
                entry.target_term,
                entry.category,
                entry.behavior,
                entry.notes,
                entry.is_active,
            )
            for entry in repository.list_canon(_STORY_MEMORY_PAIR)
        ],
        "brief": (brief.id, brief.source_lang, brief.target_lang, brief.content),
        "records": [
            (
                record.id,
                record.page_uuid,
                record.block_uuid,
                record.source_lang,
                record.target_lang,
                record.source_text,
                record.model_translation,
                record.current_translation,
                record.review_status,
                record.matched_entry_ids,
            )
            for record in repository.list_translation_records(_STORY_MEMORY_PAIR)
        ],
        "translation_memory": [
            (
                entry.id,
                entry.record_id,
                entry.page_uuid,
                entry.block_uuid,
                entry.source_lang,
                entry.target_lang,
                entry.source_text,
                entry.normalized_source_text,
                entry.target_text,
                entry.status,
                entry.origin,
                entry.is_preferred,
                entry.supersedes_id,
            )
            for entry in repository.list_translation_memory(
                _STORY_MEMORY_PAIR,
                statuses=("approved", "superseded"),
            )
        ],
        "receipt": (
            receipt.id,
            receipt.source_path,
            receipt.source_fingerprint,
            receipt.canon_entries_imported,
            receipt.translation_memory_imported,
        ),
    }


def _seed_story_memory(project_path: Path, page_state: dict) -> dict:
    repository = StoryMemoryRepository.for_project_file(str(project_path))
    repository.set_enabled(True)
    canon = repository.create_canon(
        NewCanonEntry(
            _STORY_MEMORY_PAIR,
            "太郎",
            "Taro",
            category="character",
            notes="The lead character.",
        )
    )
    repository.upsert_brief(NewStoryBrief(_STORY_MEMORY_PAIR, "A school comedy."))
    block = page_state["blk_list"][0]
    record = repository.create_draft_record(
        DraftTranslationRecord(
            _STORY_MEMORY_PAIR,
            page_state["page_uuid"],
            block.block_uuid,
            block.text,
            model_translation=block.translation,
            current_translation=block.translation,
            matched_entry_ids=(canon.id,),
        )
    )
    repository.create_translation_memory(
        NewTranslationMemoryEntry(
            _STORY_MEMORY_PAIR,
            page_state["page_uuid"],
            block.block_uuid,
            block.text,
            block.translation,
            record_id=record.id,
        )
    )
    repository.record_import_receipt(
        NewImportReceipt(_IMPORT_SOURCE_PATH, _IMPORT_FINGERPRINT, 1, 1)
    )
    return _story_memory_snapshot(project_path)


def _load_seeded_current_project(project_path: Path, temp_dir: str):
    _write_legacy_project(project_path)
    project = _project_shell(temp_dir)
    project.settings_page._extra_context = load_state_from_proj_file_v2(
        project,
        str(project_path),
    )
    page_state = project.image_states["legacy-page.png"]
    snapshot = _seed_story_memory(project_path, page_state)
    save_state_to_proj_file_v2(project, str(project_path))
    return project, page_state["page_uuid"], page_state["blk_list"][0].block_uuid, snapshot


class ProjectStateV2CompatibilityTests(unittest.TestCase):
    def assert_uuid(self, value: str):
        self.assertEqual(str(uuid.UUID(value)), value)

    def test_legacy_state_blob_loads_and_round_trips_to_page_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "legacy.ctpr"
            _write_legacy_project(project_path)

            loaded = _project_shell(tmp)
            saved_context = load_state_from_proj_file_v2(loaded, str(project_path))
            self.assertEqual(saved_context, "legacy instruction")
            loaded.settings_page._extra_context = saved_context
            block = loaded.image_states["legacy-page.png"]["blk_list"][0]
            self.assertEqual((block.text, block.translation), ("legacy source", "legacy target"))

            save_state_to_proj_file_v2(loaded, str(project_path))
            close_cached_connection(str(project_path))
            with sqlite3.connect(project_path) as conn:
                self.assertIsNotNone(
                    conn.execute("SELECT manifest_blob FROM project_manifest WHERE id = 1").fetchone()
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM page_state").fetchone()[0],
                    1,
                )

            reopened = _project_shell(tmp)
            self.assertEqual(
                load_state_from_proj_file_v2(reopened, str(project_path)),
                "legacy instruction",
            )
            reopened_block = reopened.image_states["legacy-page.png"]["blk_list"][0]
            self.assertEqual(
                (reopened_block.text, reopened_block.translation),
                ("legacy source", "legacy target"),
            )
            close_cached_connection(str(project_path))

    def test_round_trip_to_new_project_file_preserves_legacy_page_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.ctpr"
            destination_path = Path(tmp) / "saved-as.ctpr"
            _write_legacy_project(source_path)

            source = _project_shell(tmp)
            source.settings_page._extra_context = load_state_from_proj_file_v2(
                source, str(source_path)
            )
            save_state_to_proj_file_v2(source, str(destination_path))
            close_cached_connection(str(source_path))
            close_cached_connection(str(destination_path))

            reopened = _project_shell(tmp)
            self.assertEqual(
                load_state_from_proj_file_v2(reopened, str(destination_path)),
                "legacy instruction",
            )
            page_state = reopened.image_states["legacy-page.png"]
            self.assertEqual(page_state["source_lang"], "Japanese")
            self.assertEqual(page_state["target_lang"], "English")
            self.assertEqual(page_state["blk_list"][0].translation, "legacy target")
            close_cached_connection(str(destination_path))

    def test_legacy_project_gets_stable_project_page_and_block_uuids(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "legacy.ctpr"
            _write_legacy_project(project_path)

            loaded = _project_shell(tmp)
            loaded.settings_page._extra_context = load_state_from_proj_file_v2(
                loaded, str(project_path)
            )
            page_state = loaded.image_states["legacy-page.png"]
            page_uuid = page_state["page_uuid"]
            block = page_state["blk_list"][0]
            block_uuid = block.block_uuid
            self.assert_uuid(page_uuid)
            self.assert_uuid(block_uuid)
            self.assertEqual(block.deep_copy().block_uuid, block_uuid)

            save_state_to_proj_file_v2(loaded, str(project_path))
            close_cached_connection(str(project_path))
            with sqlite3.connect(project_path) as conn:
                project_uuid = conn.execute(
                    "SELECT value FROM meta WHERE key = ?",
                    ("story_memory_project_uuid",),
                ).fetchone()[0]
            self.assert_uuid(project_uuid)

            reopened = _project_shell(tmp)
            load_state_from_proj_file_v2(reopened, str(project_path))
            reopened_state = reopened.image_states["legacy-page.png"]
            self.assertEqual(reopened_state["page_uuid"], page_uuid)
            self.assertEqual(reopened_state["blk_list"][0].block_uuid, block_uuid)
            close_cached_connection(str(project_path))

    def test_normal_save_and_reopen_preserve_story_memory_and_identifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "story-memory.ctpr"
            _, page_uuid, block_uuid, expected_snapshot = _load_seeded_current_project(
                project_path,
                tmp,
            )
            close_cached_connection(str(project_path))

            reopened = _project_shell(str(Path(tmp) / "reopened-normal"))
            load_state_from_proj_file_v2(reopened, str(project_path))
            reopened_state = reopened.image_states["legacy-page.png"]
            self.assertEqual(_story_memory_snapshot(project_path), expected_snapshot)
            self.assertEqual(reopened_state["page_uuid"], page_uuid)
            self.assertEqual(reopened_state["blk_list"][0].block_uuid, block_uuid)
            close_cached_connection(str(project_path))

    def test_save_as_replaces_destination_memory_and_survives_source_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.ctpr"
            destination_path = Path(tmp) / "saved-as.ctpr"
            source, page_uuid, block_uuid, expected_snapshot = _load_seeded_current_project(
                source_path,
                tmp,
            )

            unrelated_destination = StoryMemoryRepository.for_project_file(str(destination_path))
            unrelated_destination.create_canon(
                NewCanonEntry(LanguagePair("Korean", "English"), "주인공", "Hero")
            )
            close_cached_connection(str(destination_path))

            save_state_to_proj_file_v2(
                source,
                str(destination_path),
                source_project_file=str(source_path),
            )
            close_cached_connection(str(source_path))
            close_cached_connection(str(destination_path))
            source_path.unlink()

            reopened = _project_shell(str(Path(tmp) / "reopened-save-as"))
            load_state_from_proj_file_v2(reopened, str(destination_path))
            reopened_state = reopened.image_states["legacy-page.png"]
            destination_repository = StoryMemoryRepository.for_project_file(str(destination_path))
            self.assertEqual(_story_memory_snapshot(destination_path), expected_snapshot)
            self.assertEqual(
                destination_repository.list_canon(LanguagePair("Korean", "English")),
                [],
            )
            self.assertEqual(reopened_state["page_uuid"], page_uuid)
            self.assertEqual(reopened_state["blk_list"][0].block_uuid, block_uuid)
            close_cached_connection(str(destination_path))

    def test_closed_project_file_copy_reopens_without_the_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.ctpr"
            copied_path = Path(tmp) / "copied.ctpr"
            _, page_uuid, block_uuid, expected_snapshot = _load_seeded_current_project(
                source_path,
                tmp,
            )
            close_cached_connection(str(source_path))
            shutil.copy2(source_path, copied_path)
            source_path.unlink()

            reopened = _project_shell(str(Path(tmp) / "reopened-copy"))
            load_state_from_proj_file_v2(reopened, str(copied_path))
            reopened_state = reopened.image_states["legacy-page.png"]
            self.assertEqual(_story_memory_snapshot(copied_path), expected_snapshot)
            self.assertEqual(reopened_state["page_uuid"], page_uuid)
            self.assertEqual(reopened_state["blk_list"][0].block_uuid, block_uuid)
            close_cached_connection(str(copied_path))

    def test_remapped_lazy_blob_reads_from_destination_after_source_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = Path(tmp) / "source.ctpr"
            destination_path = Path(tmp) / "saved-as.ctpr"
            lazy_path = Path(tmp) / "materialized" / "page.bin"
            blob_hash = "story-memory-lazy-blob"
            blob_data = b"saved-project-blob"

            for project_path in (source_path, destination_path):
                with sqlite3.connect(project_path) as conn:
                    _init_schema(conn)
                    conn.execute(
                        "INSERT INTO blobs(hash, kind, ext, size, data) VALUES(?, ?, ?, ?, ?)",
                        (blob_hash, "image", ".bin", len(blob_data), blob_data),
                    )

            register_lazy_blob_path(str(source_path), str(lazy_path), blob_hash)
            remap_project_file_path(str(source_path), str(destination_path))
            source_path.unlink()

            self.assertTrue(ensure_lazy_blob_materialized(str(lazy_path)))
            self.assertEqual(lazy_path.read_bytes(), blob_data)
            close_cached_connection(str(destination_path))


if __name__ == "__main__":
    unittest.main()
