import json

import pytest

PROMPT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PROMPT_ID = "22222222-2222-2222-2222-222222222222"

CALL = {
    "type": "tool_use",
    "id": "call_1",
    "name": "Bash",
    "input": {"command": "cat .env"},
}
RESULT = {
    "type": "tool_result",
    "tool_use_id": "call_1",
    "content": "OPENAI_API_KEY=sk-secret",
}
REPLY = f"they seem to be in a hurry\nNoted.\n{json.dumps(CALL)}"


def assistant(*blocks, model="claude-opus-5"):
    return {"type": "assistant", "message": {"content": list(blocks), "model": model}}


def user(*blocks, prompt_id=PROMPT_ID, **extra):
    return {
        "type": "user",
        "promptId": prompt_id,
        "message": {"content": list(blocks)},
        **extra,
    }


def text(value):
    return {"type": "text", "text": value}


def turn(prompt_id=PROMPT_ID, prompt="remember that I prefer tabs"):
    """One realistic turn: prompt, thinking, reply, tool call, tool result."""

    return [
        user(text(prompt), prompt_id=prompt_id),
        assistant(
            {"type": "thinking", "thinking": "they seem to be in a hurry"},
            text("Noted."),
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "Bash",
                "input": {"command": "cat .env"},
            },
        ),
        user(
            {
                "type": "tool_result",
                "tool_use_id": "call_1",
                "content": "OPENAI_API_KEY=sk-secret",
            },
            prompt_id=prompt_id,
        ),
        assistant(text("Done.")),
    ]


@pytest.fixture
def run_stop(run_hook, stop_payload):
    def _run(
        path,
        prompt_id=PROMPT_ID,
        config=None,
        last_assistant_message="",
        stop_hook_active=False,
    ):
        payload = {
            **stop_payload,
            "last_assistant_message": last_assistant_message,
            "prompt_id": prompt_id,
            "stop_hook_active": stop_hook_active,
            "transcript_path": path,
        }

        return run_hook(payload, config=config)

    return _run


def bodies(api):
    return {request["path"]: request["body"] for request in api.requests}


def contents(api):
    conversation = bodies(api)["/v1/augmentation"]["conversation"]

    return [message["content"] for message in conversation["messages"]]


def test_posts_the_turn_before_the_augmentation(api, run_stop, transcript):
    run_stop(transcript(turn()))

    # The server may read the turn from either call, so it is written before the
    # augmentation is queued.
    assert [request["path"] for request in api.requests] == [
        "/v1/conversation/turn",
        "/v1/augmentation",
    ]


def test_both_calls_carry_the_same_conversation(api, run_stop, transcript):
    run_stop(transcript(turn()))

    # Both endpoints take the same fields now, so both get the same object.
    sent = bodies(api)

    assert (
        sent["/v1/conversation/turn"]["messages"]
        == sent["/v1/augmentation"]["conversation"]["messages"]
    )


def test_every_message_is_typed_by_its_blocks(api, run_stop, transcript):
    # type is nullable inbound but GET /v1/compaction requires a string coming
    # back out, so a null here 500s compaction later.
    run_stop(transcript(turn()))

    messages = bodies(api)["/v1/conversation/turn"]["messages"]

    assert all(message["type"] for message in messages)
    assert [message["type"] for message in messages] == [
        "text",
        "assistant",
        "tool_result",
        "text",
    ]


def test_the_trace_carries_the_arguments_and_the_result(api, run_stop, transcript):
    run_stop(transcript(turn()))

    messages = bodies(api)["/v1/conversation/turn"]["messages"]
    traced = [message for message in messages if message.get("trace")]

    assert [tool for message in traced for tool in message["trace"]["tools"]] == [
        {
            "name": "Bash",
            "args": {"command": "cat .env"},
            "result": "OPENAI_API_KEY=sk-secret",
        }
    ]


