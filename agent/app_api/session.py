from __future__ import annotations

import os
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

from . import observations
from .actions import AppActions
from .dispatch import GuiDispatcher
from .hermetic import HermeticEnvironment
from .interaction import AgentInteractionPolicy
from .jobs import JobTracker


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
        policy: AgentInteractionPolicy | None = None,
    ) -> None:
        self.window = window
        self.environment = environment
        self.policy = policy
        self.dispatcher = GuiDispatcher(window)
        self.jobs = JobTracker(window, on_complete=self._after_job)
        self.actions = AppActions(self)
        self._owns_window = owns_window
        self._closed = False

    @classmethod
    def attach(cls, window: Any) -> AppSession:
        """Operate an existing window. Call on the GUI thread."""
        return cls(window, owns_window=False)

    @classmethod
    def boot(
        cls,
        environment: HermeticEnvironment | None = None,
        *,
        policy: AgentInteractionPolicy | None = None,
        show: bool = True,
    ) -> AppSession:
        """Start the application in this process. Call on the main thread.

        With an ``environment``, the process is isolated first, so nothing else
        in the process may have used Qt settings or the keyring before this call.
        Hermetic sessions are unattended: unless ``policy`` is given, prompts are
        answered by an ``AgentInteractionPolicy`` with no pre-authorized answers.
        """
        if environment is not None:
            environment.apply()
            _pin_hermetic_settings(environment)
            if policy is None:
                policy = AgentInteractionPolicy()

        from PySide6 import QtWidgets

        QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        if policy is not None:
            # Installed before the window exists so startup prompts are covered.
            policy.install()
        from controller import ComicTranslate

        window = ComicTranslate()
        if show:
            window.show()
        return cls(window, owns_window=True, environment=environment, policy=policy)

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

    def wait_until_idle(self, timeout: float = 120) -> None:
        """Wait until no application work is queued or running.

        Completion callbacks can queue follow-up work, such as the autosave
        after a translation run, so an action's job may finish first.
        """
        runner = self.window.task_runner_ctrl
        threadpool = self.window.threadpool

        def idle() -> bool:
            return not runner.operation_queue and threadpool.activeThreadCount() == 0

        deadline = time.monotonic() + timeout
        while not self.wait(self.submit(idle), timeout):
            if time.monotonic() > deadline:
                raise TimeoutError("application work did not finish in time")
            self._pause(0.05)

    def _pause(self, seconds: float) -> None:
        if not self.dispatcher.on_gui_thread():
            time.sleep(seconds)
            return
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, int(seconds * 1000))

    # Jobs that only read the session; any other job may change a snapshot.
    READ_ONLY_JOBS = frozenset({"render_page_preview"})

    def _after_job(self, job: Any) -> None:
        """Keep the hermetic run's snapshot current after every change."""
        if self.environment is None or not job.started or job.kind in self.READ_ONLY_JOBS:
            return
        events = self.policy.events if self.policy is not None else ()
        observations.write_snapshot(
            observations.snapshot(self.window, events), self.environment.run_dir / "state.json"
        )

    def snapshot(self) -> dict:
        """Observable session state; see ``observations.snapshot``."""
        events = self.policy.events if self.policy is not None else ()
        return self.wait(self.submit(observations.snapshot, self.window, events))

    def write_snapshot(self, path: str | os.PathLike | None = None) -> Path:
        """Write a snapshot, by default to the hermetic run directory."""
        if path is None:
            if self.environment is None:
                raise ValueError("this session has no run directory; pass a path")
            path = self.environment.run_dir / "state.json"
        return observations.write_snapshot(self.snapshot(), path)

    def close(self) -> None:
        """Shut down a booted window. An attached window is left open.

        A hermetic session writes a final snapshot first, so scoring can read
        the end state after the process exits.
        """
        if self._closed:
            return
        self._closed = True
        if not self._owns_window:
            return
        # Closing releases the project store; background saves must finish first.
        self.wait_until_idle()
        if self.environment is not None:
            self.write_snapshot()
        # A booted session's unsaved work is disposable; skip the save prompt.
        self.window._skip_close_prompt = True
        self.window.close()
        if self.policy is not None:
            self.policy.uninstall()


def _pin_hermetic_settings(environment: HermeticEnvironment) -> None:
    """Keep autosave off and pointed inside the sandbox before the window loads."""
    from PySide6.QtCore import QSettings

    settings = QSettings("ComicLabs", "ComicTranslate")
    settings.beginGroup("export")
    settings.setValue("project_autosave_enabled", False)
    settings.setValue("project_autosave_folder", str(environment.autosave_dir))
    settings.endGroup()
    settings.sync()
