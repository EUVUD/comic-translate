from __future__ import annotations

import json
import sys
import unittest

from tests.agent_session_support import run_in_hermetic_session

SECRET = "sk-hermetic-secret"

SCRIPT = """
result["webtoon_without_pages"] = finished(actions.set_webtoon_mode(True))
finished(actions.load_inputs([write_page("001.png", 40), write_page("002.png", 80)]))
window = session.window

result["languages"] = finished(actions.set_languages("Japanese", "English"))
result["page_languages"] = [
    [window.image_states[path]["source_lang"], window.image_states[path]["target_lang"]]
    for path in window.image_files
]
result["unknown_language"] = finished(actions.set_languages("Klingon", "English"))

result["translators"] = actions.available_tools("translator")
result["tools"] = finished(actions.set_tools(
    translator="Custom", ocr="Default", inpainter="LaMa",
    custom_credentials={"api_key": "%(secret)s", "api_url": "http://127.0.0.1:9", "model": "fixture"},
))
result["unknown_tool"] = finished(actions.set_tools(translator="Babelfish"))
result["unknown_credential_field"] = finished(actions.set_tools(custom_credentials={"password": "x"}))

fonts = actions.available_fonts()
result["font"] = fonts[0]
result["render"] = finished(actions.set_render_options(font=fonts[0], uppercase=False, min_font_size=10, max_font_size=30))
result["render_settings_font"] = window.render_settings().font_family
result["unknown_font"] = finished(actions.set_render_options(font="No Such Font 123"))

result["webtoon_on"] = finished(actions.set_webtoon_mode(True))
result["webtoon_off"] = finished(actions.set_webtoon_mode(False))
""" % {"secret": SECRET}


@unittest.skipUnless(sys.platform.startswith("linux"), "hermetic sessions are Linux-only")
class ConfigurationActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_in_hermetic_session(SCRIPT)

    def _assert_rejected(self, name: str, error_type: str) -> None:
        job = self.result[name]
        self.assertEqual(job["status"], "failed", job)
        self.assertEqual(job["errors"][0]["type"], error_type)

    def test_languages_apply_to_every_page(self):
        self.assertEqual(self.result["languages"]["status"], "succeeded", self.result["languages"])
        self.assertEqual(self.result["page_languages"], [["Japanese", "English"], ["Japanese", "English"]])
        self._assert_rejected("unknown_language", "ValueError")

    def test_tools_are_selected_by_english_name(self):
        job = self.result["tools"]

        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["result"]["tools"], {
            "translator": "Custom", "ocr": "Default", "inpainter": "LaMa", "detector": "RT-DETR-v2",
        })
        self.assertTrue(job["result"]["custom_configured"])
        self.assertIn("Custom", self.result["translators"])

    def test_credentials_never_appear_in_results(self):
        self.assertNotIn(SECRET, json.dumps(self.result))

    def test_invalid_tool_requests_are_rejected(self):
        self._assert_rejected("unknown_tool", "ValueError")
        self._assert_rejected("unknown_credential_field", "ValueError")

    def test_render_options_select_the_font(self):
        job = self.result["render"]

        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["result"], {
            "font": self.result["font"], "uppercase": False, "min_font_size": 10, "max_font_size": 30,
        })
        self.assertEqual(self.result["render_settings_font"], self.result["font"])
        self._assert_rejected("unknown_font", "ValueError")

    def test_webtoon_mode_needs_pages_and_toggles(self):
        self._assert_rejected("webtoon_without_pages", "NoPagesLoaded")
        self.assertEqual(self.result["webtoon_on"]["result"], {"webtoon_mode": True})
        self.assertEqual(self.result["webtoon_off"]["result"], {"webtoon_mode": False})


if __name__ == "__main__":
    unittest.main()
