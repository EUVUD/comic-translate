from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from PySide6 import QtCore, QtWidgets

from app.ui import interaction as app_interaction

_Role = QtWidgets.QMessageBox.ButtonRole

# Answers that may be pre-authorized for a prompt, matched by button role so
# they work in every interface language.
ANSWER_ROLES = {
    "accept": (_Role.AcceptRole, _Role.YesRole),
    "reject": (_Role.RejectRole, _Role.NoRole),
    "destructive": (_Role.DestructiveRole,),
}


@dataclass
class PromptEvent:
    """A prompt the application raised during an unattended session."""

    prompt_id: str | None  # None when the dialog did not go through run_modal
    title: str
    text: str
    buttons: list[str] = field(default_factory=list)
    answer: str | None = None  # an ANSWER_ROLES key, or None when dismissed


class AgentInteractionPolicy:
    """Answer prompts for an unattended session instead of showing them.

    A prompt routed through ``app.ui.interaction.run_modal`` gets the answer
    pre-authorized for its prompt id, or no answer at all, which every routed
    call site treats as cancel. Any other modal dialog that opens, such as a
    static message box or a file picker, is dismissed as soon as it shows.
    Every prompt is recorded in ``events`` so the agent sees what happened.
    """

    def __init__(self, answers: Mapping[str, str] | None = None) -> None:
        answers = dict(answers or {})
        unknown = sorted(set(answers.values()) - set(ANSWER_ROLES))
        if unknown:
            raise ValueError(f"unknown answers {unknown}; expected one of {sorted(ANSWER_ROLES)}")
        self.answers = answers
        self.events: list[PromptEvent] = []
        self._guard = _ModalGuard(self.events)

    def install(self) -> None:
        """Answer every prompt in this process. Call on the GUI thread."""
        app_interaction.set_interaction_policy(self)
        self._guard.start()

    def uninstall(self) -> None:
        self._guard.stop()
        if app_interaction.get_interaction_policy() is self:
            app_interaction.set_interaction_policy(None)

    def run_modal(self, dialog: QtWidgets.QDialog, prompt_id: str) -> int:
        event = _describe(dialog, prompt_id)
        answer = self.answers.get(prompt_id)
        if answer is not None and _apply_answer(dialog, answer):
            event.answer = answer
        self.events.append(event)
        return dialog.result()


def _describe(dialog: QtWidgets.QDialog, prompt_id: str | None) -> PromptEvent:
    if isinstance(dialog, QtWidgets.QMessageBox):
        text = "\n".join(part for part in (dialog.text(), dialog.informativeText()) if part)
        return PromptEvent(prompt_id, dialog.windowTitle(), text, [b.text() for b in dialog.buttons()])
    return PromptEvent(prompt_id, dialog.windowTitle(), "")


def _apply_answer(dialog: QtWidgets.QDialog, answer: str) -> bool:
    if isinstance(dialog, QtWidgets.QMessageBox):
        for button in dialog.buttons():
            if dialog.buttonRole(button) in ANSWER_ROLES[answer]:
                # The box is never shown; clicking still sets clickedButton().
                button.click()
                return True
        return False
    if answer == "accept":
        dialog.accept()
        return True
    if answer == "reject":
        dialog.reject()
        return True
    return False


class _ModalGuard(QtCore.QObject):
    """Dismiss modal dialogs that open without going through ``run_modal``.

    A timer polls for the active modal widget; it keeps firing inside a
    dialog's own event loop. An application-wide event filter would be simpler,
    but a Python filter is called for every event on every object, including
    objects being destroyed, and that crashed PySide in this application.
    """

    INTERVAL_MS = 50

    def __init__(self, events: list[PromptEvent]) -> None:
        super().__init__()
        self._events = events
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._dismiss_active_modal)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _dismiss_active_modal(self) -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        if isinstance(dialog, QtWidgets.QDialog) and dialog.isVisible():
            self._events.append(_describe(dialog, None))
            dialog.reject()
