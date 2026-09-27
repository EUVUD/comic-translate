from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# A lightweight import test installs only a QtCore stub. This test needs real
# Qt widgets, so restore the real package when discovery shares one process.
if not getattr(sys.modules.get("PySide6"), "__file__", None):
    sys.modules.pop("PySide6.QtCore", None)
    sys.modules.pop("PySide6", None)

from PySide6 import QtWidgets

from agent.app_api.session import AppSession

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Boots the real application in a fresh process: hermetic isolation cannot be
# undone, and other tests leave import stubs in the shared discovery process.
BOOT_PROBE = textwrap.dedent(
    """
    import json, sys, threading, time
    from pathlib import Path
    from agent.app_api.hermetic import HermeticEnvironment
    from agent.app_api.session import AppSession

    environment = HermeticEnvironment.create(sys.argv[1], shared_models_dir=sys.argv[2])
    session = AppSession.boot(environment)
    window = session.window

    observed = {}

    def agent_thread():
        future = session.submit(lambda: {
            "window": type(window).__name__,
            "pages": list(window.image_files),
            "on_gui_thread": session.dispatcher.on_gui_thread(),
        })
        observed.update(future.result(timeout=30))
        # Snapshots taken from the agent's thread run on the GUI thread.
        observed["snapshot_settings"] = sorted(session.snapshot()["settings"])

    worker = threading.Thread(target=agent_thread)
    worker.start()
    from PySide6.QtWidgets import QApplication
    while worker.is_alive():
        QApplication.processEvents()
        time.sleep(0.01)

    export = window.settings_page.get_export_settings()
    observed["autosave_enabled"] = export["project_autosave_enabled"]
    observed["autosave_in_sandbox"] = environment.contains(export["project_autosave_folder"])
    observed["visible"] = window.isVisible()

    from app.ui import interaction
    from app.ui.messages import Messages
    observed["policy"] = type(interaction.get_interaction_policy()).__name__
    # Would block on a modal dialog without the unattended policy.
    Messages.show_error_with_copy(window, "Error", "probe failure", "details")
    observed["prompt"] = session.policy.events[-1].prompt_id

    session.close()
    observed["visible_after_close"] = window.isVisible()
    observed["policy_after_close"] = type(interaction.get_interaction_policy()).__name__
    final = json.loads((environment.run_dir / "state.json").read_text(encoding="utf-8"))
    observed["final_snapshot"] = {
        "schema": final["schema"],
        "pages": final["pages"],
        "prompts": [prompt["prompt_id"] for prompt in final["prompts"]],
    }
    print(json.dumps(observed))
    """
)


class AttachedSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_attached_window_is_left_open_on_close(self):
        window = QtWidgets.QMainWindow()
        window.show()
        session = AppSession.attach(window)

        self.assertIs(session.submit(lambda: session.window).result(), window)
        session.close()
        self.assertTrue(window.isVisible())
        window.close()

    def test_wait_on_gui_thread_processes_queued_work(self):
        session = AppSession.attach(QtWidgets.QMainWindow())
        futures = []

        import threading

        worker = threading.Thread(target=lambda: futures.append(session.submit(lambda: "done")))
        worker.start()
        worker.join(timeout=5)

        self.assertEqual(session.wait(futures[0], timeout=5), "done")


@unittest.skipUnless(sys.platform.startswith("linux"), "hermetic sessions are Linux-only")
class BootedSessionTests(unittest.TestCase):
    def test_boot_runs_the_real_window_inside_the_sandbox(self):
        with tempfile.TemporaryDirectory() as parent:
            parent_path = Path(parent)
            completed = subprocess.run(
                [sys.executable, "-c", BOOT_PROBE, parent, str(parent_path / "shared-models")],
                cwd=REPOSITORY_ROOT,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                capture_output=True,
                text=True,
                timeout=180,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        observed = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(observed["window"], "ComicTranslate")
        self.assertEqual(observed["pages"], [])
        self.assertTrue(observed["on_gui_thread"])
        self.assertFalse(observed["autosave_enabled"])
        self.assertTrue(observed["autosave_in_sandbox"])
        self.assertTrue(observed["visible"])
        self.assertEqual(observed["policy"], "AgentInteractionPolicy")
        self.assertEqual(observed["prompt"], "messages.error_details")
        self.assertFalse(observed["visible_after_close"])
        self.assertEqual(observed["policy_after_close"], "GuiInteractionPolicy")
        self.assertEqual(observed["snapshot_settings"], ["detector", "inpainter", "ocr", "translator", "use_gpu"])
        self.assertEqual(observed["final_snapshot"], {
            "schema": 1,
            "pages": [],
            "prompts": ["messages.error_details"],
        })


if __name__ == "__main__":
    unittest.main()
