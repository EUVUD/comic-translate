from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# A lightweight import test installs only a QtCore stub.  This dialog test uses
# real QtWidgets, so restore the real package when discovery shares one process.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from PySide6 import QtWidgets

from app.projects.project_state_v2 import close_cached_connection
from app.projects.story_memory_repository import LanguagePair, StoryMemoryRepository
from app.ui.story_memory_dialog import StoryMemoryDialog


class StoryMemoryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self._project_path = Path(self._temporary_directory.name) / "story-memory.ctpr"
        self.repository = StoryMemoryRepository.for_project_file(str(self._project_path))
        self.language_pair = LanguagePair("Japanese", "English")

    def tearDown(self) -> None:
        close_cached_connection(str(self._project_path))
        self._temporary_directory.cleanup()

    def test_save_enables_project_memory_and_persists_bounded_brief(self):
        dialog = StoryMemoryDialog(self.repository, self.language_pair)
        dialog.enabled_checkbox.setChecked(True)
        dialog.brief_edit.setPlainText("A short school comedy.")

        dialog._save()

        self.assertTrue(dialog.changes_saved)
        self.assertTrue(self.repository.get_metadata().enabled)
        self.assertEqual(
            self.repository.get_brief(self.language_pair).content,
            "A short school comedy.",
        )


if __name__ == "__main__":
    unittest.main()
