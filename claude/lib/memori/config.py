"""
Where every setting comes from, resolved once.

One file, ~/.claude/memori/config.json, written by the configure skill. Nothing
else is a source: no environment variable, and nothing a workspace can reach.
"""

import json
import os

CONFIG = "~/.claude/memori/config.json"

DEFAULTS = {
    "api_header_name": "X-Memori-API-Key",
    "api_header_value": None,
    "api_url": None,
    "application_env": "production",
    "debug": "false",
    "entity_id": None,
    "identity_token": None,
}

API_KEYS = {
    "local": "local-sdk-key",
    "production": "96a7ea3e-11c2-428c-b9ae-5a168363dc80",
    "staging": "c18b1022-7fe2-42af-ab01-b1f9139184f0",
}

REQUIRED = ("api_header_value", "api_url", "entity_id", "identity_token")

FALSE = ("", "0", "false", "no", "off")

_loaded = None
_unreadable = False


def path():
    return os.path.expanduser(CONFIG)


def stored():
    """
    What the configure skill wrote, or {} where it has not run.

    A file that is absent and a file that is unusable both leave the plugin
    unconfigured, but only one of them is a mistake, so they are told apart here
    and `unreadable()` reports the difference.
    """

    global _unreadable

    _unreadable = False

    if not os.path.exists(path()):
        return {}

    try:
        with open(path()) as f:
            found = json.load(f)
    except Exception:
        _unreadable = True
        return {}

    if not isinstance(found, dict):
        _unreadable = True
        return {}

    return found


def load():
    """Every setting as {name: value}. Cached; call load() again to redo."""

    global _loaded

    configured = stored()
    resolved = {
        name: configured.get(name) or default for name, default in DEFAULTS.items()
    }

    # An explicit key still wins: a deployment on its own host has one no
    # environment here names.
    if not resolved["api_header_value"]:
        named = str(resolved["application_env"]).strip().lower()
        resolved["api_header_value"] = API_KEYS.get(named)

    _loaded = resolved

    return resolved


def setting(name):
    if _loaded is None:
        load()

    return _loaded[name]


def environment():
    """The environment named, however it was capitalised or spaced."""

    return str(setting("application_env")).strip().lower()


def unknown_environment():
    """The environment named, if it is not one there is a client key for."""

    named = environment()

    return None if named in API_KEYS else named


def unreadable():
    """Whether a config file is there but cannot be used."""

    if _loaded is None:
        load()

    return _unreadable


def is_configured():
    return all(setting(name) for name in REQUIRED)


def debug():
    # JSON gives a real boolean, but a hand-edited file may give the string
    # "false", which is truthy.
    return str(setting("debug")).strip().lower() not in FALSE
