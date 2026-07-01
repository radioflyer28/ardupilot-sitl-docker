#!/usr/bin/env bash
set -euo pipefail

build_target="${PX4_BUILD_TARGET:-px4_sitl_sih}"
build_dir="${PX4_BUILD_DIR:-${build_target}}"
px4_root="${PX4_ROOT:-${HOME}/PX4-Autopilot}"
build_path="${px4_root}/build/${build_dir}"
instance="${INSTANCE:-0}"
model="${MODEL:-${PX4_SIM_MODEL:-sihsim_quadx}}"

if [ ! -x "${build_path}/bin/px4" ]; then
    printf 'run-px4-sih.sh: missing PX4 binary: %s\n' "${build_path}/bin/px4" >&2
    exit 1
fi

if [ ! -d "${build_path}/etc" ]; then
    printf 'run-px4-sih.sh: missing PX4 runtime etc directory: %s\n' "${build_path}/etc" >&2
    exit 1
fi

export PX4_SIM_MODEL="${model}"
export PX4_HOME_LAT="${PX4_HOME_LAT:-${LAT:-}}"
export PX4_HOME_LON="${PX4_HOME_LON:-${LON:-}}"
export PX4_HOME_ALT="${PX4_HOME_ALT:-${ALT:-}}"
export PX4_SIM_SPEED_FACTOR="${PX4_SIM_SPEED_FACTOR:-${SPEEDUP:-1}}"

if [ -n "${SYSID:-}" ]; then
    export PX4_PARAM_MAV_SYS_ID="${PX4_PARAM_MAV_SYS_ID:-${SYSID}}"
fi

if [ -n "${PX4_RUN_DIR:-}" ]; then
    run_dir="${PX4_RUN_DIR}"
elif [ -n "${ARTIFACTS_DIR:-}" ]; then
    run_dir="${ARTIFACTS_DIR}/instance_${instance}"
else
    run_dir="/tmp/px4-sih/instance_${instance}"
fi

mkdir -p "${run_dir}"
cd "${run_dir}"

exec "${build_path}/bin/px4" -i "${instance}" -d "${build_path}/etc" "$@"
