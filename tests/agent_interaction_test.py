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

from PySide6 import QtCore, QtWidgets

from agent.app_api.interaction import AgentInteractionPolicy
from app.ui import interaction
from app.ui.messages import Messages

Role = QtWidgets.QMessageBox.ButtonRole


def _unsaved_changes_box() -> tuple[QtWidgets.QMessageBox, dict[str, QtWidgets.QAbstractButton]]:
    """Mirror of the application's close prompt."""
    box = QtWidgets.QMessageBox()
    box.setWindowTitle("Unsaved Changes")
    box.setText("Save changes to this file?")
    buttons = {
        "save": box.addButton("Save", Role.AcceptRole),
        "discard": box.addButton("Don't Save", Role.DestructiveRole),
        "cancel": box.addButton("Cancel", Role.RejectRole),
    }
    return box, buttons


class AgentInteractionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        self.failsafe_fired = False

    def tearDown(self) -> None:
        interaction.set_interaction_policy(None)

    def _install(self, answers=None) -> AgentInteractionPolicy:
        policy = AgentInteractionPolicy(answers)
        policy.install()
        self.addCleanup(policy.uninstall)
        return policy

    def _start_failsafe(self) -> None:
        """Reject a stuck modal dialog so a broken guard fails instead of hanging."""
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self._reject_stuck_dialog)
        timer.start(5000)
        self.addCleanup(timer.stop)

    def _reject_stuck_dialog(self) -> None:
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal is not None:
            self.failsafe_fired = True
            modal.reject()

    def test_unanswered_prompt_is_recorded_and_cancelled(self):
        policy = self._install()
        box, _ = _unsaved_changes_box()

        interaction.run_modal(box, "main_window.unsaved_changes")

        self.assertIsNone(box.clickedButton())
        event = policy.events[-1]
        self.assertEqual(event.prompt_id, "main_window.unsaved_changes")
        self.assertEqual(event.title, "Unsaved Changes")
        self.assertEqual(event.text, "Save changes to this file?")
        # Button order follows the platform's layout, not insertion order.
        self.assertCountEqual(event.buttons, ["Save", "Don't Save", "Cancel"])
        self.assertIsNone(event.answer)

    def test_pre_authorized_answer_clicks_the_matching_role(self):
        for answer, expected in (("accept", "save"), ("destructive", "discard"), ("reject", "cancel")):
            with self.subTest(answer=answer):
                policy = self._install({"main_window.unsaved_changes": answer})
                box, buttons = _unsaved_changes_box()

                interaction.run_modal(box, "main_window.unsaved_changes")

                self.assertIs(box.clickedButton(), buttons[expected])
                self.assertEqual(policy.events[-1].answer, answer)
                policy.uninstall()

    def test_unknown_answer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown answers"):
            AgentInteractionPolicy({"main_window.unsaved_changes": "maybe"})

    def test_routed_application_prompt_does_not_block(self):
        policy = self._install()

        Messages.show_error_with_copy(None, "Error", "Export failed", "Traceback ...")

        self.assertEqual(policy.events[-1].prompt_id, "messages.error_details")
        self.assertEqual(policy.events[-1].text, "Export failed")

    def test_guard_dismisses_a_static_message_box(self):
        policy = self._install()
        self._start_failsafe()

        QtWidgets.QMessageBox.warning(None, "Save failed", "The disk is full.")

        self.assertFalse(self.failsafe_fired, "guard did not dismiss the dialog")
        event = policy.events[-1]
        self.assertIsNone(event.prompt_id)
        self.assertEqual(event.title, "Save failed")
        self.assertEqual(event.text, "The disk is full.")

    def test_guard_dismisses_a_file_picker(self):
        policy = self._install()
        self._start_failsafe()

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None, "Open comic", options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
        )

        self.assertFalse(self.failsafe_fired, "guard did not dismiss the dialog")
        self.assertEqual(path, "")
        self.assertEqual(policy.events[-1].title, "Open comic")

    def test_uninstall_restores_interactive_behavior(self):
        policy = self._install()
        policy.uninstall()

        self.assertIsInstance(interaction.get_interaction_policy(), interaction.GuiInteractionPolicy)


if __name__ == "__main__":
    unittest.main()
