"""Tests for .pm/tools/pm_check.py.

pm_check finds the repo root from its own file location, so each test builds a
small fake repo in a temp dir, copies the script into <tmp>/.pm/tools/ and runs
it as a subprocess, exactly the way a user or a git hook would.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PM_CHECK = Path(__file__).resolve().parent.parent / "tools" / "pm_check.py"


def _remove_readonly(func, path, _exc_info):
    """git marks .git/objects read-only on Windows; make them writable first."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pm_check_test_"))
        self.addCleanup(shutil.rmtree, self.root, False, _remove_readonly)
        tools = self.root / ".pm" / "tools"
        tools.mkdir(parents=True)
        shutil.copy(PM_CHECK, tools / "pm_check.py")
        (self.root / "backlog.config.yml").write_text("", encoding="utf-8")

    def write(self, relpath, text):
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_check(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / ".pm" / "tools" / "pm_check.py"), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def git(self, *args, env=None):
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=full_env,
            check=True,
        )

    def git_init(self):
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")

    def commit(self, message, date):
        self.git(
            "commit",
            "-q",
            "-m",
            message,
            env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
        )


class CleanRepoTest(RepoTestCase):
    def test_clean_repo_reports_no_problems(self):
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")
        self.write("README.md", "# Readme\n")
        self.write(
            "docs/guide.md",
            "---\ndepends_on: [D-01]\n---\n\n# Guide\n\n[readme](../README.md)\n",
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 0)
        self.assertIn("No problems found", result.stdout)


