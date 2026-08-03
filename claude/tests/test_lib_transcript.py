"""
Transcript parsing, tested by import rather than through a subprocess.

The subprocess tests in test_capture.py still cover the same ground end to end;
these exist so the parsing rules can be exercised exhaustively and instantly.
"""

import json

from memori import transcript


def text(value):
    return {"type": "text", "text": value}


def user(*blocks, **extra):
    return {
        "type": "user",
        "promptId": "p1",
        "message": {"content": list(blocks)},
        **extra,
    }


def assistant(*blocks, model="claude-opus-5"):
    return {"type": "assistant", "message": {"content": list(blocks), "model": model}}


# +--- block_text ---+


def test_text_blocks_are_kept():
    assert transcript.block_text(text("  hello  ")) == "hello"


def test_tool_calls_become_a_name_only():
    block = {"type": "tool_use", "name": "Bash", "input": {"command": "cat .env"}}

    assert transcript.block_text(block) == "[tool: Bash]"


def test_thinking_is_kept():
    assert transcript.block_text({"type": "thinking", "thinking": " hmm "}) == "hmm"


def test_redacted_thinking_has_no_text_to_send():
    assert transcript.block_text({"type": "redacted_thinking", "data": "AbC=="}) is None


def test_a_tool_result_stays_out_of_the_prose():
    # `turn` puts it on the message's trace instead.
    assert transcript.block_text({"type": "tool_result", "content": "secret"}) is None


def test_a_non_dict_block_is_ignored():
    assert transcript.block_text("not a block") is None


# +--- message_of ---+


def test_only_conversation_rows_become_messages():
    for kind in ("attachment", "ai-title", "queue-operation", "system"):
        assert (
            transcript.message_of({"type": kind, "message": {"content": "x"}}) is None
        )


def test_string_content_is_read():
    row = {"type": "user", "message": {"content": "plain string"}}

    assert transcript.message_of(row) == {"content": "plain string", "role": "user"}


def test_claude_codes_own_text_is_skipped():
    for flag in ("isMeta", "isCompactSummary"):
        assert transcript.message_of(user(text("hi"), **{flag: True})) is None


def test_a_sidechain_row_is_not_skipped():
    # Nothing sets it since 2.1.220: subagent turns go to their own file.
    assert transcript.message_of(user(text("hi"), isSidechain=True)) == {
        "content": "hi",
        "role": "user",
    }


def test_a_row_with_nothing_sendable_yields_nothing():
    assert (
        transcript.message_of(user({"type": "tool_result", "content": "out"})) is None
    )


def test_blocks_are_joined():
    row = assistant(text("Noted."), {"type": "tool_use", "name": "Bash"})

    assert transcript.message_of(row)["content"] == "Noted.\n[tool: Bash]"


# +--- tool_uses / tool_results ---+


def call(name="Bash", args=None, id="t1"):
    return {"type": "tool_use", "id": id, "name": name, "input": args or {}}


def result(value, id="t1"):
    return {"type": "tool_result", "tool_use_id": id, "content": value}


def test_a_tool_use_becomes_a_trace_tool_awaiting_its_result():
    row = assistant(call(args={"command": "cat .env"}))

    assert transcript.tool_uses(row) == [
        ("t1", {"name": "Bash", "args": {"command": "cat .env"}, "result": None})
    ]


def test_args_that_are_not_an_object_are_sent_as_an_empty_one():
    # One odd block should not cost the whole turn its validation.
    for odd in ("a string", ["a", "list"], None):
        row = assistant({"type": "tool_use", "id": "t1", "name": "B", "input": odd})

        assert transcript.tool_uses(row) == [
            ("t1", {"name": "B", "args": {}, "result": None})
        ]


def test_a_row_without_list_content_has_no_tools():
    assert transcript.tool_uses({"message": {"content": "plain"}}) == []
    assert transcript.tool_results({"message": {"content": "plain"}}) == []


def test_tool_results_are_read_with_their_call_id():
    row = user(result("OPENAI_API_KEY=sk-secret"))

    assert transcript.tool_results(row) == [("t1", "OPENAI_API_KEY=sk-secret")]


# +--- trace assembly ---+


def test_the_trace_hangs_off_the_message_that_made_the_call(tmp_path):
    rows = [user(text("go")), assistant(text("Running."), call())]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert "trace" not in messages[0]
    assert messages[1]["content"] == "Running.\n[tool: Bash]"
    assert messages[1]["trace"]["tools"][0]["name"] == "Bash"


def test_a_result_reaches_the_call_it_belongs_to(tmp_path):
    rows = [
        user(text("go")),
        assistant(call(args={"command": "cat .env"})),
        user(result("OPENAI_API_KEY=sk-secret")),
    ]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert messages[1]["trace"]["tools"] == [
        {
            "name": "Bash",
            "args": {"command": "cat .env"},
            "result": "OPENAI_API_KEY=sk-secret",
        }
    ]


