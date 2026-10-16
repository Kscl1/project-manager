"""Tests for tools/setup/bom.py: version parsing, the status rules, real command probes and the shipped bom.toml.

Standard library only. The probe tests run real processes (this Python, a .cmd or shell script on PATH), so they
exercise the operating system they run on; the rest are plain functions.
"""

import io
import json
import os
import platform
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "setup"))

import bom  # noqa: E402

PY = sys.executable


class ParseVersion(unittest.TestCase):
    def test_real_outputs(self):
        cases = {
            "Python 3.11.9": "3.11.9",
            "Python 3.11": "3.11",
            "git version 2.54.0.windows.1": "2.54.0",
            "git version 2.55.0": "2.55.0",
            "v24.14.0": "24.14.0",
            "2.1.300 (Claude Code)": "2.1.300",
            "1.52.0\n": "1.52.0",
        }
        for text, version in cases.items():
            self.assertEqual(bom.parse_version(text), version, text)

    def test_suffix_is_kept_so_it_cannot_be_compared(self):
        self.assertEqual(bom.parse_version("Python 3.15.0rc1"), "3.15.0rc1")
        self.assertEqual(bom.parse_version("tool 1.2.3-beta.4"), "1.2.3-beta.4")

    def test_no_version(self):
        for text in ("", None, "command not found", "build 7"):
            self.assertIsNone(bom.parse_version(text), text)


class Compare(unittest.TestCase):
    def test_numbers_not_text(self):
        self.assertEqual(bom.compare("2.10.0", "2.9.0"), 1)
        self.assertEqual(bom.compare("1.9", "1.10"), -1)

    def test_missing_parts_count_as_zero(self):
        self.assertEqual(bom.compare("3.11", "3.11.0"), 0)
        self.assertEqual(bom.compare("3.11", "3.11.9"), -1)


class Status(unittest.TestCase):
    def test_rules(self):
        cases = [
            ((None, False, None), bom.MISSING),
            (("/bin/x", False, None), bom.FAILED),
            (("/bin/x", True, None), bom.UNREADABLE),
            (("/bin/x", True, "3.15.0rc1"), bom.CANNOT_COMPARE),
            (("/bin/x", True, "3.10.14"), bom.BELOW),
            (("/bin/x", True, "3.11"), bom.OK),
            (("/bin/x", True, "3.11.9"), bom.OK),
            (("/bin/x", True, "3.14.8"), bom.UNTESTED),
        ]
        for probed, expected in cases:
            self.assertEqual(bom.status(*probed, "3.11", "3.11.9"), expected, probed)


class Probe(unittest.TestCase):
    def test_missing_command(self):
        self.assertEqual(bom.probe(["pm-no-such-command-xyz", "--version"]), (None, False, None))

    def test_python_is_the_running_interpreter(self):
        self.assertEqual(bom.probe(["python", "--version"]), (PY, True, platform.python_version()))

    def test_version_on_non_zero_exit_is_not_taken(self):
        result = bom.probe([PY, "-c", "print('1.2.3'); raise SystemExit(3)"])
        self.assertEqual(result, (PY, False, None))

    def test_timeout(self):
        result = bom.probe([PY, "-c", "import time; time.sleep(10)"], timeout=0.5)
        self.assertEqual(result, (PY, False, None))

    def test_script_found_on_path(self):
        """A tool installed as a script on PATH: npm's .cmd shims on Windows, a shell script on Linux."""
        with tempfile.TemporaryDirectory() as folder:
            if os.name == "nt":
                script = Path(folder) / "pm-fake-tool.cmd"
                script.write_text("@echo pm-fake-tool 1.2.3\r\n")
            else:
                script = Path(folder) / "pm-fake-tool"
                script.write_text("#!/bin/sh\necho pm-fake-tool 1.2.3\n")
                script.chmod(0o755)
            with patch.dict(os.environ, {"PATH": folder + os.pathsep + os.environ["PATH"]}):
                path, ran_ok, version = bom.probe(["pm-fake-tool", "--version"])
        self.assertEqual(Path(path).name.lower(), script.name.lower())
        self.assertEqual((ran_ok, version), (True, "1.2.3"))

    def test_folder_runs_the_check_inside_it_and_absent_is_missing(self):
        check = [PY, "-c", "print(open('tag').read())"]
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):
            self.assertEqual(bom.probe(check, folder="~/bridge"), (None, False, None))  # never run elsewhere
            (Path(home) / "bridge").mkdir()
            (Path(home) / "bridge" / "tag").write_text("v1.1.0\n")
            self.assertEqual(bom.probe(check, folder="~/bridge"), (str(Path(home) / "bridge"), True, "1.1.0"))


