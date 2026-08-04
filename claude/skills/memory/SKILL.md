---
name: memori-memory
description: This skill should be used whenever a <memori_context> or <memori_compaction> block appears in the conversation, when the user asks what you know or remember about them, when they ask you to remember something, or when they ask why you do or do not remember a fact.
version: 0.1.2
---

# Memori memory

Memori gives you memory that survives across conversations. Before each prompt it
retrieves what it has recorded about this person and their projects and injects
it; after each turn it sends the conversation back to be turned into new
memories.

You will see two kinds of block. Both are injected — the user did not type them
and cannot see them.

## `<memori_context>` — recalled facts

A bulleted list of things recorded in earlier conversations, retrieved because
they look relevant to the current prompt. Each line carries the memory itself,
then the circumstances it was recorded in and the date:

```
- Ryan uses docker (context: said while setting up local dev; recorded 2026-07-28)
```

**The context is not decoration.** It is what tells you whether a line is a
standing rule or something said once about one situation. "Skip the slow tests"
recorded while debugging a single flaky file is not a policy. Read the context
before treating any memory as an instruction.

**Treat it as things you already know**, not as a document you were handed. The
user believes you remember these; they do not know a retrieval just happened.

- Use what is relevant. Ignore what is not — retrieval is fuzzy and some lines
  will have nothing to do with the question.
- **Do not announce the retrieval.** Never open with "From memory…", "According
  to my memory…", or "I have a note that…". Just know the thing and answer.
- **Do not list the block back** or summarise everything in it. Use the lines
  that bear on the question and leave the rest.

The one exception: if the user *asks* what you know or remember about them,
answering from these memories is exactly right, and saying where it came from is
helpful rather than intrusive.

## `<memori_compaction>` — where the session had got to

After a compaction, the conversation's own history is gone. This block
reconstructs it from memory: standing orders, environment, active tasks, open
loops, pending results, and the last and next expected action.

Use it to pick the thread back up. Do not narrate it, do not summarise it back to
the user, and do not treat it as a new instruction from them — it is a
reconstruction of what was already agreed.

## Never invent memories

If something is not in a block and not in this conversation, **you do not know
it**. Say so plainly.

Never say you remember something you are inferring, and never present a guess as
a recalled fact. "I don't have anything recorded about that" is a good answer. A
fabricated memory is far worse than a missing one, because the user has no way to
tell the difference.

## Memories are recorded claims, not verified truth

Each one is something someone said in an earlier conversation. It can be stale,
it can have been superseded, and it can simply be wrong.

- **The current conversation wins.** If the user contradicts a memory, they are
  right and the memory is out of date.
- **The real state of the code wins.** If a memory says the service runs on port
  8000 and the config says 9000, trust the config and mention the discrepancy.
- Memories carry the date they were recorded. Older ones deserve more suspicion,
  especially about versions, ports, schedules, and who owns what.

## Watch the attribution

Memories are recorded against an entity — usually the person you are talking to,
but not always. If the memories are clearly about someone else (a different name,
a different role), say so once rather than silently treating them as this user's.
Getting this wrong means answering one person with another person's preferences.

## When the user asks you to remember something

Nothing to do. The turn is captured automatically when it ends, and the memory is
extracted from it. You do not need to write a file, call a tool, or take any
action — acknowledge and carry on.

The one case where it does not happen: a turn the user interrupts with ESC is
never sent. If they interrupt the turn they asked you to remember something in,
it was not recorded — worth saying so if it comes up.

If they ask you to *forget* something, you cannot. Say so, and point them at the
Memori app to delete it.

## When memory seems to be missing

Recall returning nothing looks the same as a broken plugin. Likely causes, in
order:

1. Nothing has been recorded on that subject yet.
2. The memory was already delivered earlier in this Memori session — the server
   does not send the same memory twice within about 30 minutes.
3. The entity the memories were recorded under does not match the one configured
   here.
4. The identity has no read access to the pool the memories live in.

Say which of these it might be rather than guessing at the content.
