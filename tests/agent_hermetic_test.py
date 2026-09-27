from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from agent.app_api.hermetic import HermeticEnvironment

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Runs in a fresh process: a signed-in user's token is stored first, exactly as
# the application stores it without a system keyring, then the hermetic
# environment is applied and the application's own lookup must find nothing.
ISOLATION_PROBE = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from PySide6.QtCore import QSettings

    user_settings = QSettings("ComicLabs", "ComicTranslate")
    user_settings.setValue("auth/access_token", "user-secret")
    user_settings.sync()

    from agent.app_api.hermetic import HermeticEnvironment
    environment = HermeticEnvironment.create(sys.argv[1])
    environment.apply()

    import keyring
    from app.account.auth.token_storage import get_token

    settings = QSettings("ComicLabs", "ComicTranslate")
    settings.setValue("probe", "hermetic")
    settings.sync()
    print(repr(get_token("access_token")))
    print(type(keyring.get_keyring()).__module__)
    print(Path(settings.fileName()).is_relative_to(environment.config_dir))
    """
)


class HermeticEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.parent = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_create_prepares_sandbox_directories(self):
        environment = HermeticEnvironment.create(self.parent)

        self.assertEqual(environment.root.parent, self.parent)
        for directory in (
            environment.config_dir,
            environment.inputs_dir,
            environment.outputs_dir,
            environment.autosave_dir,
            environment.run_dir,
        ):
            self.assertTrue(directory.is_dir(), directory)

    def test_variables_round_trip_through_child_environment(self):
        environment = HermeticEnvironment.create(self.parent, engine_profile="fixtures", allow_network=True)
        variables = environment.variables()

        self.assertEqual(variables["XDG_CONFIG_HOME"], str(environment.config_dir))
        self.assertEqual(variables["PYTHON_KEYRING_BACKEND"], "keyring.backends.null.Keyring")
        self.assertEqual(variables["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(HermeticEnvironment.from_environ(variables), environment)
        self.assertIsNone(HermeticEnvironment.from_environ({}))

    def test_contains_accepts_only_sandbox_paths(self):
        environment = HermeticEnvironment.create(self.parent)

        self.assertTrue(environment.contains(environment.outputs_dir / "vol1.pdf"))
        self.assertFalse(environment.contains(environment.config_dir / "ComicLabs"))
        self.assertFalse(environment.contains(environment.outputs_dir / ".." / ".." / "escape.txt"))

    def test_apply_refuses_unsupported_platforms_before_changing_anything(self):
        environment = HermeticEnvironment.create(self.parent)
        before = dict(os.environ)

        with patch("agent.app_api.hermetic.isolation_supported", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "only supported on Linux"):
                environment.apply()
        self.assertEqual(dict(os.environ), before)

    @unittest.skipUnless(sys.platform.startswith("linux"), "settings isolation is Linux-only")
    def test_apply_hides_existing_user_token_and_settings(self):
        user_config = self.parent / "user-config"
        child_environment = {**os.environ, "XDG_CONFIG_HOME": str(user_config)}
        completed = subprocess.run(
            [sys.executable, "-c", ISOLATION_PROBE, str(self.parent)],
            cwd=REPOSITORY_ROOT,
            env=child_environment,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.split(), ["None", "keyring.backends.null", "True"])
        user_file = (user_config / "ComicLabs" / "ComicTranslate.conf").read_text(encoding="utf-8")
        self.assertIn("user-secret", user_file)
        self.assertNotIn("probe", user_file)


if __name__ == "__main__":
    unittest.main()
