# Memori integrations

Official Memori integrations for third-party tools. This repository is also a
Claude Code plugin marketplace.

| Integration | What it is | |
|---|---|---|
| [claude](claude/) | Persistent memory for Claude Code | [Install](claude/INSTALL.md) |

## Memori for Claude Code

Gives Claude persistent memory. Before each prompt it asks Memori what it already
knows about you and injects it; after each turn it sends the conversation back to
be remembered.

**[Install and configure →](claude/INSTALL.md)**

When Claude Code compacts a long conversation, the recalled memories fall out of
context along with everything else. Memori then re-injects a summary of what the
session had established, so the thread survives.

## What gets sent

The whole turn: your prompts, Claude's replies, its thinking, every tool call
with its full arguments, every tool result in full, and the attachments Claude
Code adds.

There is no redaction and no filtering, so **anything a session reads reaches the
server**: a credential in a file Claude opened, a token printed by a command it
ran, or one you pasted into a prompt yourself.

The only thing removed is the plugin's own injected context. A turn is sent once,
no conversation is kept on disk, and an interrupted turn is not remembered.

## What it keeps on disk

One file, `~/.claude/memori/config.json`, written by `/memori:configure` with
`chmod 600`: your settings and nothing else. It is the only place the identity
token exists in full, and uninstalling does not remove it.

It is also the only place the plugin reads settings from. There are no
environment variables, so a repository cannot configure Memori.

## Failures are silent

**The only thing this plugin ever adds to a conversation is the memories it
recalled.** No status, no warning, no notice that something failed. Errors go to
the hook's stderr, so `claude --debug-file memori.log` is how you see one, and the
Memori dashboard is the only place that shows what was stored.

The hooks never exit non-zero. A dead server, missing credentials or a slow
response degrade to "no memories", never to a lost prompt or a turn that will not
end.

## License

MIT. See [LICENSE](LICENSE).
