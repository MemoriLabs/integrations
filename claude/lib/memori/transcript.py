"""
Turning Claude Code's transcript into the messages Memori stores.

A transcript is JSONL and holds far more than conversation: attachments,
titles, queue operations, file-history snapshots. Only `user` and `assistant`
rows are conversation, and every block within one is sent.

A message says the same thing twice: `content` names each tool call, and
`trace` carries that call's arguments and its result. The backend reads both
and links them by message index, so the name stays in the prose to mark the
place the call was made.
"""

import json

CONVERSATION = ("assistant", "user")

# Typed `user`, but Claude Code wrote them, not the person: the skill files it
# pastes in when a skill loads, and the summary it writes at a compaction.
NOT_CONVERSATION = ("isCompactSummary", "isMeta")


def json_row(line):
    try:
        row = json.loads(line)
    except ValueError:
        return {}

    return row if isinstance(row, dict) else {}


def block_text(block):
    """One content block as text, or None for a block with no text of its own."""

    if not isinstance(block, dict):
        return None

    if block.get("type") == "text":
        return (block.get("text") or "").strip()

    # Usually empty: Claude Code 2.1.220 keeps the reasoning in an encrypted
    # `signature` and writes the text as "".
    if block.get("type") == "thinking":
        return (block.get("thinking") or "").strip()

    if block.get("type") == "tool_use":
        return f"[tool: {block.get('name')}]"

    return None


def tool_uses(row):
    """
    This row's tool calls as (call id, trace tool) pairs.

    `args` has to be an object or the server rejects the whole turn, so
    anything else becomes an empty one.
    """

    content = (row.get("message") or {}).get("content")
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

    content = (row.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []

    return [
        (block.get("tool_use_id"), block.get("content"))
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]


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

    A generator, though that no longer bounds what a turn costs: results are
    kept now, so `turn` accumulates the whole of it either way.
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
        if message:
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
        messages.append({"content": reply, "role": "assistant"})

    return messages, model
