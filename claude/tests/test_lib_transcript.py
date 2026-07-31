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


def test_tool_results_and_thinking_are_dropped():
    assert transcript.block_text({"type": "tool_result", "content": "secret"}) is None
    assert transcript.block_text({"type": "thinking", "thinking": "hmm"}) is None


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


def test_rows_that_only_look_like_conversation_are_skipped():
    for flag in ("isSidechain", "isMeta", "isCompactSummary"):
        assert transcript.message_of(user(text("hi"), **{flag: True})) is None


def test_a_row_with_nothing_sendable_yields_nothing():
    assert (
        transcript.message_of(user({"type": "tool_result", "content": "out"})) is None
    )


def test_blocks_are_joined():
    row = assistant(text("Noted."), {"type": "tool_use", "name": "Bash"})

    assert transcript.message_of(row)["content"] == "Noted.\n[tool: Bash]"


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
