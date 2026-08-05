# Memori integrations

Official Memori integrations for third-party tools. This repository is also a
Claude Code plugin marketplace.

| Integration | What it is |
|---|---|
| [claude](claude/) | Persistent memory for Claude Code. Recall before each prompt, capture after each turn. |

## Claude Code

Using the desktop app? Follow the
**[Claude Code Desktop steps](claude/INSTALL.md#install-in-claude-code-desktop)**.

From the command line:

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs
claude plugin enable memori@memorilabs
```

Then start a session and run `/memori:configure`, which asks for your API URL,
identity token and entity ID and saves them to `~/.claude/memori/config.json`.

It installs **disabled**, and nothing is sent until it is both enabled and
configured.

See **[claude/](claude/)** for the configuration options, what gets sent, what it
keeps on disk, and how to check it is working. The
**[quickstart](claude/INSTALL.md)** has the required values and the steps.

This is a monorepo, so you can limit what lands on disk:

```bash
claude plugin marketplace add MemoriLabs/integrations \
  --sparse .claude-plugin claude
```

## Development

Python 3.12 to develop and run the tests. The plugin itself runs on 3.9 and up,
which is what `claude/hooks/python.sh` gates on, because that is what macOS
ships and stranding it would break the default install.

Formatting is black at 88 columns and isort with the black profile, matching the
Memori backend.

**Installing copies the plugin**, into
`~/.claude/plugins/cache/memorilabs/memori/<version>/`, and that copy is what
runs. Editing a checkout changes nothing until the version is bumped. If you
added the marketplace from a local path rather than from GitHub, the entry keeps
that path, so moving the directory breaks the plugin with `cache-miss` and the
marketplace has to be re-added.

```bash
pip install pre-commit
pre-commit install
```

Every setting lives in `~/.claude/memori/config.json` and nowhere else — no
environment variable, and nothing a workspace can reach. To point a development
install at a local server, edit that file:

```json
{
  "api_url": "http://localhost:8000",
  "application_env": "local",
  "entity_id": "…",
  "identity_token": "id_…"
}
```

The hooks read it once per run, so a change takes effect on the next prompt.

Tests live at the repository root rather than inside an integration, because
everything under `claude/` is copied into every install.

```bash
python -m pytest tests -q

claude plugin validate .                            # the marketplace manifest
claude plugin validate claude/.claude-plugin/plugin.json
```

Run both `validate` calls from the repository root, and in that order. On a
directory `validate` takes the marketplace manifest if it finds one and stops
there, so the one-argument form never checks `plugin.json`.

## Releasing

An installed plugin is pinned to the `version` in its `plugin.json`, and the
cached copy is what runs. **A change that does not bump the version never
reaches anyone.** So a release is:

1. Bump `version` in the integration's `plugin.json`.
2. Bump the matching `version` in `.claude-plugin/marketplace.json`.
3. Bump the `version` frontmatter in each `claude/skills/*/SKILL.md`.
4. Tag it:

```bash
claude plugin tag claude --push
```

`claude plugin tag` creates a `memori--v<version>` tag and refuses to run if
`plugin.json` and the marketplace entry disagree, which is what keeps steps 1
and 2 honest. Step 3 is kept honest by the test suite, not by the tagger, so run
the tests before tagging.

## License

MIT. See [LICENSE](LICENSE).
