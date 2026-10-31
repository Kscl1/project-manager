"""Tests for ``python .pm/tools/pm_feedback.py``.

A throwaway project holds synthetic private data: task and decision titles, a project name, a git user, a secret in
the environment. The error output and the command carry that data plus paths, secrets and a prompt. The tests check
that none of it reaches the written report or the body handed to ``gh``, and that ``gh issue create`` runs only after
an explicit yes. ``gh`` is never really called: ``subprocess.run`` is wrapped and every ``gh issue`` call recorded.

Standard library only.
"""

import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "pm_feedback.py"
spec = importlib.util.spec_from_file_location("pm_feedback", SCRIPT)
pm_feedback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm_feedback)

TASK_TITLE = "Secret launch plan for Zephyr Corp"
DECISION_TITLE = "Zephyr pricing stays private"
PROJECT_NAME = "zephyr-ledger"
GIT_USER = "Quill Testperson"
GIT_EMAIL = "quill@example.com"
ENV_SECRET = "zz-local-value-123456"
GITHUB_TOKEN = "ghp_" + "a1B2" * 9  # built at run time, so the secret scanners do not flag this file
OPENAI_KEY = "sk-" + "Zq9" * 8
PASSWORD = "hunter2-" + "x7" * 4
PROMPT = "write the invoice exporter for my biggest client"
PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA7zq\n-----END RSA PRIVATE KEY-----"


def make_project(base):
    root = base / "zephyr-ledger-app"
    tasks = root / ".pm" / "backlog" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "task-7 - Secret-launch-plan-for-Zephyr-Corp.md").write_text(
        f"---\nid: TASK-7\ntitle: '{TASK_TITLE}'\nstatus: Ready\n---\n\nbody\n", encoding="utf-8"
    )
    (root / ".pm" / "decisions").mkdir()
    (root / ".pm" / "decisions" / "D-01.md").write_text(f'---\nid: D-01\ntitle: "{DECISION_TITLE}"\n---\n')
    (root / ".pm" / "VERSION").write_text("package: abc1234 2026-10-15\ninstalled: 2026-10-15\n")
    (root / "backlog.config.yml").write_text(f'project_name: "{PROJECT_NAME}"\n')
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", GIT_USER], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", GIT_EMAIL], cwd=root, check=True)
    return root


def error_output(root):
    return "\n".join(
        [
            "Traceback (most recent call last):",
            f'  File "{root / ".pm" / "tools" / "pm_check.py"}", line 40, in main',
            f'  File "{root / "src" / "billing" / "exporter.py"}", line 9, in run',
            f'  File "{Path.home() / "notes" / "client-list.txt"}", line 1',
            '  File "/home/quill/clients/acme/main.py", line 3',
            r"  File 'C:\Users\quill\clients\acme\main.py', line 3",
            "while reading .pm/backlog/tasks/task-7 - Secret-launch-plan-for-Zephyr-Corp.md and src/billing/rates.py",
            f"task: {TASK_TITLE}; decision: {DECISION_TITLE}; project {PROJECT_NAME}",
            f"author {GIT_USER} <{GIT_EMAIL}>",
            f"GITHUB_TOKEN={GITHUB_TOKEN} OPENAI={OPENAI_KEY} password: {PASSWORD} env {ENV_SECRET}",
            "Authorization: Bearer abcdefghijklmnop123",
            PRIVATE_KEY,
            f'prompt was "{PROMPT}"',
            "KeyError: 'status'",
        ]
    )


FORBIDDEN = [
    TASK_TITLE,
    DECISION_TITLE,
    PROJECT_NAME,
    "zephyr-ledger-app",
    GIT_USER,
    GIT_EMAIL,
    ENV_SECRET,
    GITHUB_TOKEN,
    OPENAI_KEY,
    PASSWORD,
    PROMPT,
    "MIIEpAIBAAKCAQEA7zq",
    "abcdefghijklmnop123",
    "Secret-launch-plan",
    "billing",
    "exporter",
    "client-list",
    "clients",
    "quill",
    str(Path.home()),
    Path.home().as_posix(),
]


