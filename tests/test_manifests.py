"""
The JSON Claude Code reads before any of our code runs.

`claude plugin validate` checks these against the published schema, but it needs
the CLI, and it will not catch the things specific to this plugin: that the paths
in hooks.json point at files that exist, that capture stays non-blocking and
recall stays blocking, or that the two manifests still agree with each other.

The two manifests live at different levels: plugin.json belongs to this plugin,
marketplace.json belongs to the repository and catalogues every integration in
it. So `claude plugin validate` has to be pointed at each of them separately.
"""

import json
import os

from conftest import _ROOT

SCRIPTS = ("session_start", "stop", "user_prompt_submit")

SHIM = "python.sh"

REPO = os.path.dirname(_ROOT)

NAME = "memori"


def manifest(name):
    with open(os.path.join(_ROOT, ".claude-plugin", name)) as f:
        return json.load(f)


def catalogue():
    """The repository's marketplace manifest, which sits a level above us."""

    with open(os.path.join(REPO, ".claude-plugin", "marketplace.json")) as f:
        return json.load(f)


def entry():
    """Our own row in that catalogue. Found by name -- siblings will be added."""

    found = [p for p in catalogue()["plugins"] if p["name"] == NAME]

    assert len(found) == 1, f"expected exactly one {NAME} entry, got {len(found)}"

    return found[0]


def hooks():
    with open(os.path.join(_ROOT, "hooks", "hooks.json")) as f:
        return json.load(f)["hooks"]


def handlers(event):
    return [handler for group in hooks()[event] for handler in group["hooks"]]


def frontmatter(path):
    with open(path) as f:
        body = f.read()

    _, _, rest = body.partition("---\n")
    block, _, _ = rest.partition("\n---")

    found = {}

    for line in block.splitlines():
        key, separator, value = line.partition(":")
        if separator and not key.startswith(" "):
            found[key.strip()] = value.strip()

    return found


def test_the_plugin_manifest_declares_what_it_needs():
    plugin = manifest("plugin.json")

    assert plugin["name"] == "memori"
    assert plugin["version"]
    for field in ("$schema", "description", "homepage", "keywords", "repository"):
        assert plugin[field], field


def test_the_plugin_installs_disabled():
    # It talks to an external service the moment it is on, which is the case the
    # docs single out for this field.
    assert manifest("plugin.json")["defaultEnabled"] is False


def test_the_manifest_asks_for_no_configuration():
    # `userConfig` would put the credential in Claude Code's own store, which
    # only a hook process can read -- and then no skill could report on it. The
    # configure skill owns the file instead.
    assert "userConfig" not in manifest("plugin.json")


def test_the_configure_skill_owns_every_setting_the_hooks_read():
    # A setting the skill never mentions is one nobody can discover, since there
    # is no generated form any more.
    from memori import config

    with open(os.path.join(_ROOT, "skills", "configure", "SKILL.md")) as f:
        body = f.read()

    for name in config.DEFAULTS:
        assert name in body, name


def test_the_configure_skill_names_the_environments_that_have_a_key():
    # Naming one the resolver has no key for leaves the plugin unconfigured.
    from memori import config

    with open(os.path.join(_ROOT, "skills", "configure", "SKILL.md")) as f:
        body = f.read()

    for name in config.API_KEYS:
        assert name in body, name


def test_the_configure_skill_never_prints_a_whole_token():
    # It reads a file holding one, and is read by a model that will happily echo
    # what it was shown unless told not to.
    with open(os.path.join(_ROOT, "skills", "configure", "SKILL.md")) as f:
        body = f.read().lower()

    assert "never print the identity token in full" in body


def test_the_two_manifests_agree():
    plugin = manifest("plugin.json")
    row = entry()

    assert row["name"] == plugin["name"]
    assert row["description"] == plugin["description"]

    # The version is deliberately duplicated. `claude plugin tag` reads both and
    # refuses to tag a release when they disagree, so the copy is what makes the
    # release check possible -- but only if something keeps them in step, which
    # is this assertion.
    assert row["version"] == plugin["version"]


def test_the_catalogue_points_at_this_directory():
    source = entry()["source"]

    assert source.startswith("./")
    assert os.path.isdir(os.path.join(REPO, source))
    assert os.path.samefile(os.path.join(REPO, source), _ROOT)


def test_the_skills_are_versioned_with_the_plugin():
    plugin = manifest("plugin.json")["version"]
    skills = os.path.join(_ROOT, "skills")

    for name in os.listdir(skills):
        front = frontmatter(os.path.join(skills, name, "SKILL.md"))
        assert front.get("version") == plugin, name


