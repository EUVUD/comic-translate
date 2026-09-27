from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# pipeline_config_test installs import stubs (modules without ``__file__``) that
# stay in sys.modules while discovery shares one process. Drop them so the real
# settings page loads.
for _name in ("PySide6", "PySide6.QtCore", "app.ui.messages", "app.ui.settings.settings_page"):
    if _name in sys.modules and not getattr(sys.modules[_name], "__file__", None):
        del sys.modules[_name]

from app.ui.settings.settings_page import SettingsPage


class StartupCreditRefreshTests(unittest.TestCase):
    def test_signed_out_startup_skips_the_online_probe(self):
        page = MagicMock()
        page.auth_client.is_authenticated.return_value = False

        SettingsPage._refresh_credits_on_startup(page)

        page._is_online.assert_not_called()
        page.auth_client.check_session_async.assert_not_called()

    def test_signed_in_startup_refreshes_the_session_when_online(self):
        page = MagicMock()
        page.auth_client.is_authenticated.return_value = True
        page._is_online.return_value = True

        SettingsPage._refresh_credits_on_startup(page)

        page.auth_client.check_session_async.assert_called_once()


class BackgroundUpdateCheckTests(unittest.TestCase):
    def test_offline_skips_the_background_check(self):
        page = MagicMock()
        with patch.dict(os.environ, {"CT_OFFLINE": "1"}):
            SettingsPage.check_for_updates(page, is_background=True)

        page.update_checker.check_for_updates.assert_not_called()

    def test_offline_still_runs_an_explicit_check(self):
        page = MagicMock()
        with patch.dict(os.environ, {"CT_OFFLINE": "1"}):
            SettingsPage.check_for_updates(page, is_background=False)

        page.update_checker.check_for_updates.assert_called_once()

    def test_background_check_runs_when_not_offline(self):
        page = MagicMock()
        with patch.dict(os.environ):
            os.environ.pop("CT_OFFLINE", None)
            SettingsPage.check_for_updates(page, is_background=True)

        page.update_checker.check_for_updates.assert_called_once()


if __name__ == "__main__":
    unittest.main()
