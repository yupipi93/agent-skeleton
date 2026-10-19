"""init idempotency, pruning, toggles, overrides, ownership and projects."""
import json
import os
import unittest

from tests.helpers import RepoTestCase, snapshot, write


class InitTest(RepoTestCase):
    def test_init_twice_is_identical(self):
        self.add_demo_bundle()
        self.run_cli("init")
        first = snapshot(self.repo)
        out = self.run_cli("init").stdout
        self.assertEqual(snapshot(self.repo), first)
        self.assertIn("(0 written, 0 pruned, 0 skipped)", out)
        self.assertEqual(self.run_cli("init", "--check").returncode, 0)

    def test_generated_tree_shape(self):
        self.run_cli("init")
        r = self.repo
        self.assertEqual((r / "CLAUDE.md").read_text().splitlines()[0], "@AGENTS.md")
        self.assertFalse((r / "GEMINI.md").exists())
        for d in (".claude/skills", ".agents/skills"):
            link = r / d / "workspace-guide"
            self.assertTrue(link.is_symlink())
            self.assertEqual(os.readlink(link), "../../kit/bundles/core/skills/workspace-guide")
            self.assertTrue((link / "SKILL.md").is_file())
        self.assertTrue((r / ".cursor/rules/agent-safety-gates.mdc").is_file())
        self.assertTrue((r / ".agents/rules/agent-safety-gates.md").is_file())
        self.assertFalse((r / ".mcp.json").exists())  # no MCP servers in the default kit
        cursor_hooks = r / ".cursor/hooks.json"  # kit hooks only (jira MCP text guard)
        if cursor_hooks.exists():
            self.assertNotIn("local/bundles", cursor_hooks.read_text())
        settings = json.loads((r / ".claude/settings.json").read_text())
        self.assertEqual(settings["plansDirectory"], "plans")
        self.assertIn("Bash(terraform apply *)", settings["permissions"]["deny"])

    def test_disable_enable_round_trip(self):
        original_local = '# mine\n[bundles]\nvoice = false  # stays\n'
        self.local_toml(original_local)
        self.run_cli("init")
        before = snapshot(self.repo, with_mtime=False)

        self.run_cli("disable", "mac")
        self.assertFalse((self.repo / ".claude/skills/mac-setup").exists())
        self.run_cli("disable", "plan-files")
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(settings["skillOverrides"]["plan-files"], "off")
        gemini = json.loads((self.repo / ".gemini/settings.json").read_text())
        self.assertIn("plan-files", gemini["skills"]["disabled"])

        self.run_cli("enable", "plan-files")
        self.run_cli("enable", "mac")
        self.assertEqual((self.repo / "skeleton.local.toml").read_text(), original_local)
        self.assertEqual(snapshot(self.repo, with_mtime=False), before)

    def test_disable_rule_and_enable_off_bundle(self):
        self.run_cli("disable", "no-broad-process-kill")
        self.assertFalse((self.repo / ".claude/rules/no-broad-process-kill.md").exists())
        self.assertFalse((self.repo / ".cursor/rules/no-broad-process-kill.mdc").exists())
        self.run_cli("enable", "style")
        self.assertTrue((self.repo / ".cursor/rules/no-em-dash.mdc").exists())
        local = (self.repo / "skeleton.local.toml").read_text()
        self.assertIn('no-broad-process-kill = false', local)
        self.assertIn("style = true", local)
        bad = self.run_cli("enable", "does-not-exist", check=False)
        self.assertNotEqual(bad.returncode, 0)

    def test_invocation_override_renders_copy(self):
        self.local_toml('[skills]\n"plan-files" = { invocation = "user" }\n')
        self.run_cli("init")
        link = self.repo / ".claude/skills/plan-files"
        self.assertEqual(os.readlink(link), "../../.skeleton/rendered-skills/plan-files")
        rendered = (self.repo / ".skeleton/rendered-skills/plan-files/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", rendered)
        kit = (self.repo / "kit/bundles/core/skills/plan-files/SKILL.md").read_text()
        self.assertNotIn("disable-model-invocation", kit)
        self.assertTrue((self.repo / ".gemini/commands/plan-files.toml").exists())

        self.local_toml("")
        self.run_cli("init")
        self.assertEqual(os.readlink(link), "../../kit/bundles/core/skills/plan-files")
        self.assertFalse((self.repo / ".skeleton/rendered-skills").exists())
        self.assertFalse((self.repo / ".gemini/commands/plan-files.toml").exists())

    def test_user_override_path(self):
        fork = self.tmp / "my-skills" / "readme-sync"
        write(fork / "SKILL.md", "---\nname: readme-sync\ndescription: My fork.\n---\n# Fork\n")
        self.local_toml(f'[overrides]\n"readme-sync" = "{fork}"\n')
        self.run_cli("init")
        self.assertEqual(os.readlink(self.repo / ".agents/skills/readme-sync"), str(fork))
        self.assertIn("overridden", self.run_cli("list", "--skills").stdout)

    def test_tools_subset_prunes_others(self):
        self.run_cli("init")
        out = self.run_cli("init", "--tools", "claude").stdout
        self.assertIn("pruned", out)
        for gone in (".cursor", ".gemini", ".agents"):
            self.assertFalse((self.repo / gone).exists(), gone)
        self.assertTrue((self.repo / ".claude/skills/workspace-guide").is_symlink())
        self.assertNotEqual(self.run_cli("init", "--check", check=False).returncode, 0)

    def test_does_not_clobber_foreign_files(self):
        write(self.repo / ".claude/settings.json", '{"mine": true}\n')
        write(self.repo / ".claude/settings.local.json", '{"personal": true}\n')
        proc = self.run_cli("init", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("skipped .claude/settings.json", proc.stderr)
        self.assertEqual((self.repo / ".claude/settings.json").read_text(), '{"mine": true}\n')
        self.run_cli("init", "--force")
        self.assertIn("permissions", (self.repo / ".claude/settings.json").read_text())
        self.assertEqual((self.repo / ".claude/settings.local.json").read_text(), '{"personal": true}\n')

    def test_stale_links_pruned_without_manifest(self):
        self.run_cli("init")
        (self.repo / ".skeleton/generated.json").unlink()
        os.symlink("../../kit/bundles/core/skills/gone", self.repo / ".claude/skills/gone")
        self.run_cli("init")
        self.assertFalse(os.path.lexists(self.repo / ".claude/skills/gone"))

    def test_local_bundle_can_be_disabled(self):
        self.add_demo_bundle()
        self.run_cli("init")
        self.assertTrue((self.repo / ".mcp.json").exists())
        listing = self.run_cli("list").stdout
        self.assertIn("local", listing)
        self.run_cli("disable", "demo")
        self.assertFalse((self.repo / ".mcp.json").exists())
        cursor_hooks = self.repo / ".cursor/hooks.json"
        if cursor_hooks.exists():
            self.assertNotIn("local/bundles/demo", cursor_hooks.read_text())
        self.assertNotIn("local/bundles/demo", (self.repo / ".claude/settings.json").read_text())

    def test_list_names_enabled(self):
        names = self.run_cli("list", "--names", "--enabled").stdout.split()
        self.assertIn("core", names)
        self.assertNotIn("voice", names)
        self.assertNotIn("style", names)

    def test_projects_add_remove(self):
        code = self.home / "code"
        for n in ("alpha-service", "beta-web", "gamma"):
            (code / n).mkdir(parents=True)
        self.local_toml(f'[paths]\nprojects_dir = "{code}"\n')
        out = self.run_cli("projects", "add", "alpha").stdout
        self.assertIn("alpha-service", out)
        link = self.repo / "projects/alpha-service"
        self.assertTrue(link.is_symlink())
        ws = json.loads((self.repo / "agent-skeleton.code-workspace").read_text())
        self.assertEqual([f["path"] for f in ws["folders"]], [".", "projects/alpha-service"])
        self.assertIn("alpha-service", self.run_cli("projects", "list").stdout)
        self.run_cli("projects", "remove", "alph")
        self.assertFalse(os.path.lexists(link))
        self.assertTrue((code / "alpha-service").is_dir())
        self.assertEqual(self.run_cli("projects", "add", "zzz", check=False).returncode, 1)

    def test_projects_sync_rewrites_workspace_without_linking(self):
        code = self.home / "code"
        (code / "alpha-service").mkdir(parents=True)
        (self.repo / "projects").mkdir(exist_ok=True)
        os.symlink(str(code / "alpha-service"), self.repo / "projects/alpha-service")
        os.symlink(str(code / "gone"), self.repo / "projects/gone")
        ws_path = self.repo / "agent-skeleton.code-workspace"
        ws_path.write_text(json.dumps({"folders": [], "settings": {"editor.tabSize": 2}}))
        out = self.run_cli("projects", "sync").stdout
        self.assertIn("2 project(s)", out)
        self.assertIn("gone", out)
        ws = json.loads(ws_path.read_text())
        self.assertEqual([f["path"] for f in ws["folders"]],
                         [".", "projects/alpha-service", "projects/gone"])
        self.assertEqual(ws["settings"], {"editor.tabSize": 2})
        self.assertEqual(sorted(os.listdir(self.repo / "projects")), ["alpha-service", "gone"])
        before = ws_path.read_text()
        self.run_cli("projects", "sync")
        self.assertEqual(ws_path.read_text(), before)

    def test_new_skill_scaffold_passes_check(self):
        self.run_cli("new-skill", "core", "demo-thing", "--user-invocable")
        text = (self.repo / "kit/bundles/core/skills/demo-thing/SKILL.md").read_text()
        self.assertIn("name: demo-thing", text)
        self.assertIn("disable-model-invocation: true", text)
        self.run_cli("check")
        self.assertNotEqual(self.run_cli("new-skill", "core", "Bad_Name", check=False).returncode, 0)

    def test_doctor_runs(self):
        self.run_cli("init")
        out = self.run_cli("doctor").stdout
        self.assertIn("generated tree is up to date", out)
        self.assertIn("Third", out.replace("third", "Third"))


if __name__ == "__main__":
    unittest.main()
