"""
Choosing the interpreter the hooks run under.

hooks.json runs `bash hooks/python.sh <entry point>`, so this script decides
whether a hook runs at all. Only a real process can show that: which candidate
it settles on, what it exports before handing over, and -- the part that matters
most -- that a machine with no usable Python still leaves the session alone.

test_manifests.py covers the wiring that reaches it.
"""

import json

import pytest
from conftest import script

RAN = ["-c", "print('ran')"]


# +--- picking an interpreter ---+


def test_the_hook_runs_when_python3_works(run_shim):
    result = run_shim({"python3": "works"}, RAN)

    assert result.returncode == 0
    assert result.stdout.strip() == "ran"


def test_the_windows_store_stub_is_stepped_over(run_shim):
    # It is on PATH and it runs, so `command -v` would have picked it and the
    # hook would have done nothing. Exit 49, no output, no error.
    result = run_shim({"python3": "stub", "python": "works"}, RAN)

    assert result.returncode == 0
    assert result.stdout.strip() == "ran"


def test_an_interpreter_that_fails_the_version_gate_is_stepped_over(run_shim):
    result = run_shim({"python3": "refuses", "python": "works"}, RAN)

    assert result.returncode == 0
    assert result.stdout.strip() == "ran"


# +--- when there is nothing to run ---+


@pytest.mark.parametrize(
    "plant",
    [
        {},
        {"python3": "stub"},
        {"python3": "stub", "python": "stub"},
        {"python3": "refuses", "python": "refuses"},
    ],
)
def test_no_usable_interpreter_still_exits_zero(run_shim, plant):
    # The whole reason the script exists. A non-zero exit is a blocking error to
    # Claude Code, and on UserPromptSubmit it erases what the user typed, so a
    # machine without Python has to lose its memories and nothing else.
    result = run_shim(plant, RAN)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_a_machine_without_python_says_so(run_shim):
    # Warned rather than logged: this never fixes itself, and the alternative is
    # a plugin that looks installed and remembers nothing.
    result = run_shim({"python3": "stub"}, RAN)

    assert "nothing is being remembered" in result.stderr
    assert "python.org" in result.stderr


# +--- what it hands over ---+


def test_utf8_is_forced_before_python_starts(run_shim):
    # Windows Python defaults to cp1252, which cannot read a path holding CJK or
    # Arabic characters, and it is too late to set once the interpreter is up.
    result = run_shim(
        {"python3": "works"}, ["-c", "import os; print(os.environ['PYTHONUTF8'])"]
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "1"


def test_arguments_reach_the_interpreter_untouched(run_shim):
    result = run_shim(
        {"python3": "works"},
        ["-c", "import sys; print(sys.argv[1:])", "one", "two three"],
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "['one', 'two three']"


# +--- the real entry points ---+


def test_a_real_entry_point_runs_through_the_shim(run_shim, stop_payload):
    # What hooks.json actually does. The entry points have their own coverage in
    # test_entry_points.py, which reaches them directly; this is the one place
    # the two halves are exercised together.
    result = run_shim(
        {"python3": "works"},
        [script("stop")],
        payload=json.dumps({**stop_payload, "transcript_path": ""}),
    )

    assert result.returncode == 0


def test_a_real_entry_point_survives_having_no_interpreter(run_shim, stop_payload):
    result = run_shim(
        {"python3": "stub"},
        [script("stop")],
        payload=json.dumps(stop_payload),
    )

    assert result.returncode == 0