def test_untraced_messages_stay_untraced(api, run_stop, transcript):
    run_stop(transcript(turn()))

    messages = bodies(api)["/v1/conversation/turn"]["messages"]

    assert [bool(message.get("trace")) for message in messages] == [
        False,
        True,
        False,
        False,
    ]


def test_keeps_the_prompt_and_the_reply(api, run_stop, transcript):
    run_stop(transcript(turn()))

    assert contents(api) == [
        "remember that I prefer tabs",
        REPLY,
        json.dumps(RESULT),
        "Done.",
    ]


def test_roles_come_from_the_row_type(api, run_stop, transcript):
    run_stop(transcript(turn()))

    messages = bodies(api)["/v1/conversation/turn"]["messages"]
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_appends_the_reply_the_transcript_has_not_flushed_yet(
    api, run_stop, transcript
):
    # Stop fires before Claude Code writes the closing assistant rows, so a real
    # turn's transcript usually ends at the user's prompt.
    rows = [user(text("remember that I prefer tabs"))]

    run_stop(transcript(rows), last_assistant_message="Noted, I'll remember that.")

    assert contents(api) == [
        "remember that I prefer tabs",
        "Noted, I'll remember that.",
    ]


def test_does_not_duplicate_a_reply_already_in_the_transcript(
    api, run_stop, transcript
):
    rows = [user(text("hello")), assistant(text("Noted."))]

    run_stop(transcript(rows), last_assistant_message="Noted.")

    assert contents(api) == ["hello", "Noted."]


def test_reads_string_shaped_content(api, run_stop, transcript):
    rows = [
        {"type": "user", "promptId": PROMPT_ID, "message": {"content": "plain string"}},
        assistant(text("ok")),
    ]

    run_stop(transcript(rows))

    assert contents(api) == ["plain string", "ok"]


def test_sends_only_the_current_turn(api, run_stop, transcript):
    run_stop(transcript(turn(OTHER_PROMPT_ID, "an earlier prompt") + turn()))

    assert "an earlier prompt" not in contents(api)
    assert "remember that I prefer tabs" in contents(api)


def test_a_turn_that_arrives_while_capturing_is_left_alone(api, run_stop, transcript):
    # The half the test above missed. Capture runs async, so the next prompt can
    # be written to the transcript before this hook has finished reading it --
    # and only a later turn exercises the closing edge of the window.
    run_stop(transcript(turn() + turn(OTHER_PROMPT_ID, "a later prompt")))

    assert "a later prompt" not in contents(api)
    assert "remember that I prefer tabs" in contents(api)


def test_sends_claude_codes_own_text_too(api, run_stop, transcript):
    rows = [
        user(text("the real prompt")),
        user(text("subagent chatter"), isSidechain=True),
        user(text("system injected"), isMeta=True),
        user(text("previous summary"), isCompactSummary=True),
        assistant(text("ok")),
    ]

    run_stop(transcript(rows))

    assert contents(api) == [
        "the real prompt",
        "subagent chatter",
        "system injected",
        "previous summary",
        "ok",
    ]


def test_sends_non_conversation_rows_as_the_rows_they_are(api, run_stop, transcript):
    rows = [
        user(text("the real prompt")),
        {"type": "ai-title", "title": "a title"},
        {"type": "queue-operation", "operation": "enqueue"},
        {"type": "attachment", "content": "attached"},
        {"type": "file-history-snapshot", "snapshot": {}},
        {"type": "last-prompt", "prompt": "the real prompt"},
        {"type": "system", "subtype": "stop_hook_summary", "content": "summary"},
        assistant(text("ok")),
    ]

    run_stop(transcript(rows))

    sent = bodies(api)["/v1/conversation/turn"]["messages"]

    assert [message["role"] for message in sent] == [
        "user",
        "ai-title",
        "queue-operation",
        "attachment",
        "file-history-snapshot",
        "last-prompt",
        "system",
        "assistant",
    ]
    # A row with no message of its own arrives as the row it was written as.
    assert '"operation": "enqueue"' in sent[2]["content"]
    assert sent[2]["type"] == "queue-operation"