class DecisionReferenceTest(RepoTestCase):
    def test_depends_on_unknown_decision_reported(self):
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")
        self.write("docs/guide.md", "---\ndepends_on: [D-99]\n---\n\nbody\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("depends on D-99, which does not exist", result.stdout)

    def test_depends_on_superseded_decision_names_replacement(self):
        self.write(
            ".pm/decisions.md",
            "- ~~**D-01** old rule~~ \u2192 D-02\n- **D-02** new rule\n",
        )
        self.write("docs/guide.md", "---\ndepends_on: [D-01]\n---\n\nbody\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("depends on D-01, which was superseded by D-02", result.stdout)

    def test_decision_defined_twice_reported(self):
        self.write(
            ".pm/decisions.md",
            "- **D-01** first rule\n- **D-01** duplicate rule\n",
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("D-01 is defined twice", result.stdout)


class DecisionFilesTest(RepoTestCase):
    """One file per decision under .pm/decisions/, replaced ones in archive/, and a generated index."""

    def decision(self, relpath, ident, title, status, extra=""):
        front = f'---\nid: {ident}\ntitle: "{title}"\nstatus: {status}\ndate: 2026-10-01\n{extra}---\n\n'
        return self.write(relpath, front + f"# {ident} {title}\n\n## Karar\n\nx\n")

    def setUp(self):
        super().setUp()
        self.write(".pm/decisions.md", "# Decisions\n\nHand-written rules stay above the index.\n")
        self.decision(".pm/decisions/D-01.md", "D-01", "First rule, with a comma", "accepted")
        self.decision(".pm/decisions/archive/D-02.md", "D-02", "Old rule", "superseded", "replaced_by: D-01\n")

    def test_index_must_be_written_then_stays_current(self):
        stale = self.run_check()
        self.assertEqual(stale.returncode, 1)
        self.assertIn("decision index is out of date", stale.stdout)

        self.assertEqual(self.run_check("--write-index").returncode, 0)
        index = (self.root / ".pm" / "decisions.md").read_text(encoding="utf-8")
        self.assertIn("Hand-written rules stay above the index.", index)
        self.assertIn("| [D-01](decisions/D-01.md) | First rule, with a comma | 2026-10-01 |", index)
        self.assertIn("| [D-02](decisions/archive/D-02.md) | Old rule | superseded | D-01 |", index)
        self.assertEqual(self.run_check().returncode, 0)

        self.decision(".pm/decisions/D-03.md", "D-03", "New rule", "accepted")
        self.assertIn("decision index is out of date", self.run_check().stdout)

    def test_depends_on_archived_decision_names_its_replacement(self):
        self.run_check("--write-index")
        self.write("docs/guide.md", "---\ndepends_on: [D-02]\n---\n\nbody\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("depends on D-02, which was superseded by D-01", result.stdout)

    def test_depends_on_decision_kept_elsewhere(self):
        self.decision(".pm/decisions/archive/D-03.md", "D-03", "Kept in another repo", "elsewhere")
        self.run_check("--write-index")
        self.write("docs/guide.md", "---\ndepends_on: [D-03]\n---\n\nbody\n")

        result = self.run_check()

        self.assertIn("depends on D-03, which is archived and no longer in force here", result.stdout)

    def test_status_id_folder_and_replacement_are_checked(self):
        self.decision(".pm/decisions/D-03.md", "D-30", "Wrong id", "acepted")
        self.decision(".pm/decisions/D-04.md", "D-04", "Replaced but in force folder", "superseded")
        self.decision(".pm/decisions/archive/D-05.md", "D-05", "Points nowhere", "superseded", "replaced_by: D-99\n")
        self.run_check("--write-index")

        out = self.run_check().stdout

        self.assertIn("frontmatter id is D-30, the file is D-03", out)
        self.assertIn("status is acepted", out)
        self.assertIn("status superseded belongs in archive/", out)
        self.assertIn("a superseded decision needs `replaced_by: D-n`", out)
        self.assertIn("D-05: replaced_by D-99 does not exist", out)

    def test_a_path_into_a_sibling_repo_must_exist(self):
        sibling = Path(tempfile.mkdtemp(prefix="pm_check_sibling_", dir=self.root.parent))
        self.addCleanup(shutil.rmtree, sibling, False, _remove_readonly)
        (sibling / "tools").mkdir()
        (sibling / "tools" / "run.py").write_text("", encoding="utf-8")
        here, gone = f"../{sibling.name}/tools/run.py", f"../{sibling.name}/tools/old.py"
        path = self.decision(".pm/decisions/D-03.md", "D-03", "Applied next door", "accepted")
        prose = f"\nApplied in `{here}` and `{gone}`; the rule names files as `../{sibling.name}/...`.\n"
        path.write_text(path.read_text(encoding="utf-8") + prose, encoding="utf-8")
        self.run_check("--write-index")

        out = self.run_check().stdout

        self.assertIn(f"{gone} does not exist", out)
        self.assertNotIn(f"{here} does not exist", out)
        self.assertNotIn("/... does not exist", out, "a placeholder is not a path")

    def test_a_sibling_repo_that_is_not_here_is_skipped(self):
        path = self.decision(".pm/decisions/D-03.md", "D-03", "Applied elsewhere", "accepted")
        path.write_text(
            path.read_text(encoding="utf-8") + "\nApplied in `../no-such-repo-here/x.py`.\n", encoding="utf-8"
        )
        self.decision(".pm/decisions/archive/D-04.md", "D-04", "Old", "superseded", "replaced_by: D-03\n")
        self.run_check("--write-index")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_sibling_path_inside_a_command_must_exist_and_repo_paths_are_not_read(self):
        sibling = Path(tempfile.mkdtemp(prefix="pm_check_sibling_", dir=self.root.parent))
        self.addCleanup(shutil.rmtree, sibling, False, _remove_readonly)
        (sibling / "run.py").write_text("", encoding="utf-8")
        here, gone = f"../{sibling.name}/run.py", f"../{sibling.name}/tools/old.py"
        prose = f"\nRun `python {gone} --flag` or `python {here}`; it once lived in `tools/gone.py`.\n"
        path = self.decision(".pm/decisions/D-03.md", "D-03", "A command", "accepted")
        path.write_text(path.read_text(encoding="utf-8") + prose, encoding="utf-8")
        self.run_check("--write-index")

        out = self.run_check().stdout

        self.assertIn(f"{gone} does not exist", out)
        self.assertNotIn(f"{here} does not exist", out)
        self.assertNotIn("tools/gone.py", out, "a decision is a dated record for paths in this repo")

    def test_odd_sibling_paths_neither_crash_nor_block(self):
        sibling = Path(tempfile.mkdtemp(prefix="pm_check_sibling_", dir=self.root.parent))
        self.addCleanup(shutil.rmtree, sibling, False, _remove_readonly)
        (sibling / "run.py").write_text("", encoding="utf-8")
        gone = f"`../{sibling.name}/gone.py`"
        prose = f"\nSee `.././`, `../{sibling.name}/run.py:12` and\n\n```text\n{gone}\n```\n"
        path = self.decision(".pm/decisions/D-03.md", "D-03", "Odd paths", "accepted")
        path.write_text(path.read_text(encoding="utf-8") + prose, encoding="utf-8")
        old = self.decision(".pm/decisions/archive/D-04.md", "D-04", "Old", "superseded", "replaced_by: D-03\n")
        old.write_text(old.read_text(encoding="utf-8") + f"\nOnce in {gone}.\n", encoding="utf-8")
        self.run_check("--write-index")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_same_id_in_force_and_archived(self):
        self.decision(".pm/decisions/D-02.md", "D-02", "Twin", "accepted")
        self.run_check("--write-index")

        self.assertIn("D-02 is defined twice", self.run_check().stdout)


class RepoPathTest(RepoTestCase):
    """A living doc's file paths in backticks exist; dated records are not read; a named deleting commit passes."""

    LIVING = '---\ntype: living_doc\ntitle: "Roadmap"\n---\n\n# Roadmap\n\n'

    def setUp(self):
        super().setUp()
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")
        self.write("docs/guide.md", "# Guide\n")

    def test_a_missing_path_fails_and_real_paths_pass(self):
        self.write(
            "docs/roadmap.md",
            self.LIVING + "- The export ran from `tools/export_public.py`; its README was `public/README.md`.\n"
            "- Read `docs/guide.md`, `guide.md:3` and run `python .pm/tools/pm_check.py --staged`.\n"
            "- Not paths: `docs/research/`, `feat/x`, `docs/...`, `.pm/local/runs/x.md`, `*.md`, `v1.2`.\n"
            "\n```text\ntools/fenced.py\n```\n",
        )

        out = self.run_check().stdout

        self.assertIn("docs/roadmap.md:8: tools/export_public.py does not exist", out)
        self.assertIn("docs/roadmap.md:8: public/README.md does not exist", out)
        self.assertEqual(out.count("does not exist"), 2, out)

    def test_dated_records_are_not_read(self):
        line = "The export ran from `tools/export_public.py`.\n"
        self.write("docs/research/r1.md", "# R1\n\n" + line)
        self.write("docs/archive/old.md", "# Old\n\n" + line)
        self.write(
            ".pm/worklog/2026-10-17-1200-x.md",
            '---\ntype: worklog\ntitle: "X"\ndate: 2026-10-17\ntask: [REQ-1]\nmodels: [M]\n---\n\n' + line,
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_bare_file_name_is_matched_against_the_repo(self):
        self.write(".pm/local/only_here.py", "")
        self.write(
            "docs/roadmap.md",
            self.LIVING + "Run `pm_check.py`, not `export_public.py` or `only_here.py`; see `codex-led`.\n",
        )

        out = self.run_check().stdout

        self.assertIn("docs/roadmap.md:8: export_public.py does not exist", out)
        self.assertIn("docs/roadmap.md:8: only_here.py does not exist", out, "git-ignored .pm/local/ is not the repo")
        self.assertNotIn("pm_check.py does not exist", out)
        self.assertNotIn("codex-led", out, "a word without a known file extension is not a file name")

    def test_a_deleted_file_passes_when_its_deleting_commit_is_named(self):
        self.git_init()
        self.write("tools/export_public.py", "")
        self.git("add", "-A")
        self.commit("add the export", "2026-10-01T12:00:00")
        added = self.git("rev-parse", "--short", "HEAD").stdout.strip()
        (self.root / "tools" / "export_public.py").unlink()
        self.git("add", "-A")
        self.commit("retire the export", "2026-10-02T12:00:00")
        deleted = self.git("rev-parse", "--short", "HEAD").stdout.strip()
        self.write(
            "docs/roadmap.md",
            self.LIVING + f"- `tools/export_public.py` retired in {deleted}.\n"
            f"- `export_public.py` is gone ({deleted}).\n"
            f"- `tools/export_public.py` was added in {added}.\n",
        )

        out = self.run_check().stdout

        self.assertNotIn("roadmap.md:8:", out)
        self.assertNotIn("roadmap.md:9:", out)
        self.assertIn("roadmap.md:10: tools/export_public.py does not exist", out, "only the deleting commit counts")

    def test_a_sibling_file_passes_when_the_sibling_commit_that_deleted_it_is_named(self):
        sibling = Path(tempfile.mkdtemp(prefix="pm_check_sibling_", dir=self.root.parent))
        self.addCleanup(shutil.rmtree, sibling, False, _remove_readonly)
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "T"]):
            subprocess.run(["git", *args], cwd=sibling, check=True)
        (sibling / "old.py").write_text("", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=sibling, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "add"], cwd=sibling, check=True)
        subprocess.run(["git", "rm", "-q", "old.py"], cwd=sibling, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "remove"], cwd=sibling, check=True)
        deleted = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=sibling, capture_output=True, text=True, check=True
        ).stdout.strip()
        gone = f"../{sibling.name}/old.py"
        self.write("docs/roadmap.md", self.LIVING + f"- `python {gone}` retired in {deleted}.\n- Not `{gone}`.\n")

        out = self.run_check().stdout

        self.assertNotIn("roadmap.md:8:", out)
        self.assertIn(f"roadmap.md:9: {gone} does not exist", out)


