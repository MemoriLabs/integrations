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
what the session had established — standing orders, environment, open loops,
where you left off — and injects that, so the thread survives the compaction.

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
  --config identity_token=id_your_token_here \
  --config api_header_value=your-client-key \
  --config entity_id=your-name
claude plugin enable memori@memorilabs
memori-hook --check
```

It installs disabled — everything here goes to a server the moment it is on, so
turning it on should be deliberate. `--check` then reports the configuration a
hook would see and reaches every endpoint the plugin uses, writing nothing.

**[SETUP.md](SETUP.md) is the full guide** — prerequisites, configuring it as a
user and as a developer, per-project installs, and what to do when nothing is
being recalled or remembered.

Two things worth knowing before you start:

- **`entity_id` is required, and is what a memory is attributed to.** A turn
  captured without one is accepted by the server and then makes no memories, so
  the plugin refuses to run until it is set. Use the same value everywhere you
  talk to Memori. It is not an access boundary — what you can recall is decided
  by your identity token and the pool it can read.
- **A project's `.claude/settings.json` cannot configure Memori.** A repository
  can commit that file and Claude Code merges its `env` block into every hook, so
  anything a workspace supplies is refused and named rather than used.

## What gets sent

Only conversation:

- your prompts and Claude's replies
- tool **names**, as `[tool: Bash]`

Never tool output, tool arguments, Claude's thinking, or subagent traffic — tool
results are the bulk of any transcript and the likeliest place a secret is
sitting, so they are excluded wholesale rather than scanned.

Each turn is scoped by the `prompt_id` Claude Code provides, so a turn is sent
once and nothing is kept on disk. Capture runs `async`, off the end of the turn,
so nothing waits on it. **A turn you interrupt is not remembered** — `Stop` does
not fire on ESC, and catching it later would mean keeping state between sessions.

## Safety

The hook **never exits non-zero**. A dead server, missing credentials, a corrupt
transcript, or a slow response all degrade to "no memories" — never to a lost
prompt or a turn that will not end. That is deliberate: on `UserPromptSubmit` a
blocking exit erases what you typed, and on `Stop` it forbids Claude from
stopping.

Everything is best-effort and out of the way. If Memori is down you should not
notice.

## Development

macOS and Linux. The hooks are spawned as `python3`, which Windows does not
have under that name.

```
python -m pytest tests -q
claude plugin validate ..                           # the marketplace manifest
claude plugin validate .claude-plugin/plugin.json   # the plugin manifest
```

Both. The marketplace manifest belongs to the repository, one level up, and
catalogues every integration in it; `plugin.json` belongs to this directory.
`validate` on a directory stops at the marketplace manifest, so it never reaches
`plugin.json` on its own.

`tests/test_manifests.py` covers what the schema cannot: that the wired paths
exist, that capture stays non-blocking and recall stays blocking, that the
catalogue points back at this directory, and that its version still matches
`plugin.json`.

### Layout

```
hooks/hooks.json            wires each event to its script
hooks/session_start.py      one thin entry point per event
hooks/stop.py
hooks/user_prompt_submit.py
bin/memori-hook             --check, --version, and a manual dispatcher
lib/memori/__init__.py      the version, read from the manifest
lib/memori/config.py        where every setting comes from, resolved once
lib/memori/api.py           HTTP against Memori, and how failures are reported
lib/memori/transcript.py    turning a transcript into messages
lib/memori/render.py        the two blocks injected into Claude's context
lib/memori/events.py        one function per hook event
lib/memori/hook.py          stdin in, context out
lib/memori/check.py         the diagnostic
skills/memory/SKILL.md      how Claude should treat what gets injected
skills/check/SKILL.md       running the diagnostic from inside a session
```

Entry points add `lib/` to `sys.path` and import from there, which is the same
shape Anthropic's own `hookify` plugin uses. Standard library only, so there is
still nothing to install.

### Tests

`test_lib_*.py` import the library directly and run in milliseconds. The rest
drive the real scripts as subprocesses against a stdlib HTTP stub, using hook
payloads captured from a live session in `tests/fixtures/` — that layer covers
what only a real process can: exit codes, stdout shape, and the entry points
`hooks.json` actually calls.

To drive it against a Memori backend, load the plugin from disk and enable it —
`--plugin-dir` loads it but leaves it off, because the manifest ships
`defaultEnabled: false`:

```
export MEMORI_API_URL=http://localhost:8000
export MEMORI_IDENTITY_TOKEN=id_your_token_here
export MEMORI_API_HEADER_VALUE=your-client-key
export MEMORI_ENTITY_ID=your-name

echo '{"enabledPlugins": ["memori"]}' > /tmp/dev-settings.json
claude --plugin-dir . --settings /tmp/dev-settings.json
```

Note that `MEMORI_*` in your shell does **not** win over the `env` block of your
own `~/.claude/settings.json` — that outranks it. If a dev session is reading the
wrong server, `memori-hook --check` names the source of every value.

## License

MIT. See [LICENSE](../LICENSE).
