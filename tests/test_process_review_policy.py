"""Guard the shipped review and audit instructions against conflicting policies."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PM = ROOT / "template" / ".pm"


def text(path):
    return (PM / path).read_text(encoding="utf-8")


class ReviewPolicyTest(unittest.TestCase):
    def test_step_seven_applies_the_same_risk_rule_to_peer_leads(self):
        lead = text("roles/lead.md")
        step = lead.split("\n7. ", 1)[1].split("\n8. ", 1)[0]
        for phrase in (
            "security, data, money, permissions or a public release",
            "different model family",
            "Review: lead self-check",
            "author does not perform the independent review",
            "peer lead's package follows the same risk rule",
        ):
            self.assertIn(phrase, step)
        self.assertNotIn("Never review your own code", step)
        self.assertNotIn("also gets cross-review", step)

    def test_self_check_handoff_finds_project_work_beyond_recent_setup_children(self):
        spec = importlib.util.spec_from_file_location("pm_resume_review_policy", PM / "tools/pm_resume.py")
        resume = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(resume)
        summary = resume.final_summary(
            [
                "## Final Summary",
                "Owner said: Fix the project.",
                "Found: It works.",
                "Next: none.",
                "Review: lead self-check (tests and diff)",
            ]
        )
        project = {
            "id": "TASK-1",
            "title": "Project fix",
            "status": "Done",
            "updated": "2026-01-01",
            "summary": summary,
        }
        children = [
            {
                "id": f"TASK-{i + 2}",
                "title": f"Setup child {i}",
                "status": "Done",
                "updated": f"2026-01-{i + 2:02}",
                "summary": ["Setup done."],
            }
            for i in range(resume.CLOSED_SHOWN + 2)
        ]
        recent = "\n".join(resume.closed_lines([project, *children]))
        self.assertIn("Setup child", recent)
        self.assertNotIn("Project fix", recent)
        self.assertIn("Review: lead self-check (tests and diff)", project["summary"])

        step = text("roles/lead.md").split("\n7. ", 1)[1].split("\n8. ", 1)[0]
        for phrase in (
            "`Review: lead self-check (<what was checked>)` as one of its first lines",
            "`backlog task list -s Done --plain`",
            "closed since the last session",
            "open every full summary with `backlog task <id> --plain`",
            "even when more than three tasks closed",
            "all Done summaries if the last session's end is unclear",
            "say in one line if you disagree with a self-check",
        ):
            self.assertIn(phrase, step)

    def test_charter_records_only_work_actually_done(self):
        charter = text("templates/charter.md")
        for phrase in (
            "lead card, step 7",
            "Review: lead self-check",
            "only when it was actually done",
            "pending with an owner and a review point",
            "intent and acceptance",
        ):
            self.assertIn(phrase, charter)
        self.assertNotIn("a different-family frontier model challenges", charter)
        self.assertNotIn("- Independent review:", charter)

    def test_lead_reads_optional_records_and_reviews_assumptions_by_risk(self):
        lead = text("roles/lead.md")
        self.assertIn("If `.pm/charter.md` exists, read it", lead)
        self.assertIn("Read the relevant `.pm/specs/<epic>/requirements.md` if it exists", lead)
        self.assertIn("Challenge expensive assumptions under the risk rule in step 7", lead)

    def test_package_guide_marks_both_records_optional(self):
        self.assertIn("`charter.md` if it exists, then `specs/<epic>/requirements.md` if it exists", text("README.md"))

    def test_research_and_model_roles_follow_the_risk_rule(self):
        reviewer = text("roles/reviewer.md")
        self.assertIn("lead card, step 7", reviewer)
        self.assertIn("Review: lead self-check", reviewer)
        models = text("models.md")
        self.assertIn("peer lead's package follows the risk rule", models)
        self.assertNotIn("runs its own helpers, cross-reviews", models)

    def test_both_audits_allow_a_labelled_lead_fallback(self):
        for path in ("templates/doc-audit.md", "templates/decision-audit.md"):
            with self.subTest(path=path):
                audit = text(path)
                self.assertIn("lead card, step 7", audit)
                self.assertIn("When no worker can run, the lead runs the audit itself and labels it", audit)
                self.assertNotIn("A second worker from another model family", audit)
                self.assertNotIn("a second cheap worker, from a different model family", audit)
