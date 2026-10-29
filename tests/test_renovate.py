"""Bound Renovate's regex edits to pins/candidates, never compatibility evidence.

The config validator checks Renovate's schema. These tests check match/replacement
boundaries using Python's equivalent named-group syntax; they do not contact upstreams.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RenovateTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
        self.bom = (ROOT / "tools/setup/bom.toml").read_text(encoding="utf-8")

    def patterns(self, index):
        return [
            re.compile(re.sub(r"\(\?<([A-Za-z]+)>", r"(?P<\1>", pattern))
            for pattern in self.config["customManagers"][index]["matchStrings"]
        ]

    def test_only_custom_managers_and_no_automerge(self):
        self.assertEqual(self.config["enabledManagers"], ["custom.regex"])
        self.assertIs(self.config["automerge"], False)
        for manager in self.config["customManagers"]:
            self.assertEqual(manager["managerFilePatterns"], ["/^tools/setup/bom\\.toml$/"])

    def test_npm_pins_cover_setup_commands(self):
        matches = [match for pattern in self.patterns(0) for match in pattern.finditer(self.bom)]
        self.assertEqual(
            {match["depName"] for match in matches},
            {"backlog.md", "likec4", "@earendil-works/pi-coding-agent", "pi-mcp-adapter", "pi-web-access"},
        )
        self.assertEqual(len(matches), 9)  # Windows/Linux copies plus the all-platform LikeC4 pin

    def test_herdr_candidate_not_tested(self):
        matches = [match for pattern in self.patterns(1) for match in pattern.finditer(self.bom)]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["currentValue"], "0.9.5")
        self.assertIn('tested = "0.9.5"', self.bom)
        self.assertIn("https://herdr.dev/latest.json", str(self.config["customDatasources"]))

    def test_skill_candidates_keep_real_provenance(self):
        matches = [match for pattern in self.patterns(2) for match in pattern.finditer(self.bom)]
        self.assertEqual(len(matches), 2)
        self.assertEqual({match["depName"] for match in matches}, {"mattpocock/skills"})
        for match in matches:
            self.assertEqual(match["currentValue"], "v1.3.1")
        self.assertIn('ref = "mattpocock/skills@49dd158 (grilling)"', self.bom)

    def test_watches_follow_releases_not_commits(self):
        # The owner wants a PR only when upstream publishes a release, never for each branch commit.
        for manager in self.config["customManagers"]:
            self.assertNotIn(manager.get("datasourceTemplate"), {"github-digest", "git-refs"})
            self.assertNotIn("currentDigest", " ".join(manager["matchStrings"]))
        self.assertNotIn("upstream_commit", self.bom)

    def test_likec4_skill_moves_with_the_cli_pin(self):
        # Its main branch documents unreleased syntax; the skill follows the release the CLI pin names.
        item = self.bom.split('id = "pm-likec4-dsl"')[1].split("[[item]]")[0]
        self.assertNotIn("upstream_commit", item)
        self.assertIn('ref = "likec4/likec4@v1.60.0 (likec4-dsl)"', item)
        self.assertIn("npx likec4@1.60.0", self.bom)

    def test_replacing_every_capture_cannot_change_min_tested_or_ref(self):
        changed = self.bom
        for index in range(3):
            for pattern in self.patterns(index):

                def bump(match):
                    group = "currentDigest" if "currentDigest" in match.groupdict() else "currentValue"
                    start, end = match.span(group)
                    offset = match.start()
                    replacement = "a" * 40 if group == "currentDigest" else "99.0.0"
                    return match[0][: start - offset] + replacement + match[0][end - offset :]

                changed = pattern.sub(bump, changed)
        protected = re.compile(r"^(?:min|tested|ref) = .+$", re.MULTILINE)
        self.assertEqual(protected.findall(changed), protected.findall(self.bom))
        self.assertNotEqual(changed, self.bom)


if __name__ == "__main__":
    unittest.main()
