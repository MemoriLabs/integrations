---
name: configure
description: Set up Memori or report how it is configured. Use ONLY when the user explicitly asks about Memori itself - runs /memori:configure, pastes a Memori identity token, asks to set Memori up or point it at staging, or asks whether Memori is working. Never use it because memory was recalled or because the user mentioned something worth remembering.
version: 0.1.6
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Bash(mkdir *)
  - Bash(chmod *)
---

# /memori:configure — Memori setup

Writes and reports `~/.claude/memori/config.json`. The hooks read that file and
nothing else, so this skill is the only way Memori gets configured.

**Memori runs in the background and does not talk to the user.** Everything
below applies only while the user is asking about Memori itself. The moment they
move on, so do you: never mention Memori, capture, recall, extraction, entity
IDs, or hooks again, and never tell someone that what they just said will be
remembered. Telling you something is not asking you about the plugin.

Arguments passed: `$ARGUMENTS`

---

## No args — report and guide

Read the file. A missing file means not configured, which is not an error.

**Never print the identity token in full** — show the first 12 characters and
stop. Show `set` or `not set` for the client key; it is a public per-environment
value and its content helps nobody.

```
api_url          https://api.memorilabs.ai      (required)
entity_id        jane-doe                       (required)
identity_token   id_abc123def4…                 (required)
application_env  production                     optional, default production
api_header_value set                            from application_env
debug            off                            optional, default off
```

Then the next step:

- **Nothing set** → *"Give me your API URL, identity token and entity ID and
  I'll save them. The identity token is on your Memori dashboard and starts
  with `id_`."*
- **Something missing** → name only what is missing.
- **All three set** → say it is configured, and see below for whether it works.

Mention the optional settings only if asked or if one is wrong.
`api_header_name` exists for a deployment on its own host; leave it alone.

## Is it working?

Answer from the configuration, and be plain about what cannot be known from
here:

- **Not configured** → nothing happens at all, by design. Nothing is sent and
  nothing is recalled.
- **Configured** → recall runs before every prompt. Whether it is reaching the
  server, and whether memories are accumulating, shows up in the Memori
  dashboard and nowhere else.

A `<memori_context>` block appearing this session is the one positive signal
available from inside it. There is no negative signal: a refused token or an
unreachable server goes to the hook's stderr, which Claude Code only shows when
started with `--debug-file`. Say so rather than reporting that all is well.

**Never call the API yourself to test it.** Putting the identity token into a
shell command writes it into this session's transcript, which Memori captures
and turns into a memory. Point at the dashboard instead.

If memory seems *thin* rather than broken, the likely causes in order are:
nothing recorded on that subject yet, extraction not finished (it runs in a
worker, so a memory is not recallable the moment it is mentioned), an
`entity_id` that does not match the one the memories were recorded under, or an
identity with no read access to the pool they live in.

## With values — save them

The user may give all three at once, one at a time, or in prose. Take what they
give and keep what is already saved.

1. `mkdir -p ~/.claude/memori`
2. Read any existing file so other settings survive; merge the new values in.
3. Write the whole object back as JSON.
4. **Read it back and confirm it parses.** You are the most likely reason this
   file is ever malformed, and a hook that cannot read it stops working.
5. `chmod 600 ~/.claude/memori/config.json` — it holds a credential. On Windows
   this does nothing; say so rather than claiming the file is locked down.
6. Confirm, then show the no-args report.

```json
{
  "api_url": "https://api.memorilabs.ai",
  "entity_id": "jane-doe",
  "identity_token": "id_…",
  "application_env": "production"
}
```

**Validate before saving, and say so rather than saving something broken:**

- an identity token starts with `id_`
- an API URL starts with `http://` or `https://` and has no trailing slash
- `application_env` is `local`, `staging` or `production` — anything else leaves
  the plugin with no client key and nothing is remembered

## `clear` — remove the configuration

Delete the file. Say that memories already on the server are untouched, and that
recall and capture stop at the next prompt.

---

## Implementation notes

- **The hooks read this file once per run**, so a change takes effect at the next
  hook — which is the `Stop` ending this turn, not the next prompt. No restart.
- Nothing fires while the plugin is unconfigured: `events.run` returns before any
  handler unless all four required settings resolve.
- `application_env` supplies the client API key, so `api_header_value` is only
  set by hand on a deployment carrying its own.
- This file is the only place the identity token exists in full.
