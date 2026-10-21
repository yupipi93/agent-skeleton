# Bundles

A bundle is a folder under `kit/bundles/<name>/` (or `local/bundles/<name>/` for private
ones) with a `bundle.toml` and any of `skills/`, `rules/`, `hooks.toml`, `mcp.toml`,
`scripts/` and `setup.sh`. Turn one on or off with `bin/skeleton enable|disable <name>`;
see what is on with `bin/skeleton list`.

| | Bundle | Default | Skills | Rules | Hooks | Setup wizard | In one line |
|---|---|:---:|:---:|:---:|:---:|:---:|---|
| 🦴 | [core](core.md) | on | 4 | 3 | | | Safety gates, workspace guide, skill authoring, plan files, the shared script library |
| 🌿 | [git](git.md) | on | 6 | 1 | | | Worktree per write, conventional commits, PRs with a full body on GitHub or Bitbucket |
| 🎫 | [jira](jira.md) | on | 4 | 2 | 2 | `setup jira` | Jira Cloud through REST scripts: forms context, rich ADF text, safe transitions |
| 🏗️ | [terraform](terraform.md) | on | 5 | 1 | | | The agent plans, you apply: plan review, import and state, YAML settings |
| ☁️ | [gcp](gcp.md) | on | 6 | 1 | | | gcloud identity routing, IAP as the real caller, deploy checks, billing report |
| 📝 | [docs](docs.md) | on | 5 | | | | Mermaid house style, print-ready PDF, rich-paste chat messages, plan to docs |
| 🔁 | [loops](loops.md) | on | 2 | | | | Loop engineering and `/loopify` |
| 🍎 | [mac](mac.md) | on | 1 | | | | Install, check and repair the kit on macOS |
| 🎧 | [voice](voice.md) | off | 3 | 1 | 1 | `setup voice` | Spoken summaries, text notifications, the Stop hook, the local voice hub |
| 📬 | [google](google.md) | off | 3 | | | `setup google` | Google Chat, Docs and Gmail (read-only) through your own OAuth client |
| ✒️ | [style](style.md) | off | 1 | 2 | | | House style: no em dash, prose without AI-writing tells, a draft checker |

Every bundle requires `core`. Homebrew dependencies are grouped per bundle in the
[`Brewfile`](../../Brewfile); `bin/install-mac.sh` installs the groups of the enabled ones.

## Writing a bundle

The contract (`bundle.toml` fields, skill and rule frontmatter, `hooks.toml`, `mcp.toml`,
the hook script contract, script conventions) is in
[customization](../customization.md#bundle-layout). Add a page here for every new kit
bundle and a `# group: <bundle>` section to the Brewfile.
