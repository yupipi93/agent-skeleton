# Documentation

Start with [getting started](getting-started.md), then pick what you need.

## Guides

| Page | Read it when |
|---|---|
| [Getting started](getting-started.md) | Installing, rendering the workspace, the everyday commands |
| [Customization](customization.md) | Changing anything: `skeleton.local.toml`, private bundles, the bundle, rule, hook and MCP contracts |
| [Architecture](architecture.md) | You want to know how `bin/skeleton init` loads, resolves, plans and applies |
| [Tool support](tool-support.md) | What is generated for Claude Code, Cursor, Gemini CLI and Antigravity, and each tool's quirks |
| [Decisions](decisions.md) | Why something works the way it does (numbered records, newest last) |

## Bundles

One page per bundle, with its skills, rules, hooks, scripts, configuration and
dependencies: [bundles index](bundles/README.md).

| | Bundle | | Bundle |
|---|---|---|---|
| 🦴 | [core](bundles/core.md) | 📝 | [docs](bundles/docs.md) |
| 🌿 | [git](bundles/git.md) | 🔁 | [loops](bundles/loops.md) |
| 🎫 | [jira](bundles/jira.md) | 🍎 | [mac](bundles/mac.md) |
| 🏗️ | [terraform](bundles/terraform.md) | 🎧 | [voice](bundles/voice.md) |
| ☁️ | [gcp](bundles/gcp.md) | 📬 | [google](bundles/google.md) |
| ✒️ | [style](bundles/style.md) | | |

## Tools

Standalone tools that bundles drive:

| Tool | Used by | Page |
|---|---|---|
| `tools/billing-exec-report` | gcp (`gcp-billing-report`) | [README](../tools/billing-exec-report/README.md) |
| `tools/voice-hub` | voice (`voice-hub`) | [README](../tools/voice-hub/README.md) |

## Images

The README images live in [`assets/`](assets/). They are hand-written SVG on an opaque
card, so they read the same in GitHub's light and dark themes; `social-preview.png` is
rendered from `social-preview.svg` with headless Chrome:

```bash
kit/bundles/docs/scripts/chrome.sh screenshot docs/assets/social-preview.svg docs/assets/social-preview.png 1280,640
```

## Project files

[Contributing](../CONTRIBUTING.md), [security policy](../SECURITY.md),
[license](../LICENSE), and the shared agent entrypoint [AGENTS.md](../AGENTS.md).
