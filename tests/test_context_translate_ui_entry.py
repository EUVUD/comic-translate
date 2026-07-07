import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContextTranslateUiEntryTests(unittest.TestCase):
    def test_context_translate_button_is_wired_to_workflow(self):
        workspace = (ROOT / "app/ui/main_window/builders/workspace.py").read_text()
        controller = (ROOT / "controller.py").read_text()
        manual_workflow = (ROOT / "app/controllers/manual_workflow.py").read_text()

        self.assertIn("context_translate_button", workspace)
        self.assertIn("Context Translate", workspace)
        self.assertIn("self.context_translate_button.setEnabled(True)", workspace)
        self.assertIn("self.context_translate_button.setEnabled(True)", controller)
        self.assertIn(
            "self.context_translate_button.clicked.connect("
            "self.translate_image_with_context_workflow)",
            controller,
        )
        self.assertIn("def translate_image_with_context_workflow", controller)
        self.assertIn("def translate_image_with_context_workflow", manual_workflow)
        self.assertIn("validate_custom_translator", manual_workflow)
        self.assertIn(
            "self.main.pipeline.translate_image_with_context_workflow,",
            manual_workflow,
        )


if __name__ == "__main__":
    unittest.main()
