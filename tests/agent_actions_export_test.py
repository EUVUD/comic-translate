from __future__ import annotations

import sys
import unittest

from tests.agent_session_support import run_in_hermetic_session

SCRIPT = """
finished(actions.load_inputs([write_page("001.png", 40), write_page("002.png", 80)]))
out = environment.outputs_dir

for extension in ("pdf", "cbz", "cb7", "zip"):
    result[extension] = finished(actions.export(str(out / f"vol1.{extension}")))
result["existing"] = finished(actions.export(str(out / "vol1.pdf")))
result["overwrite"] = finished(actions.export(str(out / "vol1.pdf"), overwrite=True))
result["unsupported_format"] = finished(actions.export(str(out / "vol1.docx")))

result["save"] = finished(actions.save_project(str(out / "vol1.ctpr")))
result["save_again"] = finished(actions.save_project(str(out / "vol1.ctpr")))
(out / "other.ctpr").write_bytes(b"not mine")
result["save_over_other"] = finished(actions.save_project(str(out / "other.ctpr")))
result["save_elsewhere"] = finished(actions.save_project(str(out / "missing" / "x.ctpr")))

finished(actions.load_inputs([write_page("003.png", 120)], discard_unsaved=True))
result["reopen"] = finished(actions.open_project(str(out / "vol1.ctpr"), discard_unsaved=True))
"""


@unittest.skipUnless(sys.platform.startswith("linux"), "hermetic sessions are Linux-only")
class SaveAndExportActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_in_hermetic_session(SCRIPT, timeout=600)

    def _assert_rejected(self, name: str, error_type: str) -> None:
        job = self.result[name]
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(job["errors"][0]["type"], error_type)

    def test_every_export_format_contains_every_page(self):
        for extension in ("pdf", "cbz", "cb7", "zip"):
            with self.subTest(extension=extension):
                job = self.result[extension]
                self.assertEqual(job["status"], "succeeded", job)
                [output] = job["result"]["outputs"]
                self.assertTrue(output["path"].endswith(f"vol1.{extension}"))
                self.assertEqual((output["pages"], output["expected_pages"]), (2, 2))

    def test_existing_exports_are_only_replaced_on_request(self):
        self._assert_rejected("existing", "OutputExists")
        self.assertEqual(self.result["overwrite"]["status"], "succeeded", self.result["overwrite"])
        self._assert_rejected("unsupported_format", "ValueError")

    def test_saving_binds_the_session_to_the_project(self):
        job = self.result["save"]

        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["result"]["pages"], 2)
        self.assertGreater(job["result"]["bytes"], 0)
        self.assertFalse(job["result"]["unsaved_changes"])
        self.assertEqual(self.result["save_again"]["status"], "succeeded", self.result["save_again"])

    def test_saving_never_replaces_another_file_silently(self):
        self._assert_rejected("save_over_other", "OutputExists")
        self._assert_rejected("save_elsewhere", "FileNotFoundError")

    def test_a_saved_project_reopens_with_its_pages(self):
        job = self.result["reopen"]

        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["result"]["pages"], 2)


if __name__ == "__main__":
    unittest.main()
