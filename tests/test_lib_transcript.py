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


def test_a_tool_call_is_sent_as_the_block_it_is():
    block = {"type": "tool_use", "name": "Bash", "input": {"command": "cat .env"}}

    assert transcript.block_text(block) == json.dumps(block)


def test_thinking_is_kept():
    assert transcript.block_text({"type": "thinking", "thinking": " hmm "}) == "hmm"


def test_a_block_with_no_text_of_its_own_is_sent_as_json():
    # Images, documents, redacted thinking, and anything Anthropic adds next.
    for block in (
        {"type": "redacted_thinking", "data": "AbC=="},
        {"type": "image", "source": {"type": "base64", "data": "iVBOR"}},
        {"type": "something_new", "whatever": 1},
    ):
        assert transcript.block_text(block) == json.dumps(block)


def test_a_tool_result_is_sent_as_the_block_it_is():
    block = {"type": "tool_result", "content": "x"}

    assert transcript.block_text(block) == json.dumps(block)


def test_a_non_dict_block_is_sent_as_json():
    assert transcript.block_text("not a block") == '"not a block"'


# +--- message_of ---+


def test_every_row_becomes_a_message_whatever_its_type():
    for kind in ("attachment", "ai-title", "queue-operation", "system"):
        row = {"type": kind, "message": {"content": "x"}}

        assert transcript.message_of(row) == {
            "content": "x",
            "role": kind,
            "type": "text",
        }


def test_a_row_carrying_no_message_is_sent_as_the_row():
    row = {"type": "file-history-snapshot", "messageId": "abc"}

    assert transcript.message_of(row) == {
        "content": json.dumps(row),
        "role": "file-history-snapshot",
        "type": "file-history-snapshot",
    }


def test_a_row_with_no_type_still_becomes_a_message():
    assert transcript.message_of({"message": {"content": "x"}})["role"] == "unknown"


def test_string_content_is_read():
    row = {"type": "user", "message": {"content": "plain string"}}

    assert transcript.message_of(row) == {
        "content": "plain string",
        "role": "user",
        "type": "text",
    }


def test_claude_codes_own_text_is_sent_too():
    for flag in ("isMeta", "isCompactSummary"):
        assert transcript.message_of(user(text("hi"), **{flag: True})) == {
            "content": "hi",
            "role": "user",
            "type": "text",
        }


def test_a_sidechain_row_is_not_skipped():
    # Nothing sets it since 2.1.220: subagent turns go to their own file.
    assert transcript.message_of(user(text("hi"), isSidechain=True)) == {
        "content": "hi",
        "role": "user",
        "type": "text",
    }


def test_a_tool_result_row_is_typed_by_its_block():
    block = {"type": "tool_result", "content": "out"}
    message = transcript.message_of(user(block))

    assert message == {
        "content": json.dumps(block),
        "role": "user",
        "type": "tool_result",
    }


def test_blocks_are_joined():
    call = {"type": "tool_use", "name": "Bash"}
    row = assistant(text("Noted."), call)

    assert transcript.message_of(row)["content"] == f"Noted.\n{json.dumps(call)}"


# +--- stripped ---+


def injected(tag, body="- Ryan prefers tabs"):
    return f"<{tag}>\nRecalled from long-term memory.\n\n{body}\n</{tag}>"


def test_an_injected_block_is_removed():
    for tag in transcript.INJECTED:
        assert transcript.stripped(injected(tag)).strip() == ""


def test_what_surrounds_an_injected_block_is_kept():
    text = f"before\n{injected('memori_context')}\nafter"

    assert transcript.stripped(text) == "before\n\nafter"


def test_every_injected_block_goes_not_just_the_first():
    text = injected("memori_context") + injected("memori_context") + "kept"

    assert transcript.stripped(text) == "kept"


def test_an_unterminated_block_is_left_alone():
    # Deleting to the end of the turn on a stray opening tag would lose more
    # than it saves.
    text = "<memori_context>\nno closing tag, and a real reply after it"

    assert transcript.stripped(text) == text


def test_the_tags_are_the_ones_render_injects():
    # They are written out in render and matched here; nothing makes the two
    # agree except this.
    from memori import render

    assert sorted(transcript.INJECTED) == sorted(
        (render.COMPACTION_TAG, render.CONTEXT_TAG)
    )


def test_a_row_that_is_only_an_injected_block_falls_back_to_the_row():
    message = transcript.message_of(user(text(injected("memori_context"))))

    assert message["type"] == "user"
    assert "memori_context" not in message["content"]


def test_a_row_keeps_what_the_user_typed_around_the_block():
    row = user(text(f"{injected('memori_context')}\nwhat do you remember?"))

    assert transcript.message_of(row)["content"] == "what do you remember?"


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
    assert json.dumps(call()) in messages[1]["content"]
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


def test_a_tool_result_keeps_blocks_the_prose_would_lose(tmp_path):
    # A tool that reads a file mentioning the tag reported what it found, and
    # the trace is meant to be what the tool returned.
    rows = [
        user(text("go")),
        assistant(call(name="Read")),
        user(result(injected("memori_context"))),
    ]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert "memori_context" in messages[1]["trace"]["tools"][0]["result"]


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
    # the window. The attachment is sent too, as the row it is.
    rows = [
        user(text("mine")),
        {"type": "attachment", "attachment": {"type": "skill_listing"}},
        assistant(text("my reply")),
    ]

    messages, _ = transcript.turn(payload(write(tmp_path, rows)))

    assert [m["role"] for m in messages] == ["user", "attachment", "assistant"]
    assert [m["content"] for m in messages][::2] == ["mine", "my reply"]


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
        {"content": "remember this", "role": "user", "type": "text"},
        {"content": "Noted.", "role": "assistant", "type": "text"},
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