class WorklogFrontmatterTest(RepoTestCase):
    """Worklogs carry type, title, date, task and models once one of them does."""

    GOOD = '---\ntype: worklog\ntitle: "A delivery"\ndate: 2026-10-11\ntask:\n  - REQ-1\nmodels:\n  - Model A (high)\n---\n\n# A delivery\n'

    def setUp(self):
        super().setUp()
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")

    def test_old_worklogs_without_frontmatter_pass_until_one_has_it(self):
        self.write(".pm/worklog/2026-10-10-1200-old.md", "# Old delivery\n")
        self.assertEqual(self.run_check().returncode, 0)

        self.write(".pm/worklog/2026-10-11-1200-new.md", self.GOOD)
        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("2026-10-10-1200-old.md: frontmatter lacks type, title, date, task, models", result.stdout)

    def test_date_must_match_file_name_and_keys_present(self):
        self.write(".pm/worklog/2026-10-11-1200-new.md", self.GOOD)
        self.write(".pm/worklog/2026-10-09-0900-wrong.md", self.GOOD)
        self.write(".pm/worklog/2026-10-11-1300-no-models.md", self.GOOD.replace("models:\n  - Model A (high)\n", ""))

        out = self.run_check().stdout

        self.assertIn("2026-10-09-0900-wrong.md:4: date 2026-10-11 does not match the file name", out)
        self.assertIn("no-models.md: frontmatter lacks models", out)
        self.assertNotIn("2026-10-11-1200-new.md", out)


class RecordTypeTest(RepoTestCase):
    """A file that declares `type:` uses a known type and carries its keys; Backlog files keep their own type."""

    def setUp(self):
        super().setUp()
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")

    def test_living_doc_needs_a_title(self):
        self.write("docs/good.md", '---\ntype: living_doc\ntitle: "Good"\n---\n\n# Good\n')
        self.write("docs/bad.md", "---\ntype: living_doc\n---\n\n# Bad\n")

        out = self.run_check().stdout

        self.assertIn("docs/bad.md: a living_doc needs title in its frontmatter", out)
        self.assertNotIn("docs/good.md", out)

    def test_unknown_type_is_reported_but_backlog_tasks_are_skipped(self):
        self.write("docs/odd.md", '---\ntype: memo\ntitle: "Odd"\n---\n\n# Odd\n')
        self.write(".pm/backlog/tasks/task-1 - X.md", "---\nid: TASK-1\ntitle: X\nstatus: Ready\ntype: epic\n---\n")

        out = self.run_check().stdout

        self.assertIn("docs/odd.md:2: unknown type memo", out)
        self.assertNotIn("task-1", out)


