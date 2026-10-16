"""`bin/skeleton check` catches the authoring mistakes it promises to catch."""
import unittest

from tests.helpers import RepoTestCase, write

EM_DASH = "\u2014"


class CheckTest(RepoTestCase):
    def test_repo_passes(self):
        self.assertIn("check** passed", self.run_cli("check").stdout)

    def test_name_mismatch(self):
        write(self.repo / "kit/bundles/core/skills/real-name/SKILL.md",
              "---\nname: other-name\ndescription: Something.\n---\n# X\n")
        proc = self.run_cli("check", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("must equal the folder name 'real-name'", proc.stdout)

    def test_em_dash(self):
        write(self.repo / "docs/extra.md", f"# Title\n\nOne {EM_DASH} two\n")
        proc = self.run_cli("check", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("docs/extra.md:3: contains U+2014", proc.stdout)

    def test_denylisted_home_path_and_email(self):
        home_path = "/Us" + "ers/someone/project"
        mail = "someone" + "@" + "corp-mail.io"
        write(self.repo / "docs/leak.md", f"Path {home_path}\nMail {mail}\nOk you@example.com\n")
        proc = self.run_cli("check", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("docs/leak.md:1", proc.stdout)
        self.assertIn("docs/leak.md:2", proc.stdout)
        self.assertNotIn("docs/leak.md:3", proc.stdout)

    def test_skill_rules(self):
        long_desc = "x" * 301
        write(self.repo / "kit/bundles/core/skills/long-one/SKILL.md",
              f"---\nname: long-one\ndescription: {long_desc}\n---\n" + "line\n" * 510)
        write(self.repo / "kit/bundles/core/skills/colon-one/SKILL.md",
              "---\nname: colon-one\ndescription: Does this: and that\n---\n# X\n")
        write(self.repo / "kit/bundles/core/skills/Bad_Folder/SKILL.md",
              "---\nname: Bad_Folder\ndescription: x\n---\n")
        out = self.run_cli("check", check=False).stdout
        self.assertIn("description is 301 chars", out)
        self.assertIn("lines (keep SKILL.md under 500", out)
        self.assertIn("contains ': ' unquoted", out)
        self.assertIn("folder name must match", out)

    def test_rule_and_hook_validation(self):
        write(self.repo / "kit/bundles/core/rules/broken.md", "---\ndescription: x\napply: sometimes\n---\nBody\n")
        write(self.repo / "kit/bundles/core/rules/globless.md", "---\ndescription: x\napply: glob\n---\nBody\n")
        write(self.repo / "kit/bundles/core/hooks.toml",
              '[[hook]]\nid = "h1"\nevent = "whenever"\nrun = "scripts/missing.sh"\n')
        out = self.run_cli("check", check=False).stdout
        self.assertIn("'apply' must be one of always, glob, manual", out)
        self.assertIn("apply: glob needs a non-empty globs list", out)
        self.assertIn("event must be one of", out)
        self.assertIn("run script scripts/missing.sh does not exist", out)

    def test_bundle_manifest_validation(self):
        write(self.repo / "kit/bundles/broken/bundle.toml", 'name = "nope"\nrequires = ["ghost"]\n')
        out = self.run_cli("check", check=False).stdout
        self.assertIn("must equal the folder 'broken'", out)
        self.assertIn("missing 'emoji'", out)
        self.assertIn("requires unknown bundle 'ghost'", out)


if __name__ == "__main__":
    unittest.main()
