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


def test_both_credentials_are_required_and_sensitive():
    options = manifest("plugin.json")["userConfig"]

    for name in ("api_header_value", "identity_token"):
        assert options[name]["required"] is True, name
        assert options[name]["sensitive"] is True, name


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


def test_the_library_reports_the_manifest_version():
    import memori

    assert memori.version() == manifest("plugin.json")["version"]


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
        assert found[0]["args"] == [f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{name}.py"]


def test_every_wired_script_exists():
    for name in SCRIPTS:
        assert os.path.isfile(os.path.join(_ROOT, "hooks", f"{name}.py"))


def test_hooks_use_exec_form():
    # The docs prescribe it for anything referencing a path placeholder: each
    # arg is passed through verbatim, with no shell to quote against.
    for event in hooks():
        for handler in handlers(event):
            assert handler["type"] == "command", event
            assert handler["command"] == "python3", event
            assert "args" in handler, event


def test_capture_runs_synchronously():
    # An async hook is started and not waited for, so a non-interactive session
    # exits before it finishes and the turn is never captured. Both endpoints it
    # calls are plain inserts, measured at about 45ms together, so the turn ends
    # synchronously instead. The short timeout bounds a slow server: capture is
    # the thing worth losing there, not the turn.
    assert "async" not in handlers("Stop")[0]
    assert handlers("Stop")[0]["timeout"] <= 5


def test_recall_still_blocks():
    # It has to: the prompt goes to the model as soon as this hook returns, and
    # context that arrives afterwards has missed the turn it was recalled for.
    assert "async" not in handlers("UserPromptSubmit")[0]


def test_session_start_is_filtered_to_compactions_by_the_matcher():
    # Rather than starting a Python process on every session to discover it has
    # nothing to do.
    assert [group.get("matcher") for group in hooks()["SessionStart"]] == ["compact"]


def test_every_skill_is_loadable():
    skills = os.path.join(_ROOT, "skills")

    for name in os.listdir(skills):
        path = os.path.join(skills, name, "SKILL.md")
        assert os.path.isfile(path), name

        front = frontmatter(path)
        assert front.get("name"), name
        assert front.get("description"), name
