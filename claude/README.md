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

Each block opens with a line telling Claude how to read it: as something it
already knows rather than something it was handed, without announcing the
lookup, and never as grounds to claim it remembers anything the block does not
say.

No proxy, no `base_url` to change, no SDK. Three hooks, one skill, and a little
standard library Python.

## Install

Using the desktop app? Follow the
**[Claude Code Desktop steps](INSTALL.md#install-in-claude-code-desktop)**.

From the command line:

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs
claude plugin enable memori@memorilabs
```

It installs disabled. Everything here goes to a server the moment it is enabled
and configured, so both are separate steps.

Then start a session and run `/memori:configure`. It asks for an API URL, an
identity token and an entity ID, and writes them to
`~/.claude/memori/config.json` with `chmod 600`. That file is the only place the
plugin reads configuration from — no environment variables, and nothing a
repository can reach.

`application_env` decides which client API key is sent. It defaults to
`production`; set it to `staging` or `local` to talk to those instead. The keys
identify the caller rather than authenticating it, so the plugin carries them and
only a deployment on its own host sets `api_header_value` by hand.

**The only thing this plugin ever adds to a conversation is the memories it
recalled.** Nothing else — no status, no warning, no notice that something
failed. A refused token or an unreachable server is written to the hook's
stderr, which means `claude --debug-file memori.log` and reading that file. It
is a deliberate trade: recall stays the one channel into your context, and the
cost is that a failure is silent until you go and look.

Ask **"is Memori working?"** and Claude reads your configuration back. Whether
memories are actually accumulating is a question for the Memori dashboard, which
is the only place that shows what was stored.

See the **[quickstart](INSTALL.md)** for the required values and installation.

Two constraints to know before starting:

- **`entity_id` is required, and is what a memory is attributed to.** A turn
  captured without one is accepted by the server and makes no memories, so the
  plugin refuses to run until it is set. Use the same value in every Memori
  client. It is not an access boundary: what can be recalled is decided by the
  identity token and the pool it can read.
- **A repository cannot configure Memori.** Configuration lives in one file
  under your home directory, so a cloned project has no way to say where your
  conversation is sent, who it is attributed to, or what authenticates it.

## What gets sent

The whole turn:

- your prompts, Claude's replies, and its thinking
- every tool call with its full arguments, and every tool result in full
- the attachments Claude Code adds to a turn

There is no redaction and no filtering, so **anything a session reads reaches the
server**: a credential in a file Claude opened, a token printed by a command it
ran, or one you pasted into a prompt yourself. Tool results are the bulk of any
transcript and the likeliest place a secret sits, and they are sent.

The one thing removed is this plugin's own injected context, so extraction does
not read a recalled memory back as something newly stated.

Each turn is scoped by the `prompt_id` Claude Code provides, so a turn is sent
once, and no conversation is kept on disk. Capture is two inserts and runs at the
end of the turn, adding a few tens of milliseconds; the extraction it queues
happens in a worker, so nothing waits for that.
**An interrupted turn is not remembered**: `Stop` does not fire on ESC, and
catching it later would mean tracking unfinished turns between sessions.

## What it keeps on disk

One file: `~/.claude/memori/config.json`, written by `/memori:configure` with
`chmod 600`. Your settings and nothing else — no conversation, no log, no cache.
It is the only place the identity token exists in full, and the only thing the
hooks read configuration from.

Uninstalling does not remove it. Delete `~/.claude/memori/` if you want it gone.

## Safety

The hook **never exits non-zero**. A dead server, missing credentials, a corrupt
transcript, or a slow response all degrade to "no memories", never to a lost
prompt or a turn that will not end. On `UserPromptSubmit` a blocking exit erases
the typed prompt, and on `Stop` it forbids Claude from stopping.

Everything is best-effort. A Memori outage should not be noticeable in a
session.

## License

MIT. See [LICENSE](../LICENSE).
