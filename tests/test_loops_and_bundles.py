"""The terraform, gcp, docs and loops bundles ship the skills, commands and rules they document."""
from __future__ import annotations

import unittest

from tests.helpers import ROOT, load_cli

BUNDLES = ROOT / "kit" / "bundles"
EXPECTED = {
    "terraform": {"terraform-gcp", "terraform-plan-review", "terraform-import-and-state",
                  "iac-docs-maintenance", "terraform-yaml-settings"},
    "gcp": {"gcp-iap-impersonation", "gcp-cloud-run-deploy-verify", "gcp-oauth-client-setup",
            "gcp-cloudsql-data-api", "gcp-billing-report", "gcp-identity-routing"},
    "docs": {"docs-mermaid-diagrams", "docs-print-ready-pdf", "docs-markdown-pdf-vscode",
             "docs-plan-to-docs", "chat-rich-message"},
    "loops": {"loop-engineering", "loopify"},
}
COMMANDS = {"docs-plan-to-docs", "loopify"}
RULES = {"terraform": {"terraform-apply-requires-approval"}, "gcp": {"database-mutation-requires-approval"}}


class BundleContentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cli = load_cli()

    def test_skills_and_invocation(self) -> None:
        for bundle, skills in EXPECTED.items():
            found = {p.name for p in (BUNDLES / bundle / "skills").iterdir() if (p / "SKILL.md").is_file()}
            self.assertEqual(found, skills, bundle)
            for name in skills:
                text = (BUNDLES / bundle / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                block, _ = self.cli.split_frontmatter(text)
                is_command = "disable-model-invocation: true" in (block or "")
                self.assertEqual(is_command, name in COMMANDS, f"{name}: command flag")

    def test_gate_rules_are_always_on(self) -> None:
        for bundle, rules in RULES.items():
            for rule in rules:
                text = (BUNDLES / bundle / "rules" / f"{rule}.md").read_text(encoding="utf-8")
                self.assertIn("apply: always", text)
                self.assertLess(len(text.encode("utf-8")), 2600, f"{rule} should stay short")

    def test_no_skill_tells_the_agent_to_apply(self) -> None:
        """Apply commands only appear as handover blocks next to an approval question."""
        for bundle in ("terraform", "gcp", "loops"):
            for skill in (BUNDLES / bundle / "skills").glob("*/SKILL.md"):
                text = skill.read_text(encoding="utf-8").lower()
                if "terraform apply" in text:
                    self.assertTrue("apply now?" in text or "approval" in text or "approve" in text,
                                    f"{skill} mentions terraform apply without the approval gate")


if __name__ == "__main__":
    unittest.main()
