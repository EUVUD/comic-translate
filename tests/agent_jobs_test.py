from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# A lightweight import test installs only a QtCore stub. This test needs real
# Qt signals, so restore the real package when discovery shares one process.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from PySide6 import QtCore, QtWidgets

from agent.app_api.jobs import JobTracker
from agent.app_api.session import AppSession


class _Window(QtCore.QObject):
    """The two things JobTracker uses from ComicTranslate."""

    task_failed = QtCore.Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.markers_queued = 0

    def run_finish_only(self, finished_callback, error_callback=None):
        # Like the application's task queue: runs after pending work.
        self.markers_queued += 1
        QtCore.QTimer.singleShot(0, self, finished_callback)


class JobTrackerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        self.window = _Window()
        self.tracker = JobTracker(self.window)
        self.session = AppSession.attach(QtWidgets.QMainWindow())

    def _finish(self, job):
        return self.session.wait(job.future, timeout=5)

    def test_job_succeeds_after_the_queued_work(self):
        events = []

        def finish(job):
            events.append("finish")
            job.result["pages"] = 2

        job = self.tracker.start("load", lambda: events.append("begin"), finish)

        self.assertEqual((events, job.status), (["begin"], "running"))
        self._finish(job)
        self.assertEqual(events, ["begin", "finish"])
        self.assertEqual(job.to_dict(), {
            "id": "load-1", "kind": "load", "status": "succeeded", "result": {"pages": 2}, "errors": [],
            "progress": {},
        })

    def test_failure_reported_during_the_job_fails_it(self):
        job = self.tracker.start(
            "load",
            lambda: self.window.task_failed.emit("FileNotFoundError", "missing.cbz"),
            lambda job: None,
        )

        self._finish(job)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.errors, [{"type": "FileNotFoundError", "message": "missing.cbz"}])

    def test_failures_after_completion_are_not_attributed_to_the_job(self):
        job = self.tracker.start("load", lambda: None, lambda job: None)
        self._finish(job)

        self.window.task_failed.emit("RuntimeError", "later")

        self.assertEqual((job.status, job.errors), ("succeeded", []))

    def test_begin_error_fails_immediately_without_queueing(self):
        def begin():
            raise ValueError("unsupported file")

        job = self.tracker.start("load", begin, lambda job: None)

        self.assertTrue(job.future.done())
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.errors, [{"type": "ValueError", "message": "unsupported file"}])
        self.assertEqual(self.window.markers_queued, 0)

    def test_failed_postcondition_fails_the_job(self):
        def finish(job):
            raise AssertionError("no pages were loaded")

        job = self.tracker.start("load", lambda: None, finish)

        self._finish(job)
        self.assertEqual(job.errors, [{"type": "AssertionError", "message": "no pages were loaded"}])

    def test_prepare_runs_before_the_work_starts(self):
        events = []

        job = self.tracker.start(
            "translate",
            lambda: events.append("begin"),
            lambda job: events.append("finish"),
            prepare=lambda job: events.append(f"prepare {job.id}"),
        )
        self._finish(job)

        self.assertEqual(events, ["prepare translate-1", "begin", "finish"])

    def test_completion_hook_runs_before_waiters_wake(self):
        seen = []
        tracker = JobTracker(self.window, on_complete=lambda job: seen.append((job.kind, job.started, job.future.done())))

        started = tracker.start("load", lambda: None, lambda job: None)
        self._finish(started)
        tracker.rejected("export", "ValueError", "bad path")
        tracker.run_now("set_tools", lambda job: None)

        self.assertEqual(seen, [("load", True, False), ("export", False, False), ("set_tools", True, False)])

    def test_jobs_get_unique_ids(self):
        first = self.tracker.start("export", lambda: None, lambda job: None)
        second = self.tracker.start("export", lambda: None, lambda job: None)

        self.assertEqual((first.id, second.id), ("export-1", "export-2"))
        self.assertEqual(set(self.tracker.jobs), {"export-1", "export-2"})


if __name__ == "__main__":
    unittest.main()
