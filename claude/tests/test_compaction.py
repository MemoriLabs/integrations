import json

import pytest

COMPACTION = {
    "continuation": {
        "last_action": "wired the Stop hook",
        "next_expected_action": "run the suite",
    },
    "environment": ["backend runs on port 8000"],
    "messages": [{"content": "raw turn text", "role": "user", "type": "text"}],
    "metadata": {"date": {"execution": "2026-07-28T23:00:00"}},
    "standing_orders": ["never commit"],
    "state": {
        "active_tasks": ["wire compaction"],
        "open_loops": ["decide on tool inputs"],
        "pending_results": ["the live smoke test"],
    },
    "timeline": "started on C4, moved to packaging",
    "workspace_changes": ["integrations/claude/bin/memori-hook"],
}


@pytest.fixture
def compacted(api):
    """Serves the default compaction; call it to serve a different one."""

    def _set(response=COMPACTION):
        api.responses["/v1/compaction"] = (200, response)

        return api

    _set()

    return _set


@pytest.fixture
def run_compact(run_hook, payloads):
    session_start = next(
        payload for payload in payloads if payload["hook_event_name"] == "SessionStart"
    )

    def _run(source="compact", env=None):
        return run_hook({**session_start, "source": source}, env=env)

    return _run


def context_of(result):
    assert result.returncode == 0, result.stderr

    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_injects_the_compaction_after_a_compact(compacted, run_compact):
    context = context_of(run_compact())

    assert context.startswith("<memori_compaction>")
    assert context.endswith("</memori_compaction>")


def test_asks_the_server_rather_than_keeping_local_state(compacted, run_compact):
    api = compacted()

    run_compact()

    assert [request["path"] for request in api.requests] == ["/v1/compaction"]
    assert api.requests[0]["headers"]["Authorization"] == "Bearer id_test_acme_abcdefgh"
    assert api.requests[0]["headers"]["X-Memori-Api-Key"] == "test-client-key"


def test_renders_every_section(compacted, run_compact):
    context = context_of(run_compact())

    assert "Standing orders:\n- never commit" in context
    assert "Environment:\n- backend runs on port 8000" in context
    assert "Active tasks:\n- wire compaction" in context
    assert "Open loops:\n- decide on tool inputs" in context
    assert "Pending results:\n- the live smoke test" in context
    assert "Workspace changes:\n- integrations/claude/bin/memori-hook" in context
    assert "Timeline:\nstarted on C4, moved to packaging" in context
    assert "Last action: wired the Stop hook" in context
    assert "Next expected action: run the suite" in context


def test_drops_the_raw_messages(compacted, run_compact):
    # Claude Code's own compact summary already covers the conversation.
    assert "raw turn text" not in context_of(run_compact())


def test_skips_empty_sections(compacted, run_compact):
    compacted({**COMPACTION, "environment": [], "standing_orders": [""]})

    context = context_of(run_compact())

    assert "Environment" not in context
    assert "Standing orders" not in context
    assert "Active tasks" in context


def test_an_empty_compaction_injects_nothing(compacted, run_compact):
    compacted(
        {
            "continuation": {"last_action": "", "next_expected_action": ""},
            "environment": [],
            "standing_orders": [],
            "state": {"active_tasks": [], "open_loops": [], "pending_results": []},
            "timeline": "",
            "workspace_changes": [],
        }
    )

    result = run_compact()

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("source", ["startup", "resume", "clear"])
def test_other_session_starts_do_nothing(compacted, run_compact, source):
    api = compacted()

    result = run_compact(source=source)

    assert result.returncode == 0
    assert result.stdout == ""
    assert api.requests == []


def test_survives_the_no_session_500(api, run_compact):
    # Compaction.generate() returns None when there is no live session, and the
    # route declares a non-Optional response_model, so the caller gets a 500.
    api.responses["/v1/compaction"] = (500, {"detail": "Sorry, something went wrong"})

    result = run_compact()

    assert result.returncode == 0
    assert result.stdout == ""


def test_survives_a_dead_server(run_compact):
    result = run_compact(env={"MEMORI_API_URL": "http://127.0.0.1:1"})

    assert result.returncode == 0
    assert result.stdout == ""


def test_survives_missing_credentials(api, run_compact):
    result = run_compact(env={"MEMORI_IDENTITY_TOKEN": ""})

    assert result.returncode == 0
    assert api.requests == []
