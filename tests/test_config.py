"""Configuration as the real hooks resolve it. The rules are in test_lib_config."""

DEAD_SERVER = {"api_url": "http://127.0.0.1:1"}

CONFIGURED = {
    "api_header_value": "file-client-key",
    "entity_id": "file-entity",
    "identity_id": "id_from_the_file",
}


def test_reads_configuration_from_the_file(recalled, run_hook, prompt_payload):
    api = recalled("a fact")

    run_hook(prompt_payload, config=CONFIGURED)

    request = api.requests[0]
    assert request["headers"]["Authorization"] == "Bearer id_from_the_file"
    assert request["headers"]["X-Memori-Api-Key"] == "file-client-key"
    assert request["body"]["attribution"] == {"entity": {"id": "file-entity"}}


def test_a_later_write_replaces_an_earlier_one(recalled, run_hook, prompt_payload):
    # Rotating an identity id is editing one key; the rest of the file survives.
    api = recalled("a fact")

    run_hook(prompt_payload, config={**CONFIGURED, "identity_id": "id_rotated"})

    assert api.requests[0]["headers"]["Authorization"] == "Bearer id_rotated"
    assert api.requests[0]["body"]["attribution"] == {"entity": {"id": "file-entity"}}


def test_a_false_debug_setting_does_not_log(run_hook, prompt_payload):
    # A hand-edited file can hold the string "false", which is truthy.
    result = run_hook(prompt_payload, config={**DEAD_SERVER, "debug": "false"})

    assert result.stderr == ""


def test_a_true_debug_setting_logs(run_hook, prompt_payload):
    result = run_hook(prompt_payload, config={**DEAD_SERVER, "debug": True})

    assert "[memori] recall failed" in result.stderr


def test_debug_is_on_for_any_truthy_spelling(run_hook, prompt_payload):
    result = run_hook(prompt_payload, config={**DEAD_SERVER, "debug": "1"})

    assert "[memori] recall failed" in result.stderr
