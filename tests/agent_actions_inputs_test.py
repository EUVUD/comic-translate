from __future__ import annotations

import sys
import unittest

from tests.agent_session_support import run_in_hermetic_session

SCRIPT = """
first = write_page("001.png", 40)
second = write_page("002.png", 80)
result["load"] = finished(actions.load_inputs([first, second]))
result["reload_with_unsaved_changes"] = finished(actions.load_inputs([first]))

pages_dir = environment.inputs_dir / "archive_pages"
pages_dir.mkdir()
archive = environment.inputs_dir / "vol1.cbz"
with zipfile.ZipFile(archive, "w") as bundle:
    for index, value in enumerate((100, 120, 140), start=1):
        bundle.write(write_page(f"{index:03}.png", value, pages_dir), f"{index:03}.png")
result["load_archive"] = finished(actions.load_inputs([str(archive)], discard_unsaved=True))

broken = environment.inputs_dir / "broken.png"
broken.write_bytes(b"not an image")
result["load_broken"] = finished(actions.load_inputs([str(broken)], discard_unsaved=True))
result["prompts"] = [event.prompt_id for event in session.policy.events]

for name in ("project.ctpr", "layer.psd", "notes.txt"):
    (environment.inputs_dir / name).write_bytes(b"")
inputs = environment.inputs_dir
result["rejections"] = {
    "empty": finished(actions.load_inputs([])),
    "missing": finished(actions.load_inputs([str(inputs / "nope.png")])),
    "project": finished(actions.load_inputs([str(inputs / "project.ctpr")])),
    "unsupported": finished(actions.load_inputs([str(inputs / "notes.txt")])),
    "mixed_psd": finished(actions.load_inputs([str(inputs / "layer.psd"), first])),
    "open_not_project": finished(actions.open_project(first)),
    "open_missing": finished(actions.open_project(str(inputs / "gone.ctpr"))),
}
"""


@unittest.skipUnless(sys.platform.startswith("linux"), "hermetic sessions are Linux-only")
class InputActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_in_hermetic_session(SCRIPT)

    def test_loading_images_reports_the_pages(self):
        job = self.result["load"]

        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["result"], {"pages": 2, "names": ["001.png", "002.png"]})

    def test_unsaved_changes_block_a_new_load(self):
        job = self.result["reload_with_unsaved_changes"]

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["errors"][0]["type"], "UnsavedChanges")

    def test_archive_pages_are_loaded_in_order(self):
        job = self.result["load_archive"]

        self.assertEqual(job["status"], "succeeded", job)
        # Archive pages are extracted lazily and named by their position.
        self.assertEqual(job["result"], {"pages": 3, "names": ["1.png", "2.png", "3.png"]})

    def test_unreadable_image_fails_the_job_and_is_reported(self):
        job = self.result["load_broken"]

        self.assertEqual(job["status"], "failed")
        self.assertTrue(job["errors"], "the application's error should reach the job")
        self.assertIn("messages.error_details", self.result["prompts"])

    def test_invalid_requests_are_rejected_before_anything_runs(self):
        expected = {
            "empty": "ValueError",
            "missing": "FileNotFoundError",
            "project": "UnsupportedInput",
            "unsupported": "UnsupportedInput",
            "mixed_psd": "UnsupportedInput",
            "open_not_project": "ValueError",
            "open_missing": "FileNotFoundError",
        }
        for name, error_type in expected.items():
            with self.subTest(name=name):
                job = self.result["rejections"][name]
                self.assertEqual(job["status"], "failed")
                self.assertEqual(job["errors"][0]["type"], error_type)


if __name__ == "__main__":
    unittest.main()
