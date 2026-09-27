from __future__ import annotations

import time
from concurrent.futures import Future
from typing import Any, Callable

from .dispatch import GuiDispatcher
from .hermetic import HermeticEnvironment


class AppSession:
    """A live Comic Translate main window that the agent operates.

    ``boot`` starts the application in this process, normally inside a hermetic
    environment. ``attach`` wraps a window that already exists. Either way, work
    reaches the window through ``submit``, which runs on the GUI thread.
    """

    def __init__(
        self,
        window: Any,
        *,
        owns_window: bool,
        environment: HermeticEnvironment | None = None,
    ) -> None:
        self.window = window
        self.environment = environment
        self.dispatcher = GuiDispatcher(window)
        self._owns_window = owns_window
        self._closed = False

    @classmethod
    def attach(cls, window: Any) -> AppSession:
        """Operate an existing window. Call on the GUI thread."""
        return cls(window, owns_window=False)

    @classmethod
    def boot(cls, environment: HermeticEnvironment | None = None, *, show: bool = True) -> AppSession:
        """Start the application in this process. Call on the main thread.

        With an ``environment``, the process is isolated first, so nothing else
        in the process may have used Qt settings or the keyring before this call.
        """
        if environment is not None:
            environment.apply()
            _pin_hermetic_settings(environment)

        from PySide6 import QtWidgets

        QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        from controller import ComicTranslate

        window = ComicTranslate()
        if show:
            window.show()
        return cls(window, owns_window=True, environment=environment)

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        """Run ``fn`` on the GUI thread; see ``GuiDispatcher.submit``."""
        return self.dispatcher.submit(fn, *args, **kwargs)

    def wait(self, future: Future, timeout: float | None = None) -> Any:
        """Return ``future``'s result.

        On the GUI thread this keeps processing events while waiting, so queued
        work and completion signals still arrive.
        """
        if not self.dispatcher.on_gui_thread():
            return future.result(timeout)

        from PySide6.QtCore import QEventLoop
        from PySide6.QtWidgets import QApplication

        deadline = None if timeout is None else time.monotonic() + timeout
        while not future.done():
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("GUI work did not finish in time")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        return future.result()

    def close(self) -> None:
        """Shut down a booted window. An attached window is left open."""
        if self._closed:
            return
        self._closed = True
        if not self._owns_window:
            return
        # A booted session's unsaved work is disposable; skip the save prompt.
        self.window._skip_close_prompt = True
        self.window.close()


def _pin_hermetic_settings(environment: HermeticEnvironment) -> None:
    """Keep autosave off and pointed inside the sandbox before the window loads."""
    from PySide6.QtCore import QSettings

    settings = QSettings("ComicLabs", "ComicTranslate")
    settings.beginGroup("export")
    settings.setValue("project_autosave_enabled", False)
    settings.setValue("project_autosave_folder", str(environment.autosave_dir))
    settings.endGroup()
    settings.sync()
