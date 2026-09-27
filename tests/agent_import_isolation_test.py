from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import textwrap
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Imports the application the way comic.py does, in a clean process, and lists
# any agent or evaluation package that came along.
PROBE = textwrap.dedent(
    """
    import sys
    import controller  # noqa: F401  (the application's main module)
    loaded = sorted({name.split(".")[0] for name in sys.modules} & {"agent", "evals", "mcp", "inspect_ai"})
    print("LOADED", ",".join(loaded))
    """
)


class ImportIsolationTests(unittest.TestCase):
    def test_application_startup_imports_no_agent_packages(self):
        completed = subprocess.run(
            [sys.executable, "-c", PROBE],
            cwd=REPOSITORY_ROOT,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True,
            text=True,
            timeout=180,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        [line] = [line for line in completed.stdout.splitlines() if line.startswith("LOADED")]
        self.assertEqual(line, "LOADED ", "the application must not import agent, evals, mcp or inspect_ai")


if __name__ == "__main__":
    unittest.main()
