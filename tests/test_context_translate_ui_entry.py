import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StoryMemoryUiEntryTests(unittest.TestCase):
    def test_story_memory_button_opens_project_scoped_configuration(self):
        workspace = (ROOT / "app/ui/main_window/builders/workspace.py").read_text()
        controller = (ROOT / "controller.py").read_text()
        manual_workflow = (ROOT / "app/controllers/manual_workflow.py").read_text()

        self.assertIn("context_translate_button", workspace)
        self.assertIn("Story Memory…", workspace)
        self.assertIn("Configure project Story Memory", workspace)
        self.assertIn("self.context_translate_button.setEnabled(True)", workspace)
        self.assertIn("self.context_translate_button.setEnabled(True)", controller)
        self.assertIn(
            "self.context_translate_button.clicked.connect("
            "self.show_story_memory_dialog)",
            controller,
        )
        self.assertIn("def show_story_memory_dialog", controller)
        self.assertIn("is_sqlite_project_file", controller)
        self.assertIn("StoryMemoryDialog", controller)
        self.assertIn("LanguagePair", controller)
        self.assertNotIn("validate_custom_translator", manual_workflow)


if __name__ == "__main__":
    unittest.main()