def test_results_are_matched_by_id_not_by_order(tmp_path):
    rows = [
        user(text("go")),
        assistant(call(name="Read", id="a"), call(name="Grep", id="b")),
        user(result("second", id="b"), result("first", id="a")),
    ]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert [(t["name"], t["result"]) for t in messages[1]["trace"]["tools"]] == [
        ("Read", "first"),
        ("Grep", "second"),
    ]


def test_a_result_for_an_unknown_call_is_ignored(tmp_path):
    # It belongs to a turn this one does not cover.
    rows = [user(text("go")), assistant(call()), user(result("stray", id="elsewhere"))]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert messages[1]["trace"]["tools"][0]["result"] is None


def test_a_call_whose_result_never_arrives_keeps_a_null_result(tmp_path):
    # Stop can fire before the result is written.
    rows = [user(text("go")), assistant(call())]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert messages[1]["trace"]["tools"][0]["result"] is None


def test_a_message_without_tool_calls_carries_no_trace(tmp_path):
    rows = [user(text("go")), assistant(text("done"))]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert all("trace" not in message for message in messages)


# +--- rows_for_turn / turn ---+


def write(tmp_path, rows, trailing=""):
    path = tmp_path / "transcript.jsonl"

    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
        f.write(trailing)

    return str(path)


def payload(path, last_assistant_message=""):
    return {
        "last_assistant_message": last_assistant_message,
        "prompt_id": "p1",
        "transcript_path": path,
    }


def test_the_window_opens_at_the_prompt_and_stays_open(tmp_path):
    rows = [
        {"type": "user", "promptId": "earlier", "message": {"content": "old"}},
        user(text("current")),
        assistant(text("reply")),
    ]

    found = list(transcript.rows_for_turn(write(tmp_path, rows), "p1"))

    assert [r["type"] for r in found] == ["user", "assistant"]


def test_the_window_closes_when_the_next_turn_begins(tmp_path):
    # Stop runs async, so a queued prompt can land in the file while this hook is
    # still reading it. Absorbing it would merge the two turns and capture the
    # second one twice.
    rows = [
        user(text("mine")),
        assistant(text("my reply")),
        {"type": "user", "promptId": "later", "message": {"content": "NEXT TURN"}},
        {"type": "assistant", "message": {"content": [text("NEXT REPLY")]}},
    ]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert [m["content"] for m in messages] == ["mine", "my reply"]


def test_rows_without_a_prompt_id_stay_in_the_open_turn(tmp_path):
    # Assistant rows and attachments carry none; only the next user prompt closes
    # the window.
    rows = [
        user(text("mine")),
        {"type": "attachment", "attachment": {"type": "skill_listing"}},
        assistant(text("my reply")),
    ]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert [m["content"] for m in messages] == ["mine", "my reply"]


def test_rows_are_yielded_rather_than_collected(tmp_path):
    # A single turn can hold a tool result of any size, and those are exactly the
    # rows that get discarded. Reading one at a time keeps the peak cost the
    # largest row instead of the sum of them.
    found = transcript.rows_for_turn(write(tmp_path, [user(text("hi"))]), "p1")

    assert not isinstance(found, list)
    assert next(found)["type"] == "user"


def test_an_unparseable_trailing_line_is_skipped(tmp_path):
    path = write(tmp_path, [user(text("hi"))], trailing='{"type": "assistant", "mess')

    assert len(list(transcript.rows_for_turn(path, "p1"))) == 1


def test_an_unknown_prompt_id_matches_nothing(tmp_path):
    path = write(tmp_path, [user(text("hi"))])

    assert list(transcript.rows_for_turn(path, "nope")) == []


def test_the_model_comes_from_the_last_assistant_row_naming_one(tmp_path):
    rows = [
        user(text("hi")),
        assistant(text("a"), model="claude-opus-5"),
        assistant(text("b"), model=None),
    ]

    _, model = transcript.turn(payload(write(tmp_path, rows)))

    assert model == "claude-opus-5"


def test_no_assistant_row_means_no_model(tmp_path):
    _, model = transcript.turn(payload(write(tmp_path, [user(text("hi"))])))

    assert model is None


def test_the_reply_is_appended_when_the_transcript_lacks_it(tmp_path):
    payload = {
        "transcript_path": write(tmp_path, [user(text("remember this"))]),
        "prompt_id": "p1",
        "last_assistant_message": "Noted.",
    }

    messages, _ = transcript.turn(payload)

    assert messages == [
        {"content": "remember this", "role": "user"},
        {"content": "Noted.", "role": "assistant"},
    ]


def test_the_reply_is_not_duplicated(tmp_path):
    payload = {
        "transcript_path": write(
            tmp_path, [user(text("hi")), assistant(text("Noted."))]
        ),
        "prompt_id": "p1",
        "last_assistant_message": "Noted.",
    }

    messages, model = transcript.turn(payload)

    assert [m["content"] for m in messages] == ["hi", "Noted."]
    assert model == "claude-opus-5"
