import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HOOK = os.path.join(_ROOT, "bin", "memori-hook")
_FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "hook_payloads.json")

# Most tests import the library directly, which is far quicker than forking a
# process. The subprocess tests remain, covering what only the real binary can:
# exit codes, stdout shape, and the entry scripts hooks.json actually calls.
sys.path.insert(0, os.path.join(_ROOT, "lib"))


def script(name, suffix=".py"):
    """Path to one of the files hooks.json points at."""

    return os.path.join(_ROOT, "hooks", f"{name}{suffix}")


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

        status, response = self.server.responses.get(self.path, (200, {}))
        payload = json.dumps(response).encode()

        self.send_response(status)
        self.send_header("content-length", str(len(payload)))
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def api(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    server.requests = []
    server.responses = {}

    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("MEMORI_API_URL", f"http://127.0.0.1:{server.server_port}")

    yield server

    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path_factory):
    for key in list(os.environ):
        if key.startswith("MEMORI_") or key.startswith("CLAUDE_PLUGIN_OPTION_"):
            monkeypatch.delenv(key, raising=False)

    # Configuration is resolved partly from settings files, so tests must not see
    # the developer's own. Point HOME and the project root somewhere empty; tests
    # that need a settings file write one there themselves.
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path_factory.mktemp("project")))

    monkeypatch.setenv("MEMORI_API_HEADER_NAME", "X-Memori-API-Key")
    monkeypatch.setenv("MEMORI_API_HEADER_VALUE", "test-client-key")
    monkeypatch.setenv("MEMORI_ENTITY_ID", "tester")
    monkeypatch.setenv("MEMORI_IDENTITY_TOKEN", "id_test_acme_abcdefgh")


@pytest.fixture(scope="session")
def payloads():
    """The nine real payloads captured in the C1 observation run."""

    with open(_FIXTURES) as f:
        return json.load(f)["sequence"]


@pytest.fixture
def prompt_payload(payloads):
    return next(p for p in payloads if p["hook_event_name"] == "UserPromptSubmit")


@pytest.fixture
def project_settings(monkeypatch, tmp_path):
    """Write the .claude/settings.json a cloned repository could have committed."""

    def _write(env):
        root = tmp_path / "workspace"
        (root / ".claude").mkdir(parents=True, exist_ok=True)

        with open(root / ".claude" / "settings.json", "w") as f:
            json.dump({"env": env}, f)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))

        # Claude Code merges that block into every hook process before the hook
        # gets a say. Reproducing it is the whole point of these tests.
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        return str(root)

    return _write


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
    def _run(payload, env=None, args=(), entry=_HOOK):
        environment = dict(os.environ)
        environment.update(env or {})

        return subprocess.run(
            [sys.executable, entry, *args],
            capture_output=True,
            env=environment,
            input=payload if isinstance(payload, str) else json.dumps(payload),
            text=True,
            timeout=30,
        )

    return _run


@pytest.fixture
def run_script(run_hook):
    """Drive one of the per-event entry points, as Claude Code does."""

    def _run(name, payload, env=None):
        return run_hook(payload, env=env, entry=script(name))

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
def settings(monkeypatch):
    """Resolve configuration afresh; the library caches it per process."""

    from memori import config

    config.load()

    yield config.load

    config.load()


@pytest.fixture
def run_check(run_hook):
    def _run(env=None):
        return run_hook("", env=env, args=["--check"])

    return _run
