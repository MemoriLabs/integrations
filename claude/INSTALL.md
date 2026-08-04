# Memori for Claude Code: quickstart

## Before you start

You need four values from your Memori administrator or dashboard:

- **API URL**, such as `https://memori.example.com`
- **Identity token**, which starts with `id_`
- **Client API key**
- **Entity ID**, a lowercase name for the person whose memories this plugin
  should use, such as `jane-doe`

Use the same entity ID in every Memori client.

## Install in Claude Code Desktop

Plugins work in **Local** and **SSH** Code sessions, but not Remote sessions.

1. Open the **Code** tab and start a Local session.
2. Click **+** beside the prompt box, then choose **Plugins** → **Manage
   plugins**.
3. Open **Marketplaces**, add `MemoriLabs/integrations`, and return to the
   plugin browser.
4. Find **Memori** and install it for your user account.
5. Enable Memori and enter the four values above when prompted.

Start a new Code session after enabling the plugin.

## Install from the command line

Replace the example values below, then run:

```bash
claude plugin marketplace add MemoriLabs/integrations
claude plugin install memori@memorilabs \
  --config api_url=https://memori.example.com \
  --config identity_token=id_your_token_here \
  --config api_header_value=your-client-key \
  --config entity_id=jane-doe
claude plugin enable memori@memorilabs
```

The plugin starts disabled, so the final command is required.

## Check your setup

Start Claude Code and ask:

> Is Memori working?

Claude will check the configuration and connection without saving anything.
On a new account, `0 memories returned` is normal.

That is it. Memori now recalls relevant memories before each prompt and captures
new ones after each completed turn.

## Important privacy note

When enabled, the plugin sends the full conversation to your Memori server,
including prompts, replies, tool calls, tool results, and attachments. Do not
enable it in a project where that is not appropriate.

## Need help?

- Run the check again by asking Claude to **run the Memori diagnostic**.
- Confirm the plugin is enabled with `claude plugin list`.
- Change your configuration with `/plugin configure memori@memorilabs` inside
  Claude Code.
- If memories are not appearing, confirm that every Memori client uses the same
  entity ID.
