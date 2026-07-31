import json
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFEST = os.path.join(_ROOT, ".claude-plugin", "plugin.json")
_SKILL = os.path.join(_ROOT, "skills", "memory", "SKILL.md")

DEAD_SERVER = {"MEMORI_API_URL": "http://127.0.0.1:1"}

PLUGIN_OPTIONS = {
    "MEMORI_API_HEADER_VALUE": "",
    "MEMORI_ENTITY_ID": "",
    "MEMORI_IDENTITY_TOKEN": "",
    "CLAUDE_PLUGIN_OPTION_API_HEADER_VALUE": "plugin-client-key",
    "CLAUDE_PLUGIN_OPTION_ENTITY_ID": "plugin-entity",
    "CLAUDE_PLUGIN_OPTION_IDENTITY_TOKEN": "id_from_plugin_config",
}


@pytest.fixture(scope="session")
def manifest():
    with open(_MANIFEST) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def skill():
    with open(_SKILL) as f:
        return f.read()


def test_the_manifest_declares_every_setting_the_hook_reads(manifest):
    assert set(manifest["userConfig"]) == {
        "api_header_value",
        "api_url",
        "debug",
        "entity_id",
        "identity_token",
    }


def test_every_option_has_a_title(manifest):
    # `claude plugin validate` rejects a userConfig entry without one, and it is
    # not run in CI.
    for name, option in manifest["userConfig"].items():
        assert option.get("title"), name


def test_credentials_are_marked_sensitive(manifest):
    for name in ("api_header_value", "identity_token"):
        assert manifest["userConfig"][name]["sensitive"] is True


def test_the_skill_is_where_claude_code_looks_for_it(skill):
    # Claude Code only scans <plugin>/skills/<name>/SKILL.md by default; anywhere
    # else and it loads zero skills without saying so.
    assert skill.startswith("---\n")

    frontmatter = skill.split("---")[1]
    assert "name: memori-memory" in frontmatter
    assert "description:" in frontmatter


def test_the_skill_covers_both_injected_blocks(skill):
    assert "<memori_context>" in skill
    assert "<memori_compaction>" in skill


def test_reads_configuration_from_plugin_options(recalled, run_hook, prompt_payload):
    api = recalled("a fact")

    run_hook(prompt_payload, env=PLUGIN_OPTIONS)

    request = api.requests[0]
    assert request["headers"]["Authorization"] == "Bearer id_from_plugin_config"
    assert request["headers"]["X-Memori-Api-Key"] == "plugin-client-key"
    assert request["body"]["attribution"] == {"entity": {"id": "plugin-entity"}}


def test_the_environment_overrides_plugin_options(recalled, run_hook, prompt_payload):
    api = recalled("a fact")

    run_hook(prompt_payload, env={"CLAUDE_PLUGIN_OPTION_IDENTITY_TOKEN": "id_ignored"})

    assert api.requests[0]["headers"]["Authorization"] == (
        "Bearer id_test_acme_abcdefgh"
    )


def test_a_false_debug_option_does_not_log(run_hook, prompt_payload):
    # A boolean userConfig arrives as the string "false", which is truthy.
    result = run_hook(
        prompt_payload, env={**DEAD_SERVER, "CLAUDE_PLUGIN_OPTION_DEBUG": "false"}
    )

    assert result.stderr == ""


def test_a_true_debug_option_logs(run_hook, prompt_payload):
    result = run_hook(
        prompt_payload, env={**DEAD_SERVER, "CLAUDE_PLUGIN_OPTION_DEBUG": "true"}
    )

    assert "[memori] recall failed" in result.stderr


def test_the_debug_environment_variable_still_logs(run_hook, prompt_payload):
    result = run_hook(prompt_payload, env={**DEAD_SERVER, "MEMORI_DEBUG": "1"})

    assert "[memori] recall failed" in result.stderr
