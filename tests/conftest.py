import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

# Outside the plugin, not beside it: marketplace.json points `source` at
# ./claude, and everything under that is copied into every install.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(os.path.dirname(_HERE), "claude")
_FIXTURES = os.path.join(_HERE, "fixtures", "hook_payloads.json")

# Claude Code runs one script per event and nothing dispatches on the event
# name, so this is where the mapping lives rather than in anything that ships.
SCRIPT_FOR = {
    "SessionStart": "session_start",
    "Stop": "stop",
    "UserPromptSubmit": "user_prompt_submit",
}

# Most tests import the library directly, which is far quicker than forking a
# process. The subprocess tests remain, covering what only a real process can:
# exit codes, stdout shape, and the entry scripts hooks.json actually calls.
sys.path.insert(0, os.path.join(_ROOT, "lib"))


def script(name, suffix=".py"):
    """Path to one of the files hooks.json points at."""

    return os.path.join(_ROOT, "hooks", f"{name}{suffix}")


def config_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "memori", "config.json")


def stored():
    try:
        with open(config_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def configure(values):
    """
    Write what the configure skill would leave behind.

    Merged onto whatever is already there, so a test names only what it cares
    about. An empty value unsets, which is how a test says "never configured".
    """

    merged = {**stored(), **values}

    os.makedirs(os.path.dirname(config_path()), exist_ok=True)

    with open(config_path(), "w") as f:
        json.dump({k: v for k, v in merged.items() if v not in (None, "")}, f)


class _Recorder(BaseHTTPRequestHandler):
    def do_GET(self):
        self.__record(None)

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)

        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None

        self.__record(body)

    def __record(self, body):
        self.server.requests.append(
            {"body": body, "headers": dict(self.headers), "path": self.path}
        )

        # Keyed by endpoint: a test says what /v1/compaction answers without
        # having to spell out the query string the plugin sends it.
        endpoint = self.path.split("?")[0]
        status, response = self.server.responses.get(endpoint, (200, {}))
        payload = json.dumps(response).encode()

        self.send_response(status)
        self.send_header("content-length", str(len(payload)))
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def api(environment):
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    server.requests = []
    server.responses = {}

    threading.Thread(target=server.serve_forever, daemon=True).start()

    # After `environment`, which writes the rest of the configuration.
    configure({"api_url": f"http://127.0.0.1:{server.server_port}"})

    yield server

    server.shutdown()
    server.server_close()


CONFIGURED = {
    "api_header_name": "X-Memori-API-Key",
    "api_header_value": "test-client-key",
    "entity_id": "tester",
    "identity_id": "id_test_acme_abcdefgh",
}


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path_factory):
    # The config file lives under HOME, so a developer's own install would
    # otherwise answer for a test.
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))

    # The cache outlives a test: the module is imported once for the session.
    from memori import config

    config._loaded = None

    configure(CONFIGURED)


@pytest.fixture(scope="session")
def payloads():
    """The nine real payloads captured in the C1 observation run."""

    with open(_FIXTURES) as f:
        return json.load(f)["sequence"]


@pytest.fixture
def prompt_payload(payloads):
    return next(p for p in payloads if p["hook_event_name"] == "UserPromptSubmit")


@pytest.fixture
def recalled(api):
    def _set(*contents):
        api.responses["/v1/recall"] = (
            200,
            {
                "conversation": {"messages": []},
                "memories": [
                    {
                        "content": content,
                        "context": "some context",
                        "date": {"created": "2026-07-01T10:00:00Z"},
                    }
                    for content in contents
                ],
            },
        )

        return api

    return _set


@pytest.fixture
def stop_payload(payloads):
    return next(p for p in payloads if p["hook_event_name"] == "Stop")


@pytest.fixture
def transcript(tmp_path):
    def _write(rows, trailing=""):
        path = tmp_path / "transcript.jsonl"

        with open(path, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

            f.write(trailing)

        return str(path)

    return _write


@pytest.fixture
def run_hook():
    """
    Drive the entry point hooks.json names for this payload's event.

    `config` names the settings this test wants changed; the subprocess inherits
    HOME, so it reads the file those land in.
    """

    def _run(payload, config=None, entry=None):
        if config:
            configure(config)

        if entry is None:
            named = (
                payload.get("hook_event_name") if isinstance(payload, dict) else None
            )
            entry = script(SCRIPT_FOR.get(named, "user_prompt_submit"))

        return subprocess.run(
            [sys.executable, entry],
            capture_output=True,
            input=payload if isinstance(payload, str) else json.dumps(payload),
            text=True,
            timeout=30,
        )

    return _run


@pytest.fixture
def run_script(run_hook):
    """Drive one of the per-event entry points, as Claude Code does."""

    def _run(name, payload, config=None):
        return run_hook(payload, config=config, entry=script(name))

    return _run


# How a planted interpreter behaves. `stub` is the Microsoft Store stand-in,
# which is the reason the shim probes by running rather than by `command -v`:
# it is on PATH, it runs, and it exits 49 having done nothing.
INTERPRETERS = {
    "works": None,
    "stub": "exit 49",
    "refuses": "exit 1",
}


@pytest.fixture
def run_shim(tmp_path):
    """
    Drive hooks/python.sh over a PATH holding only what a test plants.

    Which interpreter it picks is the whole behaviour, so the real ones are kept
    out of the way: `plant` names each candidate and how it should behave, and
    anything unnamed is simply absent.
    """

    def _run(plant, args, payload=""):
        binaries = tmp_path / "bin"
        binaries.mkdir(exist_ok=True)

        for name, behaviour in plant.items():
            path = binaries / name
            body = INTERPRETERS[behaviour] or f'exec {sys.executable} "$@"'

            with open(path, "w") as f:
                f.write(f"#!/bin/sh\n{body}\n")

            os.chmod(path, 0o755)

        # Only what was planted. Leaving the real directories on PATH would let
        # the developer's own python3 answer for a test that planted none, and
        # the interesting cases are the ones where nothing usable exists. bash
        # is resolved here instead, since PATH no longer reaches it.
        return subprocess.run(
            [shutil.which("bash") or "/bin/bash", script("python", ".sh"), *args],
            capture_output=True,
            env={**os.environ, "PATH": str(binaries)},
            input=payload,
            text=True,
            timeout=30,
        )

    return _run


@pytest.fixture
def settings():
    """Resolve configuration afresh, for a test that rewrites the file."""

    from memori import config

    return config.load
