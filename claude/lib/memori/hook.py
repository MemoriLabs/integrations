"""
The plumbing every hook entry point shares: stdin in, context out.

THIS NEVER EXITS NON-ZERO. A non-zero exit means "blocking error" to Claude
Code: on UserPromptSubmit it erases what the user typed, and on Stop it refuses
to let the turn end. A dead server, bad credentials or a slow response must all
degrade to "no memories", never to a broken session.
"""

import json
import sys

from memori import api, events


def read_payload(stream=None):
    raw = (stream or sys.stdin).read()
    payload = json.loads(raw) if raw.strip() else {}

    return payload if isinstance(payload, dict) else {}


def emit(context, event):
    # additionalContext must be nested inside hookSpecificOutput; at the top
    # level Claude Code silently ignores it.
    json.dump(
        {
            "hookSpecificOutput": {
                "additionalContext": context,
                "hookEventName": event,
            }
        },
        sys.stdout,
    )


def main(handler=None):
    """
    Run one hook.

    Pass a handler when the entry point serves a single event, which is how
    hooks.json wires them. With no handler the event name in the payload picks
    one, which is what `bin/memori-hook` does for manual runs and tests.
    """

    try:
        payload = read_payload()
        if not payload:
            return 0

        if handler is None:
            context = events.handle(payload)
        else:
            context = events.run(handler, payload)

        if context:
            emit(context, payload.get("hook_event_name"))
    except Exception as e:
        api.log(f"unhandled error: {e}")

    return 0
