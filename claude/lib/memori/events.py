"""
One function per hook event.

Each returns the context to inject, or None. None is the normal outcome: there
was nothing to recall, nothing to capture, or nothing to say.
"""

from memori import api, config, render, transcript

NO_CREDENTIALS = (
    "not configured; set MEMORI_API_URL, MEMORI_IDENTITY_TOKEN, "
    "MEMORI_API_HEADER_VALUE and MEMORI_ENTITY_ID, or configure the plugin"
)

NO_PROMPT_ID = (
    "this Stop carried no prompt_id, so the turn cannot be told apart from the "
    "rest of the transcript and nothing is being remembered. Claude Code has "
    "sent one since v2.1.196; upgrade."
)

REFUSED = (
    "this project's .claude/settings.json sets {names} for Memori. A repository "
    "does not get to decide that, so it was ignored. Set it in "
    "~/.claude/settings.json, or configure the plugin."
)


def on_user_prompt_submit(payload):
    """Recall what Memori knows about the prompt and inject it."""

    # The hooks reference documents user_prompt, but this build sends prompt.
    # The fallback covers builds that differ.
    query = (payload.get("prompt") or payload.get("user_prompt") or "").strip()
    if not query:
        return None

    try:
        data = api.post(
            "/v1/recall", {"attribution": api.attribution(), "query": query}
        )
    except Exception as e:
        api.report_failure("recall", e)
        return None

    return render.memories(data.get("memories") or [])


def on_stop(payload):
    """Send the finished turn to be remembered. Injects nothing."""

    # Another plugin's Stop hook can refuse to let the turn end, and Stop fires
    # again once it finally does. The turn is not over yet, and that later Stop
    # carries the whole of it, so capturing now would send the first half twice.
    if payload.get("stop_hook_active"):
        api.log("the turn is being held open by another stop hook; not capturing")
        return None

    if not payload.get("transcript_path"):
        return None

    # prompt_id is the only marker separating this turn from the rest of the
    # transcript, and there is no second way to derive it. Without one, capture
    # becomes a no-op that would otherwise go unreported.
    if not payload.get("prompt_id"):
        api.warn(NO_PROMPT_ID)
        return None

    try:
        messages, model = transcript.turn(payload)

        if not messages:
            api.log("no messages in the turn; nothing to capture")
            return None

        deliver(messages, model)
        api.log(f"captured {len(messages)} messages")
    except Exception as e:
        api.report_failure("capture", e)

    return None


def on_session_start(payload):
    """
    After a compaction, rebuild what the session knew.

    Only compaction. A session that is merely starting needs nothing injected,
    because the first prompt recalls on its own before the model sees it.
    """

    if payload.get("source") != "compact":
        return None

    try:
        data = api.get("/v1/compaction", timeout=api.COMPACTION_TIMEOUT)
    except Exception as e:
        api.report_failure("compaction", e)
        return None

    return render.compaction(data or {})


def deliver(messages, model):
    """
    Post the turn, then post it for extraction.

    Order matters: the server may read the turn from either call, so the turn is
    written before the augmentation is queued. Both carry the same messages, so
    it does not matter which one it is read from.
    """

    api.post(
        "/v1/conversation/turn",
        {"attribution": api.attribution(), "messages": messages},
        timeout=api.CAPTURE_TIMEOUT,
    )
    api.post(
        "/v1/augmentation",
        {
            "conversation": {"messages": messages},
            "meta": {
                "attribution": api.attribution(),
                "llm": {"model": {"provider": "anthropic", "version": model}},
                "platform": {"provider": "claude-code"},
            },
        },
        timeout=api.CAPTURE_TIMEOUT,
    )


HANDLERS = {
    "SessionStart": on_session_start,
    "Stop": on_stop,
    "UserPromptSubmit": on_user_prompt_submit,
}


def handle(payload):
    """Dispatch by event name. Used when one entry point serves every event."""

    handler = HANDLERS.get(payload.get("hook_event_name"))

    return run(handler, payload) if handler else None


def run(handler, payload):
    """Run one handler, once credentials are known to exist."""

    if config.refused():
        api.warn(REFUSED.format(names=", ".join(config.refused())))

    if not config.is_configured():
        api.log(NO_CREDENTIALS)
        return None

    return handler(payload)
