# Memori for Claude Code: quickstart

## Before you start

You need three values from your Memori administrator or dashboard:

- **API URL**, such as `https://api.memorilabs.ai`
- **Identity token**, which starts with `id_`
- **Entity ID**, a lowercase name for the person whose memories this plugin
  should use, such as `jane-doe`

Use the same entity ID in every Memori client. There is no API key to go and
find; the plugin carries it.

Once enabled and configured, the plugin sends your full conversation to your
Memori server with no redaction: prompts, replies, tool calls, tool results and
attachments. See [what gets sent](../README.md#what-gets-sent) before enabling
it somewhere that matters.

## 1. Install

### Claude Code Desktop

Plugins work in **Local** and **SSH** Code sessions, but not Remote sessions.

1. Open the **Code** tab and start a Local session.
2. Click **+** beside the prompt box, then choose **Plugins** → **Manage
   plugins**.
3. Open **Marketplaces**, add `MemoriLabs/integrations`, and return to the
   plugin browser.
4. Find **Memori** and install it for your user account.
5. Enable Memori.

Start a new Code session, then configure it below.

### Command line

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs
claude plugin enable memori@memorilabs
```

The plugin starts disabled, so the final command is required.

## 2. Configure

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

## 3. Check it worked

Ask Claude:

> Is Memori working?

It reads your configuration back. It sends nothing and changes nothing.

That is it. Memori now recalls relevant memories before each prompt and captures
new ones after each completed turn.

## If something is wrong

Nothing else about the plugin is visible from inside a session: the only thing it
ever adds to a conversation is the memories it recalled, so a failure is silent
by design. Work through these in order.

- Confirm the plugin is enabled with `claude plugin list`.
- Confirm your configuration with `/memori:configure`, and that every Memori
  client uses the same entity ID.
- Check the Memori dashboard, the only place that shows whether memories are
  accumulating. On a new account it stays empty until a turn or two has been
  captured and extracted.
- Read the hook's own errors:

  ```bash
  claude --debug-file memori.log
  ```

  A rejected token, an entity that cannot read its pool, a url that is not a
  Memori server, and a config file that cannot be parsed are all written there in
  full.

## Uninstalling

Removing the plugin leaves `~/.claude/memori/config.json` behind, which holds
your settings and identity token. Delete `~/.claude/memori/` if you want it gone.
