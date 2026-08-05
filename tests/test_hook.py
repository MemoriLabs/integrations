import json


def context_of(result):
    assert result.returncode == 0, result.stderr
    if not result.stdout:
        return None

    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_injects_recalled_memories(recalled, run_hook, prompt_payload):
    recalled("Ryan prefers Python over Java")

    context = context_of(run_hook(prompt_payload))

    assert context.startswith("<memori_context>")
    assert (
        "- Ryan prefers Python over Java "
        "(context: some context; recorded 2026-07-01)" in context
    )
    assert context.endswith("</memori_context>")


def test_output_nests_additional_context(recalled, run_hook, prompt_payload):
    recalled("Ryan prefers Python over Java")

    output = json.loads(run_hook(prompt_payload).stdout)

    # At the top level Claude Code silently ignores it.
    assert set(output) == {"hookSpecificOutput"}
    assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"


def test_queries_with_the_prompt_field(recalled, run_hook, prompt_payload):
    api = recalled("Ryan prefers Python over Java")

    run_hook(prompt_payload)

    # The reference documents user_prompt; this build sends prompt.
    assert prompt_payload["prompt"] == "What does greet.py do?"
    assert api.requests[0]["body"]["query"] == "What does greet.py do?"


def test_sends_attribution_and_both_auth_headers(recalled, run_hook, prompt_payload):
    api = recalled("Ryan prefers Python over Java")

    run_hook(prompt_payload)

    request = api.requests[0]
    assert request["path"] == "/v1/recall"
    assert request["body"]["attribution"] == {"entity": {"id": "tester"}}
    assert request["headers"]["Authorization"] == "Bearer id_test_acme_abcdefgh"
    assert request["headers"]["X-Memori-Api-Key"] == "test-client-key"


def test_renders_every_memory(recalled, run_hook, prompt_payload):
    recalled("first fact", "second fact")

    context = context_of(run_hook(prompt_payload))

    assert "- first fact (context: some context; recorded 2026-07-01)" in context
    assert "- second fact (context: some context; recorded 2026-07-01)" in context


def test_empty_recall_injects_nothing(api, run_hook, prompt_payload):
    api.responses["/v1/recall"] = (
        200,
        {"conversation": {"messages": []}, "memories": []},
    )

    result = run_hook(prompt_payload)

    assert result.returncode == 0
    assert result.stdout == ""


def test_ignores_unhandled_events(api, run_hook, payloads):
    handled = ("SessionStart", "Stop", "UserPromptSubmit")

    for payload in payloads:
        if payload["hook_event_name"] in handled:
            continue

        result = run_hook(payload)

        assert result.returncode == 0, payload["hook_event_name"]
        assert result.stdout == "", payload["hook_event_name"]

    assert api.requests == []


def test_survives_a_dead_server(run_hook, prompt_payload):
    result = run_hook(prompt_payload, config={"api_url": "http://127.0.0.1:1"})

    assert result.returncode == 0
    assert result.stdout == ""


def test_a_refused_recall_injects_nothing(api, run_hook, prompt_payload):
    # What recall returned is the only thing this plugin ever puts in the
    # context. A failure reaches stderr and goes no further, however permanent.
    api.responses["/v1/recall"] = (401, {"detail": "Unauthorized"})

    result = run_hook(prompt_payload)

    assert result.returncode == 0
    assert result.stdout == ""


def test_survives_missing_credentials(api, run_hook, prompt_payload):
    result = run_hook(prompt_payload, config={"identity_token": ""})

    assert result.returncode == 0
    assert result.stdout == ""
    assert api.requests == []


def test_survives_malformed_stdin(run_hook):
    assert run_hook("this is not json").returncode == 0


def test_survives_empty_stdin(run_hook):
    assert run_hook("").returncode == 0


def test_survives_a_non_object_payload(run_hook):
    assert run_hook("[1, 2, 3]").returncode == 0


def test_blank_prompt_is_not_recalled(api, run_hook, prompt_payload):
    result = run_hook({**prompt_payload, "prompt": "   "})

    assert result.returncode == 0
    assert result.stdout == ""
    assert api.requests == []


def test_falls_back_to_the_user_prompt_field(recalled, run_hook, prompt_payload):
    api = recalled("Ryan prefers Python over Java")

    payload = {k: v for k, v in prompt_payload.items() if k != "prompt"}
    payload["user_prompt"] = "legacy field"

    assert context_of(run_hook(payload)) is not None
    assert api.requests[0]["body"]["query"] == "legacy field"


def test_memory_without_a_date_still_renders(api, run_hook, prompt_payload):
    api.responses["/v1/recall"] = (
        200,
        {"conversation": {"messages": []}, "memories": [{"content": "undated fact"}]},
    )

    context = context_of(run_hook(prompt_payload))

    assert "- undated fact\n" in context
    assert "recorded" not in context


# +--- what a hook says out loud ---+


def test_an_unauthorized_hook_warns_even_with_debug_off(api, run_hook, prompt_payload):
    # A 401 never fixes itself, so it must not be silent the way a timeout can be.
    api.responses["/v1/recall"] = (401, {"detail": "Unauthorized"})

    result = run_hook(prompt_payload)

    assert result.returncode == 0
    assert "HTTP 401" in result.stderr
    assert "config.json" in result.stderr


def test_an_unreadable_config_warns_even_with_debug_off(api, run_hook, prompt_payload):
    # Nothing else would say so: the hooks go quiet, and the log that explains
    # why needs the debug setting out of the file it cannot read.
    from conftest import config_path

    with open(config_path(), "w") as f:
        f.write("{ not json")

    result = run_hook(prompt_payload)

    assert result.returncode == 0
    assert result.stdout == ""
    assert "could not be read" in result.stderr
    assert api.requests == []


def test_never_configured_stays_quiet(api, run_hook, prompt_payload):
    # The other half: an install nobody has set up yet is not a fault.
    import os

    from conftest import config_path

    os.remove(config_path())

    result = run_hook(prompt_payload)

    assert result.returncode == 0
    assert result.stderr == ""
    assert api.requests == []


def test_other_failures_stay_quiet_with_debug_off(run_hook, prompt_payload):
    result = run_hook(prompt_payload, config={"api_url": "http://127.0.0.1:1"})

    assert result.returncode == 0
    assert result.stderr == ""
