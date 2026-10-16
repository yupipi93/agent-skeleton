"""Unit tests of the per-tool renderers (rules, hooks, MCP, Gemini commands)."""
import json
import unittest
from pathlib import Path

from tests.helpers import RepoTestCase, load_cli

sk = load_cli()
ROOT = Path("/tmp/repo")


def rule(apply, globs=None, desc="Desc: with colon."):
    meta = {"description": desc, "apply": apply}
    if globs:
        meta["globs"] = globs
    return sk.Rule(name="r", bundle="b", path=ROOT / "kit/bundles/b/rules/r.md", meta=meta, body="# R\n\nBody.\n")


class RuleRenderTest(unittest.TestCase):
    def test_cursor(self):
        out = sk.render_rule_cursor(ROOT, rule("glob", ["**/*.tf", "*.md"]))
        self.assertTrue(out.startswith('---\ndescription: "Desc: with colon."\nglobs: **/*.tf,*.md\n'
                                       "alwaysApply: false\n---\n"))
        self.assertIn(sk.MARKER, out)
        self.assertIn("alwaysApply: true", sk.render_rule_cursor(ROOT, rule("always")))
        manual = sk.render_rule_cursor(ROOT, rule("manual"))
        self.assertIn("alwaysApply: false", manual)
        self.assertNotIn("globs", manual)

    def test_claude(self):
        always = sk.render_rule_claude(ROOT, rule("always"))
        self.assertTrue(always.startswith("<!-- "))
        self.assertNotIn("---\n", always.split("\n", 1)[0])
        glob = sk.render_rule_claude(ROOT, rule("glob", ["**/*.tf"]))
        self.assertTrue(glob.startswith('---\npaths:\n  - "**/*.tf"\n---\n'))
        self.assertIsNone(sk.render_rule_claude(ROOT, rule("manual")))

    def test_antigravity(self):
        self.assertIn("trigger: always_on", sk.render_rule_antigravity(ROOT, rule("always")))
        g = sk.render_rule_antigravity(ROOT, rule("glob", ["a/**", "b/*"]))
        self.assertIn("trigger: glob\n", g)
        self.assertIn("globs: a/**,b/*\n", g)
        self.assertIn("trigger: manual", sk.render_rule_antigravity(ROOT, rule("manual")))

    def test_gemini_concat(self):
        out = sk.render_gemini_rules(ROOT, [rule("always"), rule("glob", ["**/*.tf"]), rule("manual")])
        self.assertIn("# Scoped rules", out)
        self.assertIn("> Applies to files matching: `**/*.tf`", out)
        self.assertEqual(out.count("Body."), 2)  # manual rules are omitted
        self.assertIsNone(sk.render_gemini_rules(ROOT, [rule("manual")]))


class HookMappingTest(unittest.TestCase):
    def hook(self, event, match=None):
        return sk.Hook(id="h", bundle="b", event=event, run="scripts/h.sh", match=match or {})

    def test_event_names(self):
        expected = {
            "claude": ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"],
            "cursor": ["sessionStart", "beforeSubmitPrompt", "preToolUse", "postToolUse", "stop", "sessionEnd"],
            "gemini": ["SessionStart", "BeforeAgent", "BeforeTool", "AfterTool", "AfterAgent", "SessionEnd"],
            "antigravity": ["SessionStart", None, "PreToolUse", "PostToolUse", "Stop", None],
        }
        for tool, names in expected.items():
            got = [sk.hook_event_name(self.hook(e), tool) for e in sk.EVENTS]
            self.assertEqual(got, names, tool)

    def test_cursor_special_events(self):
        self.assertEqual(sk.hook_event_name(self.hook("before_tool", {"mcp": "x"}), "cursor"), "beforeMCPExecution")
        self.assertEqual(sk.hook_event_name(self.hook("before_tool", {"shell": True}), "cursor"),
                         "beforeShellExecution")
        self.assertEqual(sk.hook_event_name(self.hook("after_tool", {"mcp": "x"}), "cursor"), "afterMCPExecution")

    def test_matchers(self):
        h = self.hook("before_tool", {"mcp": "atlassian.*"})
        self.assertEqual(sk.hook_matcher(h, "claude"), "mcp__atlassian.*")
        self.assertIsNone(sk.hook_matcher(h, "cursor"))
        self.assertEqual(sk.hook_matcher(h, "gemini"), "atlassian.*")
        t = self.hook("before_tool", {"tool": "Edit|Write"})
        self.assertEqual(sk.hook_matcher(t, "claude"), "Edit|Write")
        self.assertEqual(sk.hook_matcher(t, "cursor"), "Write")
        self.assertEqual(sk.hook_matcher(t, "gemini"), "replace|write_file")
        self.assertIsNone(sk.hook_matcher(self.hook("stop", {"tool": "Edit"}), "claude"))


