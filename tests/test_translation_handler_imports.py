import sys
import types
import unittest


class TranslationHandlerImportTests(unittest.TestCase):
    def test_handler_import_does_not_load_langgraph(self):
        qt = types.SimpleNamespace(
            LayoutDirection=types.SimpleNamespace(
                RightToLeft="rtl",
                LeftToRight="ltr",
            )
        )
        sys.modules.setdefault("PySide6", types.ModuleType("PySide6"))
        qtcore = types.ModuleType("PySide6.QtCore")
        qtcore.Qt = qt
        sys.modules.setdefault("PySide6.QtCore", qtcore)

        from pipeline.translation_handler import TranslationHandler

        self.assertTrue(hasattr(TranslationHandler, "translate_image"))
        self.assertFalse("langgraph" in sys.modules)


if __name__ == "__main__":
    unittest.main()
