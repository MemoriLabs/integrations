# Memori integrations

Official Memori integrations for third-party tools. This repository is also a
Claude Code plugin marketplace.

| Integration | What it is |
|---|---|
| [claude](claude/) | Persistent memory for Claude Code. Recall before each prompt, capture after each turn. |

## Claude Code

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs \
  --config identity_token=id_your_token_here \
  --config api_header_value=your-client-key \
  --config entity_id=your-name
claude plugin enable memori@memorilabs
memori-hook --check
```

It installs **disabled**, on purpose — every prompt and reply goes to a server
the moment it is on, so turning it on should be deliberate. `--check` then
reports the configuration a hook would see and reaches every endpoint the
plugin uses, writing nothing.

**[claude/SETUP.md](claude/SETUP.md) is the full guide** —
prerequisites, configuration, per-project installs, and what to do when nothing
is being recalled or remembered.

This is a monorepo, so you can limit what lands on disk:

```bash
claude plugin marketplace add MemoriLabs/integrations \
  --sparse .claude-plugin claude
```

## Development

Python 3.12, and the same formatting the Memori backend uses — black at 88
columns, isort with the black profile.

```bash
pip install pre-commit
pre-commit install
```

Each integration owns its own tests. For the Claude Code plugin:

```bash
(cd claude && python -m pytest tests -q)

claude plugin validate .                            # the marketplace manifest
claude plugin validate claude/.claude-plugin/plugin.json
```

Run both `validate` calls from the repository root, and in that order — on a
directory `validate` takes the marketplace manifest if it finds one and stops
there, so the one-argument form never checks `plugin.json`.

## Releasing

An installed plugin is pinned to the `version` in its `plugin.json`, and the
cached copy is what runs. **A change that does not bump the version never
reaches anyone.** So a release is:

1. Bump `version` in the integration's `plugin.json`.
2. Bump the matching `version` in `.claude-plugin/marketplace.json`.
3. Add a `CHANGELOG.md` entry under the new version.
4. Tag it:

```bash
claude plugin tag claude --push
```

`claude plugin tag` creates a `memori--v<version>` tag and refuses to run if
`plugin.json` and the marketplace entry disagree, which is what keeps steps 1
and 2 honest.

## License

MIT. See [LICENSE](LICENSE).
