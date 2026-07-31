"""
Turning Claude Code's transcript into the messages Memori stores.

A transcript is JSONL and holds far more than conversation -- attachments,
titles, queue operations, file-history snapshots. Only `user` and `assistant`
rows are conversation, and only some of their content blocks may be sent.
"""

import json

CONVERSATION = ("assistant", "user")

# Rows that look like conversation but are not. Sidechain rows are subagent
# traffic, which already reaches the parent as a tool result; the other two are
# Claude Code's own text.
NOT_CONVERSATION = ("isCompactSummary", "isMeta", "isSidechain")


def json_row(line):
    try:
        row = json.loads(line)
    except ValueError:
        return {}

    return row if isinstance(row, dict) else {}


def block_text(block):
    """One content block as text, or None for blocks that must not be sent."""

    if not isinstance(block, dict):
        return None

    if block.get("type") == "text":
        return (block.get("text") or "").strip()

    # The tool's name, never its arguments, and never its result. Tool results
    # are the bulk of a transcript and the likeliest place for a secret to be
    # sitting in a file that was read.
    if block.get("type") == "tool_use":
        return f"[tool: {block.get('name')}]"

    return None


def message_of(row):
    """One transcript row as a message, or None if it is not conversation."""

    if row.get("type") not in CONVERSATION:
        return None

    if any(row.get(flag) for flag in NOT_CONVERSATION):
        return None

    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        parts = [content.strip()]
    elif isinstance(content, list):
        parts = [text for text in map(block_text, content) if text]
    else:
        return None

    text = "\n".join(part for part in parts if part).strip()

    return {"content": text, "role": row["type"]} if text else None


def rows_for_turn(path, prompt_id):
    """
    Every row belonging to one turn: the prompt that opened it, then the rest.

    A generator, so no caller ever holds the raw rows. A single turn can contain
    a tool result of arbitrary size, and those are the rows we are about to throw
    away -- reading them one at a time keeps the peak cost the largest row rather
    than the sum of them.
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
                # reading -- without this the turns merge and the next one is
                # captured twice. Rows that carry no promptId at all (assistant
                # rows, attachments) belong to the turn already open.
                break

            if row:
                yield row


def turn(payload):
    """The finished turn as (messages, model), read from a Stop payload."""

    messages = []
    model = None

    for row in rows_for_turn(payload["transcript_path"], payload["prompt_id"]):
        # The last assistant row that names one wins, which forward iteration
        # gives by overwriting.
        if row.get("type") == "assistant":
            model = (row.get("message") or {}).get("model") or model

        message = message_of(row)
        if message:
            messages.append(message)

    # Stop fires before Claude Code has flushed the closing assistant rows, so
    # the transcript usually stops at the user's prompt and the reply would be
    # lost. It is on the payload, so take it from there.
    reply = (payload.get("last_assistant_message") or "").strip()
    if reply and (not messages or messages[-1]["content"] != reply):
        messages.append({"content": reply, "role": "assistant"})

    return messages, model
