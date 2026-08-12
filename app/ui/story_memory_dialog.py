"""Minimal project-scoped controls for existing Story Memory data."""

from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

from app.projects.story_memory_repository import NewStoryBrief, StoryMemoryRepository
from app.projects.story_memory_types import LanguagePair
from modules.translation.context.models import DEFAULT_STORY_MEMORY_CONTEXT_BUDGET


class StoryMemoryDialog(QtWidgets.QDialog):
    """Enable one saved project's memory and edit its bounded Story Brief.

    Canon and approved translation memory are already durable project data.  The
    dialog intentionally does not manufacture either from automatic output; it
    only exposes the minimal controls required to opt in and to provide the
    optional project brief used by normal translation requests.
    """

    MAX_BRIEF_CHARACTERS = (
        DEFAULT_STORY_MEMORY_CONTEXT_BUDGET.max_story_brief_characters
    )

    def __init__(
        self,
        repository: StoryMemoryRepository,
        language_pair: LanguagePair,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(repository, StoryMemoryRepository):
            raise TypeError("repository must be a StoryMemoryRepository")
        if not isinstance(language_pair, LanguagePair):
            raise TypeError("language_pair must be a LanguagePair")

        self.repository = repository
        self.language_pair = language_pair
        self.changes_saved = False
        self.setWindowTitle(self.tr("Story Memory"))
        self.resize(600, 440)

        metadata = repository.get_metadata()
        brief = repository.get_brief(language_pair)
        active_canon_count = len(repository.list_canon(language_pair, active_only=True))
        approved_memory_count = len(repository.list_translation_memory(language_pair))

        layout = QtWidgets.QVBoxLayout(self)

        project_label = QtWidgets.QLabel(
            self.tr("Project: {name}").format(
                name=os.path.basename(repository.project_file),
            ),
            self,
        )
        project_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        layout.addWidget(project_label)

        language_label = QtWidgets.QLabel(
            self.tr("Language pair: {source} → {target}").format(
                source=language_pair.source_lang,
                target=language_pair.target_lang,
            ),
            self,
        )
        layout.addWidget(language_label)

        self.enabled_checkbox = QtWidgets.QCheckBox(
            self.tr("Use Story Memory for direct LLM translation"),
            self,
        )
        self.enabled_checkbox.setChecked(metadata.enabled)
        layout.addWidget(self.enabled_checkbox)

        disclosure = QtWidgets.QLabel(
            self.tr(
                "When enabled, only the configured Story Brief and matching, "
                "bounded canon or approved translation-memory entries are sent "
                "with a direct LLM translation request. Other project memory "
                "stays local. Traditional translators are unchanged."
            ),
            self,
        )
        disclosure.setWordWrap(True)
        layout.addWidget(disclosure)

        summary = QtWidgets.QLabel(
            self.tr("Active canon: {canon}    Approved translation memory: {tm}").format(
                canon=active_canon_count,
                tm=approved_memory_count,
            ),
            self,
        )
        layout.addWidget(summary)

        layout.addWidget(QtWidgets.QLabel(self.tr("Story Brief (optional)"), self))
        self.brief_edit = QtWidgets.QTextEdit(self)
        self.brief_edit.setPlaceholderText(
            self.tr("A short, project-specific brief for this language pair.")
        )
        self.brief_edit.setPlainText(brief.content if brief is not None else "")
        self.brief_edit.textChanged.connect(self._update_brief_count)
        layout.addWidget(self.brief_edit, 1)

        self.brief_count_label = QtWidgets.QLabel(self)
        layout.addWidget(self.brief_count_label)
        self._update_brief_count()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _brief_text(self) -> str:
        return self.brief_edit.toPlainText().strip()

    def _update_brief_count(self) -> None:
        count = len(self._brief_text())
        self.brief_count_label.setText(
            self.tr("{count} / {limit} characters").format(
                count=count,
                limit=self.MAX_BRIEF_CHARACTERS,
            )
        )

    def _save(self) -> None:
        brief_text = self._brief_text()
        if len(brief_text) > self.MAX_BRIEF_CHARACTERS:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Story Brief Too Long"),
                self.tr("Keep the Story Brief within {limit} characters.").format(
                    limit=self.MAX_BRIEF_CHARACTERS,
                ),
            )
            return

        metadata_before = self.repository.get_metadata()
        brief_before = self.repository.get_brief(self.language_pair)
        self.repository.set_enabled(self.enabled_checkbox.isChecked())
        if brief_text:
            if brief_before is None or brief_before.content != brief_text:
                self.repository.upsert_brief(
                    NewStoryBrief(self.language_pair, brief_text)
                )
        elif brief_before is not None:
            self.repository.delete_brief(self.language_pair)

        metadata_after = self.repository.get_metadata()
        self.changes_saved = (
            metadata_before.memory_revision != metadata_after.memory_revision
        )
        self.accept()
