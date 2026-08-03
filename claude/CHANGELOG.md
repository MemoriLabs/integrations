# Changelog

An installed plugin is pinned to the `version` in `.claude-plugin/plugin.json`,
so every change that should reach anyone needs a new version here.

## 0.1.1

First release. Three hooks, two skills, and standard library Python only.

- `entity_id` is required alongside the two credentials. A turn captured without
  one is accepted by the server and then produces no memories, so defaulting it
  to your username bought a plugin that looked configured and never recalled
  anything.
- `UserPromptSubmit` recalls from Memori and injects what it knows.
- `Stop` sends the finished turn to be remembered.
- `SessionStart` rebuilds the session's context after a compaction.
- Only conversation is sent: prompts, replies, and tool **names**. Never tool
  output, tool arguments, thinking, or subagent traffic.
- A project's `.claude/settings.json` cannot configure the plugin. Claude Code
  merges its `env` block into every hook process, so a repository could
  otherwise redirect capture; anything a workspace supplies is refused by name.
- Redirects that leave the host, or drop from https to http, are refused rather
  than followed with the credentials attached.
- Server data cannot close the block it is injected into. Memory content is
  attacker-influenceable, so a memory carrying `</memori_context>` would end the
  block early and whatever followed would read as though it came from outside.
- The hook never exits non-zero. A dead server, bad credentials or a slow
  response degrade to "no memories", never to a lost prompt or a turn that will
  not end.
