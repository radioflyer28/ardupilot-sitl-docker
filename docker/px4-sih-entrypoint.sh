#!/usr/bin/env bash
set -e

if [ "$#" -eq 0 ]; then
    exec /usr/local/bin/run-px4-sih.sh
fi

if [ "${1#-}" != "$1" ]; then
    exec /usr/local/bin/run-px4-sih.sh "$@"
fi

exec "$@"
