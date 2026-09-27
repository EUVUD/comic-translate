from __future__ import annotations

import sys
import unittest

from tests.agent_session_support import run_in_hermetic_session

# Two pages run through the real pipeline with fixture engines. OCR fails once
# on the second page, so the first run skips it and a retry recovers it.
SCRIPT = """
from evals.fixtures import FixtureProfile, page_fingerprint

def comic_page(name, stroke_rows):
    # Light page with dark, glyph-like strokes inside the text box, so the
    # real mask, inpainting and rendering stages have text to work on.
    image = np.full((96, 72, 3), 235, dtype=np.uint8)
    for row in stroke_rows:
        image[row:row + 2, 12:52] = 20
    path = environment.inputs_dir / name
    imk.write_image(str(path), image)
    return str(path), page_fingerprint(image)

first, first_page = comic_page("001.png", (14, 20, 26))
second, second_page = comic_page("002.png", (54, 60, 66))
profile = FixtureProfile({
    "pages": {
        first_page: {"blocks": [{"xyxy": [8, 10, 56, 32], "bubble_xyxy": [2, 4, 62, 38], "text": "こんにちは"}]},
        # Free text (no bubble) is cleaned by the inpainting model rather than
        # the bubble fast fill, so both cleaning paths are exercised.
        second_page: {"blocks": [{"xyxy": [8, 50, 56, 72], "bubble_xyxy": None, "text": "さようなら"}]},
    },
    "translations": {"こんにちは": "Hello", "さようなら": "Goodbye"},
    "faults": [{"stage": "ocr", "page": second_page, "error": "http_500", "times": 1}],
})
profile.install()

finished(actions.load_inputs([first, second]))
finished(actions.set_languages("Japanese", "English"))
finished(actions.set_tools(
    translator="Custom", ocr="Default", inpainter="LaMa",
    custom_credentials={"api_key": "fixture", "api_url": "http://127.0.0.1:9", "model": "fixture"},
))
result["without_font"] = finished(actions.translate_pages())
finished(actions.set_render_options(font=actions.available_fonts()[0]))

result["first_run"] = finished(actions.translate_pages(), timeout=300)
result["retry"] = finished(actions.retry_skipped(), timeout=300)
result["pages"] = session.snapshot()["pages"]
result["nothing_to_retry"] = finished(actions.retry_skipped())
result["skip"] = finished(actions.skip_pages([1]))
result["skip_state"] = session.snapshot()["pages"][1]["skip"]
result["out_of_range"] = finished(actions.translate_pages([5]))
result["stages"] = sorted({stage for stage, _ in profile.calls})

from agent.app_api import observations
result["detail"] = observations.page_detail(session.window, 0)
preview_path = environment.run_dir / "previews" / "page-1.png"
result["preview"] = finished(actions.render_page_preview(1, str(preview_path)))
preview, original = imk.read_image(str(preview_path)), imk.read_image(second)
result["preview_shape_matches"] = preview.shape == original.shape
result["preview_differs"] = bool((preview != original).any())
result["bad_preview"] = finished(actions.render_page_preview(9, str(preview_path)))
"""


@unittest.skipUnless(sys.platform.startswith("linux"), "hermetic sessions are Linux-only")
class TranslationActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_in_hermetic_session(SCRIPT, timeout=600)

    def test_preflight_explains_why_a_run_cannot_start(self):
        job = self.result["without_font"]

        self.assertEqual(job["status"], "failed")
        self.assertEqual([error["type"] for error in job["errors"]], ["NoFontSelected"])

    def test_first_run_skips_the_page_whose_ocr_failed(self):
        job = self.result["first_run"]

        self.assertEqual(job["status"], "succeeded", job)
        result = job["result"]
        self.assertEqual((result["pages"], result["completed"]), (2, 1))
        self.assertEqual([(entry["page"], entry["name"]) for entry in result["skipped"]], [(1, "002.png")])
        self.assertTrue(result["skipped"][0]["reasons"], "the skip reason should be reported")
        self.assertEqual((result["no_text"], result["untranslated"]), ([], []))
        self.assertFalse(result["complete"])

    def test_retry_recovers_the_skipped_page(self):
        job = self.result["retry"]

        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual((job["result"]["pages"], job["result"]["skipped"]), (1, []))
        self.assertTrue(job["result"]["complete"])

    def test_every_page_ends_up_translated_rendered_and_cleaned(self):
        pages = [(page["blocks"], page["translated_blocks"], page["text_items"]) for page in self.result["pages"]]

        self.assertEqual(pages, [(1, 1, 1), (1, 1, 1)])
        for page in self.result["pages"]:
            self.assertGreater(page["inpainted_patches"], 0, f"page {page['index']} was not cleaned")

    def test_the_real_pipeline_ran_every_stage(self):
        # The speech bubble is cleaned by fast fill; the free text on page 2
        # goes through the inpainting model.
        self.assertEqual(self.result["stages"], ["detection", "inpainting", "ocr", "translation"])

    def test_retry_needs_skipped_pages(self):
        job = self.result["nothing_to_retry"]

        self.assertEqual((job["status"], job["errors"][0]["type"]), ("failed", "NothingToRetry"))

    def test_pages_can_be_skipped(self):
        self.assertEqual(self.result["skip"]["result"], {"pages": [1], "skip": True})
        self.assertTrue(self.result["skip_state"])

    def test_page_detail_shows_source_text_and_translation(self):
        [block] = self.result["detail"]["block_details"]

        self.assertEqual((block["text"], block["translation"]), ("こんにちは", "Hello"))
        self.assertEqual(block["text_class"], "text_bubble")

    def test_preview_renders_the_translated_page(self):
        job = self.result["preview"]

        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual((job["result"]["page"], job["result"]["width"], job["result"]["height"]), (1, 72, 96))
        self.assertTrue(self.result["preview_shape_matches"])
        self.assertTrue(self.result["preview_differs"], "the preview should show the cleaned, translated page")
        self.assertEqual(self.result["bad_preview"]["errors"][0]["type"], "ValueError")

    def test_page_indices_are_validated(self):
        job = self.result["out_of_range"]

        self.assertEqual((job["status"], job["errors"][0]["type"]), ("failed", "ValueError"))


if __name__ == "__main__":
    unittest.main()
