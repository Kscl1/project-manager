"""Tests for tools/setup/bom.py: version parsing, the status rules and the shipped bom.toml (standard library only)."""

import platform
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "setup"))

import bom  # noqa: E402


class ParseVersion(unittest.TestCase):
    def test_real_outputs(self):
        cases = {
            "Python 3.11.9": "3.11.9",
            "git version 2.54.0.windows.1": "2.54.0",
            "v24.14.0": "24.14.0",
            "2.1.300 (Claude Code)": "2.1.300",
            "1.52.0\n": "1.52.0",
        }
        for text, version in cases.items():
            self.assertEqual(bom.parse_version(text), version, text)

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
            ((False, None), bom.MISSING),
            ((True, None), bom.UNREADABLE),
            ((True, "3.10.14"), bom.BELOW),
            ((True, "3.11.0"), bom.OK),
            ((True, "3.11.9"), bom.OK),
            ((True, "3.14.8"), bom.UNTESTED),
        ]
        for (found, version), expected in cases:
            self.assertEqual(bom.status(found, version, "3.11", "3.11.9"), expected, version)


class InstalledVersion(unittest.TestCase):
    def test_missing_command(self):
        self.assertEqual(bom.installed_version(["pm-no-such-command-xyz", "--version"]), (False, None))

    def test_this_python(self):
        self.assertEqual(bom.installed_version([sys.executable, "--version"]), (True, platform.python_version()))


class CheckAll(unittest.TestCase):
    def test_rows_and_summary(self):
        items = [
            {"name": "A", "check": ["a"], "min": "1.0", "tested": "1.2"},
            {"name": "B", "check": ["b"], "min": "1.0", "tested": "1.2"},
            {"name": "C", "check": ["c"], "min": "1.0", "tested": "1.2"},
        ]
        found = {"a": (True, "1.1"), "b": (False, None), "c": (True, "0.9")}
        rows = bom.check_all(items, lambda check: found[check[0]])
        self.assertEqual(
            rows,
            [
                ("A", "1.1", "1.0", "1.2", bom.OK),
                ("B", "-", "1.0", "1.2", bom.MISSING),
                ("C", "0.9", "1.0", "1.2", bom.BELOW),
            ],
        )
        self.assertEqual(bom.summary(rows), "3 checked: 1 ok, 1 missing, 1 below minimum")


class ShippedBom(unittest.TestCase):
    """bom.toml is hand-edited: every item must be complete and its versions must make sense."""

    def test_items_are_complete(self):
        items = bom.load()
        self.assertTrue(items)
        names = [item["name"] for item in items]
        self.assertEqual(len(names), len(set(names)), "duplicate item names")
        for item in items:
            with self.subTest(item=item.get("name")):
                self.assertIn(item["layer"], ("core", "map"))
                self.assertIsInstance(item["check"], list)
                self.assertTrue(item["check"])
                self.assertEqual(bom.parse_version(item["min"]), item["min"])
                self.assertEqual(bom.parse_version(item["tested"]), item["tested"])
                self.assertLessEqual(bom.compare(item["min"], item["tested"]), 0, "min above tested")
                self.assertTrue(item["install"]["windows"])
                self.assertTrue(item["install"]["linux"])


if __name__ == "__main__":
    unittest.main()
