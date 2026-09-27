from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from agent.app_api.observations import snapshot, write_snapshot


@dataclass
class _Block:
    translation: str = ""


@dataclass
class _Prompt:
    prompt_id: str | None
    title: str
    buttons: list[str] = field(default_factory=list)


def _window(*, webtoon_mode: bool = False) -> SimpleNamespace:
    """Stand-in exposing the attributes ``snapshot`` reads from ComicTranslate."""
    selections = {"translator": "自定义", "ocr": "Default", "inpainter": "LaMa", "detector": "RT-DETR-v2"}
    settings_page = SimpleNamespace(
        ui=SimpleNamespace(value_mappings={"自定义": "Custom"}),
        get_tool_selection=selections.__getitem__,
        is_gpu_enabled=lambda: False,
    )
    return SimpleNamespace(
        settings_page=settings_page,
        project_file="/sandbox/vol1.ctpr",
        has_unsaved_changes=lambda: True,
        webtoon_mode=webtoon_mode,
        curr_img_idx=0,
        image_files=["/sandbox/inputs/01.png", "/sandbox/inputs/02.png"],
        image_states={
            "/sandbox/inputs/01.png": {
                "blk_list": [_Block("saved earlier")],
                "viewer_state": {"text_items_state": []},
                "source_lang": "Japanese",
                "target_lang": "English",
            },
            "/sandbox/inputs/02.png": {
                "blk_list": [_Block("one"), _Block("  "), _Block("two")],
                "viewer_state": {"text_items_state": [{}, {}]},
                "source_lang": "Japanese",
                "target_lang": "English",
                "skip": True,
            },
        },
        # Live state of the displayed page (index 0), not yet saved back.
        blk_list=[_Block("hello"), _Block("")],
        image_viewer=SimpleNamespace(text_items=[object()]),
        batch_report_ctrl=SimpleNamespace(_latest_batch_report={
            "finished_at": datetime(2026, 9, 27, 12, 30),
            "completed_count": 1,
            "skipped_count": 1,
            "skipped_entries": [{"image_path": "/sandbox/inputs/02.png", "reasons": ["OCR"]}],
        }),
    )


class SnapshotTests(unittest.TestCase):
    def test_settings_use_canonical_tool_names(self):
        settings = snapshot(_window())["settings"]

        self.assertEqual(settings["translator"], "Custom")
        self.assertEqual(settings["ocr"], "Default")
        self.assertFalse(settings["use_gpu"])

    def test_displayed_page_reports_live_state(self):
        pages = snapshot(_window())["pages"]

        self.assertEqual(pages[0]["blocks"], 2)
        self.assertEqual(pages[0]["translated_blocks"], 1)
        self.assertEqual(pages[0]["text_items"], 1)
        self.assertEqual(pages[0]["name"], "01.png")

    def test_other_pages_report_saved_state(self):
        page = snapshot(_window())["pages"][1]

        self.assertEqual(page["blocks"], 3)
        self.assertEqual(page["translated_blocks"], 2)
        self.assertEqual(page["text_items"], 2)
        self.assertTrue(page["skip"])
        self.assertEqual((page["source_lang"], page["target_lang"]), ("Japanese", "English"))

    def test_webtoon_mode_reports_saved_state_for_every_page(self):
        page = snapshot(_window(webtoon_mode=True))["pages"][0]

        self.assertEqual((page["blocks"], page["translated_blocks"], page["text_items"]), (1, 1, 0))

    def test_snapshot_is_json_ready(self):
        data = snapshot(_window(), [_Prompt("messages.error_details", "Error", ["OK"])])

        self.assertEqual(data["batch_report"]["finished_at"], "2026-09-27T12:30:00")
        self.assertEqual(data["prompts"], [
            {"prompt_id": "messages.error_details", "title": "Error", "buttons": ["OK"]},
        ])
        self.assertEqual(json.loads(json.dumps(data)), data)

    def test_write_snapshot_replaces_the_file_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run" / "state.json"
            first = snapshot(_window())
            write_snapshot(first, path)
            second = dict(first, current_page=1)
            write_snapshot(second, path)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), second)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["state.json"])


if __name__ == "__main__":
    unittest.main()