class EndToEndRenderTest(RepoTestCase):
    def test_demo_bundle_renders_everywhere(self):
        self.add_demo_bundle()
        self.run_cli("init")
        r = self.repo

        claude = json.loads((r / ".claude/settings.json").read_text())
        hooks = claude["hooks"]
        self.assertEqual(hooks["Stop"][0]["hooks"][0]["command"],
                         '"$CLAUDE_PROJECT_DIR"/local/bundles/demo/scripts/hook.sh --client claude')
        self.assertEqual(hooks["Stop"][0]["hooks"][0]["timeout"], 20)
        pre = {g.get("matcher"): g for g in hooks["PreToolUse"]}
        self.assertIn("mcp__atlassian.*", pre)
        self.assertIn("Bash", pre)
        demo = lambda groups: [g for g in groups if "/demo/" in g["hooks"][0]["command"]]  # noqa: E731
        self.assertIn("--mode context --client claude", demo(hooks["UserPromptSubmit"])[0]["hooks"][0]["command"])
        self.assertEqual(claude["$schema"], "https://json.schemastore.org/claude-code-settings.json")

        cursor = json.loads((r / ".cursor/hooks.json").read_text())
        self.assertEqual(cursor["version"], 1)
        self.assertIn({"command": "./local/bundles/demo/scripts/hook.sh --client cursor", "timeout": 15,
                       "failClosed": True}, cursor["hooks"]["beforeMCPExecution"])
        self.assertIn("beforeShellExecution", cursor["hooks"])
        self.assertIn("stop", cursor["hooks"])

        gemini = json.loads((r / ".gemini/settings.json").read_text())
        self.assertEqual(gemini["hooks"]["AfterAgent"][0]["hooks"][0]["timeout"], 20000)
        self.assertIn("demo-mcp-guard", [g["hooks"][0]["name"] for g in gemini["hooks"]["BeforeTool"]])
        self.assertEqual(gemini["context"]["fileName"], ["AGENTS.md", ".gemini/RULES.md"])
        self.assertEqual(gemini["mcpServers"]["remote"], {
            "httpUrl": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer ${DEMO_TOKEN}"}})

        anti = json.loads((r / ".agents/hooks.json").read_text())
        self.assertNotIn("UserPromptSubmit", anti["hooks"])
        self.assertEqual(len(demo(anti["hooks"]["PreToolUse"])), 1)  # mcp hook excludes antigravity

        mcp = json.loads((r / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(mcp["local-tool"]["type"], "stdio")
        self.assertEqual(mcp["local-tool"]["args"], [f"{r}/server.js"])
        self.assertEqual(mcp["remote"]["type"], "http")
        cmcp = json.loads((r / ".cursor/mcp.json").read_text())["mcpServers"]
        self.assertEqual(cmcp["local-tool"]["env"], {"API_TOKEN": "${env:DEMO_TOKEN}"})
        amcp = json.loads((r / ".agents/mcp_config.json").read_text())["mcpServers"]
        self.assertEqual(amcp["remote"]["serverUrl"], "https://mcp.example.com/mcp")

        self.assertTrue((r / ".claude/rules/tf-only.md").read_text().startswith('---\npaths:\n  - "**/*.tf"'))
        self.assertFalse((r / ".claude/rules/on-demand.md").exists())
        self.assertIn("trigger: manual", (r / ".agents/rules/on-demand.md").read_text())
        self.assertIn("globs: **/*.tf,**/*.tfvars", (r / ".cursor/rules/tf-only.mdc").read_text())

        toml = (r / ".gemini/commands/demo-command.toml").read_text()
        parsed = sk.tomllib.loads(toml)
        self.assertEqual(parsed["description"], "A slash command: does demo things.")
        self.assertIn("{{args}}", parsed["prompt"])
        self.assertFalse((r / ".gemini/commands/plan-files.toml").exists())
        self.assertTrue((r / ".claude/skills/demo-command").is_symlink())

    def test_user_profile_rule(self):
        self.local_toml('[user]\nname = "Ada"\nlanguage = "es"\n')
        self.run_cli("init")
        text = (self.repo / ".claude/rules/skeleton-user-profile.md").read_text()
        self.assertIn("The user's name is Ada.", text)
        self.assertIn("`es`", (self.repo / ".gemini/RULES.md").read_text())


if __name__ == "__main__":
    unittest.main()
