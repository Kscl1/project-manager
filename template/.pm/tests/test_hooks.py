"""Tests for the package hooks in .pm/hooks/.

Each test builds a small git repo in a temp dir with the package hook and pm_check, then runs the hook
the way git does: with the repo root as the working directory.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
SH = shutil.which("sh") or shutil.which("bash")
GIT = shutil.which("git")


@unittest.skipUnless(SH and GIT, "needs sh and git")
class HookTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pm_hooks_test_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run([GIT, "init", "-q"], cwd=self.root, check=True)
        for part in ("hooks", "tools"):
            shutil.copytree(PKG / part, self.root / ".pm" / part)
        (self.root / "backlog.config.yml").write_text("", encoding="utf-8")

    def project_hook(self, name, body):
        path = self.root / ".githooks" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n")

    def run_hook(self, name, *args):
        return subprocess.run([SH, f".pm/hooks/{name}", *args], cwd=self.root, capture_output=True, text=True)

    def test_pre_commit_without_project_hook_passes(self):
        self.assertEqual(self.run_hook("pre-commit").returncode, 0)

    def test_pre_commit_runs_the_project_hook_after_the_doc_check(self):
        self.project_hook("pre-commit", "echo ran > ran.txt")
        self.assertEqual(self.run_hook("pre-commit").returncode, 0)
        self.assertTrue((self.root / "ran.txt").exists())

    def test_failing_project_pre_commit_blocks(self):
        self.project_hook("pre-commit", "exit 4")
        self.assertEqual(self.run_hook("pre-commit").returncode, 4)

    def test_the_gate_asks_for_python_39(self):
        # a python that is too old for the tools (and no python3): the hook must name the version it needs
        fake = self.root / "bin"
        fake.mkdir()
        for name in ("python", "python3"):
            script = fake / name
            script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
            script.chmod(0o755)
        result = subprocess.run(
            [SH, ".pm/hooks/pre-commit"],
            cwd=self.root,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": str(fake)},
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Python 3.9+ not found", result.stderr)

    def test_commit_msg_without_project_hook_passes(self):
        self.assertEqual(self.run_hook("commit-msg", "MSG").returncode, 0)

    def test_commit_msg_hands_the_message_file_to_the_project_hook(self):
        self.project_hook("commit-msg", 'test "$1" = MSG || exit 5\nexit 3')
        self.assertEqual(self.run_hook("commit-msg", "MSG").returncode, 3)


if __name__ == "__main__":
    unittest.main()
