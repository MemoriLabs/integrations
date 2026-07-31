"""
Configuration resolution, tested by import.

There is one resolver. The diagnostic used to have its own, with different
precedence, and it kept them in step by mutating os.environ -- so this is the
part most worth pinning down.
"""

import json

from memori import config


def user_settings(tmp_path, monkeypatch, env):
    claude = tmp_path / ".claude"
    claude.mkdir(exist_ok=True)

    with open(claude / "settings.json", "w") as f:
        json.dump({"env": env}, f)

    monkeypatch.setenv("HOME", str(tmp_path))


def test_precedence_runs_settings_then_environment_then_plugin_then_default(
    monkeypatch, tmp_path, settings
):
    user_settings(tmp_path, monkeypatch, {"MEMORI_ENTITY_ID": "from-settings"})
    monkeypatch.setenv("MEMORI_ENTITY_ID", "from-environment")
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_API_URL", "http://from-plugin-config")

    settings()

    assert config.setting("entity_id") == "from-settings"
    assert config.source("entity_id") == "settings.json"
    assert config.setting("api_url") == "http://from-plugin-config"
    assert config.source("api_url") == "plugin config"
    assert config.source("debug") == "default"


def test_a_hook_and_the_diagnostic_resolve_the_same_configuration(
    monkeypatch, tmp_path, settings
):
    # These used to differ: only --check read the files, so a terminal could
    # report one entity while the hook beside it used another.
    user_settings(tmp_path, monkeypatch, {"MEMORI_ENTITY_ID": "from-settings"})
    monkeypatch.setenv("MEMORI_ENTITY_ID", "from-environment")

    settings()

    assert config.setting("entity_id") == "from-settings"


def test_a_broken_settings_file_is_survivable(monkeypatch, tmp_path, settings):
    claude = tmp_path / ".claude"
    claude.mkdir()
    with open(claude / "settings.json", "w") as f:
        f.write("{ not json")

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MEMORI_ENTITY_ID", "still-works")

    settings()

    assert config.setting("entity_id") == "still-works"


def test_the_entity_is_never_guessed(monkeypatch, settings):
    """
    An unset entity leaves the plugin unconfigured rather than inventing one.

    A turn captured without an entity is accepted by the server and then makes
    no memories, so a guessed value buys a plugin that looks like it is working
    and never recalls anything.
    """

    monkeypatch.delenv("MEMORI_ENTITY_ID", raising=False)
    settings()

    assert config.setting("entity_id") is None
    assert not config.is_configured()


def test_configured_means_all_four(monkeypatch, settings):
    for name in ("MEMORI_API_HEADER_VALUE", "MEMORI_API_URL", "MEMORI_ENTITY_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MEMORI_IDENTITY_TOKEN", "id_x")
    settings()
    assert not config.is_configured()

    monkeypatch.setenv("MEMORI_API_HEADER_VALUE", "key")
    settings()
    assert not config.is_configured()

    monkeypatch.setenv("MEMORI_ENTITY_ID", "tester")
    settings()
    assert not config.is_configured()

    monkeypatch.setenv("MEMORI_API_URL", "https://memori.example")
    settings()
    assert config.is_configured()


def test_a_project_cannot_say_where_conversation_is_sent(project_settings, settings):
    project_settings({"MEMORI_API_URL": "http://attacker.example"})
    settings()

    # There is no default to fall back to, so a refused api_url leaves the plugin
    # unconfigured -- which is the safe direction. It cannot end up pointing at
    # whatever the repository asked for.
    assert config.setting("api_url") is None
    assert config.source("api_url") == "default"
    assert config.refused() == ("api_url",)
    assert not config.is_configured()


def test_a_project_cannot_supply_credentials_or_the_entity(project_settings, settings):
    project_settings(
        {
            "MEMORI_API_HEADER_NAME": "X-Theirs",
            "MEMORI_API_HEADER_VALUE": "their-key",
            "MEMORI_ENTITY_ID": "someone-else",
            "MEMORI_IDENTITY_TOKEN": "id_theirs",
        }
    )
    settings()

    assert config.refused() == (
        "api_header_name",
        "api_header_value",
        "entity_id",
        "identity_token",
    )
    assert not config.is_configured()


def test_a_project_cannot_smuggle_a_value_past_the_check_by_its_type(
    monkeypatch, tmp_path, settings
):
    # Claude Code coerces the JSON to a string on its way into the environment,
    # while we read the same file with json.load and keep the type. Measured: an
    # array arrives as the plain string, so any value comparison walks straight
    # past it. Naming the key has to be the whole test.
    root = tmp_path / "workspace"
    (root / ".claude").mkdir(parents=True)

    with open(root / ".claude" / "settings.json", "w") as f:
        json.dump({"env": {"MEMORI_API_URL": ["http://attacker.example"]}}, f)

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("MEMORI_API_URL", "http://attacker.example")

    settings()

    assert config.setting("api_url") is None
    assert config.refused() == ("api_url",)


def test_what_is_reported_as_refused_is_what_is_actually_refused(
    monkeypatch, tmp_path, settings
):
    # These used to disagree: the notice fired on one rule and the enforcement on
    # another, so the plugin could say it ignored a value while using it.
    root = tmp_path / "workspace"
    (root / ".claude").mkdir(parents=True)

    with open(root / ".claude" / "settings.json", "w") as f:
        json.dump({"env": {"MEMORI_API_URL": 8080, "MEMORI_ENTITY_ID": ""}}, f)

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("MEMORI_API_URL", "8080")
    monkeypatch.setenv("MEMORI_ENTITY_ID", "")

    settings()

    assert config.refused() == ("api_url", "entity_id")
    assert config.setting("api_url") is None
    assert config.source("api_url") == "default"


def test_a_project_may_still_turn_on_logging(project_settings, settings):
    project_settings({"MEMORI_DEBUG": "true"})
    settings()

    assert config.debug() is True
    assert config.refused() == ()


def test_refusing_a_project_value_falls_back_to_yours(
    monkeypatch, tmp_path, project_settings, settings
):
    project_settings({"MEMORI_API_URL": "http://attacker.example"})
    user_settings(tmp_path, monkeypatch, {"MEMORI_API_URL": "http://yours.example"})

    settings()

    assert config.setting("api_url") == "http://yours.example"
    assert config.source("api_url") == "settings.json"
    # Still said out loud. Your own settings happening to outrank the repository
    # is not a reason to keep quiet about the repository having tried.
    assert config.refused() == ("api_url",)


def test_the_plugins_own_config_is_not_a_project_value(
    monkeypatch, project_settings, settings
):
    # userConfig lives in user settings or the keychain, so a workspace cannot
    # reach it even when it sets the MEMORI_* name for the same setting.
    project_settings({"MEMORI_API_URL": "http://attacker.example"})
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_API_URL", "http://from-plugin-config")

    settings()

    assert config.setting("api_url") == "http://from-plugin-config"


def test_an_untouched_project_refuses_nothing(monkeypatch, settings):
    monkeypatch.setenv("MEMORI_API_URL", "http://from-your-shell")
    settings()

    assert config.setting("api_url") == "http://from-your-shell"
    assert config.refused() == ()


def test_a_boolean_option_arrives_as_a_string(monkeypatch, settings):
    # userConfig booleans reach us as "false", which is truthy.
    for value, expected in (
        ("false", False),
        ("0", False),
        ("off", False),
        ("", False),
        ("true", True),
        ("1", True),
    ):
        monkeypatch.setenv("MEMORI_DEBUG", value)
        settings()
        assert config.debug() is expected, value
