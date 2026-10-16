# Contributing to agent-skeleton

Thanks for helping. Skills, rules, scripts, renderers, docs and bug reports are all welcome.

## Ground rules

These are checked by `bin/skeleton check`, the tests or review, so they save you a round trip:

- **English everywhere** (files, comments, CLI output). Spanish exists only as a TTS
  language option.
- **No em dash (U+2014)** anywhere. Use a comma, colon, parentheses or `-`.
- **No personal or company data**: no real names, emails, domains, project ids, ticket
  keys or home paths. Use `Ana`, `you@example.com`, `example.com`, `my-project-id`,
  `PROJ-123` and `~`.
- **No secrets on argv.** Scripts read secrets from `~/.config/agent-skeleton/*.env`
  (mode 0600) or the environment, and pass them to `curl` on stdin (`curl -K -`).
  Use the helpers in `kit/bundles/core/scripts/lib/`.
- **Nothing is sent without an explicit flag or user action.** Offer `--dry-run`.
- **Standard library only.** Python >= 3.11 for `bin/skeleton`; bundle scripts should
  also run on the macOS system `python3` (3.9) when they can. No PyYAML.
- **Shell is bash 3.2 compatible** (no `mapfile`, associative arrays, `${x,,}`) and uses
  BSD-compatible flags, so it works on a stock Mac and on Linux.
- **Tests never touch the network or the real `HOME`.**

## Setup

```bash
git clone https://github.com/<you>/agent-skeleton.git && cd agent-skeleton
bin/install-mac.sh --groups core,dev     # or install python3 >= 3.11, git, curl, shellcheck yourself
bin/skeleton init
```

## The loop

```bash
git switch -c feat/my-change
# edit under kit/ (never under .claude/, .cursor/, .gemini/, .agents/: they are generated)
bin/skeleton init          # re-render
bin/skeleton check         # lint: names, frontmatter, rules, hooks, text
bin/skeleton test          # the suite, offline (about a minute)
shellcheck kit/bundles/*/scripts/*.sh bin/install-mac.sh   # if you touched shell
```

CI runs `check` and `test` on macOS and Linux for every pull request.

## Adding things

| You want to add | Do this |
|---|---|
| A skill | `bin/skeleton new-skill <bundle> <name>` (add `--user-invocable` for a slash command), then follow the `skill-authoring` skill: a trigger-rich `description` under 300 characters, `SKILL.md` under 500 lines, long material in `references/` |
| A rule | `kit/bundles/<b>/rules/<name>.md` with `description` and `apply: always\|glob\|manual` (plus `globs` for `glob`). Keep always-on rules under 2 KB |
| A hook | An entry in the bundle's `hooks.toml` and an executable in `scripts/` that follows the hook script contract in [customization](docs/customization.md#hookstoml) |
| A script | `kit/bundles/<b>/scripts/`, executable, with `--help`, exit codes documented in its header, and a test in `tests/` |
| A bundle | `kit/bundles/<name>/bundle.toml`, a `# group: <name>` section in the `Brewfile`, a page `docs/bundles/<name>.md` and a row in [docs/bundles/README.md](docs/bundles/README.md) and the README table |

Skills cite scripts by their repo-root-relative path (`kit/bundles/<b>/scripts/<x>`);
`check` warns when a cited path does not exist. When you change a renderer or a tool
mapping, update [docs/tool-support.md](docs/tool-support.md). When you make a choice the
docs do not cover, add a numbered entry to [docs/decisions.md](docs/decisions.md).

## Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/):
  `<type>(<scope>): <description>` with `feat`, `fix`, `docs`, `style`, `refactor`,
  `test`, `chore`, `build`, `ci` or `perf`. The scope is usually the bundle
  (`feat(jira): ...`) or `cli`.
- A PR body has four sections: **Summary**, **Changes**, **Validation** (what you ran)
  and **Rollback**. `kit/bundles/git/scripts/pr-github.sh --template` prints the scaffold.
- One topic per PR. Screenshots help for README or SVG changes: render them with
  `kit/bundles/docs/scripts/chrome.sh screenshot <file.svg> out.png`.

## Reporting bugs and ideas

Use the issue templates. Include `bin/skeleton doctor` output, your OS, and the tool
(Claude Code, Cursor, Gemini CLI, Antigravity) and its version. Never paste tokens or
the content of `~/.config/agent-skeleton/`. Security problems go through
[SECURITY.md](SECURITY.md), not public issues.