class Recorder:
    """Wraps subprocess.run: records `gh issue` calls instead of running them, passes everything else through."""

    def __init__(self):
        self.calls = []
        self.real = subprocess.run

    def __call__(self, args, *rest, **kwargs):
        if list(args[:2]) == ["gh", "issue"]:
            self.calls.append((list(args), kwargs.get("input", "")))
            self.encoding = kwargs.get("encoding")
            return subprocess.CompletedProcess(args, 0)
        return self.real(args, *rest, **kwargs)


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_project(Path(tmp.name))
        self.error_file = Path(tmp.name) / "error.txt"
        self.error_file.write_text(error_output(self.root), encoding="utf-8")
        self.gh = Recorder()
        for patch in (
            mock.patch.object(pm_feedback.subprocess, "run", self.gh),
            mock.patch.dict(pm_feedback.os.environ, {"ZEPHYR_API_TOKEN": ENV_SECRET}),
            mock.patch.object(pm_feedback, "tool_versions", lambda: "python 3.x\ngit: git version 2.x"),
            mock.patch.object(pm_feedback.shutil, "which", lambda name: name),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def run_tool(self, *args, answer=None):
        out = io.StringIO()
        reply = mock.patch("builtins.input", side_effect=EOFError if answer is None else [answer])
        with reply, redirect_stdout(out):
            code = pm_feedback.main(["--root", str(self.root), *args])
        return code, out.getvalue()

    def write_report(self):
        command = f'pi -p "{PROMPT}" --cwd {self.root}'
        code, out = self.run_tool(
            "--command",
            command,
            "--error-file",
            str(self.error_file),
            "--harness",
            "Pi 1.0.3, DeepSeek V4.1 Flash (high)",
            "--title",
            f"pm_check crashes on {TASK_TITLE}",
        )
        self.assertEqual(code, 0)
        reports = list((self.root / ".pm" / "local" / "feedback").glob("*.md"))
        self.assertEqual(len(reports), 1)
        return reports[0], out

    def assertClean(self, text):
        for value in FORBIDDEN:
            self.assertNotIn(value.lower(), text.lower(), f"{value!r} leaked")

    def test_report_keeps_only_the_diagnosis(self):
        report, out = self.write_report()
        text = report.read_text(encoding="utf-8")
        self.assertClean(text)
        self.assertClean(out)
        for field in pm_feedback.FIELDS:
            self.assertIn(f"### {field}", text)
        self.assertIn("package: abc1234", text)
        self.assertIn("<project>/.pm/tools/pm_check.py", text)  # package paths stay: they help triage
        self.assertIn("KeyError: 'status'", text)
        self.assertIn("Nothing was sent", out)
        self.assertEqual(self.gh.calls, [])

    def test_ordinary_words_and_counts_stay(self):
        tasks = self.root / ".pm" / "backlog" / "tasks"
        (tasks / "task-1.7 - Charter.md").write_text("---\nid: TASK-1.7\ntitle: Charter\n---\n", encoding="utf-8")
        line = "the charter says WIP 1/7 and/or 10/16; see src/app.py, docs/research/notes and my/folder.v2"
        text = pm_feedback.redact(line, self.root, pm_feedback.private_strings(self.root))
        self.assertEqual(text, "the charter says WIP 1/7 and/or 10/16; see <file>, <file> and <file>")

    def test_error_excerpt_is_short(self):
        self.error_file.write_text("\n".join(f"line {n}" for n in range(100)), encoding="utf-8")
        report, _ = self.write_report()
        text = report.read_text(encoding="utf-8")
        self.assertIn("line 99", text)
        self.assertNotIn("line 79\n", text)

    def test_no_answer_sends_nothing(self):
        report, _ = self.write_report()
        code, out = self.run_tool("--send", str(report))
        self.assertEqual(code, 0)
        self.assertIn("Nothing sent", out)
        self.assertEqual(self.gh.calls, [])

    def test_no_sends_nothing(self):
        report, _ = self.write_report()
        for answer in ("n", "no", "", "later", "send it?"):
            self.run_tool("--send", str(report), answer=answer)
        self.assertEqual(self.gh.calls, [])

    def test_yes_opens_one_clean_issue(self):
        report, _ = self.write_report()
        code, out = self.run_tool("--send", str(report), answer="yes")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.gh.calls), 1)
        args, body = self.gh.calls[0]
        self.assertEqual(args[:5], ["gh", "issue", "create", "--repo", pm_feedback.HOME_REPO])
        self.assertTrue(args[args.index("--title") + 1].startswith("[feedback] pm_check crashes on"))
        self.assertIn("### Error excerpt", body)
        self.assertClean(" ".join(args) + body)
        self.assertClean(out)

    def test_gh_gets_utf8_whatever_the_locale(self):
        self.error_file.write_text("DESIGN.md: 538 lines\n    → split by topic", encoding="utf-8")
        report, _ = self.write_report()
        self.run_tool("--send", str(report), "--yes")
        self.assertIn("→ split by topic", self.gh.calls[0][1])
        self.assertEqual(self.gh.encoding, "utf-8")  # not the locale's code page (cp1252 on Windows)

    def test_error_from_stdin_is_read_as_utf8(self):
        env = {**pm_feedback.os.environ, "PYTHONIOENCODING": "cp1252", "PATH": str(Path(sys.executable).parent)}
        done = self.gh.real(
            [sys.executable, str(SCRIPT), "--root", str(self.root), "--command", "pm_check", "--error-file", "-"],
            input="DESIGN.md: 538 lines\n    → split by topic\n".encode("utf-8"),
            capture_output=True,
            env=env,
        )
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        (report,) = (self.root / ".pm" / "local" / "feedback").glob("*.md")
        self.assertIn("→ split by topic", report.read_text(encoding="utf-8"))

    def test_missing_gh_sends_nothing_and_says_so(self):
        report, _ = self.write_report()
        with mock.patch.object(pm_feedback.shutil, "which", lambda name: None):
            code, out = self.run_tool("--send", str(report), "--yes")
        self.assertEqual(code, 1)
        self.assertIn("gh is missing or not signed in", out)
        self.assertIn(report.as_posix(), out)
        self.assertEqual(self.gh.calls, [])

    def test_apostrophes_in_prose_stay(self):
        private = pm_feedback.private_strings(self.root)
        prose = "it is the design system's single file, read whole by that tool's parser; users' files don't move."
        self.assertEqual(pm_feedback.redact(prose, self.root, private), prose)
        for quoted in ("prompt was 'write the invoice exporter now'", "(it's the prompt we sent)"):
            text = pm_feedback.redact(quoted.replace("(", "('").replace(")", "')"), self.root, private)
            self.assertIn("<text>", text)
        self.assertEqual(pm_feedback.redact("KeyError: 'status'", self.root, private), "KeyError: 'status'")

    def test_yes_never_sends_text_the_owner_did_not_see(self):
        report, _ = self.write_report()
        with report.open("a", encoding="utf-8") as extra:
            extra.write(f"\nadded by hand: {TASK_TITLE} {GITHUB_TOKEN} {self.root / 'src' / 'billing'}\n")
        code, out = self.run_tool("--send", str(report), "--yes")
        self.assertEqual(code, 1)
        self.assertIn("nothing sent", out)
        self.assertEqual(self.gh.calls, [])
        shown = report.read_text(encoding="utf-8")
        self.assertClean(shown)  # the file now holds the redacted text, ready to show again
        self.run_tool("--send", str(report), "--yes")
        self.assertEqual(len(self.gh.calls), 1)
        args, body = self.gh.calls[0]
        title, _, rest = shown.partition("\n")
        self.assertEqual((args[args.index("--title") + 1], body), (title.lstrip("# ").strip(), rest.strip() + "\n"))


if __name__ == "__main__":
    unittest.main()
