"""Run a script against a fresh hermetic session in a process of its own.

Hermetic isolation cannot be undone, and other tests leave import stubs in the
shared discovery process, so each session contract test gets a new process.
This module is a helper, not a test module.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Available to every script: session, actions, environment, finished(job),
# write_page(name, value) and a ``result`` dict that is returned to the test.
PREAMBLE = textwrap.dedent(
    """
    import json, sys, zipfile
    from pathlib import Path
    import numpy as np
    import imkit as imk
    from agent.app_api.hermetic import HermeticEnvironment
    from agent.app_api.session import AppSession

    environment = HermeticEnvironment.create(sys.argv[1], shared_models_dir=sys.argv[2])
    session = AppSession.boot(environment)
    actions = session.actions
    result = {}

    def finished(job, timeout=120):
        return session.wait(job.future, timeout).to_dict()

    def write_page(name, value, directory=None):
        path = Path(directory or environment.inputs_dir) / name
        imk.write_image(str(path), np.full((64, 48, 3), value, dtype=np.uint8))
        return str(path)
    """
)

EPILOGUE = textwrap.dedent(
    """
    session.close()
    print("RESULT " + json.dumps(result))
    """
)


def run_in_hermetic_session(body: str, timeout: float = 240) -> dict:
    """Run ``body`` after booting a hermetic session; return its ``result`` dict."""
    script = PREAMBLE + textwrap.dedent(body) + EPILOGUE
    with tempfile.TemporaryDirectory() as parent:
        completed = subprocess.run(
            [sys.executable, "-c", script, parent, str(Path(parent) / "shared-models")],
            cwd=REPOSITORY_ROOT,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    if completed.returncode != 0:
        raise AssertionError(f"session script failed:\n{completed.stderr[-4000:]}")
    marked = [line for line in completed.stdout.splitlines() if line.startswith("RESULT ")]
    if not marked:
        raise AssertionError(f"session script printed no result:\n{completed.stdout[-2000:]}")
    return json.loads(marked[-1][len("RESULT "):])
