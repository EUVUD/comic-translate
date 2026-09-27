from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
import itertools
from typing import Any, Callable


@dataclass
class Job:
    """A long-running application operation started by the agent.

    ``future`` resolves to the job itself once the operation and everything
    queued before it have finished; wait on it with ``AppSession.wait``.
    """

    id: str
    kind: str
    status: str = "running"  # running, succeeded or failed
    result: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)  # {"type": ..., "message": ...}
    future: Future = field(default_factory=Future, repr=False, compare=False)

    def fail(self, error_type: str, message: str) -> None:
        self.errors.append({"type": error_type, "message": message})

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "result": self.result,
            "errors": list(self.errors),
        }


class JobTracker:
    """Start application operations and tell when they are done.

    The application runs its long operations one at a time through its task
    queue (``run_threaded``). A no-op queued after an operation therefore
    finishes only once that operation and its callbacks have run, so
    ``run_finish_only`` marks the end of a job. Failures reported through
    ``default_error_handler`` arrive on ``window.task_failed``.

    Use it on the GUI thread.
    """

    def __init__(self, window: Any) -> None:
        self._window = window
        self._ids = itertools.count(1)
        self.jobs: dict[str, Job] = {}

    def start(self, kind: str, begin: Callable[[], Any], finish: Callable[[Job], None]) -> Job:
        """Run ``begin``, then call ``finish`` once the work it queued is done.

        ``finish`` checks postconditions, fills ``job.result`` and calls
        ``job.fail`` for anything that went wrong.
        """
        job = self._new(kind)
        self._window.task_failed.connect(job.fail)

        def complete() -> None:
            self._window.task_failed.disconnect(job.fail)
            self._run(job, finish)
            self._complete(job)

        try:
            begin()
        except Exception as exc:
            job.fail(type(exc).__name__, str(exc))
            self._window.task_failed.disconnect(job.fail)
            return self._complete(job)
        self._window.run_finish_only(complete)
        return job

    def run_now(self, kind: str, action: Callable[[Job], None]) -> Job:
        """Run a quick action immediately and return its finished job."""
        job = self._new(kind)
        self._run(job, action)
        return self._complete(job)

    def rejected(self, kind: str, error_type: str, message: str) -> Job:
        """A job refused before it started, for example because of bad arguments."""
        job = self._new(kind)
        job.fail(error_type, message)
        return self._complete(job)

    def _new(self, kind: str) -> Job:
        job = Job(id=f"{kind}-{next(self._ids)}", kind=kind)
        self.jobs[job.id] = job
        return job

    @staticmethod
    def _run(job: Job, step: Callable[[Job], None]) -> None:
        try:
            step(job)
        except Exception as exc:  # a failed postcondition check fails the job
            job.fail(type(exc).__name__, str(exc))

    @staticmethod
    def _complete(job: Job) -> Job:
        job.status = "failed" if job.errors else "succeeded"
        job.future.set_result(job)
        return job