class CatalogueTest(RepoTestCase):
    """docs/README.md lists every typed record between markers; the list is generated and kept current."""

    def setUp(self):
        super().setUp()
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")
        self.write("docs/guide.md", '---\ntype: living_doc\ntitle: "Guide"\n---\n\n# Guide\n')
        self.write("docs/README.md", "# docs\n\n<!-- record-catalogue:begin -->\n<!-- record-catalogue:end -->\n")

    def test_catalogue_is_generated_and_then_must_stay_current(self):
        self.assertIn("record catalogue is out of date", self.run_check().stdout)

        self.assertEqual(self.run_check("--write-index").returncode, 0)
        page = (self.root / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("| [`guide.md`](guide.md) | Guide |", page)
        self.assertEqual(self.run_check().returncode, 0)

        self.write("docs/other.md", '---\ntype: living_doc\ntitle: "Other"\n---\n\n# Other\n')
        self.assertIn("record catalogue is out of date", self.run_check().stdout)

    def test_no_markers_means_no_catalogue(self):
        self.write("docs/README.md", "# docs\n")

        self.assertEqual(self.run_check().returncode, 0)


class LinkTest(RepoTestCase):
    def test_missing_link_reported_and_non_link_forms_ignored(self):
        self.write("docs/README.md", "# Readme\n")
        self.write(
            "index.md",
            "# Index\n"
            "\n"
            "[missing](missing.md)\n"
            "[site](https://example.com/page.md)\n"
            "[anchor](#section)\n"
            "`[inline](inline-code.md)`\n"
            "```\n"
            "[fenced](fenced.md)\n"
            "```\n",
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("link to missing.md does not exist", result.stdout)
        self.assertNotIn("inline-code.md", result.stdout)
        self.assertNotIn("fenced.md", result.stdout)
        self.assertNotIn("example.com", result.stdout)

    def test_link_into_pm_local_reported(self):
        self.write(".pm/local/runs/x/common.md", "# Local only\n")
        self.write(
            "docs/note.md", "# Note\n\n[brief](../.pm/local/runs/x/common.md)\n`../.pm/local/runs/x/common.md`\n"
        )

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("points into .pm/local/"), 1)

    def test_link_with_wrong_case_reported(self):
        self.write("docs/README.md", "# Readme\n")
        self.write("index.md", "[bad](docs/Readme.md)\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "link to docs/Readme.md does not exist (paths are case-sensitive)",
            result.stdout,
        )

    def test_percent_encoded_link_resolves(self):
        self.write("docs/a b.md", "# A\n")
        self.write("index.md", "[ok](docs/a%20b.md)\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    STUDY_SECTIONS = (
        "Kısa cevap",
        "Soru ve yöntem",
        "Bulgular",
        "Öneri ve sonuç",
        "Alternatifler ve itirazlar",
        "Sınırlar",
        "Okuma haritası",
    )

    def study(self, name, front=None, sections=STUDY_SECTIONS):
        fields = front or {
            "type": "study",
            "title": "T",
            "date": "2026-10-06",
            "task": "[REQ-1]",
            "question": "Q?",
            "validity": "güncel kanıt",
            "decisions": "[]",
            "models": "m",
            "terms": "[a, b]",
        }
        head = "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "---\n# T\n"
        body = "".join(f"\n## {s}\n\ntext\n" for s in sections)
        self.write(f"docs/research/{name}/README.md", head + body)
        self.write(f"docs/research/{name}/material/note.md", "# Note\n")

    def test_study_following_the_standard_passes(self):
        self.study("good")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_study_missing_terms_and_a_section_is_reported(self):
        self.study("bad", front={"title": "T", "date": "2026-10-06", "terms": ""}, sections=self.STUDY_SECTIONS[:-1])

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/research/bad/README.md: study entry lacks question", result.stdout)
        self.assertIn("docs/research/bad/README.md: a study entry declares `type: study`", result.stdout)
        self.assertIn("terms is empty", result.stdout)
        self.assertIn("lacks the section 'Okuma haritası'", result.stdout)

    def test_study_root_with_an_extra_file_is_reported(self):
        self.study("messy")
        self.write("docs/research/messy/O-opus.md", "# Loose\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/research/messy: O-opus.md sits in the study root", result.stdout)

    def test_old_study_without_terms_is_not_checked(self):
        self.write("docs/research/old/00-ozet.md", "# Old\n")
        self.write("docs/research/old/README.md", "---\ntitle: Old\n---\n# Old\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_broken_link_under_worktree_is_ignored(self):
        self.write(".worktrees/x/README.md", "[missing](nope.md)\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 0)
        self.assertIn("No problems found", result.stdout)

    def test_broken_link_under_pm_local_is_ignored(self):
        self.write(".pm/local/README.md", "[missing](nope.md)\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 0)
        self.assertIn("No problems found", result.stdout)

    def test_broken_link_under_docs_is_reported(self):
        self.write("docs/README.md", "[missing](nope.md)\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("link to nope.md does not exist", result.stdout)

    def test_broken_link_under_docs_archive_is_reported(self):
        self.write("docs/archive/research/R1-old.md", "[missing](../../research/R1-old.md)\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/archive/research/R1-old.md:1: link to ../../research/R1-old.md", result.stdout)

    def test_broken_link_in_backlog_task_archive_is_ignored(self):
        self.write(".pm/backlog/archive/tasks/req-1 - Old.md", "[missing](nope.md)\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 0)
        self.assertIn("No problems found", result.stdout)


class LineLimitTest(RepoTestCase):
    def test_long_doc_reported(self):
        self.write("long.md", "\n".join(f"line {i}" for i in range(301)) + "\n")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("long.md: 301 lines, limit is 300", result.stdout)

    def test_long_file_of_a_copied_skill_exempt(self):
        long = "\n".join(f"line {i}" for i in range(301)) + "\n"
        self.write(".agents/skills/pm-copied/LICENSE", "MIT\n")
        self.write(".agents/skills/pm-copied/references/long.md", long)
        self.write(".agents/skills/pm-own/SKILL.md", long)

        result = self.run_check()

        self.assertNotIn("pm-copied", result.stdout)
        self.assertIn(".agents/skills/pm-own/SKILL.md: 301 lines", result.stdout)

    def test_tool_owned_files_are_not_checked(self):
        # Issue #66: a design tool's DESIGN.md is one file by format, and its frontmatter alone passed the limit.
        long = "\n".join(f"line {i}" for i in range(301)) + "\n"
        self.write("DESIGN.md", long + "[gone](nope.md)\n")
        self.write("docs/design/tokens.md", long)
        self.write("other.md", long)
        self.write(".pm/tool-owned.txt", "# written by the design tool\nDESIGN.md\n\n  docs/design/tokens.md\n")

        result = self.run_check()

        self.assertNotIn("DESIGN.md", result.stdout)
        self.assertNotIn("tokens.md", result.stdout)
        self.assertIn("other.md: 301 lines", result.stdout)
        self.assertIn("list it in .pm/tool-owned.txt", result.stdout)

    def test_long_research_doc_and_decision_log_exempt(self):
        body = "\n".join(f"line {i}" for i in range(301)) + "\n"
        self.write("research/big.md", body)
        self.write("docs/research/study/big.md", body)
        self.write("docs/archive/research/big.md", body)
        self.write(".pm/decisions.md", "- **D-01** x\n" + body)

        result = self.run_check()

        self.assertEqual(result.returncode, 0)
        self.assertIn("No problems found", result.stdout)


class StagedTest(RepoTestCase):
    def test_staged_checks_only_staged_docs(self):
        self.git_init()
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")
        self.write("docs/staged_bad.md", "[missing](nope.md)\n")
        self.write("docs/unstaged_bad.md", "[missing](nope2.md)\n")
        self.git("add", "docs/staged_bad.md")

        result = self.run_check("--staged")

        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/staged_bad.md", result.stdout)
        self.assertIn("link to nope.md does not exist", result.stdout)
        self.assertNotIn("unstaged_bad.md", result.stdout)

    def test_staged_decision_log_checks_all_docs(self):
        self.git_init()
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")
        self.write("docs/other_bad.md", "[missing](nope.md)\n")
        self.write("docs/untracked_bad.md", "[missing](nope2.md)\n")
        self.git("add", ".pm/decisions.md")

        result = self.run_check("--staged")

        self.assertEqual(result.returncode, 1)
        self.assertIn("docs/other_bad.md", result.stdout)
        self.assertIn("docs/untracked_bad.md", result.stdout)

    def test_files_git_ignores_are_not_docs(self):
        # Issue #37: an ignored tool report over the line limit failed every check and blocked decision commits.
        self.git_init()
        self.write(".gitignore", "build/\n")
        self.write(".pm/decisions.md", "- **D-01** sandbox decision\n")
        self.write("build/report.md", "\n".join(f"line {i}" for i in range(301)) + "\n")
        self.write("docs/untracked_bad.md", "[missing](nope.md)\n")
        self.git("add", ".pm/decisions.md")

        for args in ((), ("--staged",)):
            result = self.run_check(*args)

            self.assertNotIn("build/report.md", result.stdout)
            self.assertIn("docs/untracked_bad.md", result.stdout)


class StaleTest(RepoTestCase):
    def test_stale_flags_described_path_changed_after_review(self):
        self.git_init()
        self.write("src/app.py", "x = 1\n")
        self.write(
            "docs/guide.md",
            "---\ndescribes: [src/app.py]\nreviewed: 2020-01-03\n---\n\nbody\n",
        )
        self.git("add", "-A")
        self.commit("init", "2020-01-02T00:00:00")
        self.write("src/app.py", "x = 2\n")
        self.git("add", "-A")
        self.commit("change", "2020-06-01T00:00:00")

        result = self.run_check("--stale")

        self.assertEqual(result.returncode, 0)
        self.assertIn("docs/guide.md", result.stdout)
        self.assertIn("src/app.py changed in 1 commit(s) since 2020-01-03", result.stdout)

    def test_stale_reports_no_stale_docs_when_clean(self):
        self.git_init()
        self.write("src/app.py", "x = 1\n")
        self.write(
            "docs/guide.md",
            "---\ndescribes: [src/app.py]\nreviewed: 2020-01-03\n---\n\nbody\n",
        )
        self.git("add", "-A")
        self.commit("init", "2020-01-02T00:00:00")

        result = self.run_check("--stale")

        self.assertEqual(result.returncode, 0)
        self.assertIn("No stale docs", result.stdout)
        self.assertIn("Coverage: 1 of 1 docs declare", result.stdout)


class DoneTaskTest(RepoTestCase):
    def task(self, status, criteria, dod=None, summary=None, kind="task"):
        parts = [
            "---",
            "id: TASK-1",
            "title: Demo",
            f"status: {status}",
            *([f"type: {kind}"] if kind else []),
            "---",
            "",
            "## Acceptance Criteria",
            "<!-- AC:BEGIN -->",
            *criteria,
            "<!-- AC:END -->",
            "",
        ]
        if dod is not None:
            parts += ["## Definition of Done", "<!-- DOD:BEGIN -->", *dod, "<!-- DOD:END -->", ""]
        if summary is not None:
            parts += ["## Final Summary", "", summary, ""]
        return self.write(".pm/backlog/tasks/task-1 - Demo.md", "\n".join(parts))

    def test_done_task_with_unchecked_criteria_reported(self):
        self.task("Done", ["- [x] #1 one", "- [ ] #2 two"])

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("Done, but Acceptance Criteria has unchecked items", result.stdout)

    def test_open_task_with_unchecked_criteria_ignored(self):
        self.task("Active", ["- [ ] #1 one"], dod=["- [ ] #1 Doc impact"])

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_open_task_without_type_reported(self):
        self.task("Ready", ["- [ ] #1 one"], kind=None)

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("open task without a type", result.stdout)

    def test_done_task_without_type_passes(self):
        self.task("Done", ["- [x] #1 one"], kind=None)

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_done_task_with_dod_needs_doc_impact_line(self):
        self.task("Done", ["- [x] #1 one"], dod=["- [x] #1 Doc impact"], summary="Shipped it.")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("no 'Doc impact:' line", result.stdout)

    def test_done_task_with_doc_impact_passes(self):
        self.task("Done", ["- [x] #1 one"], dod=["- [x] #1 Doc impact"], summary="Shipped it.\nDoc impact: none")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_long_live_line_reported_only_in_open_tasks(self):
        long_next = "Next: " + "word " * 70
        for status, code in (("Active", 1), ("Done", 0)):
            path = self.task(status, ["- [x] #1 one"])
            notes = f"\n## Implementation Notes\n\n{long_next}\nEvidence: abc1234\n\n12 Oct: {long_next}\n"
            path.write_text(path.read_text(encoding="utf-8") + notes, encoding="utf-8")

            result = self.run_check()

            self.assertEqual(result.returncode, code, result.stdout)
        self.task("Active", ["- [ ] #1 one"])
        path.write_text(
            path.read_text(encoding="utf-8") + "\n## Implementation Notes\n\nNext: short\n", encoding="utf-8"
        )
        self.assertEqual(self.run_check().returncode, 0)

    def test_owner_ask_with_options_needs_them_written_out(self):
        path = self.task("Active", ["- [ ] #1 one"])
        base = path.read_text(encoding="utf-8")
        path.write_text(base + "\n## Implementation Notes\n\nNext: wait\nNeeds owner: pick A or B\n", encoding="utf-8")

        result = self.run_check()

        self.assertEqual(result.returncode, 1)
        self.assertIn("offers options A, B, but A, B is not written out", result.stdout)

        options = "\n- A: keep the old name; free, but confusing\n- **B**: rename it; one migration\n"
        path.write_text(base + "\n## Implementation Notes\n\nNext: wait\nNeeds owner: pick A or B\n" + options)
        self.assertEqual(self.run_check().returncode, 0, self.run_check().stdout)

    def test_owner_ask_options_match_any_case_and_dash_but_not_a_fenced_example(self):
        path = self.task("Active", ["- [ ] #1 one"])
        base = path.read_text(encoding="utf-8") + "\n## Implementation Notes\n\nNext: wait\n"
        for ask, options in (
            ("pick (a) or (b)", "- A: keep the old name\n- B: rename it\n"),
            ("A or B?", "- a: keep\n- b: rename\n"),
            ("pick A or B", "- A — keep the old name\n- B — rename it\n"),
        ):
            path.write_text(base + f"Needs owner: {ask}\n\n{options}", encoding="utf-8")
            self.assertEqual(self.run_check().returncode, 0, (ask, self.run_check().stdout))

        fenced = "```\n- A: an example\n- B: another\n```\n"
        path.write_text(base + "Needs owner: pick A or B\n\n" + fenced, encoding="utf-8")
        self.assertEqual(self.run_check().returncode, 1)

    def test_owner_ask_without_options_or_on_a_done_task_passes(self):
        for status, ask in (("Active", "Needs owner: say how long the install took"), ("Done", "Needs owner: A/B/C")):
            path = self.task(status, ["- [x] #1 one"])
            path.write_text(path.read_text(encoding="utf-8") + f"\n## Implementation Notes\n\n{ask}\n")

            self.assertEqual(self.run_check().returncode, 0, (status, self.run_check().stdout))

    def test_old_done_task_without_dod_needs_no_doc_impact(self):
        self.task("Done", ["- [x] #1 one"], summary="Shipped it.")

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)


ENGLISH_NOTES = (
    "The worker writes the report after the check passes, and the lead reads it before the merge. "
    "When a check fails, the lead sends the evidence back to the worker with the command that failed. "
    "This keeps the work and its proof in one place, so the next session can see what was done and why."
)
TURKISH_NOTES = (
    "Çalışan kontrol geçince raporu yazar, lead de birleştirmeden önce okur. Bir kontrol düşerse lead kanıtı "
    "ve düşen komutu çalışana geri gönderir. Böylece iş ve kanıtı tek yerde durur; bir sonraki oturum neyin "
    "yapıldığını ve nedenini görür. `pm_check` ve `backlog task edit` gibi komutlar ve dosya adları İngilizce kalır."
)


class ProjectLanguageTest(RepoTestCase):
    """In a project whose AGENTS.md names a non-English language, English record prose gets an Info line only."""

    def record(self, relpath, notes, lang="tr"):
        if lang:
            self.write("AGENTS.md", f"# Demo\n\n## Language\n\nLanguage: {lang}\n")
        dod = "- [ ] #1 Living docs this task affects are updated, and the final summary says so in one line"
        return self.write(
            relpath,
            "---\nid: TASK-1\ntitle: Demo\nstatus: Active\ntype: task\n---\n\n## Description\n\n"
            f"{notes}\n\n## Definition of Done\n<!-- DOD:BEGIN -->\n{dod}\n<!-- DOD:END -->\n\n"
            "## Implementation Notes\n\nNext: Needs owner: none\n",
        )

    def test_english_task_prose_in_a_turkish_project_gets_an_info_line_and_passes(self):
        self.record(".pm/backlog/tasks/task-1 - Demo.md", ENGLISH_NOTES)

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Info: .pm/backlog/tasks/task-1 - Demo.md: reads as English", result.stdout)
        self.assertIn("No problems found", result.stdout)

    def test_english_decision_prose_gets_an_info_line(self):
        self.write(".pm/decisions.md", "# Decisions\n")
        self.record(".pm/decisions/D-01.md", ENGLISH_NOTES)

        self.assertIn("Info: .pm/decisions/D-01.md: reads as English", self.run_check().stdout)

    def test_turkish_prose_with_english_keys_and_commands_is_quiet(self):
        self.record(".pm/backlog/tasks/task-1 - Demo.md", TURKISH_NOTES)

        self.assertNotIn("Info:", self.run_check().stdout)

    def test_english_or_unset_language_and_short_bodies_are_quiet(self):
        for lang, notes in (("en", ENGLISH_NOTES), ("", ENGLISH_NOTES), ("tr", "The check passed after the fix.")):
            with self.subTest(lang=lang, notes=notes[:20]):
                (self.root / "AGENTS.md").unlink(missing_ok=True)
                self.record(".pm/backlog/tasks/task-1 - Demo.md", notes, lang)

                self.assertNotIn("Info:", self.run_check().stdout)

    def test_a_language_line_outside_its_heading_sets_nothing(self):
        self.record(".pm/backlog/tasks/task-1 - Demo.md", ENGLISH_NOTES, lang="")
        self.write("AGENTS.md", "# Demo\n\nLanguage: Python\n\n```text\n## Language\n\nLanguage: tr\n```\n")

        self.assertNotIn("Info:", self.run_check().stdout)


class AuditOutcomesTest(RepoTestCase):
    HEADER = "| # | Verified | Outcome | Evidence |\n|---|---|---|---|\n"
    REPORT = ".pm/local/audits/demo/report.md"
    FOLLOW_UP = "Needs owner: choose a next step\nReview by: 2026-10-22 · Sam · after REQ-2\n"

    def audit(self, table=None, status="Done", notes=None, tail="", directory=".pm/backlog/tasks"):
        if notes is None:
            if table is None:
                table = self.HEADER + "| 1 | yes | fixed | abc1234 |\n"
            notes = f"Audit report: {self.REPORT}\n\nAudit outcomes:\n" + table
        return self.write(
            directory + "/audit.md",
            f"---\nid: REQ-1\nstatus: {status}\ntype: task\n---\n\n## Implementation Notes\n\n" + notes + tail,
        )

    def target(self, task_id="REQ-2", notes=FOLLOW_UP, directory=".pm/backlog/tasks"):
        return self.write(
            directory + "/unrelated-filename.md",
            f"---\nid: '{task_id}'\nstatus: Ready\ntype: task\nassignee: []\n---\n\n## Implementation Notes\n{notes}",
        )

    def assert_problem(self, message):
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)

    def test_all_outcomes_and_frontmatter_task_and_draft_ids_pass(self):
        self.target()
        self.target("DRAFT-2.1", directory=".pm/backlog/drafts")
        self.audit(
            self.HEADER
            + "| 1 | yes | fixed | ABC1234 |\n"
            + "| 2 | no | fixed | missing/file.py:12 |\n"
            + "| 3 | yes | rejected | not a live claim |\n"
            + "| 4 | yes | linked | REQ-2 |\n"
            + "| 5 | yes | asked | DRAFT-2.1 |\n"
        )
        self.write(self.REPORT, "## Findings\n" + "".join(f"| {i} | claim |\n" for i in range(1, 6)))

        result = self.run_check()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("coverage skipped", result.stdout)

    def test_missing_table_and_empty_table_fail(self):
        for notes, message in (
            (f"Audit report: {self.REPORT}\n", "no 'Audit outcomes:' table"),
            (f"Audit report: {self.REPORT}\nAudit outcomes:\n" + self.HEADER, "table is empty"),
        ):
            with self.subTest(message=message):
                self.audit(notes=notes)
                self.assert_problem(message)

    def test_wrong_or_missing_header_and_separator_fail(self):
        for table, message in (
            (self.HEADER.replace("Verified", "Confirmed") + "| 1 | yes | fixed | abc1234 |\n", "header must be"),
            ("| 1 | yes | fixed | abc1234 |\n", "header must be"),
            ("| # | Verified | Outcome | Evidence |\n| 1 | yes | fixed | abc1234 |\n", "four-cell separator"),
        ):
            with self.subTest(table=table):
                self.audit(table)
                self.assert_problem(message)

    def test_duplicate_numbers_fail_including_leading_zero_alias(self):
        self.audit(self.HEADER + "| 1 | yes | fixed | abc1234 |\n| 01 | no | fixed | def1234 |\n")
        self.assert_problem("duplicate finding number")

    def test_wrong_cell_count_fails(self):
        for row in ("| 1 | yes | fixed |", "| 1 | yes | fixed | abc1234 | extra |", "| 1 | yes | fixed | abc1234"):
            with self.subTest(row=row):
                self.audit(self.HEADER + row + "\n")
                self.assert_problem("wrong cell count")

    def test_bad_number_verified_and_outcome_fail(self):
        for row, message in (
            ("| x | yes | fixed | abc1234 |", "positive integer"),
            ("| 0 | yes | fixed | abc1234 |", "positive integer"),
            ("| 1 | maybe | fixed | abc1234 |", "Verified must be yes or no"),
            ("| 1 | yes | ignored | abc1234 |", "invalid Outcome"),
        ):
            with self.subTest(row=row):
                self.audit(self.HEADER + row + "\n")
                self.assert_problem(message)

    def test_missing_evidence_for_each_outcome_fails(self):
        for outcome, message in (
            ("fixed", "fixed needs"),
            ("rejected", "rejected needs"),
            ("linked", "linked needs an existing"),
            ("asked", "asked needs an existing"),
        ):
            with self.subTest(outcome=outcome):
                self.audit(self.HEADER + f"| 1 | yes | {outcome} | |\n")
                self.assert_problem(message)

    def test_fixed_evidence_syntax_and_hash_bounds(self):
        for evidence, valid in (
            ("abcdef", False),
            ("a" * 7, True),
            ("a" * 40, True),
            ("a" * 41, False),
            ("zzzzzzz", False),
            ("src/app.py:0", False),
            ("src/app.py:x", False),
            ("src/app.py:3", True),
            ("C:/src/app.py:3", True),
        ):
            with self.subTest(evidence=evidence):
                self.audit(self.HEADER + f"| 1 | yes | fixed | {evidence} |\n")
                result = self.run_check()
                self.assertEqual(result.returncode, 0 if valid else 1, result.stdout)

    def test_rejection_needs_three_words(self):
        self.audit(self.HEADER + "| 1 | yes | rejected | not applicable |\n")
        self.assert_problem("reason of at least three words")

    def test_unknown_and_prose_only_targets_fail_for_both_outcomes(self):
        self.target(notes="Next: REQ-99 exists only in prose\n")
        self.write(".pm/backlog/tasks/req-99.md", "# REQ-99 has no frontmatter\n")
        for outcome in ("linked", "asked"):
            with self.subTest(outcome=outcome):
                self.audit(self.HEADER + f"| 1 | yes | {outcome} | REQ-99 |\n")
                self.assert_problem("needs an existing task or draft ID")

    def test_archived_targets_fail(self):
        for directory in (".pm/backlog/archive/tasks", ".pm/backlog/tasks/archive", ".pm/backlog/drafts/archive"):
            self.target(directory=directory)
        for outcome in ("linked", "asked"):
            with self.subTest(outcome=outcome):
                self.audit(self.HEADER + f"| 1 | yes | {outcome} | REQ-2 |\n")
                self.assert_problem("not archived")

    def test_asked_target_needs_actionable_owner_line(self):
        for value in (None, "", "none", "None", "yok", "-", "?", "n/a"):
            with self.subTest(value=value):
                needs = "" if value is None else f"Needs owner: {value}\n"
                self.target(notes=needs + "Review by: 2026-10-22 · Sam · after REQ-2\n")
                self.audit(self.HEADER + "| 1 | yes | asked | REQ-2 |\n")
                self.assert_problem("needs a non-empty 'Needs owner:' line")

    def test_asked_target_needs_review_date_owner_and_condition(self):
        for review in (
            "",
            "Review by: 2026-10-22 · · after REQ-2",
            "Review by: · Sam · after REQ-2",
            "Review by: 2026-02-30 · Sam · after REQ-2",
            "Review by: 2026-2-3 · Sam · after REQ-2",
            "Review by: 2026-10-22 · Sam ·",
            "Review by: 2026-10-22",
        ):
            with self.subTest(review=review):
                self.target(notes="Needs owner: choose a next step\n" + review + "\n")
                self.audit(self.HEADER + "| 1 | yes | asked | REQ-2 |\n")
                self.assert_problem("needs 'Review by: YYYY-MM-DD · owner · condition'")

    def test_target_follow_up_lines_outside_notes_or_in_fences_do_not_count(self):
        for notes in ("```\n" + self.FOLLOW_UP + "```\n", "## Final Summary\n" + self.FOLLOW_UP):
            with self.subTest(notes=notes):
                self.target(notes=notes)
                self.audit(self.HEADER + "| 1 | yes | asked | REQ-2 |\n")
                self.assert_problem("needs a non-empty 'Needs owner:' line")
                self.assert_problem("needs 'Review by:")

    def test_report_coverage_compares_ids_not_counts(self):
        self.write(self.REPORT, "## Findings\n| 1 | first |\n| 3 | third |\n")
        self.audit(self.HEADER + "| 1 | yes | fixed | abc1234 |\n| 2 | yes | fixed | def1234 |\n")
        self.assert_problem("report finding 3 has no audit outcome row")

    def test_report_scope_ignores_fences_and_later_sections_but_includes_subheadings(self):
        for end in ("## Appendix", "# Appendix"):
            with self.subTest(end=end):
                self.write(
                    self.REPORT,
                    "| 8 | outside |\n```\n## Findings\n| 9 | example |\n```\n"
                    "## Findings\n| 1 | real |\n### Detail\n| 2 | real |\n"
                    "~~~md\n| 3 | example |\n~~~\n````md\n| 4 | example |\n````\n" + end + "\n| 5 | unrelated |\n",
                )
                self.audit(self.HEADER + "| 1 | yes | fixed | abc1234 |\n| 2 | yes | fixed | def1234 |\n")
                result = self.run_check()
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_missing_report_prints_one_info_line_without_failure(self):
        self.audit()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout.count("Info:"), 1)
        self.assertIn(self.REPORT, result.stdout)
        self.assertIn("coverage skipped", result.stdout)

    def test_missing_report_still_checks_rows(self):
        self.audit(self.HEADER + "| 1 | yes | fixed | |\n")
        self.assert_problem("fixed needs")

    def test_non_done_audit_is_not_checked(self):
        for status in ("Active", "Ready", "Owner check"):
            with self.subTest(status=status):
                self.audit(table="", status=status)
                result = self.run_check()
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("Info:", result.stdout)

    def test_done_draft_audit_and_legacy_task_root_are_checked(self):
        for directory in (".pm/backlog/drafts", "backlog/tasks"):
            with self.subTest(directory=directory):
                path = self.audit(table="", directory=directory)
                self.assert_problem("no 'Audit outcomes:' table")
                path.unlink()

    def test_audit_fields_only_count_inside_notes_and_outside_fences(self):
        for notes in (
            "Next: ordinary task\n## Final Summary\nAudit report: missing.md\n",
            "```\nAudit report: missing.md\n```\n",
            "# Other\nAudit report: missing.md\n",
        ):
            with self.subTest(notes=notes):
                self.audit(notes=notes)
                result = self.run_check()
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotIn("Info:", result.stdout)

    def test_outcomes_in_another_section_or_fence_do_not_count(self):
        for table in (
            "## Final Summary\nAudit outcomes:\n" + self.HEADER,
            "```\nAudit outcomes:\n" + self.HEADER + "```\n",
        ):
            with self.subTest(table=table):
                self.audit(notes=f"Audit report: {self.REPORT}\n" + table)
                self.assert_problem("no 'Audit outcomes:' table")

    def test_table_stops_at_first_non_table_line(self):
        for boundary in ("\n", "a paragraph\n", "```\nexample\n```\n"):
            with self.subTest(boundary=boundary):
                self.audit(self.HEADER + "| 1 | yes | fixed | abc1234 |\n" + boundary + "| 1 | maybe | bad | |\n")
                result = self.run_check()
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_later_unrelated_table_cannot_fill_coverage(self):
        self.write(self.REPORT, "## Findings\n| 1 | claim |\n| 2 | claim |\n")
        self.audit(self.HEADER + "| 1 | yes | fixed | abc1234 |\n\n" + self.HEADER + "| 2 | yes | fixed | def1234 |\n")
        self.assert_problem("report finding 2 has no audit outcome row")

    def test_exactly_one_non_empty_report_line_required(self):
        for reports in ("Audit report:\n", f"Audit report: {self.REPORT}\nAudit report: second.md\n"):
            with self.subTest(reports=reports):
                self.audit(notes=reports + "Audit outcomes:\n" + self.HEADER + "| 1 | yes | fixed | abc1234 |\n")
                self.assert_problem("exactly one non-empty 'Audit report:' line")


if __name__ == "__main__":
    unittest.main()
