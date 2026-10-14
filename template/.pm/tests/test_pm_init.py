"""Subprocess tests for the .pm package installer."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PM_INIT = Path(__file__).resolve().parent.parent / "tools" / "pm_init.py"
GIT = shutil.which("git")


def _remove_readonly(func, path, _exc_info):
    """Git marks .git/objects read-only on Windows; make them writable first."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


@unittest.skipUnless(GIT, "git is required for installer tests")
class PmInitTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pm_init_test_"))
        self.addCleanup(shutil.rmtree, self.root, onerror=_remove_readonly)
        subprocess.run([GIT, "init", "-q"], cwd=self.root, check=True)

    def run_init(self, target=None, *args):
        return subprocess.run(
            [sys.executable, str(PM_INIT), str(target or self.root), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_fresh_install_creates_package_and_named_config(self):
        result = self.run_init(self.root, "--name", "Example Project")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for relative in (
            ".pm/tools/pm_check.py",
            ".pm/hooks/pre-commit",
            ".pm/roles/lead.md",
            ".pm/templates/brief.md",
            ".pm/decisions.md",
            "CLAUDE.md",
        ):
            with self.subTest(path=relative):
                self.assertTrue((self.root / relative).is_file())
        for relative in (".pm/backlog/tasks", ".pm/worklog"):
            with self.subTest(path=relative):
                self.assertTrue((self.root / relative).is_dir())

        config = (self.root / "backlog.config.yml").read_text(encoding="utf-8")
        self.assertIn('backlog_directory: ".pm/backlog"', config)
        self.assertIn('project_name: "Example Project"', config)

    def test_install_writes_a_version_stamp(self):
        result = self.run_init()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / ".pm" / "backlog" / "drafts").is_dir())
        stamp = (self.root / ".pm" / "VERSION").read_text(encoding="utf-8")
        self.assertIn("package: ", stamp)
        self.assertIn("installed: ", stamp)

    def test_dry_run_reports_a_local_edit_and_writes_nothing(self):
        self.assertEqual(self.run_init().returncode, 0)
        edited = self.root / ".pm" / "tools" / "pm_check.py"
        edited.write_text(edited.read_text(encoding="utf-8") + "# local change\n", encoding="utf-8")
        before = edited.read_text(encoding="utf-8")

        result = self.run_init(self.root, "--upgrade", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("local-edit", result.stdout)
        self.assertIn("nothing was written", result.stdout)
        self.assertEqual(edited.read_text(encoding="utf-8"), before)
        self.assertFalse((self.root / ".pm" / "local" / "backup").exists())

    def test_dry_run_flags_a_local_edit_to_a_file_the_package_dropped(self):
        self.assertEqual(self.run_init().returncode, 0)
        source = Path(tempfile.mkdtemp(prefix="pm_pkg_"))
        self.addCleanup(shutil.rmtree, source, onerror=_remove_readonly)
        shutil.copytree(PM_INIT.parent.parent, source / ".pm")
        (source / ".pm" / "roles" / "reviewer.md").unlink()
        local = self.root / ".pm" / "roles" / "reviewer.md"
        local.write_text(local.read_text(encoding="utf-8") + "local rule\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(source / ".pm" / "tools" / "pm_init.py"), str(self.root), "--upgrade", "--dry-run"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("remove-edited", result.stdout)
        self.assertTrue(local.exists())

    def test_git_hooks_path_is_configured(self):
        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        hooks_path = subprocess.run(
            [GIT, "config", "--get", "core.hooksPath"],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        self.assertEqual(hooks_path.stdout.strip(), ".pm/hooks")

    def test_gitignore_entries_are_added_once_across_installs(self):
        first = self.run_init()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = self.run_init()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

        lines = (self.root / ".gitignore").read_text(encoding="utf-8").splitlines()
        for entry in (".pm/local/", ".pm-report.md", ".worktrees/"):
            with self.subTest(entry=entry):
                self.assertEqual(lines.count(entry), 1)

    def test_upgrade_preserves_project_data_and_edits(self):
        installed = self.run_init()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)

        preserved = {
            ".pm/backlog/tasks/task-1 - x.md": "# Task data\n",
            ".pm/decisions.md": "# Project decisions\nLocal edit\n",
            ".pm/board.md": "# Project board\nLocal board edit\n",
        }
        for relative, contents in preserved.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")

        upgraded = self.run_init(self.root, "--upgrade")

        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        for relative, contents in preserved.items():
            with self.subTest(path=relative):
                self.assertEqual((self.root / relative).read_text(encoding="utf-8"), contents)

    def test_upgrade_backs_up_replaced_package_folder(self):
        installed = self.run_init()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        extra = self.root / ".pm/tools/extra.txt"
        extra.write_text("local package file\n", encoding="utf-8")

        upgraded = self.run_init(self.root, "--upgrade")

        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        backups = list((self.root / ".pm/local/backup").glob("*/tools/extra.txt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "local package file\n")
        self.assertFalse(extra.exists())

    def test_installing_into_package_project_fails(self):
        package_project = PM_INIT.resolve().parent.parent.parent

        result = self.run_init(package_project)

        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
