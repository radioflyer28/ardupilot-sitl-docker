#!/bin/bash
set -euo pipefail

config_dir="${SITL_CONFIG_DIR:-/configs}"
ardupilot_dir="${ARDUPILOT_DIR:-$PWD}"
dest_dir="${ARDUPILOT_SCRIPT_DIR:-${ardupilot_dir}/scripts}"
bundle_scripts="${config_dir}/scripts"

resolve_config_path() {
    local path="$1"
    if [ -z "$path" ]; then
        return 0
    fi
    if [[ "$path" = /* ]]; then
        printf '%s\n' "$path"
    else
        printf '%s\n' "${config_dir}/${path}"
    fi
}

install -d -m 0755 "$dest_dir"

if [ -e "$bundle_scripts" ]; then
    if [ ! -d "$bundle_scripts" ]; then
        printf 'install-sitl-lua.sh: SITL config scripts path is not a directory: %s\n' "$bundle_scripts" >&2
        exit 1
    fi

    cp -a "${bundle_scripts}/." "$dest_dir/"
fi

if [ -n "${LUA_SCRIPT:-}" ]; then
    script_path="$(resolve_config_path "$LUA_SCRIPT")"
    if [ ! -f "$script_path" ]; then
        printf 'install-sitl-lua.sh: LUA_SCRIPT does not exist or is not a file: %s\n' "$script_path" >&2
        exit 1
    fi

    cp -a "$script_path" "$dest_dir/"
fi
