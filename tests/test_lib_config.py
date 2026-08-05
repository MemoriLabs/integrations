"""
Configuration resolution, tested by import.

One file is the whole of it. There is no environment variable and nothing a
workspace can reach, so most of what used to live here is gone.
"""

import json
import os

from conftest import config_path, configure
from memori import config


def test_a_setting_comes_from_the_file(settings):
    configure({"entity_id": "ent_brian"})

    settings()

    assert config.setting("entity_id") == "ent_brian"
    assert config.setting("debug") == "false"


def test_nothing_in_the_environment_is_a_source(monkeypatch, settings):
    """
    The plugin used to answer to CLAUDE_PLUGIN_OPTION_* and before that MEMORI_*.

    Both are dead. A stale export must not quietly outrank the file, or two
    machines holding the same config would behave differently.
    """

    configure({"entity_id": "from-the-file"})
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_ENTITY_ID", "from-the-environment")
    monkeypatch.setenv("MEMORI_ENTITY_ID", "also-from-the-environment")

    settings()

    assert config.setting("entity_id") == "from-the-file"


def test_no_file_is_not_an_error(settings):
    # Never configured is a choice, not a mistake, so nothing complains.
    os.remove(config_path())

    settings()

    assert config.setting("entity_id") is None
    assert not config.is_configured()
    assert not config.unreadable()


def test_a_broken_file_is_survivable_and_reported(settings):
    with open(config_path(), "w") as f:
        f.write("{ not json")

    settings()

    assert config.setting("entity_id") is None
    assert not config.is_configured()
    assert config.unreadable()


def test_a_file_that_is_not_an_object_is_survivable_and_reported(settings):
    with open(config_path(), "w") as f:
        json.dump(["not", "a", "mapping"], f)

    settings()

    assert not config.is_configured()
    assert config.unreadable()


def test_a_file_that_cannot_be_opened_is_reported(settings):
    os.chmod(config_path(), 0o000)

    try:
        settings()

        assert not config.is_configured()
        assert config.unreadable()
    finally:
        os.chmod(config_path(), 0o600)


def test_the_entity_is_never_guessed(settings):
    """
    An unset entity leaves the plugin unconfigured rather than inventing one.

    A turn captured without an entity is accepted by the server and then makes
    no memories, so a guessed value buys a plugin that looks like it is working
    and never recalls anything.
    """

    configure({"entity_id": ""})
    settings()

    assert config.setting("entity_id") is None
    assert not config.is_configured()


def test_configured_means_the_three_nobody_can_guess(settings):
    # The client key is the fourth, and the environment supplies it.
    configure({"api_header_value": "", "api_url": "", "entity_id": ""})
    settings()
    assert not config.is_configured()

    configure({"entity_id": "tester"})
    settings()
    assert not config.is_configured()

    configure({"api_url": "https://memori.example"})
    settings()
    assert config.is_configured()


# +--- application_env ---+


def test_the_client_key_comes_from_the_environment(settings):
    configure({"api_header_value": "", "application_env": "staging"})

    settings()

    assert config.setting("api_header_value") == config.API_KEYS["staging"]


def test_production_is_what_you_get_for_saying_nothing(settings):
    configure({"api_header_value": "", "application_env": ""})

    settings()

    assert config.environment() == "production"
    assert config.setting("api_header_value") == config.API_KEYS["production"]


def test_a_key_of_your_own_beats_the_environments(settings):
    configure({"api_header_value": "a-key-of-my-own", "application_env": "production"})

    settings()

    assert config.setting("api_header_value") == "a-key-of-my-own"


def test_the_environment_is_read_however_it_was_written(settings):
    configure({"api_header_value": "", "application_env": "  Staging "})

    settings()

    assert config.environment() == "staging"
    assert config.setting("api_header_value") == config.API_KEYS["staging"]


def test_an_environment_nobody_deploys_leaves_the_plugin_unconfigured(settings):
    # Falling back to production would send the conversation somewhere nobody
    # named.
    configure({"api_header_value": "", "application_env": "stage"})

    settings()

    assert config.unknown_environment() == "stage"
    assert config.setting("api_header_value") is None
    assert not config.is_configured()


# +--- debug ---+


def test_debug_reads_a_real_boolean(settings):
    configure({"debug": True})
    settings()
    assert config.debug()

    configure({"debug": False})
    settings()
    assert not config.debug()


def test_debug_reads_the_string_a_hand_edit_leaves(settings):
    configure({"debug": "false"})
    settings()
    assert not config.debug()

    configure({"debug": "yes"})
    settings()
    assert config.debug()
