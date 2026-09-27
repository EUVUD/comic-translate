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

# Settings-page combo box for each kind of engine.
TOOL_COMBOS = {
    "translator": "translator_combo",
    "ocr": "ocr_combo",
    "inpainter": "inpainter_combo",
    "detector": "detector_combo",
}
CUSTOM_CREDENTIAL_FIELDS = ("api_key", "api_url", "model")


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

    # Configuration

    def set_languages(self, source: str, target: str) -> Job:
        """Set the source and target language of every page, by English name."""
        from app.ui.main_window.constants import supported_source_languages, supported_target_languages

        if source not in supported_source_languages:
            return self._jobs.rejected(
                "set_languages", "ValueError",
                f"unsupported source language {source!r}; supported: {supported_source_languages}",
            )
        if target not in supported_target_languages:
            return self._jobs.rejected(
                "set_languages", "ValueError",
                f"unsupported target language {target!r}; supported: {supported_target_languages}",
            )
        window = self._window

        def apply(job: Job) -> None:
            _select(window.s_combo, window.reverse_lang_mapping.get(source, source))
            _select(window.t_combo, window.reverse_lang_mapping.get(target, target))
            window.text_ctrl.set_src_trg_all()
            unchanged = [
                os.path.basename(path)
                for path in window.image_files
                if (window.image_states[path].get("source_lang"), window.image_states[path].get("target_lang"))
                != (source, target)
            ]
            if unchanged:
                job.fail("LanguagesNotApplied", f"pages still using other languages: {unchanged}")
            job.result.update(source=source, target=target, pages=len(window.image_files))

        return self._jobs.run_now("set_languages", apply)

    def available_tools(self, kind: str) -> list[str]:
        """English names of the engines offered for ``kind`` (see ``TOOL_COMBOS``)."""
        ui = self._window.settings_page.ui
        combo = getattr(ui, TOOL_COMBOS[kind])
        return [ui.value_mappings.get(combo.itemText(i), combo.itemText(i)) for i in range(combo.count())]

    def set_tools(
        self,
        *,
        translator: str | None = None,
        ocr: str | None = None,
        inpainter: str | None = None,
        detector: str | None = None,
        use_gpu: bool | None = None,
        custom_credentials: dict[str, str] | None = None,
    ) -> Job:
        """Choose engines by English name and optionally configure the Custom endpoint.

        Credentials are written to the settings page but never included in a result.
        """
        requested = {"translator": translator, "ocr": ocr, "inpainter": inpainter, "detector": detector}
        for kind, name in requested.items():
            if name is not None and name not in self.available_tools(kind):
                return self._jobs.rejected(
                    "set_tools", "ValueError",
                    f"unknown {kind} {name!r}; available: {self.available_tools(kind)}",
                )
        unknown_fields = sorted(set(custom_credentials or {}) - set(CUSTOM_CREDENTIAL_FIELDS))
        if unknown_fields:
            return self._jobs.rejected(
                "set_tools", "ValueError",
                f"unknown Custom credential fields {unknown_fields}; expected {list(CUSTOM_CREDENTIAL_FIELDS)}",
            )
        page = self._window.settings_page

        def apply(job: Job) -> None:
            for kind, name in requested.items():
                if name is not None:
                    _select(getattr(page.ui, TOOL_COMBOS[kind]), page.ui.reverse_mappings.get(name, name))
            for field, value in (custom_credentials or {}).items():
                page.ui.credential_widgets[f"Custom_{field}"].setText(value)
            if use_gpu is not None:
                page.ui.use_gpu_checkbox.setChecked(bool(use_gpu))
                if use_gpu and not page.is_gpu_enabled():
                    job.fail("GPUUnavailable", "no usable GPU was found; engines run on the CPU")
            selected = {kind: self._tool(kind) for kind in TOOL_COMBOS}
            for kind, name in requested.items():
                if name is not None and selected[kind] != name:
                    job.fail("ToolNotSelected", f"{kind} is {selected[kind]!r}, not {name!r}")
            credentials = page.get_credentials(page.ui.tr("Custom"))
            job.result.update(
                tools=selected,
                use_gpu=bool(page.is_gpu_enabled()),
                custom_configured=all(credentials.get(field) for field in CUSTOM_CREDENTIAL_FIELDS),
            )

        return self._jobs.run_now("set_tools", apply)

    def available_fonts(self) -> list[str]:
        dropdown = self._window.font_dropdown
        return [dropdown.itemText(i) for i in range(dropdown.count())]

    def set_render_options(
        self,
        *,
        font: str | None = None,
        uppercase: bool | None = None,
        min_font_size: int | None = None,
        max_font_size: int | None = None,
    ) -> Job:
        """Choose how translations are typeset. A font is required before translating."""
        if font is not None and font not in self.available_fonts():
            return self._jobs.rejected(
                "set_render_options", "ValueError",
                f"font {font!r} is not installed; available: {self.available_fonts()[:20]}",
            )
        window = self._window
        ui = window.settings_page.ui

        def apply(job: Job) -> None:
            if font is not None:
                _select(window.font_dropdown, font)
            if uppercase is not None:
                ui.uppercase_checkbox.setChecked(bool(uppercase))
            if min_font_size is not None:
                ui.min_font_spinbox.setValue(int(min_font_size))
            if max_font_size is not None:
                ui.max_font_spinbox.setValue(int(max_font_size))
            settings = window.render_settings()
            if font is not None and settings.font_family != font:
                job.fail("FontNotSelected", f"font is {settings.font_family!r}, not {font!r}")
            for name, requested, actual in (
                ("min_font_size", min_font_size, settings.min_font_size),
                ("max_font_size", max_font_size, settings.max_font_size),
            ):
                if requested is not None and actual != requested:
                    job.fail("ValueOutOfRange", f"{name} is {actual}, not {requested}")
            job.result.update(
                font=settings.font_family,
                uppercase=bool(settings.upper_case),
                min_font_size=settings.min_font_size,
                max_font_size=settings.max_font_size,
            )

        return self._jobs.run_now("set_render_options", apply)

    def set_webtoon_mode(self, enabled: bool) -> Job:
        """Show pages as one vertical strip (webtoon mode) or one at a time."""
        window = self._window
        if enabled and not window.image_files:
            return self._jobs.rejected("set_webtoon_mode", "NoPagesLoaded", "load pages before switching to webtoon mode")

        def apply(job: Job) -> None:
            if window.webtoon_mode != enabled:
                # The GUI toggles through the button's click handler, which
                # reads the button's checked state.
                window.webtoon_toggle.setChecked(enabled)
                window.webtoon_ctrl.toggle_webtoon_mode()
            if window.webtoon_mode != enabled:
                job.fail("WebtoonModeNotChanged", f"webtoon mode is still {'on' if window.webtoon_mode else 'off'}")
            job.result["webtoon_mode"] = bool(window.webtoon_mode)

        return self._jobs.run_now("set_webtoon_mode", apply)

    def _tool(self, kind: str) -> str:
        page = self._window.settings_page
        label = page.get_tool_selection(kind)
        return page.ui.value_mappings.get(label, label)

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


def _select(combo: Any, text: str) -> None:
    index = combo.findText(text)
    if index < 0:
        raise ValueError(f"{text!r} is not an option here")
    combo.setCurrentIndex(index)


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
