#!/usr/bin/env bash
# Find a working Python 3 and hand the hook to it.
#
# `python3` on its own is not enough. On Windows it usually resolves to the
# Microsoft Store stub, which exists, runs, and exits 49 having done nothing,
# so anything that trusts `command -v` is silently dead. Each candidate is
# therefore probed by running it.
#
# This never exits non-zero, and there is no `set -e` for the same reason: a
# hook that fails is a blocking error to Claude Code, and on UserPromptSubmit
# that erases what the user typed. No interpreter means no memories, which is
# the same degradation as an unreachable server.

# Windows Python defaults to cp1252, which cannot read a path holding CJK or
# Arabic characters. Already the default everywhere else.
export PYTHONUTF8=1

# Git Bash passes POSIX paths, and a Windows interpreter reads the leading
# slash as the root of whichever drive it is on. `cygpath` exists only there,
# so the guard makes this a no-op elsewhere.
if command -v cygpath >/dev/null 2>&1; then
    converted=()
    for argument in "$@"; do
        case "$argument" in
            /*) converted+=("$(cygpath -w "$argument")") ;;
            *) converted+=("$argument") ;;
        esac
    done
    set -- "${converted[@]}"
fi

# 3.9 is what macOS ships and the oldest the library is tested against. Gating
# matters as much as the exit code below: `exec` replaces this script, so an
# interpreter too old to parse the hook dies with a SyntaxError and *its* exit
# status becomes the hook's. The version check runs inside the candidate rather
# than being compared in shell, so `py -3` needs no special case.
#
# `py -3` is the Windows launcher, and is two words, so none of these can be
# quoted as a single command.
for interpreter in "python3" "python" "py -3"; do
    # shellcheck disable=SC2086
    if $interpreter -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" \
        >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        exec $interpreter "$@"
    fi
done

# Warned rather than logged: this never fixes itself, and the alternative is a
# plugin that looks installed and remembers nothing.
echo "[memori] no Python 3.9 or newer found, so nothing is being remembered." >&2
echo "[memori] tried: python3, python, py -3" >&2
echo "[memori] on Windows install Python from python.org, not the Microsoft Store." >&2

exit 0
