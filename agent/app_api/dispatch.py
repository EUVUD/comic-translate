from __future__ import annotations

from concurrent.futures import Future
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot


class GuiDispatcher(QObject):
    """Run callables on the thread this object lives in, normally the GUI thread.

    The agent runs on worker threads, but every application action must run on
    the GUI thread. ``submit`` returns a ``concurrent.futures.Future`` that a
    worker can wait on. Calls made on the GUI thread itself run immediately, so a
    GUI-thread caller never deadlocks waiting for its own queued call.
    """

    _invoke = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # A queued connection always delivers to this object's thread, whichever
        # thread emits, and works the same on every supported PySide6 version.
        self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def on_gui_thread(self) -> bool:
        return QThread.currentThread() is self.thread()

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        future: Future = Future()
        task = (future, fn, args, kwargs)
        if self.on_gui_thread():
            self._run(task)
        else:
            self._invoke.emit(task)
        return future

    @Slot(object)
    def _run(self, task: tuple) -> None:
        future, fn, args, kwargs = task
        if not future.set_running_or_notify_cancel():
            return
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:  # handed to the caller through the future
            future.set_exception(exc)
        else:
            future.set_result(result)
