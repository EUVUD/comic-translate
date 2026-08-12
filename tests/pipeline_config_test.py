import sys
import types
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _install_import_stubs():
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.QCoreApplication = type(
        "QCoreApplication",
        (),
        {"translate": staticmethod(lambda _context, text: text)},
    )
    pyside6 = types.ModuleType("PySide6")
    sys.modules.setdefault("PySide6", pyside6)
    sys.modules.setdefault("PySide6.QtCore", qtcore)

    for module_name, class_name in (
        ("modules.inpainting.lama", "LaMa"),
        ("modules.inpainting.mi_gan", "MIGAN"),
        ("modules.inpainting.aot", "AOT"),
    ):
        module = types.ModuleType(module_name)
        setattr(module, class_name, type(class_name, (), {}))
        sys.modules.setdefault(module_name, module)

    schema = types.ModuleType("modules.inpainting.schema")
    schema.Config = type("Config", (), {})
    sys.modules.setdefault("modules.inpainting.schema", schema)

    messages = types.ModuleType("app.ui.messages")
    messages.Messages = type("Messages", (), {})
    sys.modules.setdefault("app.ui.messages", messages)

    settings_page = types.ModuleType("app.ui.settings.settings_page")
    settings_page.SettingsPage = type("SettingsPage", (), {})
    sys.modules.setdefault("app.ui.settings.settings_page", settings_page)


_install_import_stubs()

_MODULE_PATH = Path(__file__).resolve().parents[1] / "modules" / "utils" / "pipeline_config.py"
_SPEC = spec_from_file_location("pipeline_config_under_test", _MODULE_PATH)
pipeline_config = module_from_spec(_SPEC)
_SPEC.loader.exec_module(pipeline_config)


class FakeMessages:
    missing_tool_calls = 0
    not_logged_in_calls = 0

    @classmethod
    def reset(cls):
        cls.missing_tool_calls = 0
        cls.not_logged_in_calls = 0

    @classmethod
    def show_missing_tool_error(cls, *_args):
        cls.missing_tool_calls += 1

    @classmethod
    def show_not_logged_in_error(cls, *_args):
        cls.not_logged_in_calls += 1


class FakeSettingsPage:
    def __init__(self, ocr_tool, logged_in):
        self._ocr_tool = ocr_tool
        self._logged_in = logged_in
        self.ui = type("UI", (), {"tr": staticmethod(lambda text: text)})()

    def get_all_settings(self):
        return {"tools": {"ocr": self._ocr_tool}, "credentials": {}}

    def is_logged_in(self):
        return self._logged_in


class FakeMain:
    def __init__(self, ocr_tool, logged_in=False):
        self.settings_page = FakeSettingsPage(ocr_tool, logged_in)


class FakeTranslatorSettingsPage:
    def __init__(self, translator_tool, logged_in, credentials=None):
        self._translator_tool = translator_tool
        self._logged_in = logged_in
        self._credentials = credentials or {}
        self.ui = type("UI", (), {"tr": staticmethod(lambda text: text)})()

    def get_all_settings(self):
        return {
            "tools": {"translator": self._translator_tool},
            "credentials": self._credentials,
        }

    def is_logged_in(self):
        return self._logged_in


class FakeTranslatorMain:
    def __init__(self, translator_tool, logged_in, credentials=None):
        self.settings_page = FakeTranslatorSettingsPage(
            translator_tool,
            logged_in,
            credentials,
        )


class ValidateOCRTests(unittest.TestCase):
    def setUp(self):
        FakeMessages.reset()
        pipeline_config.Messages = FakeMessages

    def test_default_ocr_does_not_require_login(self):
        self.assertTrue(pipeline_config.validate_ocr(FakeMain("Default")))
        self.assertEqual(FakeMessages.not_logged_in_calls, 0)

    def test_account_backed_ocr_requires_login(self):
        self.assertFalse(pipeline_config.validate_ocr(FakeMain("Microsoft OCR")))
        self.assertEqual(FakeMessages.not_logged_in_calls, 1)

    def test_missing_ocr_tool_still_fails(self):
        self.assertFalse(pipeline_config.validate_ocr(FakeMain("")))
        self.assertEqual(FakeMessages.missing_tool_calls, 1)


class ValidateTranslatorTests(unittest.TestCase):
    def setUp(self):
        FakeMessages.reset()
        pipeline_config.Messages = FakeMessages

    def test_custom_api_does_not_require_account_login(self):
        main = FakeTranslatorMain(
            "Custom",
            logged_in=False,
            credentials={
                "Custom": {
                    "api_key": "local-key",
                    "api_url": "http://localhost:1234/v1",
                    "model": "local-model",
                }
            },
        )

        self.assertTrue(pipeline_config.validate_translator(main, "English"))
        self.assertEqual(FakeMessages.not_logged_in_calls, 0)

    def test_non_custom_translator_still_requires_account_login(self):
        main = FakeTranslatorMain("GPT-4.1", logged_in=False)

        self.assertFalse(pipeline_config.validate_translator(main, "English"))
        self.assertEqual(FakeMessages.not_logged_in_calls, 1)


if __name__ == "__main__":
    unittest.main()
