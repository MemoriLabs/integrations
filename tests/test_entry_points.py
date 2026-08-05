"""
The scripts hooks.json points at.

These are what Claude Code actually executes, so they get their own coverage:
each must handle only its own event, survive a payload it was not built for, and
never exit non-zero. The wiring that reaches them is in test_manifests.py.
"""

import json

import pytest

SCRIPTS = ("session_start", "stop", "user_prompt_submit")


def test_user_prompt_submit_injects(recalled, run_script, prompt_payload):
    recalled("Ryan prefers tabs")

    result = run_script("user_prompt_submit", prompt_payload)

    assert result.returncode == 0
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "- Ryan prefers tabs" in context


def test_stop_captures_and_injects_nothing(api, run_script, stop_payload, transcript):
    rows = [
        {
            "type": "user",
            "promptId": "p1",
            "message": {"content": [{"type": "text", "text": "remember this"}]},
        }
    ]
    payload = {
        **stop_payload,
        "prompt_id": "p1",
        "transcript_path": transcript(rows),
        "last_assistant_message": "Noted.",
    }

    result = run_script("stop", payload)

    assert result.returncode == 0
    assert result.stdout == ""
    assert [r["path"] for r in api.requests] == [
        "/v1/conversation/turn",
        "/v1/augmentation",
    ]


def test_session_start_only_acts_on_a_compaction(api, run_script, payloads):
    start = next(p for p in payloads if p["hook_event_name"] == "SessionStart")
    api.responses["/v1/compaction"] = (200, {"standing_orders": ["never commit"]})

    quiet = run_script("session_start", {**start, "source": "startup"})
    assert quiet.stdout == ""
    assert api.requests == []

    compacted = run_script("session_start", {**start, "source": "compact"})
    assert "never commit" in compacted.stdout


@pytest.mark.parametrize("name", SCRIPTS)
def test_a_script_ignores_an_event_it_does_not_own(api, run_script, name, payloads):
    # hooks.json should never send the wrong event, but a script must not act on
    # one if it does.
    others = [p for p in payloads if p["hook_event_name"] == "SessionEnd"]

    for payload in others:
        result = run_script(name, payload)
        assert result.returncode == 0


@pytest.mark.parametrize("name", SCRIPTS)
def test_a_script_survives_rubbish_on_stdin(run_script, name):
    for rubbish in ("", "not json", "[1, 2, 3]"):
        assert run_script(name, rubbish).returncode == 0


@pytest.mark.parametrize("name", SCRIPTS)
def test_a_script_survives_a_dead_server(run_script, name, payloads):
    for payload in payloads:
        result = run_script(name, payload, config={"api_url": "http://127.0.0.1:1"})
        assert result.returncode == 0
