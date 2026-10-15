"""Tests for this repo's own hooks in .githooks/ (D-86).

commit-msg is tested on message files. pre-commit is tested in a temp git repo with real staged changes;
those tests need gitleaks and ruff on PATH (CI installs them from tools/dev-tools.txt).
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = shutil.which("sh") or shutil.which("bash")
GIT = shutil.which("git")


@unittest.skipUnless(SH, "needs sh")
class CommitMsgTest(unittest.TestCase):
    def check(self, message):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8", newline="\n") as f:
            f.write(message)
        self.addCleanup(os.remove, f.name)
        return subprocess.run([SH, str(ROOT / ".githooks" / "commit-msg"), f.name], capture_output=True, text=True)

    def assert_ok(self, message):
        result = self.check(message)
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_blocked(self, message, reason):
        result = self.check(message)
        self.assertEqual(result.returncode, 1)
        self.assertIn(reason, result.stderr)

    def test_scoped_title_with_trailer_passes(self):
        self.assert_ok("docs(research): add notes\n\nWhy, briefly.\n\nRefs: #1\nAssisted-by: Claude Opus 5.5 (low)\n")

    def test_title_without_scope_passes(self):
        self.assert_ok("docs: add notes\n\nRefs: #1\nAssisted-by: DeepSeek V4.1 Flash (high)\n")

    def test_co_authored_by_is_blocked_in_any_case(self):
        self.assert_blocked("docs: x\n\nAssisted-by: A (low)\nCo-Authored-By: A <a@example.com>\n", "Co-authored-by")

    def test_generated_with_line_is_blocked(self):
        self.assert_blocked("docs: x\n\nGenerated with a tool\n\nAssisted-by: A (low)\n", "Generated with")

    def test_missing_trailer_is_blocked(self):
        self.assert_blocked("docs: x\n", "Assisted-by")

    def test_trailer_must_be_the_last_line(self):
        self.assert_blocked("docs: x\n\nAssisted-by: A (low)\n\nmore text\n", "must end with")

    def test_trailer_needs_a_thinking_level(self):
        self.assert_blocked("docs: x\n\nAssisted-by: Claude Opus 5.5\n", "<thinking level>")

    def test_unknown_type_and_trailing_period_are_blocked(self):
        self.assert_blocked("update: things\n\nAssisted-by: A (low)\n", "type(scope): subject")
        self.assert_blocked("docs: things.\n\nAssisted-by: A (low)\n", "no period")

    def test_squash_lists_each_model_once(self):
        self.assert_ok("feat: x\n\nRefs: #1\nAssisted-by: A (high)\nAssisted-by: B (low)\n")
        self.assert_blocked("feat: x\n\nAssisted-by: A (high)\nAssisted-by: A (high)\n", "once")

    def test_merge_message_may_omit_the_trailer(self):
        self.assert_ok("Merge branch 'wip/x'\n")
        self.assert_ok("Merge pull request #3: batch\n\nAssisted-by: Claude Opus 5.5 (low)\n")

    def test_work_without_a_model_says_so(self):
        self.assert_ok("docs: fix a typo\n\nRefs: none\nAssisted-by: none (human)\n")

    def test_refs_line_is_required_and_checked(self):
        self.assert_blocked("docs: x\n\nAssisted-by: A (low)\n", "Refs:")
        self.assert_blocked("docs: x\n\nRefs: REQ-12\nAssisted-by: A (low)\n", "Refs: #12")
        self.assert_blocked("docs: x\n\nRefs: #1\nRefs: #2\nAssisted-by: A (low)\n", "one Refs line")
        self.assert_ok("docs: x\n\nRefs: #4, #27\nAssisted-by: A (low)\n")

    def test_refs_line_sits_directly_above_the_trailer(self):
        self.assert_blocked("docs: x\n\nRefs: #1\n\nWhy, briefly.\n\nAssisted-by: A (low)\n", "directly above")
        self.assert_blocked("docs: x\n\nRefs: #1\n\nAssisted-by: A (low)\n", "directly above")
        self.assert_ok('Revert "docs: x"\n\nAssisted-by: A (low)\n')

    def test_git_comments_and_verbose_diff_are_ignored(self):
        self.assert_ok(
            "docs: x\n\nRefs: #1\nAssisted-by: A (low)\n# Please enter the commit message\n"
            "# ------------------------ >8 ------------------------\ndiff --git a/x b/x\n"
        )


@unittest.skipUnless(SH and GIT and shutil.which("gitleaks") and shutil.which("ruff"), "needs git, gitleaks, ruff")
class PreCommitTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="githooks_test_"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")
        shutil.copytree(ROOT / ".githooks", self.root / ".githooks")
        shutil.copy(ROOT / "ruff.toml", self.root / "ruff.toml")

    def git(self, *args):
        subprocess.run([GIT, *args], cwd=self.root, check=True, capture_output=True)

    def stage(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8", newline="\n")
        self.git("add", name)
        return path

    def run_hook(self):
        return subprocess.run([SH, ".githooks/pre-commit"], cwd=self.root, capture_output=True, text=True)

    def test_clean_change_passes(self):
        self.stage("tool.py", "x = 1\n")
        self.assertEqual(self.run_hook().returncode, 0)

    def test_staged_secret_is_blocked(self):
        token = "ghp_" + "Zq7R2mXv9KpL4tYb8NwC3hJd6FsA1eGuIo5T"  # built at runtime so this file holds no token
        self.stage("config.txt", f"token = {token}\n")
        result = self.run_hook()
        self.assertEqual(result.returncode, 1)
        self.assertIn("looks like a secret", result.stderr)
        self.assertNotIn(token, result.stdout + result.stderr, "findings are redacted")

    def test_lint_finding_is_blocked(self):
        self.stage("tool.py", "import os\n")
        self.assertEqual(self.run_hook().returncode, 1)

    def test_the_staged_version_is_checked_not_the_working_copy(self):
        path = self.stage("tool.py", "x=1\n")
        path.write_text("x = 1\n", encoding="utf-8", newline="\n")  # fixed on disk, not staged
        result = self.run_hook()
        self.assertEqual(result.returncode, 1)
        self.assertIn("not formatted", result.stderr)

    def test_local_check_runs_when_configured(self):
        self.stage("tool.py", "x = 1\n")
        self.git("config", "pm.localcheck", "echo leak found; exit 1")
        result = self.run_hook()
        self.assertEqual(result.returncode, 1)
        self.assertIn("pm.localcheck failed", result.stderr)
        self.git("config", "pm.localcheck", "true")
        self.assertEqual(self.run_hook().returncode, 0)

    def test_missing_tool_blocks_instead_of_skipping(self):
        self.stage("tool.py", "x = 1\n")
        env = {**os.environ, "PATH": str(Path(GIT).parent)}  # git only, no gitleaks or ruff
        result = subprocess.run([SH, ".githooks/pre-commit"], cwd=self.root, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not found", result.stderr)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(GIT, "needs git")
class HookModeTest(unittest.TestCase):
    def test_hooks_are_executable_in_git(self):
        # Git on Linux and macOS skips a hook without the exec bit, silently; Windows checkouts cannot show it.
        listed = subprocess.run(
            [GIT, "ls-files", "-s", ".githooks", "template/.pm/hooks"], cwd=ROOT, capture_output=True, text=True
        ).stdout.splitlines()
        self.assertTrue(listed)
        for line in listed:
            self.assertTrue(line.startswith("100755 "), line)
