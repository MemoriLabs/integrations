# Installing Memori for Claude Code

Persistent memory for Claude Code. It recalls what you have told Memori before
each prompt, and sends each finished turn back to be remembered.

You do not need to clone anything. Claude Code fetches the plugin itself.

## 1. What you need

`bash` and `python3` on your PATH. The plugin is pure standard library, so
there is nothing to install beyond an interpreter, and macOS and most Linux
distributions already have both.

Then four values. Nothing is guessed and nothing is defaulted.

| Value | `--config` name | Where it comes from |
|---|---|---|
| API URL | `api_url` | Your Memori deployment, e.g. `https://memori.example.com` |
| Identity token | `identity_token` | The Memori dashboard. Starts with `id_` |
| Client API key | `api_header_value` | The Memori dashboard |
| Entity ID | `entity_id` | You choose it. A lowercase slug naming who the memories are about, such as `jane-doe` |

The first three come from your Memori dashboard. If you cannot find them, ask
whoever administers Memori for your organisation.

**Get one wrong and nothing tells you.** Miss one entirely and the plugin does
nothing at all, which is at least consistent. Set one to a wrong value and the
server accepts what it is sent, returns nothing, and the session looks exactly
like a working one with nothing recorded yet. Step 3 is how you tell those
apart, and it is worth doing even if the install looked clean.

**Use the same `entity_id` in every Memori client** — the SDK, the gateway and
this plugin. A turn captured without one is accepted by the server and produces
no memories, so capture appears to succeed and nothing is ever recalled.

`entity_id` is not an access boundary. It records who a memory is *about*. Your
identity token and the pool's access control are what separate people.

## 2. Install

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs \
  --config api_url=https://memori.example.com \
  --config identity_token=id_your_token_here \
  --config api_header_value=your-client-key \
  --config entity_id=jane-doe
```

Claude Code prompts for any of the four you leave out, and keeps the identity
token and client key in your system keychain rather than in a file on disk.

**It installs disabled**, and that is deliberate: every prompt and reply goes to
a server the moment it is on, so switching it on should be something you did on
purpose. That is step 4, once step 3 has shown you the credentials work.

Optional: `MemoriLabs/integrations` holds every Memori integration, and adding
it downloads the lot. If you only want this one, limit what lands on disk by
adding the marketplace this way instead:

```bash
claude plugin marketplace add MemoriLabs/integrations \
  --sparse .claude-plugin claude
```

### Just one project

Install with `--scope project`, or leave the install as it is and switch the
plugin on only where you want it, in that project's `.claude/settings.json`:

```json
{
  "enabledPlugins": ["memori@memorilabs"]
}
```

A project can say **whether** the plugin runs. It cannot say how it is
configured — see the note on project settings further down. Your four values
stay where you put them at install time, whichever route you take.

## 3. Verify

Run the diagnostic against the copy you just installed:

```bash
~/.claude/plugins/cache/memorilabs/memori/0.1.3/bin/memori-hook --check
```

This runs while the plugin is still off, which is the point — you find out
whether the four values are right before a single turn is sent anywhere.

That path is the installed copy; `claude plugin list` prints the version to
substitute. The command is not on your PATH otherwise, because Claude Code adds
the plugin's `bin/` only inside a session.

What comes back is what a hook would see:

```
Memori for Claude Code 0.1.3

Configuration a hook would see
  api url     https://memori.example.com   (settings.json)
  entity id   jane-doe                     (settings.json)
  identity    id_your_toke...              (settings.json)
  client key  set                          (settings.json)

Calling /v1/recall ...
  OK, 0 memories returned.

The endpoints capture and compaction use ...
  /v1/compaction          OK
  /v1/conversation/turn   reachable, credentials accepted
  /v1/augmentation        reachable, credentials accepted
```

`0 memories returned` on a fresh install is correct — nothing has been recorded
yet.

All four lines under the configuration heading say where each value came from,
because more than one source can supply a setting and that is the part that
trips people up.

Recall working proves nothing about capture, which is why the three endpoints
below it are checked separately. An identity that can read but not write leaves
memory looking fine while nothing new is ever recorded.

## 4. Turn it on

Once the diagnostic is clean:

```bash
claude plugin enable memori@memorilabs
```

Confirm it landed:

```bash
claude plugin list
```

```
Installed plugins:

  ❯ memori@memorilabs
    Version: 0.1.3
    Scope: user
    Status: ✔ enabled
```

From here you can also ask Claude **Is Memori working?** in a session and a
bundled skill runs the same diagnostic. If it answers in prose instead of
running anything, ask it to **run the Memori diagnostic**.

## 5. Use it

```bash
claude
```

That is all. Recall runs before each prompt, capture runs when each turn ends.
Nothing is announced. Working correctly, it is not noticeable.

If you want to watch it happen rather than take that on faith:

```bash
claude --debug-file /tmp/claude.log
grep -c memori_context /tmp/claude.log     # turns that had memories injected
grep -o "\[memori\][^\"]*" /tmp/claude.log # hook activity, needs debug on
```

## What gets sent

**The whole turn.** Your prompts, Claude's replies, its reasoning, every tool
call with its full arguments, every tool result in full, and the attachments
Claude Code adds to a turn.

That means **anything a session reads reaches the server**. If Claude reads a
file holding credentials, runs a command that prints a token, or you paste a
secret into a prompt, it is sent as part of the conversation and stored.

There is no redaction and no filtering. If that matters for a repository, do not
enable the plugin for it.

Two turns are never sent: one you interrupt with ESC, because Claude Code does
not signal the end of a turn it did not finish, and one where Claude Code sent no
prompt identifier (builds since v2.1.196 always do).

## When something looks wrong

**Nothing is being recalled.** In order of likelihood:

1. Nothing has been recorded on that subject yet.
2. The turns it should have come from were captured without an `entity_id`. Run
   the diagnostic and look at the entity line.
3. The memory was already delivered earlier in this Memori session. The same
   memory is not sent twice within about 30 minutes.
4. Your identity has no read access to the pool the memories live in.

**Nothing is being remembered.** Run the diagnostic first — it reaches the
capture endpoints as well as recall, so it tells you whether the turn could have
arrived at all. If those are fine, extraction only keeps what is worth keeping:
questions usually produce nothing, while stated facts, preferences and
constraints usually produce something.

Very large turns are the other cause. A turn carrying a few hundred kilobytes of
tool output — long automated runs, large file reads, screenshots — is stored but
may produce no memories.

**Everything went quiet.** The plugin never fails loudly, by design: a broken
setup and a working one look identical from inside a session. That is what the
diagnostic is for. Three things are the exception, because they never fix
themselves and would otherwise be invisible: rejected credentials, a missing
prompt identifier, and a setting a project tried to supply. All three warn even
with debug logging off.

**A project cannot configure this.** Everything except `debug` is refused from a
project's `.claude/settings.json`. A repository can commit that file, so it does
not get to decide where your conversation is sent or what authenticates it. Set
these values with `--config`, or in `~/.claude/settings.json`.

To change a value later, run this inside Claude Code:

```
/plugin configure memori@memorilabs
```

## Updating and removing

```bash
claude plugin marketplace update memorilabs
claude plugin update memori@memorilabs
```

Restart Claude Code to pick up the new version.

Removing it entirely:

```bash
claude plugin uninstall memori@memorilabs
claude plugin marketplace remove memorilabs
```