class CheckAll(unittest.TestCase):
    def test_rows_and_summary(self):
        items = [
            {"name": "A", "kind": "command", "check": ["a"], "min": "1.0", "tested": "1.2"},
            {"name": "B", "kind": "command", "check": ["b"], "min": "1.0", "tested": "1.2"},
            {"name": "C", "kind": "command", "check": ["c"], "min": "1.0", "tested": "1.2"},
            {"name": "D", "kind": "project-file", "path": ".pm"},
        ]
        found = {"a": ("/bin/a", True, "1.1"), "b": (None, False, None), "c": ("/bin/c", False, None)}
        rows = bom.check_all(items, lambda check, **_: found[check[0]])
        self.assertEqual(
            rows,
            [
                ("A", "1.1", "1.0", "1.2", bom.OK, "/bin/a"),
                ("B", "-", "1.0", "1.2", bom.MISSING, "-"),
                ("C", "-", "1.0", "1.2", bom.FAILED, "/bin/c"),
                ("D", "-", "-", "-", bom.NOT_CHECKED, ".pm"),
            ],
        )
        self.assertEqual(bom.summary(rows), "4 items: 1 ok, 1 missing, 1 check failed, 1 not checked")


class NextStep(unittest.TestCase):
    def row(self, name, result):
        return (name, "-", "-", "-", result, "-")

    def test_every_status_has_a_level(self):
        statuses = {bom.MISSING, bom.FAILED, bom.UNREADABLE, bom.CANNOT_COMPARE, bom.NOT_CHECKED, bom.BELOW, bom.OK}
        project = {bom.IN_PROJECT, bom.NOT_IN_PROJECT, bom.MERGE}
        self.assertEqual(set(bom.LEVEL), statuses | project | {bom.UNTESTED})

    def test_worst_level_wins(self):
        ok, new, gone, skip = (
            self.row("A", bom.OK),
            self.row("B", bom.UNTESTED),
            self.row("C", bom.MISSING),
            self.row("D", bom.NOT_CHECKED),
        )
        self.assertEqual(bom.worst([ok, new, gone, skip]), "bad")
        self.assertEqual(bom.worst([ok, new, skip]), "warn")
        self.assertEqual(bom.worst([ok, skip]), "good")
        self.assertEqual(bom.worst([skip]), "skip")
        self.assertEqual(bom.worst([]), "skip")

    def test_sentences(self):
        rows = [self.row("Git", bom.MISSING), self.row("Node.js", bom.BELOW), self.row("Claude Code", bom.UNTESTED)]
        self.assertEqual(
            bom.next_step(rows),
            "Next: install or update Git (missing), Node.js (below minimum), then check again.",
        )
        rows = [self.row("Git", bom.OK), self.row("Claude Code", bom.UNTESTED), self.row(".pm", bom.NOT_CHECKED)]
        self.assertEqual(
            bom.next_step(rows),
            "All programs are installed. Worth a look: Claude Code (not tested yet).",
        )
        self.assertEqual(bom.next_step([self.row("Git", bom.OK)]), "All programs are ready.")
        self.assertEqual(
            bom.later_note(rows), 'The item marked "not checked" belongs to your project and is set up later.'
        )
        self.assertEqual(bom.later_note([self.row("Git", bom.OK)]), "")


GOOD = """
[[item]]
id = "git"
name = "Git"
kind = "command"
layer = "core"
check = ["git", "--version"]
min = "2.54.0"
tested = "2.54.0"
"""


