# Memori for Claude Code

Gives Claude persistent memory. Before each prompt it asks Memori what it already
knows about you and injects it; after each turn it sends the conversation back to
be remembered.

```
you type  ──▶  UserPromptSubmit  ──▶  POST /v1/recall  ──▶  injected as context
                                                                    │
                                                                    ▼
                                                              Claude answers
                                                                    │
turn ends ──▶  Stop  ──▶  POST /v1/conversation/turn ──▶ POST /v1/augmentation
                                                                    │
                                                     the augmentation worker
                                                     turns it into memories
```

When Claude Code compacts the conversation, the injected memories fall out of
context with everything else. `SessionStart` then asks Memori for a summary of
what the session had established: standing orders, environment, open loops, and
where it left off. That is injected so the thread survives the compaction.

A bundled skill tells Claude how to read the injected blocks: use them as things
it already knows rather than announcing a lookup, never claim to remember
something that is not there, and prefer the current conversation and the real
state of the code when a memory disagrees.

No proxy, no `base_url` to change, no SDK. Three hooks, two skills, and a little
standard library Python, with no state kept on disk.

## Install

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs \
  --config api_url=https://memori.example.com \
  --config identity_token=id_your_token_here \
  --config api_header_value=your-client-key \
  --config entity_id=jane-doe
claude plugin enable memori@memorilabs
```

It installs disabled. Everything here goes to a server the moment it is enabled,
so enabling it is a separate step.

To check it works, open Claude Code and ask **"is Memori working?"**. A bundled
skill runs the diagnostic and reports the result: the configuration a hook would
see, and whether every endpoint the plugin uses is reachable. It writes nothing.

**[SETUP.md](SETUP.md) is the full guide**: prerequisites, configuration for
users and developers, per-project installs, and what to do when nothing is being
recalled or remembered.

Two constraints to know before starting:

- **`entity_id` is required, and is what a memory is attributed to.** A turn
  captured without one is accepted by the server and makes no memories, so the
  plugin refuses to run until it is set. Use the same value in every Memori
  client. It is not an access boundary: what can be recalled is decided by the
  identity token and the pool it can read.
- **A project's `.claude/settings.json` cannot configure Memori.** A repository
  can commit that file and Claude Code merges its `env` block into every hook, so
  anything a workspace supplies is refused and named rather than used.

## What gets sent

Only conversation:

- your prompts and Claude's replies
- tool **names**, as `[tool: Bash]`

Never tool output, tool arguments, Claude's thinking, or subagent traffic. Tool
results are the bulk of any transcript and the likeliest place a secret sits, so
they are excluded wholesale rather than scanned.

Each turn is scoped by the `prompt_id` Claude Code provides, so a turn is sent
once and nothing is kept on disk. Capture is two inserts and runs at the end of
the turn, adding a few tens of milliseconds; the extraction it queues happens in
a worker, so nothing waits for that.
**An interrupted turn is not remembered**: `Stop` does not fire on ESC, and
catching it later would mean keeping state between sessions.

## Safety

The hook **never exits non-zero**. A dead server, missing credentials, a corrupt
transcript, or a slow response all degrade to "no memories", never to a lost
prompt or a turn that will not end. On `UserPromptSubmit` a blocking exit erases
the typed prompt, and on `Stop` it forbids Claude from stopping.

Everything is best-effort. A Memori outage should not be noticeable in a
session.

## License

MIT. See [LICENSE](../LICENSE).
