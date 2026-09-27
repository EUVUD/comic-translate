"""Typed actions over a live Comic Translate session.

Every action runs on the GUI thread (reach it through ``AppSession.submit``)
and returns a ``Job``. Quick actions return a finished job; long ones return
a running job that resolves once the application has finished the work.
Actions reuse the controller code paths the GUI uses and check their
postconditions, so a job only succeeds when the application reached the
expected state.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

from .jobs import Job

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif")
DOCUMENT_EXTENSIONS = (".pdf", ".epub")
ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z", ".tar", ".cbz", ".cbr", ".cb7", ".cbt")
PSD_EXTENSION = ".psd"
INPUT_EXTENSIONS = IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS + ARCHIVE_EXTENSIONS + (PSD_EXTENSION,)


class AppActions:
    """The actions available on one session. Call every method on the GUI thread."""

    def __init__(self, session: Any) -> None:
        self._window = session.window
        self._jobs = session.jobs

    # Inputs

    def load_inputs(self, paths: Sequence[str], *, discard_unsaved: bool = False) -> Job:
        """Replace the current pages with images, documents, archives or PSD files."""
        paths = [os.path.abspath(path) for path in paths]
        problem = _input_problem(paths) or self._unsaved_problem(discard_unsaved)
        if problem:
            return self._jobs.rejected("load_inputs", *problem)
        return self._jobs.start(
            "load_inputs",
            lambda: self._window.image_ctrl.thread_load_images(paths),
            self._finish_loading,
        )

    def open_project(self, path: str, *, discard_unsaved: bool = False) -> Job:
        """Open a ``.ctpr`` project in place of the current one."""
        path = os.path.normpath(os.path.abspath(path))
        if not path.lower().endswith(".ctpr"):
            return self._jobs.rejected("open_project", "ValueError", f"not a .ctpr project: {path}")
        if not os.path.isfile(path):
            return self._jobs.rejected("open_project", "FileNotFoundError", f"no such project: {path}")
        problem = self._unsaved_problem(discard_unsaved)
        if problem:
            return self._jobs.rejected("open_project", *problem)

        def finish(job: Job) -> None:
            if self._window.project_file != path:
                job.fail("ProjectNotOpened", f"the project was not opened: {path}")
            self._finish_loading(job)

        return self._jobs.start(
            "open_project",
            lambda: self._window.project_ctrl.thread_load_project(path),
            finish,
        )

    def _finish_loading(self, job: Job) -> None:
        files = list(self._window.image_files)
        if not files:
            job.fail("NoPagesLoaded", "no pages were loaded")
        job.result.update(pages=len(files), names=[os.path.basename(path) for path in files])

    def _unsaved_problem(self, discard_unsaved: bool) -> tuple[str, str] | None:
        if self._window.has_unsaved_changes() and not discard_unsaved:
            return (
                "UnsavedChanges",
                "the current project has unsaved changes; save it first or pass discard_unsaved=True",
            )
        return None


def _input_problem(paths: list[str]) -> tuple[str, str] | None:
    if not paths:
        return "ValueError", "no input paths were given"
    missing = [path for path in paths if not os.path.isfile(path)]
    if missing:
        return "FileNotFoundError", f"no such file: {', '.join(missing)}"
    extensions = [os.path.splitext(path)[1].lower() for path in paths]
    if ".ctpr" in extensions:
        return "UnsupportedInput", "open .ctpr projects with open_project"
    unsupported = sorted({ext or "(none)" for ext in extensions if ext not in INPUT_EXTENSIONS})
    if unsupported:
        return "UnsupportedInput", f"unsupported file types {unsupported}; supported: {list(INPUT_EXTENSIONS)}"
    if PSD_EXTENSION in extensions and set(extensions) != {PSD_EXTENSION}:
        return "UnsupportedInput", "PSD files cannot be loaded together with other files"
    return None
