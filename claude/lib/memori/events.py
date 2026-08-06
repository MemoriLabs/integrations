"""
One function per hook event.

Each returns the context to inject, or None. None is the normal outcome: there
was nothing to recall, nothing to capture, or nothing to say.
"""

from memori import api, config, render, transcript

NO_CREDENTIALS = "not configured; run /memori:configure"

NO_PROMPT_ID = (
    "this Stop carried no prompt_id, so the turn cannot be told apart from the "
    "rest of the transcript and nothing is being remembered. Claude Code has "
    "sent one since v2.1.196; upgrade."
)

UNREADABLE = (
    "~/.claude/memori/config.json is there but could not be read, so nothing is "
    "being remembered. Fix the JSON, or run /memori:configure to rewrite it."
)

UNKNOWN_ENVIRONMENT = (
    "the environment is {named}, which is not one of {known}, so no client key "
    "could be taken from it and nothing is being remembered. Run "
    "/memori:configure and set it to one of those."
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
            "/v1/recall",
            {
                "attribution": api.attribution(),
                "query": query,
                **session_of(payload),
            },
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

        deliver(messages, model, session_of(payload))
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
        data = api.get(
            "/v1/compaction",
            {"session_id": payload.get("session_id")},
            timeout=api.COMPACTION_TIMEOUT,
        )
    except Exception as e:
        api.report_failure("compaction", e)
        return None

    return render.compaction(data or {})


def session_of(payload):
    """
    The session block for a payload that carries one, and nothing for one that
    does not.

    The id is what the server requires; a session sent without one is rejected
    outright, where no session at all is a case it handles.
    """

    session = payload.get("session_id")

    return {"session": {"id": session}} if session else {}


def deliver(messages, model, session):
    """
    Post the turn, then post it for extraction.

    Order matters: the server may read the turn from either call, so the turn is
    written before the augmentation is queued. Both carry the same messages, so
    it does not matter which one it is read from.
    """

    api.post(
        "/v1/conversation/turn",
        {"attribution": api.attribution(), "messages": messages, **session},
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
            **session,
        },
        timeout=api.CAPTURE_TIMEOUT,
    )


def run(handler, payload):
    """Run one handler, once credentials are known to exist."""

    # Warned rather than logged: both of these leave the plugin unconfigured by
    # mistake, and would otherwise present exactly as never having set it up.
    if config.unreadable():
        api.warn(UNREADABLE)
        return None

    named = config.unknown_environment()

    if named:
        api.warn(
            UNKNOWN_ENVIRONMENT.format(
                named=named, known=", ".join(sorted(config.API_KEYS))
            )
        )
        return None

    # Never configured is a choice, so it stays quiet.
    if not config.is_configured():
        api.log(NO_CREDENTIALS)
        return None

    return handler(payload)
