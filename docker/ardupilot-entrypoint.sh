#!/usr/bin/env bash
set -eo pipefail
if [ -f "${HOME}/.ardupilot_env" ]; then
    source "${HOME}/.ardupilot_env"
fi
if [ "$#" -eq 0 ] || [[ "$1" = -* ]]; then
    exec /usr/local/bin/run-sitl.sh "$@"
fi
exec "$@"