class Load(unittest.TestCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bom.toml"
            path.write_text(textwrap.dedent(text), encoding="utf-8")
            return bom.load(path)

    def assert_rejected(self, text, message):
        with self.assertRaises(ValueError) as caught:
            self.load_text(text)
        self.assertIn(message, str(caught.exception))

    def test_good(self):
        self.assertEqual(self.load_text(GOOD)[0]["id"], "git")

    def test_duplicate_id(self):
        self.assert_rejected(GOOD + GOOD, "duplicate id")

    def test_unknown_kind(self):
        self.assert_rejected(GOOD.replace('"command"', '"plugin"'), "kind must be one of")

    def test_min_above_tested(self):
        self.assert_rejected(GOOD.replace('min = "2.54.0"', 'min = "2.55.0"'), "min is above tested")

    def test_fake_version_string(self):
        self.assert_rejected(GOOD.replace('min = "2.54.0"', 'min = "not set"'), "min must look like")

    def test_npx_is_refused(self):
        self.assert_rejected(GOOD.replace('["git", "--version"]', '["npx", "likec4", "--version"]'), "npx")

    def test_command_needs_versions(self):
        self.assert_rejected(GOOD.replace('tested = "2.54.0"', ""), "needs min and tested")

    def test_check_must_be_a_list(self):
        self.assert_rejected(GOOD.replace('["git", "--version"]', '"git"'), "check, a list of strings")

    def test_install_lines_need_a_known_os(self):
        self.assertEqual(
            self.load_text(GOOD + 'install.linux = "sudo pacman -S git"\n')[0]["install"]["linux"], "sudo pacman -S git"
        )
        self.assert_rejected(GOOD + 'install.beos = "get git"\n', "install takes install.<os>")
        self.assert_rejected(GOOD + 'upgrade.windows = ""\n', "upgrade takes upgrade.<os>")
        self.assert_rejected(GOOD + 'install = "winget install git"\n', "install takes install.<os>")

    def test_package_belongs_to_a_command_item(self):
        self.assertEqual(self.load_text(GOOD + 'package = "npm:git"\n')[0]["package"], "npm:git")
        self.assert_rejected(GOOD + "package = 1\n", "package is the name")

    def test_folder_belongs_to_a_command_item(self):
        self.assertEqual(self.load_text(GOOD + 'folder = "~/x"\n')[0]["folder"], "~/x")
        self.assert_rejected(GOOD + "folder = 1\n", "folder is where")


def item(item_id, layer="core", **extra):
    return {"id": item_id, "name": item_id.title(), "kind": "command", "layer": layer, "check": [item_id], **extra}


def row(name, result, installed="-"):
    return (name, installed, "1.0", "1.2", result, "-")


class Plan(unittest.TestCase):
    def test_only_missing_and_below_minimum_become_steps(self):
        items = [
            item("git", install={"windows": "winget install git", "linux": "pacman -S git"}),
            item("node", install={"windows": "winget install node"}, upgrade={"windows": "winget upgrade node"}),
            item("ok", install={"windows": "winget install ok"}),
            item("new", install={"windows": "winget install new"}),
        ]
        rows = [row("Git", bom.MISSING), row("Node", bom.BELOW), row("Ok", bom.OK), row("New", bom.UNTESTED)]
        steps, notes = bom.plan(items, rows, system="windows")
        self.assertEqual(
            [(s["id"], s["why"], s["command"], s["needs"]) for s in steps],
            [
                ("git", bom.MISSING, "winget install git", "winget"),
                ("node", bom.BELOW, "winget upgrade node", "winget"),
            ],
        )
        self.assertEqual(steps[0]["shell"], ["powershell", "-NoProfile", "-Command", "winget install git"])
        self.assertEqual(steps[0]["check"], ["git"])
        self.assertEqual(notes, [])

    def test_missing_item_installs_even_when_an_upgrade_line_exists(self):
        items = [item("node", install={"windows": "winget install node"}, upgrade={"windows": "winget upgrade node"})]
        steps, _ = bom.plan(items, [row("Node", bom.MISSING)], system="windows")
        self.assertEqual(steps[0]["command"], "winget install node")

    def test_os_line_then_all(self):
        items = [
            item("backlog", install={"all": "npm i -g backlog.md"}),
            item("git", install={"linux": "pacman -S git"}),
        ]
        steps, _ = bom.plan(items, [row("Backlog", bom.MISSING), row("Git", bom.BELOW)], system="linux")
        self.assertEqual([s["command"] for s in steps], ["npm i -g backlog.md", "pacman -S git"])

    def test_no_command_and_failed_check_become_notes(self):
        items = [item("git", install={"linux": "pacman -S git"}, note="Get it from git-scm.com."), item("node")]
        steps, notes = bom.plan(items, [row("Git", bom.MISSING), row("Node", bom.FAILED)], system="windows")
        self.assertEqual(steps, [])
        self.assertEqual(len(notes), 2)
        self.assertIn("no install command for windows; Get it from git-scm.com.", notes[0])
        self.assertIn("could not be verified (check failed); run node", notes[1])

    def test_unverified_versions_are_notes_not_ready(self):
        items = [item("git", install={"all": "get git"}), item("py", install={"all": "get py"})]
        rows = [row("Git", bom.UNREADABLE), row("Py", bom.CANNOT_COMPARE, "3.15.0rc1")]
        steps, notes = bom.plan(items, rows, system="linux")
        self.assertEqual(steps, [])
        self.assertIn("could not be verified (version unreadable)", notes[0])
        self.assertIn("could not be verified (cannot compare)", notes[1])

    def test_unticked_layer_is_left_out(self):
        items = [item("likec4", layer="map", install={"all": "npm i -g likec4"})]
        self.assertEqual(bom.plan(items, [row("Likec4", bom.MISSING)], layers=("core",), system="linux"), ([], []))

    def test_swarm_is_opted_into(self):
        items = [item("pi", layer="swarm", install={"all": "npm i -g pi"}, note="Needs Node.js first.")]
        rows = [row("Pi", bom.MISSING)]
        self.assertEqual(bom.plan(items, rows, system="linux"), ([], []))  # not in the default layers
        steps, _ = bom.plan(items, rows, layers=bom.LAYERS, system="linux")
        self.assertEqual((steps[0]["command"], steps[0]["note"]), ("npm i -g pi", "Needs Node.js first."))
        self.assertEqual(bom.chosen(items, rows, bom.DEFAULT_LAYERS), [])
        self.assertEqual(bom.chosen(items, rows, bom.LAYERS), rows)

    def test_installer_step_gets_the_layer_flags(self):
        flags = {layers: bom.init_step(Path("p"), layers, ["x"])["shell"][3:] for layers in [("core",), bom.LAYERS]}
        self.assertEqual(flags[("core",)], ["--keep-existing"])
        self.assertEqual(flags[bom.LAYERS], ["--keep-existing", "--map", "--swarm"])


class ListedVersion(unittest.TestCase):
    """Pi extensions: `pi list` names what the settings ask for; the version is read from the package itself."""

    def listing(self, folder):
        return f"User packages:\n  npm:pi-web-access@0.35.0\n    {folder}\n  npm:pi-btw@0.7.1\n    /x/pi-btw\n"

    def test_version_comes_from_the_installed_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"name": "pi-web-access", "version": "0.36.1"}', encoding="utf-8")
            self.assertEqual(bom.listed_version(self.listing(tmp), "npm:pi-web-access"), (tmp, True, "0.36.1"))

    def test_not_listed_is_missing(self):
        self.assertEqual(bom.listed_version(self.listing("/x"), "npm:pi-mcp-adapter"), (None, False, None))

    def test_listed_but_not_installed_is_never_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, ran_ok, version = bom.listed_version(self.listing(Path(tmp) / "gone"), "npm:pi-web-access")
            self.assertEqual((ran_ok, version), (True, None))
            self.assertEqual(bom.status(path, ran_ok, version, "0.35.0", "0.35.0"), bom.UNREADABLE)

    def test_no_folder_line_never_reads_the_current_folder(self):
        self.assertEqual(bom.listed_version("  npm:pi-web-access@0.35.0", "npm:pi-web-access"), ("-", True, None))

    def test_filtered_package_is_never_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "package.json").write_text('{"version": "0.36.1"}', encoding="utf-8")
            for source in ("npm:pi-web-access", "npm:pi-web-access@0.35.0"):
                with self.subTest(source=source):
                    found = bom.listed_version(f"  {source} (filtered)\n    {tmp}\n", "npm:pi-web-access")
                    self.assertEqual(found, (tmp, True, None))

    def test_package_without_its_folder_line_is_never_ready(self):
        listing = "User packages:\n  npm:pi-web-access@0.35.0\n  npm:pi-btw@0.7.1\n    /x/pi-btw\n"
        self.assertEqual(bom.listed_version(listing, "npm:pi-web-access"), ("-", True, None))

    def test_unversioned_name_is_found(self):
        self.assertIsNone(bom.listed_version("  npm:pi-web-access\n    /none\n", "npm:pi-web-access")[2])
        self.assertIsNotNone(bom.listed_version("  npm:pi-web-access\n    /none\n", "npm:pi-web-access")[0])


