from __future__ import annotations

import os
import sys
from types import SimpleNamespace
import unittest

import numpy as np
import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# A lightweight import test installs only a QtCore stub; the engine factories
# need the real package when discovery shares one process.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from evals.fixtures import FixtureProfile, page_fingerprint
from modules.detection.factory import DetectionEngineFactory
from modules.ocr.factory import OCRFactory
from modules.translation.processor import Translator
from modules.utils import engine_overrides
from modules.utils.exceptions import InsufficientCreditsException
from modules.utils.textblock import TextBlock


def _page(value: int) -> np.ndarray:
    return np.full((40, 60, 3), value, dtype=np.uint8)


PAGE = _page(200)
BLANK = _page(10)


def _profile(faults=()) -> FixtureProfile:
    return FixtureProfile({
        "pages": {
            page_fingerprint(PAGE): {"blocks": [
                {"xyxy": [5, 5, 25, 15], "bubble_xyxy": [0, 0, 30, 20], "text": "こんにちは"},
                {"xyxy": [30, 20, 55, 35], "bubble_xyxy": None, "text": "ドン"},
            ]},
        },
        "translations": {"こんにちは": "Hello", "ドン": "BOOM"},
        "faults": list(faults),
    })


class _Settings:
    """What the real Translator wrapper reads from the settings page."""

    ui = SimpleNamespace(tr=lambda text: text)

    def get_tool_selection(self, _kind):
        return "Custom"

    def get_credentials(self, _service):
        return {"api_key": "fixture", "api_url": "http://fixture", "model": "fixture"}

    def get_llm_settings(self):
        return {"extra_context": "", "image_input_enabled": False}

    def is_gpu_enabled(self):
        return False


class PageFingerprintTests(unittest.TestCase):
    def test_same_pixels_share_a_fingerprint(self):
        self.assertEqual(page_fingerprint(_page(200)), page_fingerprint(PAGE))

    def test_different_pixels_or_shapes_differ(self):
        self.assertNotEqual(page_fingerprint(PAGE), page_fingerprint(BLANK))
        self.assertNotEqual(page_fingerprint(PAGE), page_fingerprint(np.full((60, 40, 3), 200, np.uint8)))


class FixtureEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = _profile()
        self.profile.install()
        self.settings = _Settings()

    def tearDown(self) -> None:
        self.profile.uninstall()

    def test_factories_return_the_fixture_engines(self):
        detector = DetectionEngineFactory.create_engine(self.settings, "RT-DETR-v2")
        ocr = OCRFactory.create_engine(self.settings, "Japanese", "Default")

        self.assertEqual(type(detector).__name__, "FixtureDetector")
        self.assertEqual(type(ocr).__name__, "FixtureOCR")

    def test_detection_returns_the_page_blocks(self):
        detector = DetectionEngineFactory.create_engine(self.settings, "RT-DETR-v2")

        blocks = detector.detect(PAGE)

        self.assertEqual([list(block.xyxy) for block in blocks], [[5, 5, 25, 15], [30, 20, 55, 35]])
        self.assertEqual([block.text_class for block in blocks], ["text_bubble", "text_free"])
        self.assertEqual(detector.detect(BLANK), [])

    def test_ocr_reads_text_by_block_position(self):
        ocr = OCRFactory.create_engine(self.settings, "Japanese", "Default")
        blocks = [TextBlock(text_bbox=np.array([31, 21, 55, 35])), TextBlock(text_bbox=np.array([0, 30, 4, 39]))]

        ocr.process_image(PAGE, blocks)

        self.assertEqual([block.text for block in blocks], ["ドン", ""])

    def test_real_translator_wrapper_passes_the_page_image(self):
        main_page = SimpleNamespace(settings_page=self.settings, lang_mapping={})
        translator = Translator(main_page, "Japanese", "English")
        blocks = [TextBlock(text="こんにちは"), TextBlock(text="unknown")]

        translator.translate(blocks, PAGE, "")

        self.assertTrue(translator.supports_context)
        self.assertEqual([block.translation for block in blocks], ["Hello", ""])
        self.assertEqual(self.profile.calls[-1], ("translation", page_fingerprint(PAGE)))

    def test_inpainter_whitens_only_masked_pixels(self):
        inpainter = engine_overrides.create("inpainting", self.settings, "LaMa")
        mask = np.zeros(PAGE.shape[:2], dtype=np.uint8)
        mask[5:15, 5:25] = 255

        result = inpainter(PAGE, mask, None)

        self.assertTrue((result[5:15, 5:25] == 255).all())
        self.assertTrue((result[20:, 30:] == 200).all())
        self.assertTrue((PAGE == 200).all(), "input image must not be modified")


class FaultInjectionTests(unittest.TestCase):
    def tearDown(self) -> None:
        engine_overrides.clear()

    def test_transient_fault_fails_then_succeeds(self):
        profile = _profile([{"stage": "ocr", "page": page_fingerprint(PAGE), "error": "http_500", "times": 1}])
        profile.install()
        ocr = OCRFactory.create_engine(_Settings(), "Japanese", "Default")
        blocks = [TextBlock(text_bbox=np.array([5, 5, 25, 15]))]

        with self.assertRaises(requests.exceptions.HTTPError) as raised:
            ocr.process_image(PAGE, blocks)
        self.assertEqual(raised.exception.response.status_code, 500)

        ocr.process_image(PAGE, blocks)
        self.assertEqual(blocks[0].text, "こんにちは")

    def test_fault_applies_only_to_its_page_and_stage(self):
        profile = _profile([{"stage": "ocr", "page": page_fingerprint(BLANK), "error": "timeout", "times": 3}])
        profile.install()

        engine_overrides.create("detection", _Settings(), "RT-DETR-v2").detect(BLANK)
        engine_overrides.create("ocr", _Settings(), "Japanese", "Default").process_image(PAGE, [])

    def test_each_error_maps_to_the_exception_the_pipeline_handles(self):
        expected = {
            "http_500": requests.exceptions.HTTPError,
            "connection": requests.exceptions.ConnectionError,
            "timeout": requests.exceptions.Timeout,
            "credits": InsufficientCreditsException,
        }
        for error, exception in expected.items():
            with self.subTest(error=error):
                profile = _profile([{"stage": "detection", "page": page_fingerprint(PAGE), "error": error}])
                profile.install()
                with self.assertRaises(exception):
                    engine_overrides.create("detection", None, "RT-DETR-v2").detect(PAGE)

    def test_invalid_faults_are_rejected(self):
        for fault in (
            {"stage": "rendering", "page": "x", "error": "timeout"},
            {"stage": "ocr", "page": "x", "error": "segfault"},
            {"stage": "ocr", "page": "x", "error": "timeout", "times": 0},
        ):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                _profile([fault])

    def test_uninstall_restores_the_real_factories(self):
        profile = _profile()
        profile.install()
        profile.uninstall()

        self.assertIsNone(engine_overrides.create("ocr", None, "Japanese", "Default"))


if __name__ == "__main__":
    unittest.main()
