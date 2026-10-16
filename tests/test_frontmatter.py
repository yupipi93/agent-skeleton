import unittest

from tests.helpers import load_cli

sk = load_cli()


class FrontmatterParserTest(unittest.TestCase):
    def parse(self, text):
        meta, body = sk.read_frontmatter(text)
        return meta, body

    def test_scalars_and_quotes(self):
        meta, body = self.parse(
            '---\nname: demo\ndescription: "Has: a colon"\nflag: true\nn: 3\nq: \'it\'\'s\'\n---\nBody\n')
        self.assertEqual(meta["name"], "demo")
        self.assertEqual(meta["description"], "Has: a colon")
        self.assertIs(meta["flag"], True)
        self.assertEqual(meta["n"], 3)
        self.assertEqual(meta["q"], "it's")
        self.assertEqual(body, "Body\n")

    def test_inline_and_block_lists(self):
        meta, _ = self.parse('---\nglobs: ["**/*.tf", \'*.md\', plain]\nitems:\n  - a\n  - "b c"\n---\n')
        self.assertEqual(meta["globs"], ["**/*.tf", "*.md", "plain"])
        self.assertEqual(meta["items"], ["a", "b c"])

    def test_nested_map_and_block_scalars(self):
        meta, _ = self.parse(
            "---\nmetadata:\n  owner: team\n  tier: 2\nlit: |\n  line one\n  line two\n"
            "fold: >-\n  folded\n  text\nplain: starts here\n  and continues\n---\n")
        self.assertEqual(meta["metadata"], {"owner": "team", "tier": 2})
        self.assertEqual(meta["lit"], "line one\nline two")
        self.assertEqual(meta["fold"], "folded text")
        self.assertEqual(meta["plain"], "starts here and continues")

    def test_no_frontmatter(self):
        meta, body = self.parse("# Title\n")
        self.assertIsNone(meta)
        self.assertEqual(body, "# Title\n")

    def test_errors(self):
        for bad in ("---\nname: x\n", "---\nname: x\nname: y\n---\n", "---\n  indented: x\n---\n",
                    '---\nd: "open\n---\n', "---\nm: {a: 1}\n---\n", "---\nnot a pair\n---\n"):
            with self.assertRaises(sk.FrontmatterError, msg=bad):
                self.parse(bad)

    def test_patch_frontmatter_keeps_other_lines(self):
        text = "---\nname: demo\ndisable-model-invocation: false\ndescription: >\n  long\n  text\n---\nBody\n"
        out = sk.patch_frontmatter(text, {"disable-model-invocation": True}, {"user-invocable"})
        meta, body = self.parse(out)
        self.assertIs(meta["disable-model-invocation"], True)
        self.assertEqual(meta["description"], "long text")
        self.assertEqual(body, "Body\n")
        self.assertEqual(out.count("disable-model-invocation"), 1)


class TomlWriterTest(unittest.TestCase):
    BASE = '# my overrides\ntools = ["claude"]\n\n[bundles]\nvoice = true  # keep\n\n[paths]\nprojects_dir = "~/src"\n'

    def test_set_existing_key_keeps_comment(self):
        out = sk.toml_set_key(self.BASE, "bundles", "voice", False)
        self.assertIn("voice = false  # keep", out)
        self.assertIn("# my overrides", out)

    def test_insert_into_section_and_new_section(self):
        out = sk.toml_set_key(self.BASE, "bundles", "mac", False)
        self.assertEqual(sk.tomllib.loads(out)["bundles"], {"voice": True, "mac": False})
        out = sk.toml_set_key(out, "skills", "plan-files", {"invocation": "user"})
        self.assertEqual(sk.tomllib.loads(out)["skills"]["plan-files"], {"invocation": "user"})
        self.assertIn('plan-files = { invocation = "user" }', out)

    def test_remove_round_trip(self):
        out = sk.toml_set_key(self.BASE, "skills", "x", False)
        self.assertEqual(sk.toml_remove_key(out, "skills", "x"), self.BASE)
        out = sk.toml_set_key(self.BASE, "bundles", "mac", True)
        self.assertEqual(sk.toml_remove_key(out, "bundles", "mac"), self.BASE)

    def test_multiline_value_refused(self):
        text = '[skills]\nx = [\n  1,\n]\n'
        with self.assertRaises(ValueError):
            sk.toml_set_key(text, "skills", "x", True)


if __name__ == "__main__":
    unittest.main()
