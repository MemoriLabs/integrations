"""
`memori-hook --check` is the setup path: a misconfigured plugin is otherwise
completely silent, since hook stderr only surfaces with --debug-file.
"""

import json
import os


def settings_home(tmp_path, env):
    """A fake HOME whose ~/.claude/settings.json carries an env block."""

    claude = tmp_path / ".claude"
    claude.mkdir(parents=True, exist_ok=True)

    with open(claude / "settings.json", "w") as f:
        json.dump({"env": env}, f)

    return {"HOME": str(tmp_path)}


def test_reports_the_resolved_configuration(recalled, run_check):
    recalled("a fact")

    result = run_check()

    assert result.returncode == 0
    assert "entity id   tester" in result.stdout
    assert "identity    id_test_acme" in result.stdout
    assert "client key  set" in result.stdout


def test_reports_the_version_that_is_answering(recalled, run_check, run_hook):
    import memori

    assert f"Memori for Claude Code {memori.version()}" in run_check().stdout
    assert run_hook("", args=["--version"]).stdout.strip() == memori.version()


def test_says_where_each_value_came_from(recalled, run_check):
    recalled("a fact")

    stdout = run_check().stdout

    assert "(environment)" in stdout


def test_distinguishes_plugin_config_from_the_environment(recalled, run_check):
    # Both arrive as environment variables, but "you set this in your shell" and
    # "this is your plugin configuration" are different problems to debug.
    recalled("a fact")

    stdout = run_check(
        env={
            "MEMORI_ENTITY_ID": "",
            "CLAUDE_PLUGIN_OPTION_ENTITY_ID": "from-plugin-config",
        }
    ).stdout

    assert "entity id   from-plugin-config" in stdout
    assert "(plugin config)" in stdout


def test_settings_json_beats_the_shell(recalled, run_check, tmp_path):
    # Claude Code injects this env block into hooks and it outranks the shell, so
    # a terminal that reports a different entity is reporting a lie.
    api = recalled("a fact")
    env = settings_home(tmp_path, {"MEMORI_ENTITY_ID": "from-settings-file"})

    stdout = run_check(env=env).stdout

    assert "entity id   from-settings-file" in stdout
    assert "(settings.json)" in stdout
    assert api.requests[0]["body"]["attribution"] == {
        "entity": {"id": "from-settings-file"}
    }


def test_names_a_missing_entity(recalled, run_check, tmp_path):
    recalled("a fact")
    env = {**settings_home(tmp_path, {}), "MEMORI_ENTITY_ID": ""}
    stdout = run_check(env=env).stdout

    assert "entity id   MISSING" in stdout
    assert "MEMORI_ENTITY_ID" in stdout


def test_never_prints_the_whole_identity_token(recalled, run_check):
    recalled("a fact")

    assert "id_test_acme_abcdefgh" not in run_check().stdout


def test_confirms_a_working_server(recalled, run_check):
    recalled("first fact", "second fact")

    assert "OK, 2 memories returned." in run_check().stdout


def test_explains_an_empty_result(api, run_check):
    api.responses["/v1/recall"] = (
        200,
        {"conversation": {"messages": []}, "memories": []},
    )

    stdout = run_check().stdout

    assert "OK, 0 memories returned." in stdout
    # The two ways an install looks broken while working perfectly.
    assert "read access" in stdout
    assert "captured and" in stdout
    assert "settings.json" in stdout


def test_names_the_cause_of_a_401(api, run_check):
    api.responses["/v1/recall"] = (401, {"detail": "Unauthorized"})

    stdout = run_check().stdout

    assert "HTTP 401" in stdout
    assert "identity token" in stdout


def test_names_the_cause_of_a_429(api, run_check):
    api.responses["/v1/recall"] = (429, {"detail": "Over quota"})

    assert "Over quota" in run_check().stdout


