---
name: memori-check
description: This skill should be used when the user asks whether Memori is working, why nothing is being recalled or remembered, or asks to check, test, or debug the Memori plugin's configuration or connection.
version: 0.1.0
---

# Checking Memori

Memori's hooks never fail loudly, so a broken setup and a working one look
identical from inside a session. The diagnostic is the only way to tell them
apart.

Run it:

```bash
memori-hook --check
```

`bin/` is on the Bash tool's `PATH` while the plugin is enabled, so the bare
command works. If it is not found, the plugin is not enabled in this session —
say so, and point at `claude plugin list`.

It prints two things: the configuration a hook would actually see, with the
source of each value, and the result of reaching every endpoint the plugin uses.
Nothing is written by the check.

## Reading the output

- **`identity`, `client key` or `entity id` MISSING** — not configured. Nothing
  works, and nothing will be logged about it. Point them at
  `/plugin configure memori@memorilabs`.
- **`Ignored from this project's .claude/settings.json`** — the repository tried
  to set where conversation is sent or what authenticates it. Refused by design.
  It belongs in `~/.claude/settings.json`.
- **`entity id`** — the value people get wrong. It is what a captured turn is
  attributed to, and a turn sent without one makes no memories at all. It is not
  an access boundary: what they can recall follows the identity token and the
  pool it can read, not the entity they ask as.
- **`HTTP 401`** — always a configuration error, never transient.
- **`0 memories returned`, everything else OK** — normal on a new install, and
  normal before a captured turn has been augmented. Not a fault.
- **recall OK but an endpoint below it unreachable** — recall works and capture
  does not. This is the failure people never notice on their own; say it plainly.

Report what it said rather than interpreting it away. If the user is asking
because memory seems to be missing, the causes and their order are in the
`memori-memory` skill.