def test_every_event_runs_its_own_script():
    wired = {
        "SessionStart": "session_start",
        "Stop": "stop",
        "UserPromptSubmit": "user_prompt_submit",
    }

    for event, name in wired.items():
        found = handlers(event)
        assert len(found) == 1, event
        assert found[0]["args"] == [
            f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{SHIM}",
            f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{name}.py",
        ]


def test_every_wired_script_exists():
    for name in SCRIPTS:
        assert os.path.isfile(os.path.join(_ROOT, "hooks", f"{name}.py"))

    assert os.path.isfile(os.path.join(_ROOT, "hooks", SHIM))


def test_hooks_use_exec_form():
    # The docs prescribe it for anything referencing a path placeholder: each
    # arg is passed through verbatim, with no shell to quote against.
    for event in hooks():
        for handler in handlers(event):
            assert handler["type"] == "command", event
            assert handler["command"] == "bash", event
            assert "args" in handler, event


def test_every_event_reaches_python_through_the_shim():
    # Not `python3` directly. On Windows that name resolves to the Microsoft
    # Store stub, which runs and exits 49 having done nothing, so the plugin
    # would look installed and remember nothing. The shim probes each candidate
    # by running it.
    for event in hooks():
        for handler in handlers(event):
            assert handler["args"][0].endswith(f"/hooks/{SHIM}"), event


def test_the_shim_refuses_an_interpreter_too_old_to_parse_the_hooks():
    # `exec` replaces the shim, so a SyntaxError from an ancient interpreter
    # would surface as the hook's own non-zero exit -- the failure the shim
    # exists to prevent. 3.9 is what macOS ships and the oldest the library is
    # tested against; raising it above that would strand default macOS.
    with open(os.path.join(_ROOT, "hooks", SHIM)) as f:
        body = f.read()

    assert "sys.version_info >= (3, 9)" in body


def test_the_shim_never_fails_the_hook():
    # A non-zero exit is a blocking error to Claude Code: on UserPromptSubmit it
    # erases what the user typed. So a missing interpreter has to degrade to no
    # memories, the same as an unreachable server does. `set -e` would undo that
    # from any line in the file.
    with open(os.path.join(_ROOT, "hooks", SHIM)) as f:
        body = f.read()

    # The comments say both of these strings, so only the code is read.
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )

    assert "set -e" not in code
    assert "exit 1" not in code
    assert code.rstrip().endswith("exit 0")


def test_capture_runs_synchronously():
    # An async hook is started and not waited for, so a non-interactive session
    # exits before it finishes and the turn is never captured. Both endpoints it
    # calls are plain inserts, so the turn ends synchronously instead. The
    # timeout still bounds a slow server -- capture is the thing worth losing
    # there, not the turn -- but a turn now carries the whole transcript rather
    # than the conversation alone, and two seconds stopped fitting one.
    assert "async" not in handlers("Stop")[0]
    assert handlers("Stop")[0]["timeout"] <= 10


def test_recall_still_blocks():
    # It has to: the prompt goes to the model as soon as this hook returns, and
    # context that arrives afterwards has missed the turn it was recalled for.
    assert "async" not in handlers("UserPromptSubmit")[0]


def test_session_start_is_filtered_to_compactions_by_the_matcher():
    # Rather than starting a Python process on every session to discover it has
    # nothing to do.
    assert [group.get("matcher") for group in hooks()["SessionStart"]] == ["compact"]


def test_every_skill_is_loadable():
    # Claude Code only scans <plugin>/skills/<name>/SKILL.md, and a file it
    # cannot read frontmatter from loads as zero skills without saying so.
    skills = os.path.join(_ROOT, "skills")

    for name in os.listdir(skills):
        path = os.path.join(skills, name, "SKILL.md")
        assert os.path.isfile(path), name

        with open(path) as f:
            assert f.read().startswith("---\n"), name

        front = frontmatter(path)
        assert front.get("name"), name
        assert front.get("description"), name


def test_the_configure_skill_names_the_file_it_owns():
    with open(os.path.join(_ROOT, "skills", "configure", "SKILL.md")) as f:
        body = f.read()

    assert "~/.claude/memori/config.json" in body


def test_the_configure_skill_answers_is_it_working():
    # There is no separate diagnostic, so setup and "why is nothing being
    # remembered" have to reach the same skill. The description is what decides.
    with open(os.path.join(_ROOT, "skills", "configure", "SKILL.md")) as f:
        description = frontmatter(
            os.path.join(_ROOT, "skills", "configure", "SKILL.md")
        )["description"]
        body = f.read()

    assert "working" in description and "recalled" in description

    # Nothing the plugin does is observable from inside a session, so the only
    # honest answer sends the user somewhere else.
    assert "dashboard" in body