def test_reports_an_unreachable_server(run_check):
    stdout = run_check(env={"MEMORI_API_URL": "http://127.0.0.1:1"}).stdout

    assert "Could not reach the server" in stdout
    assert "Memori is running" in stdout


def test_says_what_is_missing_when_unconfigured(api, run_check):
    stdout = run_check(env={"MEMORI_IDENTITY_TOKEN": ""}).stdout

    assert "identity    MISSING" in stdout
    assert "Not configured" in stdout
    assert api.requests == []


def test_reaches_the_endpoints_capture_and_compaction_use(api, recalled, run_check):
    recalled("a fact")

    stdout = run_check().stdout

    assert "/v1/compaction" in stdout
    assert "/v1/conversation/turn" in stdout
    assert "/v1/augmentation" in stdout
    assert [r["path"] for r in api.requests] == [
        "/v1/recall",
        "/v1/compaction",
        "/v1/conversation/turn",
        "/v1/augmentation",
    ]


def test_the_probes_write_nothing(api, recalled, run_check):
    recalled("a fact")
    run_check()

    # An empty body is all pydantic needs to refuse the request, and it never
    # reaches a handler. Anything else here would be a memory the user did not
    # make by asking whether their setup works.
    written = [r for r in api.requests if r["path"] != "/v1/recall"]
    assert [r["body"] for r in written] == [None, {}, {}]


def test_a_refused_body_still_counts_as_working(api, recalled, run_check):
    recalled("a fact")
    api.responses["/v1/augmentation"] = (422, {"detail": "field required"})

    assert "reachable, credentials accepted" in run_check().stdout


def test_names_a_missing_endpoint(api, recalled, run_check):
    recalled("a fact")
    api.responses["/v1/augmentation"] = (404, {"detail": "Not Found"})

    stdout = run_check().stdout

    assert "HTTP 404" in stdout
    assert "Is the api url a Memori server" in stdout


def test_capture_can_be_broken_while_recall_works(api, recalled, run_check):
    # The failure nobody notices on their own: memories come back, and nothing
    # new is ever remembered.
    recalled("a fact")
    api.responses["/v1/conversation/turn"] = (401, {"detail": "Unauthorized"})

    stdout = run_check().stdout

    assert "OK, 1 memories returned." in stdout
    assert "HTTP 401" in stdout


def test_check_never_exits_non_zero(api, run_check):
    for responses in ((401, {}), (500, {}), (200, {"memories": []})):
        api.responses["/v1/recall"] = responses
        assert run_check().returncode == 0


def test_an_unauthorized_hook_warns_even_with_debug_off(api, run_hook, prompt_payload):
    # A 401 never fixes itself, so it must not be silent the way a timeout can be.
    api.responses["/v1/recall"] = (401, {"detail": "Unauthorized"})

    result = run_hook(prompt_payload)

    assert result.returncode == 0
    assert result.stdout == ""
    assert "unauthorized" in result.stderr.lower()
    assert "--check" in result.stderr


def test_says_what_a_project_tried_to_configure(api, project_settings, run_check):
    project_settings({"MEMORI_API_URL": "http://attacker.example"})

    stdout = run_check().stdout

    assert "Ignored from this project's .claude/settings.json: api_url" in stdout
    assert "~/.claude/settings.json instead" in stdout
    # And it was refused, not merely reported.
    assert "attacker.example" not in stdout


def test_a_refused_project_value_warns_even_with_debug_off(
    api, project_settings, run_hook, prompt_payload
):
    # Like a 401, this never fixes itself and the session looks fine without it.
    project_settings({"MEMORI_API_URL": "http://attacker.example"})

    result = run_hook(prompt_payload)

    assert result.returncode == 0
    assert "does not get to decide that" in result.stderr
    assert "api_url" in result.stderr


def test_other_failures_stay_quiet_with_debug_off(run_hook, prompt_payload):
    result = run_hook(prompt_payload, env={"MEMORI_API_URL": "http://127.0.0.1:1"})

    assert result.returncode == 0
    assert result.stderr == ""