class Running(unittest.TestCase):
    def test_shell_per_os(self):
        self.assertEqual(
            bom.shell_args("irm x | iex", "windows"), ["powershell", "-NoProfile", "-Command", "irm x | iex"]
        )
        self.assertEqual(bom.shell_args("curl x | bash", "linux"), ["bash", "-c", "curl x | bash"])

    def test_outcome_from_exit_code_and_recheck(self):
        self.assertEqual(bom.outcome(0, row("Git", bom.OK, "2.54.0"))[0], "done")
        self.assertEqual(bom.outcome(0, row("Git", bom.UNTESTED, "2.60.0"))[0], "done")
        self.assertEqual(bom.outcome(0, row("Git", bom.MISSING))[0], "not-found")
        self.assertEqual(bom.outcome(0, row("Git", bom.BELOW, "0.9"))[0], "too-old")
        self.assertEqual(bom.outcome(0, row("Git", bom.UNREADABLE))[0], "unverified")
        self.assertEqual(bom.outcome(0, row("Git", bom.FAILED))[0], "unverified")
        state, message = bom.outcome(5, row("Git", bom.OK, "2.54.0"))
        self.assertEqual(state, "failed")
        self.assertIn("exit code 5", message)

    def test_needs_names_the_program_that_runs_the_line(self):
        self.assertEqual(bom.needs("winget install --id Git.Git", "windows"), "winget")
        self.assertEqual(bom.needs("sudo pacman -S --needed git", "linux"), "pacman")
        self.assertEqual(bom.needs("npm i -g backlog.md@1.52.0", "linux"), "npm")
        self.assertEqual(bom.needs("irm https://claude.ai/install.ps1 | iex", "windows"), "powershell")
        self.assertEqual(bom.needs("curl -fsSL https://claude.ai/install.sh | bash", "linux"), "curl")
        self.assertEqual(bom.needs("pi install npm:pi-web-access@0.35.0", "linux"), "pi")  # after the Pi step

    def test_path_refresh_keeps_this_process_first(self):
        before = os.environ["PATH"]
        try:
            os.environ["PATH"] = os.pathsep.join(["C:\\venv\\Scripts", before])
            bom.refresh_path()
            self.assertTrue(os.environ["PATH"].startswith("C:\\venv\\Scripts" + os.pathsep))
        finally:
            os.environ["PATH"] = before


