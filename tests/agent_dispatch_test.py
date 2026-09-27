from __future__ import annotations

import os
import sys
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# A lightweight import test installs only a QtCore stub. This test needs real
# Qt threads, so restore the real package when discovery shares one process.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from PySide6 import QtWidgets
from PySide6.QtCore import QThread

from agent.app_api.dispatch import GuiDispatcher


class GuiDispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        self.dispatcher = GuiDispatcher()
        self.gui_thread = QThread.currentThread()

    def _pump_until(self, predicate, timeout: float = 5.0) -> None:
        """Process GUI events until ``predicate`` holds, as a running app would."""
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                self.fail("dispatched call was not delivered")
            self._application.processEvents()
            time.sleep(0.005)

    def _run_in_worker(self, target) -> None:
        worker = threading.Thread(target=target)
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())

    def test_worker_call_runs_on_gui_thread_and_returns_result(self):
        futures = []
        self._run_in_worker(lambda: futures.append(self.dispatcher.submit(
            lambda value: (value * 2, QThread.currentThread() is self.gui_thread), 21
        )))
        self._pump_until(futures[0].done)
        self.assertEqual(futures[0].result(), (42, True))

    def test_exception_reaches_caller(self):
        def fail():
            raise ValueError("boom")

        futures = []
        self._run_in_worker(lambda: futures.append(self.dispatcher.submit(fail)))
        self._pump_until(futures[0].done)
        with self.assertRaisesRegex(ValueError, "boom"):
            futures[0].result()

    def test_gui_thread_call_runs_immediately(self):
        calls = []
        future = self.dispatcher.submit(calls.append, "now")
        self.assertTrue(future.done())
        self.assertEqual(calls, ["now"])

    def test_cancelled_call_never_runs(self):
        calls = []
        outcome = {}

        def submit_then_cancel():
            future = self.dispatcher.submit(calls.append, "late")
            outcome["cancelled"] = future.cancel()

        self._run_in_worker(submit_then_cancel)
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            self._application.processEvents()
            time.sleep(0.005)
        self.assertTrue(outcome["cancelled"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
