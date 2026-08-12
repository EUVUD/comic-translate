from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Some lightweight tests install a QtCore-only stub.  The real translation
# factory imports the settings module, which needs the installed PySide6
# package, so restore it before importing the production classes.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from modules.translation.factory import TranslationFactory
from modules.translation.processor import Translator


class _Settings:
    def __init__(self) -> None:
        self.ui = SimpleNamespace(tr=lambda text: text)

    def get_tool_selection(self, name: str) -> str:
        if name != "translator":
            raise AssertionError(f"Unexpected tool selection: {name}")
        return "GPT-4.1"


class _MainPage:
    def __init__(self) -> None:
        self.settings_page = _Settings()
        self.lang_mapping = {"Japanese": "Japanese", "English": "English"}


class _AccountBackedLLMEngine:
    """Minimal UserTranslator-shaped engine without a network request."""

    is_llm = True

    def __init__(self) -> None:
        self.calls = []

    def translate(self, blocks, image=None, extra_context=""):
        self.calls.append((blocks, image, extra_context))
        return blocks


class TranslatorContextCapabilityTests(unittest.TestCase):
    def test_account_backed_llm_receives_image_and_story_memory_context(self):
        engine = _AccountBackedLLMEngine()
        main_page = _MainPage()
        image = object()
        blocks = [object()]

        with patch.object(
            TranslationFactory,
            "configuration_fingerprint",
            return_value="account-llm-config",
        ), patch.object(TranslationFactory, "create_engine", return_value=engine):
            translator = Translator(main_page, "Japanese", "English")

        self.assertFalse(translator.is_llm_engine)
        self.assertTrue(translator.supports_context)
        self.assertEqual(translator.configuration_fingerprint, "account-llm-config")

        self.assertIs(translator.translate(blocks, image, "memory context"), blocks)
        self.assertEqual(engine.calls, [(blocks, image, "memory context")])


if __name__ == "__main__":
    unittest.main()
