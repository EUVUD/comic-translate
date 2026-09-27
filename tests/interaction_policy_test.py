from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# pipeline_config_test installs import stubs (modules without ``__file__``) that
# stay in sys.modules while discovery shares one process. Drop them so the real
# modules load.
for _name in ("PySide6", "PySide6.QtCore", "app.ui.messages"):
    if _name in sys.modules and not getattr(sys.modules[_name], "__file__", None):
        del sys.modules[_name]

from PySide6 import QtWidgets

from app.ui import interaction
from app.ui.messages import Messages


class _RecordingPolicy:
    def __init__(self, result: int = 0) -> None:
        self.result = result
        self.prompts: list[tuple[str, QtWidgets.QDialog]] = []

    def run_modal(self, dialog, prompt_id):
        self.prompts.append((prompt_id, dialog))
        return self.result


class _FakeDialog:
    def __init__(self, result: int) -> None:
        self.result = result
        self.exec_calls = 0

    def exec(self):
        self.exec_calls += 1
        return self.result


class InteractionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def tearDown(self) -> None:
        interaction.set_interaction_policy(None)

    def test_default_policy_shows_the_dialog(self):
        dialog = _FakeDialog(result=7)

        self.assertIsInstance(interaction.get_interaction_policy(), interaction.GuiInteractionPolicy)
        self.assertEqual(interaction.run_modal(dialog, "any.prompt"), 7)
        self.assertEqual(dialog.exec_calls, 1)

    def test_installed_policy_answers_instead_of_showing(self):
        policy = _RecordingPolicy(result=1)
        dialog = _FakeDialog(result=7)
        interaction.set_interaction_policy(policy)

        self.assertEqual(interaction.run_modal(dialog, "some.prompt"), 1)
        self.assertEqual(dialog.exec_calls, 0)
        self.assertEqual([prompt_id for prompt_id, _ in policy.prompts], ["some.prompt"])

        interaction.set_interaction_policy(None)
        self.assertIsInstance(interaction.get_interaction_policy(), interaction.GuiInteractionPolicy)

    def test_error_dialog_goes_through_the_policy(self):
        policy = _RecordingPolicy()
        interaction.set_interaction_policy(policy)

        Messages.show_error_with_copy(None, "Error", "Something failed", "Traceback ...")

        prompt_id, dialog = policy.prompts[0]
        self.assertEqual(prompt_id, "messages.error_details")
        self.assertIsInstance(dialog, QtWidgets.QMessageBox)
        self.assertEqual(dialog.text(), "Something failed")


if __name__ == "__main__":
    unittest.main()
