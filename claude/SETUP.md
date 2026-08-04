# Setting up Memori for Claude Code

From nothing to a working memory loop.

## 1. What you need first

Four values. The plugin will not run until it has all four, and it does not
guess any of them.

**The API URL** of your Memori deployment. The plugin calls `/v1/recall`,
`/v1/conversation/turn`, `/v1/augmentation` and `/v1/compaction` beneath it.

**An identity token.** Starts with `id_`. It ties memories to you and is what
the server authenticates.

**A client API key.** The deployment's shared key, sent as the
`X-Memori-API-Key` header.

**An entity id.** A lowercase slug naming who the memories are about, such as
`jane-doe`. See [entity_id](#entity_id) below before you pick one.

The URL, token and key come from your Memori deployment. Where you get them
depends on how your organisation runs Memori; ask whoever administers it.

## 2. Install

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs
claude plugin enable memori@memorilabs
```

The install prompts for the four values from step 1.

`MemoriLabs/integrations` is a monorepo of Memori integrations. If you would
rather not have all of it on disk, limit the checkout:

```bash
claude plugin marketplace add MemoriLabs/integrations \
  --sparse .claude-plugin claude
```

**It installs disabled**, and that is deliberate: every prompt and reply goes to
a server the moment it is on, so switching it on should be a thing you did on
purpose. Nothing happens until you do.

You can set configuration in the install step, which is the whole setup in one
go:

```bash
claude plugin install memori@memorilabs \
  --config api_url=https://memori.example.com \
  --config identity_token=id_your_token_here \
  --config api_header_value=your-client-key \
  --config entity_id=jane-doe
```

Claude Code prompts for any of the four you leave out.

Check it landed:

```bash
claude plugin list
```

```
Installed plugins:

  ❯ memori@memorilabs
    Version: 0.1.2
    Scope: user
    Status: ✔ enabled
```

> **Installing copies the plugin.** The files are copied into
> `~/.claude/plugins/cache/memorilabs/memori/<version>/`, and that copy is what
> runs, not the marketplace checkout.
>
> That means **editing a checkout does not change an installed plugin**.
> Measured: an edit does not reach the cache, and `marketplace update` does not
> fetch it either, because the install is pinned to the version in the manifest.
> To pick up changes, bump `version` in `.claude-plugin/plugin.json`, or
> reinstall.
>
> If you added the marketplace from a **local path** rather than from GitHub, the
> entry keeps that path, so moving or deleting the directory breaks the plugin
> with `failed to load: cache-miss`. Re-add the marketplace from the new
> location.

### Per-project instead of everywhere

Install with `--scope project`, or enable it in that project's
`.claude/settings.json`:

```json
{
  "enabledPlugins": ["memori@memorilabs"]
}
```

## 3. Configure

Five settings. The first four are required, and the hooks do nothing until all
four are set.

| Setting | Purpose | Default |
|---|---|---|
| `api_url` | Base URL of your Memori deployment | none |
| `identity_token` | Your Memori identity, sent as the bearer token | none |
| `api_header_value` | Client API key for the deployment | none |
| `entity_id` | Who the memories are *about* | none |
| `debug` | Log hook activity to stderr | off |

None of the four is defaulted. A wrong value fails silently: the server accepts
what the plugin sends and no memories come back, which is indistinguishable from
having nothing recorded yet.

Set them with `--config` at install, or `/plugin configure memori@memorilabs`
inside Claude Code to change one later:

```bash
claude plugin install memori@memorilabs \
  --config api_url=https://memori.example.com \
  --config identity_token=id_your_token_here \
  --config api_header_value=your-client-key \
  --config entity_id=jane-doe
```

Claude Code prompts for anything you leave out, and keeps `identity_token` and
`api_header_value` in the system keychain rather than in a file on disk.

### One place they can never come from

**A project's `.claude/settings.json` is refused on purpose.** A repository can
commit that file, and Claude Code merges its `env` block into every hook process
before the hook gets a say, so a cloned repository could otherwise point capture
at a server of its choosing, and nothing in the session would look wrong. Claude
Code draws the same line for its own plugin config, which it stopped reading from
project settings in v2.1.207.

Everything except `debug` is refused that way, and naming the setting is enough
to refuse it; the value is never inspected. The diagnostic reports what it ignored,
and so does the hook, on stderr:

```
Ignored from this project's .claude/settings.json: api_url
  A repository can commit that file, so it does not get to say where
  your conversation is sent or what authenticates it. Set these in
  ~/.claude/settings.json instead, or configure the plugin.
```

If you genuinely want a different Memori per project, install with
`--scope project` and configure it per machine.

### entity_id

`entity_id` is what a captured turn is attributed to. A turn sent without one is
accepted by the server and produces no memories, so capture appears to succeed
and nothing is ever recalled. It is required rather than defaulted for that
reason.

Use a lowercase slug, such as `jane-doe`, and use the same value in every
Memori client: the SDK, the gateway, and this plugin.

It is not an access boundary. Memories written into a pool are recalled by
anyone whose identity can read that pool, whatever entity they ask as.
`identity_token` and the pool's access control separate people; `entity_id`
records who a memory is about.

## 4. Verify

Open Claude Code and ask it:

> Is Memori working?

The bundled `memori-check` skill runs the diagnostic and reports the result.
This requires no path, no remembered command, and nothing on `PATH`.

What it runs is `memori-hook --check`, and what comes back looks like this:

```
Memori for Claude Code 0.1.2

Configuration a hook would see
  api url     https://memori.example.com   (settings.json)
  entity id   jane-doe                     (settings.json)
  identity    id_your_toke...              (settings.json)
  client key  set                          (settings.json)

Calling /v1/recall ...
  OK, 8 memories returned.

The endpoints capture and compaction use ...
  /v1/compaction          OK
  /v1/conversation/turn   reachable, credentials accepted
  /v1/augmentation        reachable, credentials accepted
```

Each line says where the value came from, because that is the part that trips
people up: more than one source can supply a setting, and this is how you see
which one won.

The check resolves configuration exactly as a hook does, and writes nothing. The
three endpoints below recall are reached with a body the server is certain to
refuse, which proves the route is there and the credentials were accepted without
creating anything. They are checked because **recall working proves nothing about
capture**. An identity that can read but not write leaves memory looking fine
while nothing new is ever recorded.

`0 memories returned` on a fresh install is correct: nothing has been recorded
yet.

**From your own terminal, `memori-hook` is not on your `PATH`.** Claude Code adds
the plugin's `bin/` to the Bash tool's `PATH` while the plugin is enabled, and
only there, which is why asking Claude works and typing the bare command in a
terminal gives you `command not found`. If you want to run it outside a session,
use the installed copy:

```bash
~/.claude/plugins/cache/memorilabs/memori/0.1.2/bin/memori-hook --check
```

Substitute the version you have; `claude plugin list` prints it.

## 5. Use it

```bash
claude
```

That's all. Recall runs before each prompt, capture runs when each turn ends.
Nothing is announced. Working correctly, it is not noticeable.

To confirm it is running:

```bash
claude --debug-file /tmp/claude.log
grep -c memori_context /tmp/claude.log     # turns that got memories injected
grep -o "\[memori\][^\"]*" /tmp/claude.log # hook activity, needs debug on
```

## 6. When something looks wrong

**Nothing is being recalled.** In order of likelihood:

1. Nothing has been recorded on that subject yet.
2. The turns it should have come from were captured without an `entity_id`, so
   no memories were made from them. Run `--check` and look at the entity line.
3. The memory was already delivered earlier in this Memori session. The server
   will not send the same memory twice within about 30 minutes. Wait it out, or
   ask something different.
4. Your identity has no read access to the pool the memories live in.

**Nothing is being remembered.** Run `--check` first: it reaches
`/v1/conversation/turn` and `/v1/augmentation` as well as recall, so it tells
you whether the turn could have arrived at all. If those are fine, extraction
only keeps things worth keeping: questions usually produce nothing, while
stated facts, preferences and constraints usually produce something. Check the
turn arrived:

```sql
SELECT id, role, LEFT(content, 60) FROM message ORDER BY id DESC LIMIT 10;
```

Two turns that are never sent, by design: one you interrupted with ESC, and one
where Claude Code sent no `prompt_id` (it has since v2.1.196; older builds print
a warning on every turn saying so).

**It feels slow.** Recall is on the critical path of every prompt, with a 10
second ceiling. Capture runs at the end of a turn and is two inserts, so it adds
a few tens of milliseconds; the extraction it queues is done by a worker
afterwards.

**Everything went quiet.** The hook never fails loudly by design, so a broken
setup and a working one look identical from inside a session. That is what
`--check` is for. Three things are the exception, because they never fix
themselves and would otherwise be invisible: a 401, a `prompt_id` this build of
Claude Code did not send, and a setting this project tried to supply. All three
warn even with debug off.

## 7. Updating and removing

To pick up someone else's changes, pull the repo and update:

```bash
git pull
claude plugin marketplace update memorilabs   # re-read the manifest
claude plugin update memori@memorilabs        # restart to apply
```

**An update only lands if the version changed.** The install is pinned to the
`version` in `.claude-plugin/plugin.json`, and the cached copy is what runs, so
a pull that changes code but not the version leaves your install exactly as it
was. If you need the change without a version bump, reinstall:

```bash
claude plugin uninstall memori@memorilabs
claude plugin install memori@memorilabs
claude plugin enable memori@memorilabs
```

Removing it entirely:

```bash
claude plugin uninstall memori@memorilabs
claude plugin marketplace remove memorilabs
```

If you moved your clone, the marketplace still points at the old path and the
plugin fails with `cache-miss`. Remove the marketplace and add it again from the
new location.

## What the plugin sends

Only conversation: your prompts, Claude's replies, and tool **names** as
`[tool: Bash]`.

Never tool output, never tool arguments, never Claude's thinking, never subagent
traffic. Tool results are the bulk of any transcript and the likeliest place for
a secret to be sitting in a file that was read, so they are excluded wholesale.

Note that **your prompts are sent verbatim**. If you paste a credential into a
prompt, it reaches Memori as conversation, the same as any other text.

**A turn you interrupt is not sent at all.** `Stop` is what triggers capture, and
Claude Code does not fire it when you press ESC. Nothing else could pick the turn
up without the plugin keeping state between sessions, which it does not do. Say
it again in the next turn if it mattered.
