from __future__ import annotations

import ast
from pathlib import Path
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCANNED = ("app", "pipeline", "modules", "controller.py")
# Vendored widget library, and the seam itself, may call exec() directly.
ALLOWED = ("app/ui/dayu_widgets/", "app/ui/interaction.py")


class ModalRoutingTests(unittest.TestCase):
    def test_no_modal_exec_bypasses_the_interaction_policy(self):
        """Every modal dialog must run through ``app.ui.interaction.run_modal``.

        Automated sessions rely on the installed interaction policy; a direct
        ``exec()`` would block them with a dialog nobody can answer.
        """
        offenders = []
        for entry in SCANNED:
            root = REPOSITORY_ROOT / entry
            paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
            for path in paths:
                relative = path.relative_to(REPOSITORY_ROOT).as_posix()
                if relative.startswith(ALLOWED):
                    continue
                # utf-8-sig: some sources start with a byte-order mark.
                source = path.read_text(encoding="utf-8-sig")
                if "exec" not in source:  # a call must spell the name out
                    continue
                tree = ast.parse(source, filename=relative)
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("exec", "exec_")
                        and not node.args
                        and not node.keywords
                    ):
                        offenders.append(f"{relative}:{node.lineno}")

        self.assertEqual(offenders, [], "route these through app.ui.interaction.run_modal")


if __name__ == "__main__":
    unittest.main()
