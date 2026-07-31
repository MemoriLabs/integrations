"""
`--check`: what a hook would see, and whether it works.

Hooks never fail loudly, so a misconfigured plugin and a working one look
identical from inside a session.
"""

import urllib.error

import memori
from memori import api, config

HTTP_CAUSES = {
    401: "Bad identity token or client API key.",
    403: "That identity is not allowed to read here.",
    404: "No such endpoint. Is the api url a Memori server, and current?",
    429: "Over quota.",
}

# Recall is exercised for real, below, because its result is the thing people
# actually want to know. The rest are reached with a body pydantic is certain to
# refuse, which proves the route is there and the credentials were accepted
# without writing anything: validation only runs once auth has passed.
#
# Each waits as long as the hook that calls it would, so a pass here means the
# hook would have passed too. Compaction runs an LLM and is the slow one.
ENDPOINTS = (
    ("/v1/compaction", None, api.COMPACTION_TIMEOUT),
    ("/v1/conversation/turn", {}, api.TIMEOUT),
    ("/v1/augmentation", {}, api.TIMEOUT),
)


def redacted(token):
    # Enough to tell two identities apart.
    return f"{token[:12]}..." if token else "MISSING"


def print_configuration():
    rows = (
        (
            "api url",
            config.setting("api_url") or "MISSING",
            config.source("api_url"),
        ),
        (
            "entity id",
            config.setting("entity_id") or "MISSING",
            config.source("entity_id"),
        ),
        (
            "identity",
            redacted(config.setting("identity_token")),
            config.source("identity_token"),
        ),
        (
            "client key",
            "set" if config.setting("api_header_value") else "MISSING",
            config.source("api_header_value"),
        ),
    )

    print(f"Memori for Claude Code {memori.version()}")
    print("\nConfiguration a hook would see")
    for label, value, came_from in rows:
        print(f"  {label:<11} {value:<28} ({came_from})")


def print_refused():
    names = ", ".join(config.refused())

    print(f"\nIgnored from this project's .claude/settings.json: {names}")
    print("  A repository can commit that file, so it does not get to say where")
    print("  your conversation is sent or what authenticates it. Set these in")
    print("  ~/.claude/settings.json instead, or configure the plugin.")


def print_unconfigured():
    print("\nNot configured. Set MEMORI_API_URL, MEMORI_IDENTITY_TOKEN,")
    print("MEMORI_API_HEADER_VALUE and MEMORI_ENTITY_ID, in your shell or in the")
    print("env block of ~/.claude/settings.json, or configure the plugin.")


def print_empty_result():
    print("\n  Nothing came back. That is expected on a new install. If it")
    print("  persists: the identity needs read access to a memory pool that")
    print("  has something in it, and a turn has to have been captured and")
    print("  augmented before there is anything to return.")
    print("\n  Note that ~/.claude/settings.json can set MEMORI_ENTITY_ID in")
    print("  its env block, and that overrides the plugin's own setting.")


def reach(path, body, timeout):
    """Reach one endpoint without writing anything, and describe the result."""

    try:
        api.request(path, body=body, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 422:
            return "reachable, credentials accepted"

        return f"HTTP {e.code}. {HTTP_CAUSES.get(e.code, 'Unexpected response.')}"
    except Exception as e:
        return f"unreachable: {e}"

    return "OK"


def probe():
    print("\nCalling /v1/recall ...")

    try:
        data = api.post(
            "/v1/recall", {"attribution": api.attribution(), "query": "memori check"}
        )
    except urllib.error.HTTPError as e:
        cause = HTTP_CAUSES.get(e.code, "Unexpected response from the server.")
        print(f"  HTTP {e.code}. {cause}")
        return
    except Exception as e:
        print(f"  Could not reach the server: {e}")
        print("  Check the api url, and that Memori is running.")
        return

    found = len(data.get("memories") or [])
    print(f"  OK, {found} memories returned.")

    if not found:
        print_empty_result()


def probe_the_rest():
    """Recall working does not establish that capture works."""

    print("\nThe endpoints capture and compaction use ...")

    for path, body, timeout in ENDPOINTS:
        print(f"  {path:<23} {reach(path, body, timeout)}")


def main():
    config.load()

    print_configuration()

    if config.refused():
        print_refused()

    if not config.is_configured():
        print_unconfigured()
        return 0

    probe()
    probe_the_rest()

    return 0
