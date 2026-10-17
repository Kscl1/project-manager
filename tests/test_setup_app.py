"""Tests for tools/setup/app.py, headless with a fake probe and runner. Skipped where Textual is not installed (CI)."""

import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "setup"))

try:
    import app
except ImportError:
    app = None

ITEMS = [
    {"id": "a", "name": "A", "kind": "command", "layer": "core", "check": ["a"], "min": "1.0", "tested": "1.2",
     "install": {"all": "get a"}},
    {"id": "b", "name": "B", "kind": "command", "layer": "core", "check": ["b"], "min": "1.0", "tested": "1.2",
     "install": {"all": "get b"}},
    {"id": "c", "name": "C", "kind": "project-file", "layer": "core", "path": ".pm"},
]  # fmt: skip
MAP = {"id": "m", "name": "M", "kind": "command", "layer": "map", "check": ["m"], "min": "1.0", "tested": "1.0",
       "install": {"all": "get m"}}  # fmt: skip


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class CheckScreenTest(unittest.IsolatedAsyncioTestCase):
    async def test_table_shows_each_item(self):
        found = {"a": ("/bin/a", True, "1.3"), "b": (None, False, None)}
        setup = app.SetupApp(ITEMS, lambda check, **_: found[check[0]])
        async with setup.run_test(size=(120, 35)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            self.assertEqual(table.row_count, 3)
            self.assertEqual(
                [str(cell) for cell in table.get_row_at(0)], ["A", "1.3", "1.0", "1.2", "! not tested yet", "/bin/a"]
            )
            self.assertEqual(str(table.get_row_at(1)[4]), "✗ missing")
            self.assertEqual(str(table.get_row_at(2)[0]), "1 item not checked on this screen")
            self.assertEqual(str(table.get_row_at(2)[4]), "· not checked")
            summary = str(setup.query_one("#summary").content)
            self.assertIn("3 items: 1 not tested yet, 1 missing, 1 not checked", summary)
            self.assertIn("Next: install or update B (missing)", summary)

    async def test_path_column_only_when_wide(self):
        found = {"a": ("/bin/a", True, "1.1"), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check, **_: found[check[0]])
        async with setup.run_test(size=(80, 24)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            self.assertEqual(len(table.columns), 5)
            await pilot.resize_terminal(120, 35)
            await pilot.pause()
            self.assertEqual(len(table.columns), 6)
            self.assertEqual(str(table.get_row_at(0)[5]), "/bin/a")

    async def test_check_again_reads_new_versions(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = app.SetupApp(ITEMS, lambda check, **_: found[check[0]])
        async with setup.run_test() as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            found["a"] = ("/bin/a", True, "1.1")
            await pilot.press("r")
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(str(setup.query_one(app.DataTable).get_row_at(0)[4]), "✓ ok")

    async def test_r_and_enter_do_nothing_while_a_scan_runs(self):
        release = threading.Event()
        calls = []

        def slow(check):
            calls.append(check[0])
            release.wait(5)
            return None, False, None

        setup = app.SetupApp(ITEMS[:1], slow)
        async with setup.run_test() as pilot:
            await pilot.press("r", "r", "enter")
            self.assertIsInstance(setup.screen, app.Screen)
            self.assertNotIsInstance(setup.screen, app.ChooseScreen)
            release.set()
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(calls, ["a"])
            self.assertFalse(setup.scanning)

    async def test_c_and_a_click_copy_the_full_path(self):
        found = {"a": ("/a/very/long/folder/a", True, "1.1"), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check, **_: found[check[0]])
        copied = []
        async with setup.run_test(size=(80, 24)) as pilot:
            setup.copy_to_clipboard = copied.append
            await setup.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("c")  # Path column hidden at 80 columns: the key still copies
            self.assertEqual(copied, ["/a/very/long/folder/a"])
            await pilot.resize_terminal(120, 35)
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            x = sum(column.get_render_width(table) for column in table.ordered_columns[: app.PATH]) + 2
            await pilot.click(app.DataTable, offset=(x, 2))  # header is line 0, row B is line 2
            self.assertEqual(copied[-1], "/bin/b")

    async def test_a_copies_a_message_for_the_agent(self):
        found = {"a": ("/bin/a", True, "1.1"), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check, **_: found[check[0]])
        copied = []
        async with setup.run_test() as pilot:
            setup.copy_to_clipboard = copied.append
            await setup.workers.wait_for_complete()
            await pilot.press("a")
            self.assertIn("bom.py", copied[0])
            self.assertIn("--layers core,map", copied[0])
            self.assertIn("only after I say yes", copied[0])


SWARM = {"id": "h", "name": "Herdr", "kind": "command", "layer": "swarm", "check": ["h"], "min": "1.0",
         "tested": "1.0", "install": {"all": "get h"}, "note": "Its installer puts it on PATH."}  # fmt: skip


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class SwarmLayerTest(unittest.IsolatedAsyncioTestCase):
    """The swarm is opted into: until it is ticked its missing programs are neither counted nor offered."""

    async def test_unchosen_swarm_is_not_counted_until_ticked(self):
        found = {"a": ("/bin/a", True, "1.1"), "h": (None, False, None)}
        setup = app.SetupApp([ITEMS[0], SWARM], lambda check, **_: found[check[0]], system="linux")
        async with setup.run_test(size=(120, 35)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(setup.query_one(app.DataTable).row_count, 1)
            summary = str(setup.query_one("#summary").content)
            self.assertNotIn("Herdr", summary)
            self.assertIn("Not chosen: swarm, evren. Tick one", summary)
            await pilot.press("enter")
            await pilot.pause()
            setup.screen.query_one(app.SelectionList).select("swarm")
            await pilot.pause()
            self.assertIn("get h", str(setup.screen.query_one("#steps").content))
            self.assertEqual(setup.query_one(app.DataTable).row_count, 2)  # Check, under Choose, counts it now
            await pilot.press("enter")
            await pilot.pause()
            self.assertIn("Its installer puts it on PATH.", str(setup.screen.query_one("#command").content))

    async def test_done_names_what_no_check_can_see(self):
        found = {"a": ("/bin/a", True, "1.1"), "h": ("/bin/h", True, "1.0")}
        setup = app.SetupApp([ITEMS[0], SWARM], lambda check, **_: found[check[0]], system="linux")
        async with setup.run_test(size=(120, 35)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.press("enter")
            await pilot.pause()
            setup.screen.query_one(app.SelectionList).select("swarm")
            await pilot.press("enter")
            await pilot.pause()
            done = str(setup.screen.query_one("#done").content)
            self.assertIn("Everything for core, map, swarm is ready.", done)
            self.assertIn("Then: Before the first pm_run job: start herdr once", done)


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class EvrenLayerTest(unittest.IsolatedAsyncioTestCase):
    """A friend without evren-bridge: Check, Choose and Done look as they would without the item."""

    async def test_absent_bridge_is_neither_counted_nor_offered_until_ticked(self):
        evren = next(item for item in app.bom.load() if item["id"] == "evren-bridge")

        def probe(check, folder=None, **_):
            return (None, False, None) if folder else ("/bin/a", True, "1.1")  # no ~/evren-bridge on this machine

        setup = app.SetupApp([ITEMS[0], evren], probe, system="windows")
        async with setup.run_test(size=(120, 35)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(setup.query_one(app.DataTable).row_count, 1)
            summary = str(setup.query_one("#summary").content)
            self.assertIn("All programs are ready.", summary)
            self.assertNotIn("evren-bridge", summary)
            await pilot.press("enter")
            await pilot.pause()
            self.assertNotIn("git clone", str(setup.screen.query_one("#steps").content))
            await pilot.press("enter")
            await pilot.pause()
            done = str(setup.screen.query_one("#done").content)
            self.assertIn("Everything for core, map is ready.", done)
            self.assertNotIn("EVREN", done)
            await pilot.press("escape", "enter")  # back to Check, then Choose: ticking EVREN offers its clone
            await setup.workers.wait_for_complete()
            await pilot.pause()
            setup.screen.query_one(app.SelectionList).select("evren")
            await pilot.pause()
            self.assertIn(
                "git clone https://github.com/Kscl1/evren-bridge", str(setup.screen.query_one("#steps").content)
            )


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class ChooseAndInstallTest(unittest.IsolatedAsyncioTestCase):
    def make(self, items, found, codes=None):
        """An app whose runner records each command and, on success, makes its program found at version 1.1."""
        self.ran = []
        codes = codes or {}

        def runner(step):
            command = step["command"]
            self.ran.append(command)
            code = codes.get(command, 0)
            if code == 0:
                found[command.split()[-1]] = ("/bin/x", True, "1.1")
            return code

        return app.SetupApp(items, lambda check, **_: found[check[0]], runner=runner, system="linux")

    async def open_install(self, setup, pilot):
        await setup.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        self.assertIsInstance(setup.screen, app.ChooseScreen)
        await pilot.press("enter")
        await pilot.pause()
        self.assertIsInstance(setup.screen, app.InstallScreen)

    async def test_choose_lists_steps_and_map_can_be_unticked(self):
        found = {"a": ("/bin/a", True, "1.1"), "b": (None, False, None), "m": (None, False, None)}
        setup = self.make([*ITEMS, MAP], found)
        async with setup.run_test(size=(120, 35)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.press("enter")
            await pilot.pause()
            screen = setup.screen
            self.assertEqual([step["id"] for step in screen.steps], ["b", "m"])
            self.assertIn("get b", str(screen.query_one("#steps").content))
            screen.query_one(app.SelectionList).deselect("map")
            await pilot.pause()
            self.assertEqual([step["id"] for step in screen.steps], ["b"])
            self.assertEqual(setup.layers, ("core",))

    async def test_enter_never_runs_a_step_y_does(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("enter", "enter")
                self.assertEqual(self.ran, [])
                await pilot.press("y")
                await pilot.pause()
                screen = setup.screen
                self.assertEqual(self.ran, ["get a"])
                self.assertEqual(screen.states, ["done", "waiting"])
                self.assertEqual(screen.current, 1)  # moved on to the next open step
                screen.quiet_until = 0  # time passes; the user reads step 2
                await pilot.press("y")
                await pilot.pause()
                self.assertTrue(screen.finished)
                self.assertIn("2 of 2 done", str(screen.query_one("#install-hint").content))
                await pilot.press("enter")  # finished: Enter shows Done
                await pilot.pause()
                self.assertIsInstance(setup.screen, app.DoneScreen)
                self.assertIn("Everything for core, map is ready", str(setup.screen.query_one("#done").content))
                self.assertEqual(str(setup.table.get_row_at(1)[4]), "✓ ok")
                await pilot.press("escape")  # Done: Esc checks everything again
                await setup.workers.wait_for_complete()
                await pilot.pause()
                self.assertNotIsInstance(setup.screen, (app.ChooseScreen, app.InstallScreen, app.DoneScreen))

    async def test_resizing_on_install_leaves_its_table_alone(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = self.make(ITEMS, found)
        async with setup.run_test(size=(120, 35)) as pilot:
            await self.open_install(setup, pilot)
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            table = setup.screen.query_one(app.DataTable)
            self.assertEqual(
                [str(column.label) for column in table.columns.values()], ["Step", "Program", "Why", "State"]
            )
            self.assertEqual(table.row_count, 1)
            self.assertEqual(len(setup.table.columns), 5)  # the Check table followed the new width

    async def test_keys_queued_while_a_step_ran_do_not_run_the_next(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        # A long quiet window, so a slow test machine cannot let the second y through by being slow
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"), patch.object(app, "QUIET_S", 60):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y", "y")  # the second y arrives as the first step returns
                await pilot.pause()
                self.assertEqual(self.ran, ["get a"])
                self.assertEqual(setup.screen.states, ["done", "waiting"])
                setup.screen.quiet_until = 0  # time passes; the user reads step 2 and presses y
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(self.ran, ["get a", "get b"])

    async def test_back_to_choose_plans_from_the_new_rows(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                self.assertIsInstance(setup.screen, app.ChooseScreen)
                self.assertEqual([step["id"] for step in setup.screen.steps], ["b"])
                self.assertEqual(str(setup.table.get_row_at(0)[4]), "✓ ok")

    async def test_short_terminal_scrolls_to_the_command(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        async with setup.run_test(size=(80, 12)) as pilot:
            await self.open_install(setup, pilot)
            body = setup.screen.query_one("#body")
            self.assertIsInstance(body, app.VerticalScroll)
            self.assertGreater(body.max_scroll_y, 0)

    async def test_a_failed_step_stays_and_can_be_skipped(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = self.make(ITEMS, found, codes={"get a": 3})
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                screen = setup.screen
                self.assertEqual(screen.states, ["failed"])
                self.assertIn("exit code 3", str(screen.query_one("#command").content))
                await pilot.press("s")
                await pilot.pause()
                self.assertTrue(screen.finished)
                self.assertIn("Still open: A (skipped)", str(screen.query_one("#install-hint").content))

    async def test_exit_0_but_not_found_is_not_done(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check, **_: found[check[0]], runner=lambda step: 0, system="linux")
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(setup.screen.states, ["not-found"])
                self.assertIn("not found yet", str(setup.screen.query_one("#command").content))

    async def test_missing_installer_program_is_not_run(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = self.make(ITEMS, found)
        with patch.object(app.shutil, "which", lambda name: None):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(self.ran, [])
                self.assertEqual(setup.screen.states, ["waiting"])
                self.assertIn("this step needs get", str(setup.screen.query_one("#command").content))

    async def test_terminal_that_cannot_hand_over_copies_and_r_rechecks(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check, **_: found[check[0]], runner=lambda step: None, system="linux")
        copied = []
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                setup.copy_to_clipboard = copied.append
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(copied, ["get a"])
                self.assertEqual(setup.screen.states, ["waiting"])
                found["a"] = ("/bin/a", True, "1.1")  # the user ran it in another terminal
                await pilot.press("r")
                await pilot.pause()
                self.assertEqual(setup.screen.states, ["done"])


PROJECT_ITEMS = [
    {"id": "a", "name": "A", "kind": "command", "layer": "core", "check": ["a"], "min": "1.0", "tested": "1.2",
     "install": {"all": "get a"}},
    {"id": "pkg", "name": "Package", "kind": "project-file", "layer": "core", "path": ".pm/VERSION"},
    {"id": "hooks", "name": "Hooks", "kind": "project-file", "layer": "core", "path": "settings.json", "has": "ours"},
]  # fmt: skip


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class ProjectTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp(prefix="setup_project_"))
        self.home = Path(tempfile.mkdtemp(prefix="setup_home_"))
        for folder in (self.project, self.home):
            self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        self.ran = []

    def runner(self, step):
        """Stands in for pm_init: writes the package stamp and lists the user's own settings.json for /pm-setup."""
        self.ran.append(step["shell"])
        (self.project / ".pm" / "local").mkdir(parents=True, exist_ok=True)
        (self.project / ".pm" / "VERSION").write_text("package: x\n", encoding="utf-8")
        if (self.project / "settings.json").exists():
            (self.project / ".pm" / "local" / "merge-by-hand.md").write_text(
                "# Merge by hand\n\n- settings.json: add ours\n", encoding="utf-8"
            )
        return 0

    def make(self, system="linux"):
        found = {"a": ("/bin/a", True, "1.1")}
        return app.SetupApp(
            PROJECT_ITEMS, lambda check, **_: found[check[0]], self.runner, system, project=self.project, home=self.home
        )

    async def test_installer_step_then_done_with_pm_setup(self):
        (self.project / "settings.json").write_text("{}", encoding="utf-8")  # the user's own file
        setup = self.make()
        async with setup.run_test(size=(120, 40)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertIn(f"Project: {self.project}", str(setup.query_one("#summary").content))
            await pilot.press("enter", "enter")
            await pilot.pause()
            screen = setup.screen
            self.assertIsInstance(screen, app.InstallScreen)
            self.assertEqual([step["id"] for step in screen.steps], ["pm-init"])
            self.assertEqual(screen.steps[0]["ids"], ["pkg", "hooks"])
            await setup.workers.wait_for_complete()  # the plan comes from a worker
            await pilot.pause()
            panel = str(screen.query_one("#command").content)
            self.assertIn("--keep-existing", panel)
            self.assertIn("What it will do", panel)  # the installer's own plan, before y
            self.assertIn("Inside the project folder only, it will copy", panel)
            await pilot.press("y")
            await pilot.pause()
            self.assertIn("--keep-existing", self.ran[0])
            self.assertEqual(screen.states, ["merge"])  # the user's own settings.json waits for /pm-setup
            self.assertIn("settings.json", str(screen.query_one("#command").content))
            await pilot.press("enter")
            await pilot.pause()
            done = setup.screen
            self.assertIsInstance(done, app.DoneScreen)
            self.assertIn("/pm-setup", str(done.query_one("#next").content))
            self.assertIn("for /pm-setup to merge with you: settings.json", str(done.query_one("#done").content))
            self.assertFalse(done.check_action("open_desktop", ()))  # Linux: terminal commands only
            record = app.bom.read_record(self.project)
            self.assertEqual(record["layers"], ["core", "map"])

    async def test_rerun_with_nothing_left_goes_straight_to_done(self):
        (self.project / ".pm").mkdir()
        (self.project / ".pm" / "VERSION").write_text("package: x\n", encoding="utf-8")
        (self.project / "settings.json").write_text("ours", encoding="utf-8")
        app.bom.write_record(self.project, ("core",), [], "2026-10-15")
        setup = self.make(system="windows")
        async with setup.run_test(size=(120, 40)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(setup.layers, ("core",))  # from the record
            self.assertIn("Set up here before on 2026-10-15", str(setup.query_one("#summary").content))
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(setup.screen, app.DoneScreen)
            self.assertTrue(setup.screen.check_action("open_desktop", ()))
            self.assertEqual(self.ran, [])
            await pilot.press("escape")
            await setup.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("l")  # the short path still lets the user change the layers
            await pilot.pause()
            self.assertIsInstance(setup.screen, app.ChooseScreen)

    async def test_changed_bom_does_not_take_the_short_path(self):
        (self.project / ".pm").mkdir()
        (self.project / ".pm" / "VERSION").write_text("package: x\n", encoding="utf-8")
        (self.project / "settings.json").write_text("ours", encoding="utf-8")
        app.bom.write_record(self.project, ("core",), [], "2026-10-15")
        record = app.bom.read_record(self.project)
        record["bom"] = "older"
        (self.project / app.bom.RECORD).write_text(json.dumps(record), encoding="utf-8")
        setup = self.make()
        async with setup.run_test(size=(120, 40)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(setup.screen, app.ChooseScreen)

    async def test_no_plan_no_run(self):
        setup = self.make()
        with patch.object(app.bom, "PM_INIT", self.project / "missing.py"):
            async with setup.run_test(size=(120, 40)) as pilot:
                await setup.workers.wait_for_complete()
                await pilot.pause()
                await pilot.press("enter", "enter")
                await setup.workers.wait_for_complete()
                await pilot.pause()
                self.assertIn("does not run here", str(setup.screen.query_one("#command").content))
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(self.ran, [])

    def test_plan_summary_counts_and_names_what_is_kept(self):
        output = (
            "Plan for C:/p (4 change(s)):\n  copy    .pm/tools\n  copy    .pm/hooks\n  write   CLAUDE.md\n"
            "  set     git core.hooksPath  (.pm/hooks)\n\nAlready in the project, kept as it is (/pm-setup merges"
            " it with you):\n  keep    AGENTS.md  (the project has its own agent instructions)\n"
        )
        summary = app.plan_summary(output)
        self.assertIn("copy 2 package folders, write 1 file, point git at the .pm hooks", summary)
        self.assertIn("  AGENTS.md  (the project has its own agent instructions)", summary)
        self.assertEqual(app.plan_summary("python: can't open file"), "python: can't open file")

    def test_desktop_opens_detached_from_the_console(self):
        with patch.object(app.subprocess, "Popen") as popen:
            app.open_detached("claude://code/new?folder=C%3A%5Cdemo")
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["explorer.exe", "claude://code/new?folder=C%3A%5Cdemo"])
        self.assertEqual(kwargs["creationflags"], getattr(app.subprocess, "DETACHED_PROCESS", 0))
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(kwargs[stream], app.subprocess.DEVNULL)

    def test_desktop_link_encodes_the_folder(self):
        self.assertEqual(
            app.desktop_link(Path("C:/My Projects/demo")).split("folder=")[1],
            app.quote(str(Path("C:/My Projects/demo")), safe=""),
        )
        self.assertNotIn(" ", app.desktop_link(Path("C:/My Projects/demo")))


if __name__ == "__main__":
    unittest.main()
