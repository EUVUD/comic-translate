from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from app.projects.project_state_v2 import close_cached_connection
from app.projects.story_memory_repository import (
    LanguagePair,
    NewCanonEntry,
    NewStoryBrief,
    StoryMemoryRepository,
)
from modules.translation.llm.base import BaseLLMTranslation
from modules.utils.textblock import TextBlock
from pipeline.cache_manager import CacheManager
from pipeline.translation_handler import TranslationHandler


class _Combo:
    def __init__(self, value: str) -> None:
        self._value = value

    def currentText(self) -> str:
        return self._value


class _ImageViewer:
    def __init__(self, image: np.ndarray) -> None:
        self._image = image

    def hasPhoto(self) -> bool:
        return True

    def get_image_array(self) -> np.ndarray:
        return self._image


class _CapturingLLM(BaseLLMTranslation):
    def __init__(self) -> None:
        super().__init__()
        self.source_lang = "Japanese"
        self.target_lang = "English"
        self.user_prompt = ""
        self.image = None

    def _perform_translation(self, user_prompt, system_prompt, image):
        self.user_prompt = user_prompt
        self.image = image
        return '{"block_0": "Taro arrived."}'


class _CapturingDirectTranslator:
    is_llm_engine = True
    configuration_fingerprint = "direct-llm-config"

    def __init__(self) -> None:
        self.engine = _CapturingLLM()

    def translate(self, blocks, image, extra_context):
        return self.engine.translate(blocks, image, extra_context)


class _AccountBackedLLMTranslator(_CapturingDirectTranslator):
    """Mirrors UserTranslator: context-capable but not an LLM subclass."""

    is_llm_engine = False
    supports_context = True
    configuration_fingerprint = "account-llm-config"


class _TraditionalTranslator:
    is_llm_engine = False
    configuration_fingerprint = "traditional-config"

    def __init__(self) -> None:
        self.contexts = []

    def translate(self, blocks, image, extra_context):
        self.contexts.append(extra_context)
        for block in blocks:
            block.translation = "Traditional result"
        return blocks


class _ExplodingContextService:
    def prepare(self, **kwargs):
        raise AssertionError("traditional translators must not load Story Memory")


class _MainPage:
    def __init__(self, project_file: str, block: TextBlock) -> None:
        self.project_file = project_file
        self.image_files = ["page-1.png"]
        self.curr_img_idx = 0
        self.image_states = {"page-1.png": {"page_uuid": "page-1"}}
        self.blk_list = [block]
        self.s_combo = _Combo("Japanese")
        self.t_combo = _Combo("English")
        self.lang_mapping = {"Japanese": "Japanese", "English": "English"}
        self.image_viewer = _ImageViewer(np.zeros((12, 12, 3), dtype=np.uint8))
        self.settings_page = SimpleNamespace(
            get_llm_settings=lambda: {"extra_context": "Keep dialogue casual."},
            get_tool_selection=lambda name: "GPT-4.1",
            ui=SimpleNamespace(
                uppercase_checkbox=SimpleNamespace(isChecked=lambda: False),
            ),
        )


class _Pipeline:
    def get_selected_block(self):
        return None


class TranslationHandlerStoryMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._project_path = Path(self._temporary_directory.name) / "story-memory.ctpr"
        self.repository = StoryMemoryRepository.for_project_file(str(self._project_path))
        self.language_pair = LanguagePair("Japanese", "English")
        self.repository.set_enabled(True)
        self.repository.upsert_brief(
            NewStoryBrief(self.language_pair, "A school comedy with a warm tone.")
        )
        self.repository.create_canon(
            NewCanonEntry(self.language_pair, "太郎", "Taro")
        )
        self.repository.create_canon(
            NewCanonEntry(self.language_pair, "花子", "Hanako", notes="Must stay local.")
        )

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

    def test_normal_page_translation_passes_matching_memory_to_actual_llm_prompt(self):
        block = self._block()
        main_page = _MainPage(str(self._project_path), block)
        translator = _CapturingDirectTranslator()
        handler = TranslationHandler(
            main_page,
            CacheManager(),
            _Pipeline(),
            translator_builder=lambda *_: translator,
        )

        handler.translate_image()

        prompt = translator.engine.user_prompt
        self.assertIn("[User instructions]", prompt)
        self.assertIn("Keep dialogue casual.", prompt)
        self.assertIn("[Story Brief]", prompt)
        self.assertIn("A school comedy with a warm tone.", prompt)
        self.assertIn("[Canon constraints]", prompt)
        self.assertIn("太郎 -> Taro", prompt)
        self.assertNotIn("花子", prompt)
        self.assertNotIn("Hanako", prompt)
        self.assertIn('"block_0": "太郎が来た"', prompt)
        self.assertIs(translator.engine.image, main_page.image_viewer.get_image_array())
        self.assertEqual(block.translation, "Taro arrived.")

    def test_traditional_translator_keeps_original_context_without_database_lookup(self):
        block = self._block()
        main_page = _MainPage(str(self._project_path), block)
        translator = _TraditionalTranslator()
        handler = TranslationHandler(
            main_page,
            CacheManager(),
            _Pipeline(),
            request_context_service=_ExplodingContextService(),
            translator_builder=lambda *_: translator,
        )

        handler.translate_image()

        self.assertEqual(translator.contexts, ["Keep dialogue casual."])
        self.assertEqual(block.translation, "Traditional result")

    def test_account_backed_llm_proxy_receives_story_memory(self):
        block = self._block()
        main_page = _MainPage(str(self._project_path), block)
        translator = _AccountBackedLLMTranslator()
        handler = TranslationHandler(
            main_page,
            CacheManager(),
            _Pipeline(),
            translator_builder=lambda *_: translator,
        )

        handler.translate_image()

        self.assertIn("太郎 -> Taro", translator.engine.user_prompt)
        self.assertEqual(block.translation, "Taro arrived.")

    def test_visible_webtoon_restores_coordinates_when_context_preparation_fails(self):
        block = self._block()
        main_page = _MainPage(str(self._project_path), block)
        main_page.webtoon_mode = True
        main_page.image_viewer.get_visible_area_image = lambda: (
            np.zeros((12, 12, 3), dtype=np.uint8),
            [{"page_index": 0}],
        )
        translator = _CapturingDirectTranslator()
        handler = TranslationHandler(
            main_page,
            CacheManager(),
            _Pipeline(),
            translator_builder=lambda *_: translator,
        )
        handler._prepare_visible_webtoon_context = lambda *_args: (
            (_ for _ in ()).throw(RuntimeError("context failed"))
        )
        restored = []

        def convert_visible_blocks(*_args):
            block._original_xyxy = block.xyxy.copy()
            block._original_bubble_xyxy = None
            block._mapping = {"page_index": 0}
            block._page_index = 0
            block.xyxy = np.array([2, 2, 10, 10])
            return [block]

        def restore_visible_blocks(blocks):
            restored.extend(blocks)
            for visible_block in blocks:
                visible_block.xyxy = visible_block._original_xyxy

        with patch(
            "pipeline.webtoon_utils.filter_and_convert_visible_blocks",
            side_effect=convert_visible_blocks,
        ), patch(
            "pipeline.webtoon_utils.restore_original_block_coordinates",
            side_effect=restore_visible_blocks,
        ), self.assertRaisesRegex(RuntimeError, "context failed"):
            handler.translate_webtoon_visible_area()

        self.assertEqual(restored, [block])
        self.assertTrue(np.array_equal(block.xyxy, np.array([0, 0, 8, 8])))

    def test_visible_webtoon_restores_coordinates_when_translator_creation_fails(self):
        block = self._block()
        main_page = _MainPage(str(self._project_path), block)
        main_page.webtoon_mode = True
        main_page.image_viewer.get_visible_area_image = lambda: (
            np.zeros((12, 12, 3), dtype=np.uint8),
            [{"page_index": 0}],
        )
        handler = TranslationHandler(
            main_page,
            CacheManager(),
            _Pipeline(),
            translator_builder=lambda *_: (_ for _ in ()).throw(
                RuntimeError("translator creation failed")
            ),
        )
        restored = []

        def convert_visible_blocks(*_args):
            block._original_xyxy = block.xyxy.copy()
            block._original_bubble_xyxy = None
            block._mapping = {"page_index": 0}
            block._page_index = 0
            block.xyxy = np.array([2, 2, 10, 10])
            return [block]

        def restore_visible_blocks(blocks):
            restored.extend(blocks)
            for visible_block in blocks:
                visible_block.xyxy = visible_block._original_xyxy

        with patch(
            "pipeline.webtoon_utils.filter_and_convert_visible_blocks",
            side_effect=convert_visible_blocks,
        ), patch(
            "pipeline.webtoon_utils.restore_original_block_coordinates",
            side_effect=restore_visible_blocks,
        ), self.assertRaisesRegex(RuntimeError, "translator creation failed"):
            handler.translate_webtoon_visible_area()

        self.assertEqual(restored, [block])
        self.assertTrue(np.array_equal(block.xyxy, np.array([0, 0, 8, 8])))


if __name__ == "__main__":
    unittest.main()
