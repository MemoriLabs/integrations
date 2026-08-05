# Memori for Claude Code: quickstart

## Before you start

You need three values from your Memori administrator or dashboard:

- **API URL**, such as `https://api.memorilabs.ai`
- **Identity token**, which starts with `id_`
- **Entity ID**, a lowercase name for the person whose memories this plugin
  should use, such as `jane-doe`

Use the same entity ID in every Memori client.

Pointing at staging? Say so while configuring. `application_env` defaults to
`production` and supplies the client API key, so there is no key to go and find.

## Install in Claude Code Desktop

Plugins work in **Local** and **SSH** Code sessions, but not Remote sessions.

1. Open the **Code** tab and start a Local session.
2. Click **+** beside the prompt box, then choose **Plugins** → **Manage
   plugins**.
3. Open **Marketplaces**, add `MemoriLabs/integrations`, and return to the
   plugin browser.
4. Find **Memori** and install it for your user account.
5. Enable Memori.

Start a new Code session, then configure it below.

## Install from the command line

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs
claude plugin enable memori@memorilabs
```

The plugin starts disabled, so the final command is required.

## Configure it

Start a session and run:

```
/memori:configure
```

Claude asks for the three values and writes them to
`~/.claude/memori/config.json`, readable only by you. Give them in one go if you
prefer:

```
/memori:configure https://api.memorilabs.ai id_your_token_here jane-doe
```

Run it again any time to see what is set or to change something.

## Check your setup

Start Claude Code and ask:

> Is Memori working?

Claude reads your configuration back. It sends nothing and changes nothing.

Beyond that, the Memori dashboard is the only place that shows whether memories
are accumulating. On a new account it stays empty until a turn or two has been
captured and extracted.

Nothing else about the plugin is visible from inside a session: the only thing
it ever adds to a conversation is the memories it recalled, so a failure is
silent by design. To see one, start Claude Code with a debug log and read it:

```bash
claude --debug-file memori.log
```

A rejected token, an entity that cannot read its pool, a url that is not a
Memori server, and a config file that cannot be parsed are all written there in
full, whether or not `debug` is set in your configuration.

That is it. Memori now recalls relevant memories before each prompt and captures
new ones after each completed turn.

## Important privacy note

When enabled, the plugin sends the full conversation to your Memori server,
including prompts, replies, tool calls, tool results, and attachments. Do not
enable it in a project where that is not appropriate.

It also writes one file locally, `~/.claude/memori/config.json`, holding your
settings and the identity token, `chmod 600`. No conversation and no log.
Uninstalling does not remove it — delete `~/.claude/memori/` if you want it gone.

## Need help?

- Ask Claude **"is Memori working?"** and it will read your configuration back.
- Confirm the plugin is enabled with `claude plugin list`.
- Change your configuration with `/memori:configure`.
- If memories are not appearing, confirm that every Memori client uses the same
  entity ID, and that `application_env` names the deployment you meant.
- To see why something failed, run `claude --debug-file memori.log` and read it.
