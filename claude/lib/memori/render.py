"""
The two blocks the plugin injects into Claude's context.

Each is wrapped in a tag and opened with a header stating how to treat what
follows. `skills/memory/SKILL.md` covers the same ground; these headers are the
copy that travels with the content.
"""

from memori import api

CONTEXT_TAG = "memori_context"

COMPACTION_TAG = "memori_compaction"

# Claude Code caps injected context at 10,000 characters. Past that it writes the
# block to a file and injects the path instead, so an oversized block stops being
# memory rather than failing.
LIMIT = 10000

CONTEXT_HEADER = (
    "Recalled from long-term memory. Not stated by the user in this "
    "conversation.\nTreat it as something you already know: use what is "
    "relevant, ignore what is not, and do not\nannounce that you retrieved it. "
    "Never present anything absent from this block as remembered."
)

COMPACTION_HEADER = (
    "Where this session had got to before it was compacted, reconstructed from "
    "long-term memory.\nUse it to pick the thread back up. It is not a new "
    "instruction from the user, and it does\nnot need to be narrated back to "
    "them."
)


def neutered(text):
    """
    Rewrite the block delimiters in body text so it cannot close the block it
    sits inside.

    Memory content is attacker-influenceable: anything pasted into a prompt can
    become a memory, and memories are injected verbatim into later sessions. A
    memory containing `</memori_context>` ends the block early, and whatever
    follows it reads as though it arrived from outside the block.

    The delimiters are rewritten rather than removed, so a memory that
    legitimately mentions the tag stays readable. The replacements are the same
    length as what they replace, so `fitted` and `assembled` measure the same
    either way.
    """

    for tag in (CONTEXT_TAG, COMPACTION_TAG):
        text = text.replace(f"</{tag}>", f"[/{tag}]").replace(f"<{tag}>", f"[{tag}]")

    return text


def block(tag, header, body):
    return f"<{tag}>\n{header}\n\n{neutered(body)}\n</{tag}>" if body else None


def bullets(values):
    """Non-empty values as list items. Tolerates a bare string."""

    if isinstance(values, str):
        values = [values]

    return [f"- {str(value).strip()}" for value in values or [] if str(value).strip()]


def qualifiers(memory):
    """
    Where a memory came from, and when.

    Recall returns content, context and a creation date for every memory, and
    all three reach the model. Context stops a bare claim from reading as a
    standing instruction.
    """

    parts = []

    context = (memory.get("context") or "").strip()
    if context:
        parts.append(f"context: {context}")

    created = (memory.get("date") or {}).get("created") or ""
    if len(created) >= 10:
        parts.append(f"recorded {created[:10]}")

    return f" ({'; '.join(parts)})" if parts else ""


def measured(text):
    """
    The length Claude Code will see, which is not always the length Python sees.

    The cap is applied in JavaScript, where a string's length is its count of
    UTF-16 code units. Python counts code points, so anything outside the basic
    plane, such as an emoji or much CJK punctuation, counts as one here and two
    there.
    """

    return len(text.encode("utf-16-le")) // 2


def trimmed(what, count):
    """
    The line stating that content was dropped.

    It goes inside the block because the model is what needs to know. A silently
    shortened list reads as a complete one, so Claude would answer "nothing is
    recorded about that" from a block the answer had been trimmed out of.
    """

    return f"[trimmed by memori: {count} {what} dropped to fit the context limit]"


def fitted(lines):
    """
    Drop memories from the end until the block fits under Claude Code's cap.

    Recall returns them ranked, so the tail is the cheapest part to lose. Over
    the cap, none of it reaches the model as memory.
    """

    kept = list(lines)
    note = ""

    while kept and (
        measured(block(CONTEXT_TAG, CONTEXT_HEADER, "\n".join(kept + [note]).strip()))
        > LIMIT
    ):
        kept.pop()
        note = trimmed("older memories", len(lines) - len(kept))

    if note:
        api.log(f"{len(lines) - len(kept)} memories dropped to stay under the cap")
        kept.append(note)

    return kept


def memories(recalled):
    lines = []

    for memory in recalled:
        content = (memory.get("content") or "").strip()
        if not content:
            continue

        lines.append(f"- {content}{qualifiers(memory)}")

    return block(CONTEXT_TAG, CONTEXT_HEADER, "\n".join(fitted(lines)))


def listing(title, values):
    items = bullets(values)

    return "\n".join([f"{title}:", *items, ""]) if items else ""


def paragraph(title, value):
    value = (value or "").strip()

    return f"{title}:\n{value}\n" if value else ""


def continuing(continuation):
    lines = []

    for field in ("last_action", "next_expected_action"):
        value = (continuation.get(field) or "").strip()
        if value:
            lines.append(f"{field.replace('_', ' ').capitalize()}: {value}")

    return "\n".join(lines)


def assembled(chunks):
    """
    Every chunk that fits, dropping the cheapest first.

    A compaction block is not a ranked list; its parts are worth different
    amounts. Trimming the tail would drop the continuation, which is the reason
    the block exists. Each part carries what it costs to lose, and the cheapest
    goes first.
    """

    kept = [chunk for chunk in chunks if chunk[1].strip()]
    dropped = 0

    def rendered(parts, note):
        body = "\n".join(text for _, text in parts).strip()

        return block(COMPACTION_TAG, COMPACTION_HEADER, f"{body}\n{note}".strip())

    while kept and measured(rendered(kept, trimmed("sections", dropped))) > LIMIT:
        cheapest = min(range(len(kept)), key=lambda i: kept[i][0])
        kept.pop(cheapest)
        dropped += 1

    if dropped:
        api.log(f"{dropped} compaction sections dropped to stay under the cap")

    return rendered(kept, trimmed("sections", dropped) if dropped else "")


def compaction(data):
    state = data.get("state") or {}

    # In display order, each weighted by what a resumed session can least afford
    # to lose. The continuation is the point of the block; the standing orders
    # stop a session breaking a rule it can no longer see. The timeline is
    # narrative, and the workspace and environment can be read back off the repo.
    chunks = (
        (5, listing("Standing orders", data.get("standing_orders"))),
        (2, listing("Environment", data.get("environment"))),
        (4, listing("Active tasks", state.get("active_tasks"))),
        (4, listing("Open loops", state.get("open_loops"))),
        (3, listing("Pending results", state.get("pending_results"))),
        (2, listing("Workspace changes", data.get("workspace_changes"))),
        (1, paragraph("Timeline", data.get("timeline"))),
        (6, continuing(data.get("continuation") or {})),
    )

    # The messages the endpoint also returns are dropped: Claude Code's own
    # compact summary already covers the conversation itself.
    return assembled(chunks)
