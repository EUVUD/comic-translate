from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

# A lightweight import test can leave a partial Qt stub in sys.modules.  Batch
# processing imports real Qt classes, so restore the installed package here.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from app.projects.project_state_v2 import close_cached_connection
from app.projects.story_memory_repository import (
    LanguagePair,
    NewCanonEntry,
    StoryMemoryRepository,
)
from modules.utils.textblock import TextBlock
from pipeline.batch_processor import BatchProcessor
from pipeline.cache_manager import CacheManager


class _Signal:
    def __init__(self) -> None:
        self.calls = []

    def emit(self, *args) -> None:
        self.calls.append(args)


class _Settings:
    def get_llm_settings(self):
        return {"extra_context": "Keep dialogue casual."}

    def get_tool_selection(self, name):
        return {"ocr": "Default", "translator": "GPT-4.1"}[name]

    def is_gpu_enabled(self):
        return False


class _FileHandler:
    archive_info = []

    def should_pre_materialize(self, _paths):
        return False


class _Worker:
    is_cancelled = False


class _Detector:
    def __init__(self, _settings, block) -> None:
        self.block = block

    def detect(self, _image):
        return [self.block]


class _BlockDetection:
    def __init__(self) -> None:
        self.block_detector_cache = None

    def annotate_language_if_auto(self, _image, _blocks, _source_lang):
        return None


class _OCR:
    def initialize(self, _main_page, _source_lang):
        return None

    def process(self, _image, _blocks):
        return None


class _OCRHandler:
    ocr = _OCR()


class _CapturingTranslator:
    supports_context = True
    is_llm_engine = False
    configuration_fingerprint = "account-backed-llm-config"

    def __init__(self, main_page) -> None:
        self.main_page = main_page
        self.calls = []

    def translate(self, blocks, image, extra_context):
        self.calls.append((list(blocks), image, extra_context))
        for block in blocks:
            block.translation = "Taro arrived."
        # The production processor checks cancellation before the rendering
        # stages, allowing this focused test to exercise its real translate
        # boundary without inpainting or file output.
        self.main_page.current_worker.is_cancelled = True
        return blocks


class _TraditionalTranslator(_CapturingTranslator):
    supports_context = False
    configuration_fingerprint = "traditional-config"


class _MainPage:
    def __init__(self, project_file: str, image_path: str) -> None:
        self.project_file = project_file
        self.image_files = [image_path]
        self.curr_img_idx = 0
        self.image_states = {
            image_path: {
                "source_lang": "Japanese",
                "target_lang": "English",
                "page_uuid": "page-1",
            }
        }
        self.blk_list = []
        self.file_handler = _FileHandler()
        self.settings_page = _Settings()
        self.current_worker = _Worker()
        self.progress_update = _Signal()
        self.image_skipped = _Signal()


class BatchProcessorStoryMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._project_path = Path(self._temporary_directory.name) / "story-memory.ctpr"
        self._image_path = str(Path(self._temporary_directory.name) / "page.png")
        self.repository = StoryMemoryRepository.for_project_file(str(self._project_path))
        pair = LanguagePair("Japanese", "English")
        self.repository.set_enabled(True)
        self.repository.create_canon(NewCanonEntry(pair, "太郎", "Taro"))

    def tearDown(self) -> None:
        close_cached_connection(str(self._project_path))
        self._temporary_directory.cleanup()

    @staticmethod
    def _block() -> TextBlock:
        return TextBlock(
            text_bbox=np.array([0, 0, 8, 8]),
            text="太郎が来た",
            block_uuid="block-1",
        )

    def test_translate_all_passes_matching_project_memory_to_account_backed_llm(self):
        main_page = _MainPage(str(self._project_path), self._image_path)
        translator = _CapturingTranslator(main_page)
        block = self._block()
        processor = BatchProcessor(
            main_page,
            CacheManager(),
            _BlockDetection(),
            object(),
            _OCRHandler(),
        )
        with patch(
            "pipeline.batch_processor.TextBlockDetector",
            side_effect=lambda settings: _Detector(settings, block),
        ), patch(
            "pipeline.batch_processor.Translator",
            side_effect=lambda *_args: translator,
        ), patch("pipeline.batch_processor.ensure_path_materialized"), patch(
            "pipeline.batch_processor.imk.read_image",
            return_value=np.zeros((12, 12, 3), dtype=np.uint8),
        ):
            processor.batch_process()

        self.assertEqual(len(translator.calls), 1)
        self.assertIn("[Canon constraints]", translator.calls[0][2])
        self.assertIn("太郎 -> Taro", translator.calls[0][2])
        self.assertIn("Keep dialogue casual.", translator.calls[0][2])
        self.assertEqual(block.translation, "Taro arrived.")

    def test_translate_all_keeps_traditional_translator_context_unchanged(self):
        main_page = _MainPage(str(self._project_path), self._image_path)
        translator = _TraditionalTranslator(main_page)
        block = self._block()
        processor = BatchProcessor(
            main_page,
            CacheManager(),
            _BlockDetection(),
            object(),
            _OCRHandler(),
        )
        with patch(
            "pipeline.batch_processor.TextBlockDetector",
            side_effect=lambda settings: _Detector(settings, block),
        ), patch(
            "pipeline.batch_processor.Translator",
            side_effect=lambda *_args: translator,
        ), patch("pipeline.batch_processor.ensure_path_materialized"), patch(
            "pipeline.batch_processor.imk.read_image",
            return_value=np.zeros((12, 12, 3), dtype=np.uint8),
        ):
            processor.batch_process()

        self.assertEqual(len(translator.calls), 1)
        self.assertEqual(translator.calls[0][2], "Keep dialogue casual.")


if __name__ == "__main__":
    unittest.main()
