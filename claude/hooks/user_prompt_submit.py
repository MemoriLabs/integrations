#!/usr/bin/env python3

"""UserPromptSubmit hook. Recall what Memori knows and inject it."""

import os
import sys

# The library lives beside this script. CLAUDE_PLUGIN_ROOT points here too, but
# deriving it from __file__ is correct even when the script is run directly.
LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

try:
    from memori import events, hook
except ImportError as e:
    # Never fail loudly: a broken import must not break the session.
    sys.stderr.write(f"[memori] could not load the plugin library: {e}\n")
    sys.exit(0)

if __name__ == "__main__":
    sys.exit(hook.main(events.on_user_prompt_submit))
