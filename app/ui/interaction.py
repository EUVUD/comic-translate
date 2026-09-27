"""Single entry point for running modal dialogs.

Interactive use shows every dialog exactly as before. An automated session,
such as the closed-loop agent, installs a policy that answers prompts without
blocking the event loop. Each call site passes a stable ``prompt_id`` so a
policy can recognize the prompt regardless of the interface language.
"""

from __future__ import annotations

from typing import Protocol

from PySide6 import QtWidgets


class InteractionPolicy(Protocol):
    def run_modal(self, dialog: QtWidgets.QDialog, prompt_id: str) -> int:
        """Run or answer ``dialog``; return what ``dialog.exec()`` would return."""


class GuiInteractionPolicy:
    """Default policy: show the dialog and wait for the user."""

    def run_modal(self, dialog: QtWidgets.QDialog, prompt_id: str) -> int:
        return dialog.exec()


_policy: InteractionPolicy = GuiInteractionPolicy()


def run_modal(dialog: QtWidgets.QDialog, prompt_id: str) -> int:
    """Run ``dialog`` modally through the installed policy."""
    return _policy.run_modal(dialog, prompt_id)


def set_interaction_policy(policy: InteractionPolicy | None) -> None:
    """Install ``policy`` for this process; ``None`` restores the GUI default."""
    global _policy
    _policy = policy if policy is not None else GuiInteractionPolicy()


def get_interaction_policy() -> InteractionPolicy:
    return _policy