class Main(unittest.TestCase):
    """The plain-text and JSON output an agent reads, and the exit codes it can trust."""

    def run_main(self, args, found):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            code = bom.main(args, lambda check, **_: found.get(check[0], ("/bin/x", True, "999.0")))
        return code, out.getvalue()

    def test_steps_left_exit_1_and_list_commands(self):
        code, out = self.run_main([], {"git": (None, False, None)})
        self.assertEqual(code, 1)
        self.assertIn("To do on ", out)
        self.assertIn("1. Git (missing): ", out)

    def test_failed_check_is_a_note_and_exit_1(self):
        code, out = self.run_main(["--layers", "core"], {"git": ("/bin/git", False, None)})
        self.assertEqual(code, 1)
        self.assertIn("nothing can run automatically", out)
        self.assertIn("Note: Git: installed, but it could not be verified (check failed)", out)

    def test_nothing_left_exit_0(self):
        code, out = self.run_main(["--layers", "core"], {})
        self.assertEqual(code, 0)
        self.assertIn("(core): nothing", out)

    def test_json(self):
        code, out = self.run_main(["--json"], {"git": (None, False, None)})
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(data["steps"][0]["id"], "git")
        self.assertEqual(next(i for i in data["items"] if i["id"] == "git")["status"], bom.MISSING)

    def test_missing_bom_exit_2(self):
        with patch.object(bom, "BOM", Path("no-such-folder/bom.toml")), patch("sys.stderr"):
            with patch.object(bom.load, "__defaults__", (Path("no-such-folder/bom.toml"),)):
                self.assertEqual(bom.main([]), 2)

    def test_swarm_rows_and_after_step_only_when_chosen(self):
        _, out = self.run_main(["--layers", "core"], {})
        self.assertNotIn("Herdr", out)
        self.assertNotIn("Then: ", out)
        _, out = self.run_main(["--layers", "core,swarm"], {"herdr": (None, False, None)})
        self.assertIn("1. Herdr (missing): ", out)
        self.assertIn("checks its SHA-256", out)  # the item's note under its step
        self.assertIn("Then: Before the first pm_run job: start herdr once", out)

    def test_bad_layer_exit_2(self):
        with patch("sys.stderr"):
            self.assertEqual(bom.main(["--layers", "galaxy"]), 2)


