"""Subprocess tests for the .pm package installer."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PM_INIT = Path(__file__).resolve().parent.parent / "tools" / "pm_init.py"
SKILLS = PM_INIT.parent.parent.parent / ".agents" / "skills"
GIT = shutil.which("git")
# A project's own .pm/local (run folders, backups, nested repos) is no part of the package: never copy it.
PACKAGE_ONLY = shutil.ignore_patterns("__pycache__", "local")


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

    def test_version_stamp_names_a_skill_only_commit_and_its_tag(self):
        source = Path(tempfile.mkdtemp(prefix="pm_src_"))
        self.addCleanup(shutil.rmtree, source, onerror=_remove_readonly)
        shutil.copytree(PM_INIT.parent.parent, source / "template" / ".pm", ignore=PACKAGE_ONLY)
        shutil.copytree(SKILLS, source / "template" / ".agents" / "skills")
        git = [GIT, "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "core.hooksPath=.git/hooks"]
        subprocess.run([GIT, "init", "-q"], cwd=source, check=True, capture_output=True)
        subprocess.run([*git, "add", "-A"], cwd=source, check=True, capture_output=True)
        subprocess.run([*git, "commit", "-qm", "package"], cwd=source, check=True, capture_output=True)
        skill = next((source / "template" / ".agents" / "skills").glob("pm-*/SKILL.md"))
        skill.write_text(skill.read_text(encoding="utf-8") + "skill change\n", encoding="utf-8")
        subprocess.run([*git, "commit", "-qam", "skill only"], cwd=source, check=True, capture_output=True)
        subprocess.run([*git, "tag", "v9.9.9"], cwd=source, check=True, capture_output=True)
        head = subprocess.run(
            [GIT, "log", "-1", "--format=%h"], cwd=source, capture_output=True, text=True, check=True
        ).stdout.strip()

        result = subprocess.run(
            [sys.executable, str(source / "template" / ".pm" / "tools" / "pm_init.py"), str(self.root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stamp = (self.root / ".pm" / "VERSION").read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(stamp.startswith(f"package: {head} "), stamp)
        self.assertTrue(stamp.endswith(" (v9.9.9)"), stamp)

    def test_an_upgrade_with_nothing_new_keeps_everything_and_names_the_upgrade_checks(self):
        self.assertEqual(self.run_init().returncode, 0)

        result = self.run_init(self.root, "--upgrade")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / ".pm" / "local" / "backup").exists())
        self.assertIn("Plan for", result.stdout)
        plan = result.stdout.split("Plan for", 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("upgrade", plan)
        after = result.stdout.split("\nNext:", 1)[1]
        self.assertIn("python -m unittest discover -s .pm/tests", after)
        self.assertIn("python .pm/tools/pm_board.py --resume", after)
        self.assertIn("upgrading.md", after)
        self.assertNotIn("/pm-setup", after)

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

    def test_a_clone_with_autocrlf_reports_no_skill_as_edited(self):
        # Git for Windows often sets core.autocrlf=true; the manifest hashes bytes, so CRLF copies looked edited.
        self.assertEqual(self.run_init().returncode, 0)
        # Without the installed hooks: run from an installed project, the seed files cite that project's own paths
        # and its pm_check would refuse this commit.
        no_hooks = tempfile.mkdtemp(prefix="pm_nohooks_")
        self.addCleanup(shutil.rmtree, no_hooks)
        git = [GIT, "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", f"core.hooksPath={no_hooks}"]
        subprocess.run([*git, "add", "-A"], cwd=self.root, check=True, capture_output=True)
        subprocess.run([*git, "commit", "-qm", "install"], cwd=self.root, check=True, capture_output=True)
        clone = Path(tempfile.mkdtemp(prefix="pm_clone_")) / "c"
        self.addCleanup(shutil.rmtree, clone.parent, onerror=_remove_readonly)
        subprocess.run([GIT, "-c", "core.autocrlf=true", "clone", "-q", str(self.root), str(clone)], check=True)

        result = self.run_init(clone, "--upgrade", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("EDITED", result.stdout)
        self.assertNotIn("differs", result.stdout)  # a missing manifest would hide the edits

    def test_dry_run_flags_a_local_edit_to_a_file_the_package_dropped(self):
        self.assertEqual(self.run_init().returncode, 0)
        source = Path(tempfile.mkdtemp(prefix="pm_pkg_"))
        self.addCleanup(shutil.rmtree, source, onerror=_remove_readonly)
        shutil.copytree(PM_INIT.parent.parent, source / ".pm", ignore=PACKAGE_ONLY)
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

    def test_hooks_are_staged_as_executable(self):
        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        staged = subprocess.run(
            [GIT, "ls-files", "-s", ".pm/hooks"], cwd=self.root, capture_output=True, text=True, check=True
        ).stdout.splitlines()
        self.assertEqual(len(staged), 2, staged)
        for line in staged:
            self.assertTrue(line.startswith("100755 "), line)

    def test_gitignore_entries_are_added_once_across_installs(self):
        first = self.run_init()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = self.run_init()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

        lines = (self.root / ".gitignore").read_text(encoding="utf-8").splitlines()
        for entry in (".pm/local/", ".pm-report.md", ".worktrees/"):
            with self.subTest(entry=entry):
                self.assertEqual(lines.count(entry), 1)

    def test_ignore_lets_search_into_pm_once_and_keeps_existing_lines(self):
        fresh = self.run_init()
        self.assertEqual(fresh.returncode, 0, fresh.stdout + fresh.stderr)
        self.assertIn("!.pm/", (self.root / ".ignore").read_text(encoding="utf-8").splitlines())

        other = Path(tempfile.mkdtemp(prefix="pm_ignore_"))
        self.addCleanup(shutil.rmtree, other, onerror=_remove_readonly)
        subprocess.run([GIT, "init", "-q"], cwd=other, check=True)
        (other / ".ignore").write_text("vendor/\n!vendor/keep/", encoding="utf-8")  # no final newline
        self.assertEqual(self.run_init(other).returncode, 0)
        first = (other / ".ignore").read_text(encoding="utf-8")
        self.assertTrue(first.startswith("vendor/\n!vendor/keep/\n"), first)
        self.assertEqual(first.splitlines().count("!.pm/"), 1)
        self.assertEqual(self.run_init(other, "--upgrade").returncode, 0)
        self.assertEqual((other / ".ignore").read_text(encoding="utf-8"), first, "a second run changes nothing")

    @unittest.skipUnless(shutil.which("rg"), "ripgrep is required for the search check")
    def test_plain_rg_finds_pm_records_but_not_local_or_git_ignored_files(self):
        needle = "needle" + "-4711"  # split, because the installed copy of this test sits in .pm/tests/ too
        plain = Path(tempfile.mkdtemp(prefix="pm_nogit_"))  # ripgrep reads .gitignore only inside a git repository
        self.addCleanup(shutil.rmtree, plain, onerror=_remove_readonly)
        for root, git_ignored in ((self.root, "build/out.txt"), (plain, None)):
            with self.subTest(git=git_ignored is not None):
                self.assertEqual(self.run_init(root).returncode, 0)
                with (root / ".gitignore").open("a", encoding="utf-8") as out:
                    out.write("build/\n")
                for relative in (".pm/decisions/D-1-sentinel.md", ".pm/local/scratch/note.md", git_ignored):
                    if relative:
                        path = root / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(needle + "\n", encoding="utf-8")

                found = subprocess.run(
                    # An explicit path: without one, rg reads stdin when stdin is not a terminal, as in CI.
                    ["rg", "-l", needle, "."],
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                ).stdout
                found = [Path(line).as_posix() for line in found.splitlines()]
                self.assertEqual(found, [".pm/decisions/D-1-sentinel.md"])

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

    def test_install_copies_every_pm_skill_with_a_claude_pointer(self):
        source = Path(tempfile.mkdtemp(prefix="pm_pkg_"))
        self.addCleanup(shutil.rmtree, source, onerror=_remove_readonly)
        shutil.copytree(PM_INIT.parent.parent, source / ".pm", ignore=PACKAGE_ONLY)
        shutil.copytree(SKILLS, source / ".agents" / "skills")
        for name in ("pm-extra", "own-skill"):  # a pm- skill no list names, and a skill that is not the package's
            skill = source / ".agents" / "skills" / name / "SKILL.md"
            skill.parent.mkdir()
            skill.write_text(f"---\nname: {name}\ndescription: Test skill.\n---\n\nBody.\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(source / ".pm" / "tools" / "pm_init.py"), str(self.root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("pm-grilling", "pm-grill-me", "pm-scratch", "pm-extra"):
            with self.subTest(skill=name):
                self.assertTrue((self.root / ".agents" / "skills" / name / "SKILL.md").is_file())
                pointer = (self.root / ".claude" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(pointer.startswith(f"---\nname: {name}\n"))
                self.assertIn(f"Read `.agents/skills/{name}/SKILL.md`", pointer)
        self.assertTrue((self.root / ".agents" / "skills" / "pm-grilling" / "LICENSE").is_file())
        scratch = (self.root / ".claude" / "skills" / "pm-scratch" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", scratch)
        self.assertFalse((self.root / ".agents" / "skills" / "own-skill").exists())
        self.assertFalse((self.root / ".claude" / "skills" / "own-skill").exists())
        manifest = (self.root / ".pm" / "package-files.sha256").read_text(encoding="utf-8")
        self.assertIn("  .agents/skills/pm-grilling/SKILL.md", manifest)

    def test_upgrade_replaces_pm_skills_and_keeps_the_projects_own(self):
        self.assertEqual(self.run_init().returncode, 0)
        own = self.root / ".agents" / "skills" / "my-skill" / "SKILL.md"
        own.parent.mkdir()
        own.write_text("---\nname: my-skill\ndescription: Mine.\n---\n", encoding="utf-8")
        edited = self.root / ".agents" / "skills" / "pm-scratch" / "SKILL.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "local rule\n", encoding="utf-8")

        result = self.run_init(self.root, "--upgrade")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("local-edit", result.stdout)
        self.assertEqual(edited.read_bytes(), (SKILLS / "pm-scratch" / "SKILL.md").read_bytes())
        backups = list((self.root / ".pm/local/backup").glob("*/.agents/skills/pm-scratch/SKILL.md"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].read_text(encoding="utf-8").endswith("local rule\n"))
        self.assertTrue(own.is_file())

    def test_installing_into_package_project_fails(self):
        package_project = PM_INIT.resolve().parent.parent.parent

        result = self.run_init(package_project)

        self.assertNotEqual(result.returncode, 0)

    def snapshot(self):
        """Every file under the project (outside .git) with its bytes, plus the staged index."""
        files = {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(self.root).parts
        }
        index = subprocess.run([GIT, "ls-files", "-s"], cwd=self.root, capture_output=True, text=True).stdout
        return files, index

    def test_second_run_changes_nothing(self):
        self.assertEqual(self.run_init().returncode, 0)
        before = self.snapshot()

        second = self.run_init()

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("  write ", second.stdout)

    def test_session_hooks_and_mcp_are_written(self):
        self.assertEqual(self.run_init().returncode, 0)

        settings = json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        matchers = {group["matcher"] for group in settings["hooks"]["SessionStart"]}
        self.assertEqual(matchers, {"startup|resume|clear", "compact"})
        servers = json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(set(servers), {"context7"})

    def test_map_on_a_fresh_install_writes_both_servers(self):
        self.assertEqual(self.run_init(self.root, "--map").returncode, 0)

        servers = json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(set(servers), {"context7", "likec4"})

    def test_map_skill_comes_with_map_and_then_stays(self):
        skill = self.root / ".agents" / "skills" / "pm-likec4-dsl"
        self.assertEqual(self.run_init().returncode, 0)
        self.assertFalse(skill.exists())
        self.assertFalse((self.root / ".claude" / "skills" / "pm-likec4-dsl").exists())

        dry = self.run_init(self.root, "--upgrade", "--map", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn("pm-likec4-dsl  (new in the package)", dry.stdout)
        self.assertFalse(skill.exists())

        # A core-only project cannot be the source of a map install: it has no map skill to copy.
        other = Path(tempfile.mkdtemp(prefix="pm_other_"))
        self.addCleanup(shutil.rmtree, other, onerror=_remove_readonly)
        installed = self.root / ".pm" / "tools" / "pm_init.py"
        from_core = subprocess.run(
            [sys.executable, str(installed), str(other), "--map"], capture_output=True, text=True, encoding="utf-8"
        )
        self.assertNotEqual(from_core.returncode, 0)
        self.assertIn("no pm-likec4-dsl", from_core.stderr)
        self.assertFalse((other / ".pm").exists())

        self.assertEqual(self.run_init(self.root, "--map").returncode, 0)  # map chosen later
        self.assertTrue((skill / "LICENSE").is_file())
        self.assertTrue((skill / "references" / "model.md").is_file())
        pointer = (self.root / ".claude" / "skills" / "pm-likec4-dsl" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(pointer.startswith("---\nname: pm-likec4-dsl\n"))

        (skill / "SKILL.md").write_text("old\n", encoding="utf-8")
        result = self.run_init(self.root, "--upgrade")  # an upgrade without --map keeps the map skill current

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((skill / "SKILL.md").read_bytes(), (SKILLS / "pm-likec4-dsl" / "SKILL.md").read_bytes())
        manifest = (self.root / ".pm" / "package-files.sha256").read_text(encoding="utf-8")
        self.assertIn("  .agents/skills/pm-likec4-dsl/SKILL.md", manifest)

    def test_swarm_comes_with_swarm_and_then_stays(self):
        swarm, source = self.root / ".pm" / "swarm", PM_INIT.parent.parent / "swarm"
        self.assertEqual(self.run_init().returncode, 0)
        self.assertFalse(swarm.exists())

        # A core-only project cannot be the source of a swarm install: it has no swarm folder to copy.
        other = Path(tempfile.mkdtemp(prefix="pm_other_"))
        self.addCleanup(shutil.rmtree, other, onerror=_remove_readonly)
        installed = self.root / ".pm" / "tools" / "pm_init.py"
        from_core = subprocess.run(
            [sys.executable, str(installed), str(other), "--swarm"], capture_output=True, text=True, encoding="utf-8"
        )
        self.assertNotEqual(from_core.returncode, 0)
        self.assertIn("no swarm/", from_core.stderr)
        self.assertFalse((other / ".pm").exists())

        planned = self.run_init(self.root, "--check", "--swarm").stdout
        self.assertIn("copy    .pm/swarm", planned)
        self.assertEqual(self.run_init(self.root, "--swarm").returncode, 0)  # swarm chosen later
        self.assertEqual((swarm / "pm_run.py").read_bytes(), (source / "pm_run.py").read_bytes())
        self.assertTrue((swarm / "test_pm_run.py").is_file())

        (swarm / "pm_run.py").write_text("old\n", encoding="utf-8")
        result = self.run_init(self.root, "--upgrade")  # an upgrade without --swarm keeps the swarm current

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((swarm / "pm_run.py").read_bytes(), (source / "pm_run.py").read_bytes())
        manifest = (self.root / ".pm" / "package-files.sha256").read_text(encoding="utf-8")
        self.assertIn("  swarm/pm_run.py", manifest)

        # A core-only source must not upgrade a project that has the swarm: it would drop it from the manifest.
        self.assertEqual(self.run_init(other).returncode, 0)
        core_only = other / ".pm" / "tools" / "pm_init.py"
        for flags in (["--upgrade"], ["--check"], ["--upgrade", "--dry-run"]):
            with self.subTest(flags=flags):
                refused = subprocess.run(
                    [sys.executable, str(core_only), str(self.root), *flags],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn("no swarm/", refused.stderr)
                self.assertEqual((self.root / ".pm" / "package-files.sha256").read_text(encoding="utf-8"), manifest)

    def test_map_later_lists_likec4_and_rewrites_nothing(self):
        self.assertEqual(self.run_init().returncode, 0)
        before = (self.root / ".mcp.json").read_bytes()

        result = self.run_init(self.root, "--map")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".mcp.json").read_bytes(), before)
        kept = (self.root / ".pm" / "local" / "merge-by-hand.md").read_text(encoding="utf-8")
        self.assertIn("- .mcp.json: add the likec4 server", kept)

    def test_own_settings_and_mcp_are_never_edited(self):
        (self.root / ".claude").mkdir()
        own_settings = '{"permissions": {"allow": ["Bash(ls)"]}}\n'
        own_mcp = '{"mcpServers": {"mine": {"command": "mine"}}}\n'
        (self.root / ".claude" / "settings.json").write_text(own_settings, encoding="utf-8")
        (self.root / ".mcp.json").write_text(own_mcp, encoding="utf-8")

        result = self.run_init()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"), own_settings)
        self.assertEqual((self.root / ".mcp.json").read_text(encoding="utf-8"), own_mcp)
        merge = result.stdout.split("Merge by hand", 1)[1]
        self.assertIn(".claude/settings.json", merge)
        self.assertIn("context7", merge)

    def test_own_agents_file_stops_a_first_install(self):
        (self.root / "AGENTS.md").write_text("# Our rules\n", encoding="utf-8")

        result = self.run_init()

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("kept as it is", result.stdout)
        self.assertFalse((self.root / ".pm").exists())
        self.assertFalse((self.root / ".claude").exists())

    def test_keep_existing_installs_and_keeps_own_files(self):
        (self.root / "AGENTS.md").write_text("# Our rules\n", encoding="utf-8")
        (self.root / "CLAUDE.md").write_text("Use tabs.\n", encoding="utf-8")

        result = self.run_init(self.root, "--keep-existing")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), "# Our rules\n")
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "Use tabs.\n")
        self.assertTrue((self.root / ".pm" / "tools" / "pm_check.py").is_file())
        merge = result.stdout.split("Merge by hand", 1)[1]
        self.assertIn("AGENTS.md", merge)
        self.assertIn("@AGENTS.md", merge)
        kept = (self.root / ".pm" / "local" / "merge-by-hand.md").read_text(encoding="utf-8")
        self.assertIn("- AGENTS.md:", kept)
        self.assertEqual(self.run_init().returncode, 0)
        self.assertEqual((self.root / ".pm" / "local" / "merge-by-hand.md").read_text(encoding="utf-8"), kept)

    def test_own_git_hooks_are_left_alone(self):
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        stopped = self.run_init()
        kept = self.run_init(self.root, "--keep-existing")

        self.assertEqual(stopped.returncode, 3, stopped.stdout)
        self.assertEqual(kept.returncode, 0, kept.stdout + kept.stderr)
        for again in ((), ("--upgrade",)):  # a later run must not bypass them either
            self.assertEqual(self.run_init(self.root, *again).returncode, 0)
            hooks_path = subprocess.run([GIT, "config", "--get", "core.hooksPath"], cwd=self.root, capture_output=True)
            self.assertNotEqual(hooks_path.returncode, 0, "core.hooksPath must stay unset")

    def test_own_hooks_path_survives_reruns(self):
        subprocess.run([GIT, "config", "core.hooksPath", ".husky"], cwd=self.root, check=True)

        self.assertEqual(self.run_init(self.root, "--keep-existing").returncode, 0)
        self.assertEqual(self.run_init(self.root, "--upgrade").returncode, 0)

        hooks_path = subprocess.run(
            [GIT, "config", "--get", "core.hooksPath"], cwd=self.root, capture_output=True, text=True
        ).stdout.strip()
        self.assertEqual(hooks_path, ".husky")

    def test_worktree_hooks_are_found(self):
        subprocess.run([GIT, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
                       cwd=self.root, check=True)  # fmt: skip
        (self.root / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        worktree = self.root / "wt"
        subprocess.run([GIT, "worktree", "add", "-q", str(worktree)], cwd=self.root, check=True)

        result = self.run_init(worktree)

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("custom hooks: pre-commit", result.stdout)

    def test_odd_json_shapes_become_merges(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text('{"hooks": [1]}', encoding="utf-8")
        (self.root / ".mcp.json").write_text('{"mcpServers": [1]}', encoding="utf-8")

        result = self.run_init()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".mcp.json").read_text(encoding="utf-8"), '{"mcpServers": [1]}')
        kept = (self.root / ".pm" / "local" / "merge-by-hand.md").read_text(encoding="utf-8")
        self.assertIn("- .claude/settings.json:", kept)
        self.assertIn("- .mcp.json: add the context7 server", kept)

    def test_every_written_file_is_in_the_plan(self):
        (self.root / "AGENTS.md").write_text("# Our rules\n", encoding="utf-8")
        planned = self.run_init(self.root, "--check", "--map").stdout.split("\n\n")[0].splitlines()[1:]
        paths = [line.split()[1] for line in planned]
        before = set(self.snapshot()[0])

        self.assertEqual(self.run_init(self.root, "--keep-existing", "--map").returncode, 0)

        written = set(self.snapshot()[0]) - before
        self.assertTrue(written)
        for name in written:
            with self.subTest(file=name):
                self.assertTrue(any(name == p or name.startswith(p + "/") for p in paths), paths)

    def agents_text(self):
        return (self.root / "AGENTS.md").read_text(encoding="utf-8")

    def claude_settings(self):
        return json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_lang_writes_one_language_line_and_the_claude_setting(self):
        result = self.run_init(self.root, "--lang", "tr")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = self.agents_text().splitlines()
        self.assertEqual([line for line in lines if line.startswith("Language:")], ["Language: tr"])
        self.assertIn("## Start here", lines, "the template is still written around the line")
        settings = self.claude_settings()
        self.assertEqual(settings["language"], "turkish")
        self.assertIn("SessionStart", settings["hooks"])

    def test_without_lang_no_language_is_written(self):
        self.assertEqual(self.run_init().returncode, 0)

        self.assertNotIn("Language:", self.agents_text())
        self.assertNotIn("language", self.claude_settings())

    def test_lang_is_kept_by_a_rerun_and_an_upgrade(self):
        self.assertEqual(self.run_init(self.root, "--lang", "tr").returncode, 0)
        before = self.snapshot()

        rerun = self.run_init(self.root, "--lang", "tr")
        upgrade = self.run_init(self.root, "--upgrade")

        self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr)
        self.assertEqual(upgrade.returncode, 0, upgrade.stdout + upgrade.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_a_later_lang_changes_only_the_line_and_the_key(self):
        self.assertEqual(self.run_init(self.root, "--lang", "tr").returncode, 0)
        agents = self.root / "AGENTS.md"
        agents.write_text(self.agents_text() + "\nOur own rule stays.\n", encoding="utf-8")
        settings = self.claude_settings()
        settings["model"] = "ours"
        (self.root / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        expected = self.agents_text().replace("Language: tr", "Language: en")

        result = self.run_init(self.root, "--lang", "en")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.agents_text(), expected)
        settings = self.claude_settings()
        self.assertEqual((settings["language"], settings["model"]), ("english", "ours"))

    def test_lang_from_the_projects_own_package_sets_only_the_language(self):
        self.assertEqual(self.run_init().returncode, 0)
        installed = self.root / ".pm" / "tools" / "pm_init.py"
        before = self.snapshot()[0]

        def own(*args):
            return subprocess.run(
                [sys.executable, str(installed), str(self.root), *args], capture_output=True, text=True, cwd=self.root
            )

        self.assertNotEqual(own("--upgrade").returncode, 0, "only --lang may run on the package's own project")
        self.assertEqual(own("--lang", "tr", "--check").returncode, 0)
        self.assertEqual(self.snapshot()[0], before, "--check writes nothing")
        result = own("--lang", "tr")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = self.snapshot()[0]
        self.assertEqual(
            {name for name in after if after[name] != before.get(name)}, {"AGENTS.md", ".claude/settings.json"}
        )
        self.assertIn("Language: tr", self.agents_text())

        (self.root / ".claude" / "settings.json").write_text('["a"]', encoding="utf-8")
        self.assertEqual(own("--lang", "tr").returncode, 0, "AGENTS.md already says tr: only the merge line is new")
        kept = (self.root / ".pm" / "local" / "merge-by-hand.md").read_text(encoding="utf-8")
        self.assertIn('add "language": "turkish"', kept)

    def test_lang_never_rewrites_a_settings_file_of_the_users_own(self):
        for text in ("{ not json", '{"model": "ours"}'):
            with self.subTest(settings=text):
                (self.root / ".claude").mkdir(exist_ok=True)
                (self.root / ".claude" / "settings.json").write_text(text, encoding="utf-8")

                result = self.run_init(self.root, "--lang", "tr", "--keep-existing")

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"), text)
                kept = (self.root / ".pm" / "local" / "merge-by-hand.md").read_text(encoding="utf-8")
                self.assertIn('add "language": "turkish"', kept)

    def test_lang_reads_only_the_line_under_its_heading(self):
        own = "# Our rules\n\nLanguage: Python 3.12\n\n```text\n## Language\n\nLanguage: en\n```\n"
        (self.root / "AGENTS.md").write_text(own, encoding="utf-8")

        result = self.run_init(self.root, "--lang", "tr", "--keep-existing")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.agents_text()
        self.assertTrue(text.startswith(own), "the user's lines and fenced examples stay as they were")
        self.assertIn("## Language\n\nLanguage: tr\n", text)
        self.assertEqual(self.run_init(self.root, "--lang", "tr").stdout.count("  set "), 0, "a rerun finds the line")

    def test_check_prints_the_plan_and_writes_nothing(self):
        result = self.run_init(self.root, "--check")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Plan for", result.stdout)
        self.assertIn(".mcp.json", result.stdout)
        self.assertEqual([p.name for p in self.root.iterdir()], [".git"])


if __name__ == "__main__":
    unittest.main()
