"""
Memori for Claude Code.

The version lives in the manifest and nowhere else. Claude Code pins an install
to that string, so reading it back from there is the only way to be sure which
build is answering -- a directory-source marketplace reads the plugin off disk,
so an edited working copy is not necessarily the version it claims to be.
"""

import json
import os

MANIFEST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".claude-plugin",
    "plugin.json",
)


def version():
    try:
        with open(MANIFEST) as f:
            return json.load(f)["version"]
    except Exception:
        return "unknown"
