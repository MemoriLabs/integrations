"""
Turning Claude Code's transcript into the messages Memori stores.

A transcript is JSONL and holds far more than conversation: attachments,
titles, queue operations, file-history snapshots. All of it is sent. Every row
of the turn becomes a message, and anything without text of its own is sent as
the JSON it was written as, so a row type or block type we have never seen
arrives intact rather than disappearing.

Nothing is renamed on the way through: every `role` and `type` is a string
Claude Code wrote. Tool calls therefore arrive twice, in the prose and on the
trace, which is the price of not inventing a shorthand for them.

The blocks this plugin injected itself are the one thing removed.
"""

import json
import re

# Sending one back would have extraction read a recalled memory as newly stated,
# so every turn would reinforce whatever the last one recalled.
INJECTED = ("memori_compaction", "memori_context")

UNKNOWN = "unknown"


def json_row(line):
    try:
        row = json.loads(line)
    except ValueError:
        return {}

    return row if isinstance(row, dict) else {}


def content_of(row):
    """This row's content blocks, or None if it holds no message."""

    return (row.get("message") or {}).get("content")


def block_text(block):
    """One content block as text. A block with no text of its own is sent as JSON."""

    if not isinstance(block, dict):
        return json.dumps(block)

    if block.get("type") == "text":
        return (block.get("text") or "").strip()

    # Usually empty: Claude Code 2.1.220 keeps the reasoning in an encrypted
    # `signature` and writes the text as "".
    if block.get("type") == "thinking":
        return (block.get("thinking") or "").strip()

    # Sent as written, so a block type nobody here has heard of still arrives.
    return json.dumps(block)


def block_kind(row):
    """
    A message's `type`, from the blocks Claude Code wrote.

    Rows hold one kind of block almost always. Where they hold several, or
    none, the row's own type stands in rather than a name we made up.
    """

    content = content_of(row)

    if isinstance(content, str):
        return "text"

    kinds = (
        {
            block.get("type")
            for block in content
            if isinstance(block, dict) and block.get("type")
        }
        if isinstance(content, list)
        else set()
    )

    return kinds.pop() if len(kinds) == 1 else row.get("type") or UNKNOWN


def tool_uses(row):
    """
    This row's tool calls as (call id, trace tool) pairs.

    `args` has to be an object or the server rejects the whole turn.
    """

    content = content_of(row)
    if not isinstance(content, list):
        return []

    found = []

    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue

        args = block.get("input")

        found.append(
            (
                block.get("id"),
                {
                    "name": block.get("name") or "",
                    "args": args if isinstance(args, dict) else {},
                    "result": None,
                },
            )
        )

    return found


def tool_results(row):
    """This row's tool results as (call id, result) pairs."""

    content = content_of(row)
    if not isinstance(content, list):
        return []

    return [
        (block.get("tool_use_id"), block.get("content"))
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]


def stripped(text):
    """
    The text without the blocks this plugin injected into it.

    An unterminated block is left alone; the alternative is deleting the rest
    of a turn on the strength of a stray opening tag.
    """

    for tag in INJECTED:
        text = re.sub(f"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL)

    return text


def message_of(row):
    """
    One transcript row as a message. Every row becomes one.

    `role` is the row's own type, so an attachment arrives as "attachment"
    rather than dressed up as something a person said.
    """

    content = content_of(row)

    if isinstance(content, str):
        parts = [content.strip()]
    elif isinstance(content, list):
        parts = [text for text in map(block_text, content) if text]
    else:
        parts = []

    text = stripped("\n".join(part for part in parts if part)).strip()
    kind = block_kind(row)

    # A row with no message of its own is the row, and so is one the stripping
    # above emptied. Neither has a block to take its type from.
    if not text:
        text = stripped(json.dumps(row))
        kind = row.get("type") or UNKNOWN

    return {"content": text, "role": row.get("type") or UNKNOWN, "type": kind}


def rows_for_turn(path, prompt_id):
    """
    Every row belonging to one turn: the prompt that opened it, then the rest.

    A generator, though that no longer bounds what a turn costs: nothing is
    discarded now, so `turn` accumulates the whole of it either way.
    """

    started = False

    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json_row(line)
            carried = row.get("promptId")

            if not started:
                # Only user rows carry promptId. The assistant rows that follow
                # belong to the same turn but have nothing to match on, so the
                # first match opens the window.
                if carried != prompt_id:
                    continue

                started = True

            elif carried and carried != prompt_id:
                # And the next turn's prompt closes it. Stop runs async, so a
                # queued prompt can land in the file while this hook is still
                # reading. Without this the turns merge and the next one is
                # captured twice. Rows that carry no promptId at all (assistant
                # rows, attachments) belong to the turn already open.
                break

            if row:
                yield row


def turn(payload):
    """The finished turn as (messages, model), read from a Stop payload."""

    messages = []
    model = None

    # Shared with the messages they are attached to, so filling a result in
    # here changes what is about to be sent.
    awaiting = {}

    for row in rows_for_turn(payload["transcript_path"], payload["prompt_id"]):
        # The last assistant row that names one wins, which forward iteration
        # gives by overwriting.
        if row.get("type") == "assistant":
            model = (row.get("message") or {}).get("model") or model

        for call_id, result in tool_results(row):
            tool = awaiting.get(call_id)
            if tool is not None:
                tool["result"] = result

        calls = tool_uses(row)
        message = message_of(row)

        if calls:
            message["trace"] = {"tools": [tool for _, tool in calls]}

        messages.append(message)

        for call_id, tool in calls:
            if call_id:
                awaiting[call_id] = tool

    # Stop fires before Claude Code has flushed the closing assistant rows, so
    # the transcript usually stops at the user's prompt and the reply would be
    # lost. It is on the payload, so take it from there.
    reply = (payload.get("last_assistant_message") or "").strip()
    if reply and (not messages or messages[-1]["content"] != reply):
        messages.append({"content": reply, "role": "assistant", "type": "text"})

    return messages, model
