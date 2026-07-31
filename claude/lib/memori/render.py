"""
The two blocks the plugin injects into Claude's context.

Both are wrapped in a tag and opened with a header telling Claude how to treat
what follows. `skills/memory/SKILL.md` says the same things at more length; these
headers are the version that travels with the content.
"""

from memori import api

CONTEXT_TAG = "memori_context"

COMPACTION_TAG = "memori_compaction"

# Claude Code caps injected context at 10,000 characters. Past that it writes the
# block to a file and injects the path instead, which the model then has to go
# and open -- so an oversized block does not fail, it quietly stops being memory.
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
    Stop the body from closing the block it is being placed inside.

    Everything in a block comes back from the server, and memory content is
    attacker-influenceable: whatever a user pastes into a prompt can become a
    memory, and memories are injected verbatim into later sessions. A memory
    carrying `</memori_context>` ends the block early, and whatever follows it
    reads as though it arrived from outside -- a fake system turn, say.

    Measured, not hypothetical: a planted memory did exactly that, putting the
    first closing tag a quarter of the way through the block. The model spotted
    it and refused, which is the right outcome but the wrong thing to depend on.

    The delimiters are rewritten rather than the text dropped, so a memory that
    legitimately mentions the tag stays readable instead of being silently
    truncated. The replacements are the same length as what they replace, so
    the trimming in `fitted` and `assembled` measures the same either way.
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
    What the memory is, beyond its content: where it came from, and when.

    Recall returns content, context and a creation date for every memory, and all
    three are meant to reach the model. Context is what stops a bare claim from
    being read as a standing instruction.
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
    plane -- an emoji, and plenty of CJK punctuation -- is one here and two
    there. Counting the way the enforcer counts is the only way to sit under it.
    """

    return len(text.encode("utf-16-le")) // 2


def trimmed(what, count):
    """
    The line that admits something was dropped.

    In-band, because the model is the one that needs to know. A silently short
    list reads as a complete one: Claude would answer "nothing is recorded about
    that" from a block that had the answer trimmed off it, which is the exact
    failure `skills/memory/SKILL.md` spends its length trying to prevent.
    """

    return f"[trimmed by memori: {count} {what} dropped to fit the context limit]"


def fitted(lines):
    """
    Drop memories from the end until the block fits inside Claude Code's cap.

    Recall returns them ranked, so the tail is the least costly thing to lose.
    Losing the tail beats going over: over the cap, none of it is memory any more.
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

    Unlike recall, a compaction block is not a ranked list -- it is a briefing
    whose parts are worth wildly different amounts. Trimming the tail would throw
    away the continuation, which is the entire reason the block exists. So each
    part carries what it costs to lose and the cheapest goes first, which is the
    same shape Anthropic's own security-guidance plugin uses on an over-cap diff:
    keep the subset that matters rather than keep nothing.
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

    # In display order, each with what a resumed session can least afford to lose
    # it. The continuation is the point of the whole block; the standing orders
    # are what stop a session breaking a rule it can no longer see. A timeline is
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

    # The messages the endpoint also returns are deliberately dropped: Claude
    # Code's own compact summary already covers the conversation itself.
    return assembled(chunks)
