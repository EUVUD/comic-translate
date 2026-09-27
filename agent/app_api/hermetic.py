from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

NULL_KEYRING = "keyring.backends.null.Keyring"
ROOT_VARIABLE = "CT_AGENT_HERMETIC_ROOT"
PROFILE_VARIABLE = "CT_AGENT_ENGINE_PROFILE"
NETWORK_VARIABLE = "CT_AGENT_ALLOW_NETWORK"


def isolation_supported() -> bool:
    """Qt keeps settings in redirectable INI files only on Linux.

    Windows (registry) and macOS (CFPreferences) need all
    ``QSettings("ComicLabs", "ComicTranslate")`` constructions routed through
    one helper before hermetic sessions can run there.
    """
    return sys.platform.startswith("linux")


@dataclass(frozen=True)
class HermeticEnvironment:
    """Directories and settings that keep an agent session away from user data.

    Settings live in a private config directory, account credentials are hidden
    behind a keyring that stores nothing, and inputs, outputs and autosaves stay
    inside the sandbox. The model cache stays shared on purpose, so models are
    not downloaded again for every scenario.
    """

    root: Path
    engine_profile: str = "real"
    allow_network: bool = False

    @classmethod
    def create(cls, parent: str | os.PathLike | None = None, **options) -> HermeticEnvironment:
        environment = cls(Path(tempfile.mkdtemp(prefix="ct-agent-", dir=parent)), **options)
        environment.prepare()
        return environment

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] = os.environ) -> HermeticEnvironment | None:
        """Rebuild the environment a parent process described in ``variables()``."""
        root = environ.get(ROOT_VARIABLE)
        if not root:
            return None
        return cls(
            Path(root),
            engine_profile=environ.get(PROFILE_VARIABLE, "real"),
            allow_network=environ.get(NETWORK_VARIABLE) == "1",
        )

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def sandbox_dir(self) -> Path:
        return self.root / "sandbox"

    @property
    def inputs_dir(self) -> Path:
        return self.sandbox_dir / "inputs"

    @property
    def outputs_dir(self) -> Path:
        return self.sandbox_dir / "outputs"

    @property
    def autosave_dir(self) -> Path:
        return self.sandbox_dir / "autosave"

    @property
    def run_dir(self) -> Path:
        return self.root / "run"

    def prepare(self) -> None:
        for directory in (self.config_dir, self.inputs_dir, self.outputs_dir, self.autosave_dir, self.run_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def variables(self) -> dict[str, str]:
        """Environment for a child process that should run inside this sandbox."""
        return {
            "XDG_CONFIG_HOME": str(self.config_dir),
            "PYTHON_KEYRING_BACKEND": NULL_KEYRING,
            "QT_QPA_PLATFORM": "offscreen",
            ROOT_VARIABLE: str(self.root),
            PROFILE_VARIABLE: self.engine_profile,
            NETWORK_VARIABLE: "1" if self.allow_network else "0",
        }

    def contains(self, path: str | os.PathLike) -> bool:
        """True when ``path`` resolves inside the sandbox."""
        return Path(path).resolve().is_relative_to(self.sandbox_dir.resolve())

    def apply(self) -> None:
        """Isolate the current process. Call it before the application starts.

        There is no undo: Qt offers no way to read back the previous settings
        path, so each hermetic session gets a process of its own.
        """
        if not isolation_supported():
            raise RuntimeError("hermetic settings isolation is only supported on Linux")

        import keyring
        from keyring.backends.null import Keyring as NullKeyring
        from PySide6.QtCore import QSettings

        os.environ.update(self.variables())
        # Libraries read these lazily, and the process may already have used
        # them, so set both explicitly instead of relying on the variables.
        keyring.set_keyring(NullKeyring())
        for settings_format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
            QSettings.setPath(settings_format, QSettings.Scope.UserScope, str(self.config_dir))
            QSettings.setPath(settings_format, QSettings.Scope.SystemScope, str(self.config_dir / "system"))
