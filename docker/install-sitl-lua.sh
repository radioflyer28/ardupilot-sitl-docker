#!/bin/bash
set -euo pipefail

config_dir="${SITL_CONFIG_DIR:-/configs}"
ardupilot_dir="${ARDUPILOT_DIR:-$PWD}"
dest_dir="${ARDUPILOT_SCRIPT_DIR:-${ardupilot_dir}/scripts}"
bundle_scripts="${config_dir}/scripts"
mission_loader="${MISSION_LOADER_LUA:-/usr/local/share/ardupilot-sitl/load-mission.lua}"
mission_runtime_file="${MISSION_RUNTIME_FILE:-${ardupilot_dir}/missions/mission.waypoints}"
mission_runtime_dir="$(dirname "$mission_runtime_file")"

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

if [ -n "${MISSION_FILE:-}" ]; then
    mission_path="$(resolve_config_path "$MISSION_FILE")"
    if [ ! -f "$mission_path" ]; then
        printf 'install-sitl-lua.sh: MISSION_FILE does not exist or is not a file: %s\n' "$mission_path" >&2
        exit 1
    fi
    if [ ! -f "$mission_loader" ]; then
        printf 'install-sitl-lua.sh: mission loader Lua script does not exist: %s\n' "$mission_loader" >&2
        exit 1
    fi

    first_line=""
    IFS= read -r first_line < "$mission_path" || true
    first_line="${first_line%$'\r'}"
    case "$first_line" in
        "QGC WPL 110"*) ;;
        *)
            printf 'install-sitl-lua.sh: MISSION_FILE is not a QGC WPL 110 mission: %s\n' "$mission_path" >&2
            exit 1
            ;;
    esac

    install -d -m 0755 "$mission_runtime_dir"
    rm -f "$mission_runtime_file"
    cp -a "$mission_path" "$mission_runtime_file"
    rm -f "${dest_dir}/load-mission.lua"
    cp -a "$mission_loader" "${dest_dir}/load-mission.lua"
fi

if [ -n "${LUA_SCRIPT:-}" ]; then
    script_path="$(resolve_config_path "$LUA_SCRIPT")"
    if [ ! -f "$script_path" ]; then
        printf 'install-sitl-lua.sh: LUA_SCRIPT does not exist or is not a file: %s\n' "$script_path" >&2
        exit 1
    fi

    cp -a "$script_path" "$dest_dir/"
fi