class ShippedBom(unittest.TestCase):
    """The hand-edited bom.toml loads, and every shipped skill follows the pm- prefix."""

    def test_loads_and_names(self):
        items = bom.load()
        self.assertTrue(any(item["kind"] == "command" for item in items))
        for item in items:
            with self.subTest(item=item["id"]):
                if item["kind"] == "command":
                    self.assertTrue(item["install"]["windows"])
                    self.assertTrue(item["install"]["linux"])
                if "/skills/" in item.get("path", ""):
                    self.assertTrue(item["id"].startswith("pm-"))
                    self.assertTrue(Path(item["path"]).name.startswith("pm-"))

    def test_every_shipped_skill_is_checked(self):
        shipped = {p.name for p in (bom.PM_INIT.parents[2] / ".agents" / "skills").glob("pm-*")}
        listed = {Path(item["path"]).name for item in bom.load() if "/skills/" in item.get("path", "")}
        self.assertEqual(listed, shipped)


class EvrenLayer(unittest.TestCase):
    """evren-bridge is opted into, from its own repo; a machine without it gets the same table, steps and installer."""

    def setUp(self):
        self.evren = next(item for item in bom.load() if item["id"] == "evren-bridge")

    def test_own_layer_unticked_and_the_key_left_to_the_user(self):
        self.assertEqual(self.evren["layer"], "evren")
        self.assertNotIn("evren", bom.DEFAULT_LAYERS)
        for line in self.evren["install"].values():
            self.assertIn("git clone https://github.com/Kscl1/evren-bridge", line)
            self.assertNotIn("key", line.lower())  # the key is the user's to put in place
        self.assertIn("never asks for it", bom.AFTER["evren"])

    def test_ticked_and_absent_is_one_clone_step(self):
        row = bom.check_one(self.evren, lambda check, folder=None, **_: (None, False, None))
        self.assertEqual(row[4], bom.MISSING)
        steps, notes = bom.plan([self.evren], [row], layers=("core", "evren"), system="windows")
        self.assertEqual(([s["id"] for s in steps], steps[0]["needs"], notes), (["evren-bridge"], "git", []))

    def test_absent_bridge_changes_nothing_for_the_other_layers(self):
        def fake(present):
            def run(check, folder=None, **_):
                if folder:  # only the evren-bridge check runs in a folder of its own
                    return ("/home/u/evren-bridge", True, "1.1.0") if present else (None, False, None)
                return (None, False, None) if check[0] == "node" else ("/bin/x", True, "999.0")

            return run

        with tempfile.TemporaryDirectory() as project:
            for layers in ("core", "core,map", "core,map,swarm"):
                seen = []
                for present in (True, False):
                    for extra in (["--json"], []):
                        with patch("sys.stdout", new_callable=io.StringIO) as out:
                            code = bom.main(["--layers", layers, "--project", project, *extra], fake(present))
                        text = out.getvalue()
                        if extra:
                            data = json.loads(text)
                            data["items"] = [i for i in data["items"] if i["id"] != "evren-bridge"]
                            text = json.dumps(data)
                        seen.append((code, text))
                self.assertEqual(seen[:2], seen[2:], layers)
                self.assertIn("pm_init.py", seen[0][1])  # the installer step is planned the same way
                for word in ("Kscl1/evren-bridge", "EVREN API key", "\nevren-bridge "):  # no step, Then: line or row
                    self.assertNotIn(word, seen[1][1])