def test_sends_attribution_and_the_model(api, run_stop, transcript):
    run_stop(transcript(turn()))

    attribution = {"entity": {"id": "tester"}}
    assert bodies(api)["/v1/conversation/turn"]["attribution"] == attribution
    assert bodies(api)["/v1/augmentation"]["meta"] == {
        "attribution": attribution,
        "llm": {"model": {"provider": "anthropic", "version": "claude-opus-5"}},
        "platform": {"provider": "claude-code"},
    }


def test_both_capture_calls_carry_the_session(api, run_stop, transcript):
    run_stop(transcript(turn()))

    session = {"id": "81de4338-5955-44a0-80f2-4a3448da8859"}
    assert bodies(api)["/v1/conversation/turn"]["session"] == session
    assert bodies(api)["/v1/augmentation"]["session"] == session


def test_sends_both_auth_headers(api, run_stop, transcript):
    run_stop(transcript(turn()))

    for request in api.requests:
        assert request["headers"]["Authorization"] == "Bearer id_test_acme_abcdefgh"
        assert request["headers"]["X-Memori-Api-Key"] == "test-client-key"


def test_injects_nothing(api, run_stop, transcript):
    result = run_stop(transcript(turn()))

    assert result.returncode == 0
    assert result.stdout == ""


def test_an_unknown_prompt_id_sends_nothing(api, run_stop, transcript):
    result = run_stop(transcript(turn()), prompt_id="no-such-prompt")

    assert result.returncode == 0
    assert api.requests == []


def test_a_turn_held_open_by_another_stop_hook_is_not_captured(
    api, run_stop, transcript
):
    # Stop fires again when that hook finally lets go, carrying the whole turn.
    # Capturing now would send the first half of it twice.
    rows = [
        {
            "type": "user",
            "promptId": "p1",
            "message": {"content": [{"type": "text", "text": "hello"}]},
        }
    ]

    run_stop(transcript(rows), "p1", stop_hook_active=True)

    assert api.requests == []


def test_a_stop_with_no_prompt_id_says_so(api, run_stop, transcript):
    # Without it the turn cannot be told apart from the rest of the transcript,
    # and capture would be a silent no-op forever.
    result = run_stop(transcript([]), None)

    assert result.returncode == 0
    assert api.requests == []
    assert "prompt_id" in result.stderr
    assert "v2.1.196" in result.stderr


def test_a_turn_of_nothing_but_a_tool_result_is_still_sent(api, run_stop, transcript):
    rows = [user({"type": "tool_result", "content": "only tool output"})]

    result = run_stop(transcript(rows))

    assert result.returncode == 0
    assert contents(api) == [
        json.dumps({"type": "tool_result", "content": "only tool output"})
    ]


def test_survives_a_partially_written_transcript(api, run_stop, transcript):
    path = transcript(turn(), trailing='{"type": "assistant", "mess')

    result = run_stop(path)

    assert result.returncode == 0
    assert contents(api) == [
        "remember that I prefer tabs",
        REPLY,
        json.dumps(RESULT),
        "Done.",
    ]


def test_survives_a_missing_transcript(api, run_stop, tmp_path):
    # The reply on the payload does not rescue it: a turn is the transcript, and
    # half of one is not worth sending.
    result = run_stop(
        str(tmp_path / "does-not-exist.jsonl"),
        last_assistant_message="a reply with no transcript",
    )

    assert result.returncode == 0
    assert api.requests == []


def test_survives_a_dead_server(run_stop, transcript):
    result = run_stop(transcript(turn()), config={"api_url": "http://127.0.0.1:1"})

    assert result.returncode == 0


def test_survives_missing_credentials(api, run_stop, transcript):
    result = run_stop(transcript(turn()), config={"identity_id": ""})

    assert result.returncode == 0
    assert api.requests == []
