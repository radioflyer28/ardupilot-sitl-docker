#!/usr/bin/env bash
set -eo pipefail
if [ -f "${HOME}/.ardupilot_env" ]; then
    source "${HOME}/.ardupilot_env"
fi
exec python3 "$(dirname "$(readlink -f "$0")")/run-sitl.py" "$@"
