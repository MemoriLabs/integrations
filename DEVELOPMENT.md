# Development

## Setup

Python 3.12 to develop and run the tests. The plugin itself runs on 3.9 and up,
which is what `claude/hooks/python.sh` gates on, because that is what macOS
ships and stranding it would break the default install.

```bash
pip install pre-commit
pre-commit install
```

Formatting is black at 88 columns and isort with the black profile, matching the
Memori backend.

## Tests

```bash
python -m pytest tests -q
```

They live at the repository root rather than inside an integration, because
everything under `claude/` is copied into every install.

## Running a development build

**Installing copies the plugin**, into
`~/.claude/plugins/cache/memorilabs/memori/<version>/`, and that copy is what
runs. Editing a checkout changes nothing until the version is bumped.

If you added the marketplace from a local path rather than from GitHub, the entry
keeps that path, so moving the directory breaks the plugin with `cache-miss` and
the marketplace has to be re-added.

To point a development install somewhere other than production, edit
`~/.claude/memori/config.json`. The hooks read it once per run, so a change takes
effect on the next prompt.

```json
{
  "api_url": "http://localhost:8000",
  "application_env": "local",
  "entity_id": "…",
  "identity_token": "id_…",
  "debug": true
}
```

`application_env` is `production`, `staging` or `local`, and supplies the client
API key. Anything else leaves the plugin with no key, and nothing is remembered.
`api_header_value` overrides it, and is only set by hand on a deployment carrying
its own key. `debug` writes each hook's outcome to stderr. None of these are
documented client-side: a client on production never touches them.

## Validating the manifests

Run both from the repository root, in this order:

```bash
claude plugin validate .                            # the marketplace manifest
claude plugin validate claude/.claude-plugin/plugin.json
```

On a directory `validate` takes the marketplace manifest if it finds one and
stops there, so the one-argument form never checks `plugin.json`.

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
