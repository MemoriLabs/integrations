# Memori integrations

Official Memori integration for [Claude Code](https://claude.com/product/claude-code) - persistent memory for your agent.

---

## Memori for Claude Code

**Your agent learns from every session - including from what it actually did.**

Claude Code forgets everything between sessions: the bug you diagnosed yesterday, the convention you corrected twice, the command that finally worked. Memori fixes that. Before each prompt it recalls what it already knows about you, your codebase, and your past sessions, then injects it. After each turn, it learns from what happened, **including from the execution trace: what Claude tried, what failed, and what worked.**

It also survives compaction. When Claude Code compacts a long conversation, recalled memories fall out of context with everything else. Memori re-injects a summary of what the session had established, so the thread survives.

### Quickstart

**1. Install**

```
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs
claude plugin enable memori@memorilabs
```

The plugin starts disabled, so the final command is required. Then start a new session so the hooks load.

**2. Configure**

Start a session and run:

```
/memori:configure
```

Claude asks for the three values and writes them to `~/.claude/memori/config.json`, readable only by you. Give them in one go if you prefer:

```
/memori:configure https://api.memorilabs.ai id_your_identity_token_here jane-doe
```

Run it again any time to see what is set or to change something.

Full options (API keys, self-hosted endpoints, entity configuration):
[Install and configure →](https://github.com/MemoriLabs/integrations/blob/main/claude/INSTALL.md)

### How it works

1. **Recall:** before each prompt, the plugin asks Memori what it knows that's relevant and injects it into context.
2. **Act:** Claude works with that knowledge in hand: past fixes, project conventions, known dead ends.
3. **Remember:** after each turn, the full exchange is sent to Memori, which structures it into durable memories. Stale memories are superseded rather than accumulating; duplicates are consolidated.

Memori treats agent trace as a first-class input, not just what was said, but what was done. That's what makes it useful for agentic workloads (long coding sessions, CI agents, QA test automation), where the most valuable lessons live in tool calls and their outcomes, not in prose.
[Benchmarks and architecture →](https://memorilabs.ai/benchmark)

### Privacy: what gets sent

We'd rather you know exactly how this works than find out later.

The whole turn is sent to Memori: your prompts, Claude's replies, its thinking, every tool call with its full arguments, every tool result in full, and the attachments Claude Code adds. There is no redaction and no filtering, so anything a session reads reaches the server: a credential in a file Claude opened, a token printed by a command it ran, or one you pasted into a prompt yourself.

The only thing removed is the plugin's own injected context. A turn is sent once, no conversation is kept on disk, and an interrupted turn is not remembered.

> **Running in a regulated or security-sensitive environment?** Memori deploys
> as a private single-tenant VPC or fully on-prem; trace never leaves your infrastructure. [Talk to us →](https://cal.com/memori-labs/getting-started)

### What it keeps on disk

One file, `~/.claude/memori/config.json`, written by `/memori:configure` with `chmod 600`: your settings and nothing else. It is the only place the identity token exists in full.

It is also the only place the plugin reads settings from. There are no environment variables, so a repository cannot configure Memori - a cloned repo can never redirect your memories to someone else's server.

Uninstalling the plugin does not remove the file. To delete it:

```
rm -rf ~/.claude/memori
```

### Designed to never block Claude

The plugin degrades gracefully, always in the same direction: the only thing it ever adds to a conversation is the memories it recalled. No status banners, no warnings, no interruptions.

The hooks never exit non-zero. A dead server, missing credentials, or a slow response degrade to "no memories", never to a lost prompt or a turn that will not end.

Because failures are deliberately invisible in the conversation, diagnostics live elsewhere: errors go to the hook's stderr (`claude --debug-file memori.log`), and the [Memori dashboard](https://app.memorilabs.ai) shows what was stored.

### Requirements

- Claude Code (latest version recommended)
- A Memori account or self-hosted Memori instance

### Troubleshooting

**Missing memories?**

Run `claude --debug-file memori.log` and check for hook errors; verify credentials with `/memori:configure`.

**Memories look wrong or stale?**

Inspect and manage them in the dashboard. Every memory is inspectable and can be removed from recall.

**If the behavior persists**

[Open an issue](https://github.com/MemoriLabs/integrations/issues) and include the output from `claude --debug-file memori.log`.

### Enterprise

Private VPC or on-prem deployment, access-controlled memory pools per agent fleet, an immutable audit trail of every memory read, write, and permission change, and storage in your own database. If your agents run in production, this is the deployment shape for you.