PROJECT_ITEMS = [
    {"id": "pkg", "name": "Package", "kind": "project-file", "layer": "core", "path": ".pm/VERSION"},
    {"id": "hooks", "name": "Hooks", "kind": "project-file", "layer": "core", "path": "settings.json", "has": "ours"},
    {"id": "map", "name": "Map server", "kind": "project-file", "layer": "map", "path": "mcp.json", "has": "likec4",
     "similar": ["likec4"]},
]  # fmt: skip


class Project(unittest.TestCase):
    """Project files: checked only with a project folder, set up by one installer step."""

    def setUp(self):
        self.project = Path(tempfile.mkdtemp(prefix="bom_project_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.project, ignore_errors=True))

    def rows(self):
        return bom.check_all(PROJECT_ITEMS, project=self.project)

    def test_not_checked_without_a_project(self):
        self.assertEqual({row[4] for row in bom.check_all(PROJECT_ITEMS)}, {bom.NOT_CHECKED})

    def test_in_project_missing_and_merge(self):
        (self.project / ".pm").mkdir()
        (self.project / ".pm" / "VERSION").write_text("package: x\n", encoding="utf-8")
        (self.project / "settings.json").write_text("{}", encoding="utf-8")
        self.assertEqual([row[4] for row in self.rows()], [bom.IN_PROJECT, bom.MERGE, bom.NOT_IN_PROJECT])
        self.assertEqual(self.rows()[0][5], str(self.project / ".pm/VERSION"))

    def test_missing_files_become_one_installer_step(self):
        steps, notes = bom.plan(PROJECT_ITEMS, self.rows(), ("core", "map"), "linux", self.project)
        self.assertEqual([step["id"] for step in steps], ["pm-init"])
        step = steps[0]
        self.assertEqual(step["ids"], ["pkg", "hooks", "map"])
        self.assertEqual(step["shell"][1:], [str(bom.PM_INIT), str(self.project), "--keep-existing", "--map"])
        self.assertIn("--check", step["preview"])
        self.assertNotIn("--keep-existing", step["preview"])
        core_only = bom.plan(PROJECT_ITEMS, self.rows(), ("core",), "linux", self.project)[0][0]
        self.assertNotIn("--map", core_only["shell"])

    def test_own_file_goes_to_the_installer_until_handed_over(self):
        (self.project / "settings.json").write_text("{}", encoding="utf-8")
        steps, _ = bom.plan(PROJECT_ITEMS[1:2], self.rows()[1:2], ("core",), "linux", self.project)
        self.assertEqual(steps[0]["ids"], ["hooks"])  # the installer lists it for /pm-setup
        (self.project / ".pm" / "local").mkdir(parents=True)
        (self.project / ".pm" / "local" / "merge-by-hand.md").write_text(
            "# Merge by hand\n\n- settings.json: add ours\n", encoding="utf-8"
        )
        steps, notes = bom.plan(PROJECT_ITEMS[1:2], self.rows()[1:2], ("core",), "linux", self.project)
        self.assertEqual((steps, notes), ([], []))  # now /pm-setup's work: neither a step nor a note
        self.assertEqual(bom.merge_names(bom.merge_list(self.project)), "settings.json")

    def test_installer_outcome(self):
        ok = ("A", "-", "-", "-", bom.IN_PROJECT, "p")
        merge = ("B", "-", "-", "-", bom.MERGE, "p")
        absent = ("C", "-", "-", "-", bom.NOT_IN_PROJECT, "p")
        self.assertEqual(bom.project_outcome(0, [ok])[0], "done")
        self.assertEqual(bom.project_outcome(0, [ok, merge])[0], "done")
        lines = ["- AGENTS.md: add ours", "- .mcp.json: add a", "- .mcp.json: add b"]
        self.assertEqual(bom.project_outcome(0, [ok, merge], lines)[0], "merge")
        self.assertIn("AGENTS.md, .mcp.json (listed", bom.project_outcome(0, [ok], lines)[1])
        self.assertEqual(bom.project_outcome(0, [absent])[0], "unverified")
        self.assertEqual(bom.project_outcome(3, [ok])[0], "failed")

    def test_next_step_names_project_files_plainly(self):
        self.assertEqual(bom.next_step(self.rows()), "Next: set up the project files (3 not in your project yet).")

    def test_record_needs_pm_and_reads_back(self):
        self.assertFalse(bom.write_record(self.project, ("core",), [], "2026-10-15"))
        (self.project / ".pm").mkdir()
        self.assertTrue(bom.write_record(self.project, ("core", "map"), ["x"], "2026-10-15"))
        record = bom.read_record(self.project)
        self.assertEqual(record["layers"], ["core", "map"])
        self.assertEqual(record["bom"], bom.bom_hash())
        self.assertEqual(record["source"], str(bom.PM_INIT.parents[3]))

    def test_main_with_project(self):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            code = bom.main(["--project", str(self.project)], lambda check, **_: ("/bin/x", True, "999.0"))
        self.assertEqual(code, 1)
        self.assertIn(".pm and project files", out.getvalue())
        with patch("sys.stderr"):
            self.assertEqual(bom.main(["--project", str(self.project / "nope")]), 2)


class UserScan(unittest.TestCase):
    """Names of what the user already has; never the configuration behind them."""

    def test_names_only_and_similar(self):
        home = Path(tempfile.mkdtemp(prefix="bom_home_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(home, ignore_errors=True))
        for folder, name in ((".claude/skills", "likec4-dsl"), (".agents/skills", "notes")):
            (home / folder / name).mkdir(parents=True)
            (home / folder / name / "SKILL.md").write_text("---\n---\n", encoding="utf-8")
        server = {"type": "http", "url": "https://example.test", "headers": {"KEY": "secret-value"}}
        (home / ".claude.json").write_text(json.dumps({"mcpServers": {"likec4": server}}), encoding="utf-8")
        (home / ".claude" / "plugins").mkdir(parents=True)
        plugins = {"version": 2, "plugins": {"likec4@market": []}}
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(plugins), encoding="utf-8")

        scan = bom.user_scan(home)

        self.assertEqual(scan, {"skills": ["likec4-dsl", "notes"], "mcp": ["likec4"], "plugins": ["likec4"]})
        self.assertNotIn("secret-value", json.dumps(scan))
        lines = bom.similar(PROJECT_ITEMS, scan)
        self.assertEqual(len(lines), 1)
        self.assertIn("skill likec4-dsl, MCP server likec4, plugin likec4", lines[0])
        self.assertEqual(bom.similar(PROJECT_ITEMS, scan, ("core",)), [])

    def test_empty_home(self):
        self.assertEqual(
            bom.user_scan(tempfile.gettempdir() + "/no-such-home"), {"skills": [], "mcp": [], "plugins": []}
        )


if __name__ == "__main__":
    unittest.main()
