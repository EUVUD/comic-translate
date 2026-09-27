from __future__ import annotations

import os
import sys
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# A lightweight import test installs only a QtCore stub; the factories need the
# real package when discovery shares one process.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from modules.detection.factory import DetectionEngineFactory
from modules.ocr.factory import OCRFactory
from modules.translation.factory import TranslationFactory
from modules.utils import engine_overrides
from pipeline.inpainting import InpaintingHandler
from pipeline.webtoon_batch.chunk import ChunkMixin


class _Recorder:
    """Override factory that records its arguments and returns a marker engine."""

    def __init__(self, name: str) -> None:
        self.engine = SimpleNamespace(name=name)
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.engine


class EngineOverrideRegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        engine_overrides.clear()

    def test_create_returns_none_without_a_registration(self):
        self.assertIsNone(engine_overrides.create("ocr", object(), "Japanese", "Default"))

    def test_registered_factory_receives_the_arguments(self):
        recorder = _Recorder("ocr")
        engine_overrides.register("ocr", recorder)

        self.assertIs(engine_overrides.create("ocr", "settings", "Japanese", "Default"), recorder.engine)
        self.assertEqual(recorder.calls, [("settings", "Japanese", "Default")])

    def test_unknown_kind_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown engine kind"):
            engine_overrides.register("rendering", _Recorder("x"))

    def test_clear_removes_every_override(self):
        engine_overrides.register("translation", _Recorder("translation"))
        engine_overrides.clear()

        self.assertIsNone(engine_overrides.create("translation", None, "a", "b", "c"))


class FactoryOverrideTests(unittest.TestCase):
    """Each engine factory returns the registered override before any real work."""

    def setUp(self) -> None:
        # Real engines are never built here: the override is checked first, so
        # these settings only need to exist.
        self.settings = SimpleNamespace(get_tool_selection=lambda kind: "LaMa")

    def tearDown(self) -> None:
        engine_overrides.clear()

    def test_detection_factory(self):
        recorder = _Recorder("detector")
        engine_overrides.register("detection", recorder)

        engine = DetectionEngineFactory.create_engine(self.settings, "RT-DETR-v2")

        self.assertIs(engine, recorder.engine)
        self.assertEqual(recorder.calls, [(self.settings, "RT-DETR-v2")])

    def test_ocr_factory(self):
        recorder = _Recorder("ocr")
        engine_overrides.register("ocr", recorder)

        engine = OCRFactory.create_engine(self.settings, "Japanese", "Default")

        self.assertIs(engine, recorder.engine)
        self.assertEqual(recorder.calls, [(self.settings, "Japanese", "Default")])

    def test_translation_factory(self):
        recorder = _Recorder("translator")
        engine_overrides.register("translation", recorder)

        engine = TranslationFactory.create_engine(self.settings, "Japanese", "English", "GPT-4.1")

        self.assertIs(engine, recorder.engine)
        self.assertEqual(recorder.calls, [(self.settings, "Japanese", "English", "GPT-4.1")])

    def test_regular_inpainting_handler(self):
        recorder = _Recorder("inpainter")
        engine_overrides.register("inpainting", recorder)
        handler = InpaintingHandler(SimpleNamespace(settings_page=self.settings))

        self.assertIs(handler._ensure_inpainter(), recorder.engine)
        self.assertIs(handler._ensure_inpainter(), recorder.engine)
        self.assertEqual(recorder.calls, [(self.settings, "LaMa")])  # built once, then cached

    def test_webtoon_batch_inpainter(self):
        recorder = _Recorder("inpainter")
        engine_overrides.register("inpainting", recorder)
        inpainting = SimpleNamespace(inpainter_cache=None, cached_inpainter_key=None)
        processor = SimpleNamespace(main_page=SimpleNamespace(settings_page=self.settings), inpainting=inpainting)

        ChunkMixin._ensure_inpainter(processor)

        self.assertIs(inpainting.inpainter_cache, recorder.engine)
        self.assertEqual(inpainting.cached_inpainter_key, "LaMa")


if __name__ == "__main__":
    unittest.main()
