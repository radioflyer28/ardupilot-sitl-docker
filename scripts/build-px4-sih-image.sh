#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Build one PX4 SIH image for a model and PX4 release/ref.

Usage:
  scripts/build-px4-sih-image.sh <model> <version-or-ref>

Models:
  sihsim_quadx
  sihsim_airplane
  sihsim_hexa
  sihsim_xvert
  sihsim_standard_vtol
  sihsim_rover_ackermann

Examples:
  scripts/build-px4-sih-image.sh sihsim_quadx v1.16.0
  scripts/build-px4-sih-image.sh sihsim_quadx 1.16.0
  PX4_JOBS=8 ZSTD_LEVEL=6 scripts/build-px4-sih-image.sh sihsim_quadx v1.16.0
  IMAGE_OUTPUT=local scripts/build-px4-sih-image.sh sihsim_quadx main
  IMAGE_OUTPUT=registry IMAGE_REPO=ghcr.io/example/px4-sih scripts/build-px4-sih-image.sh sihsim_quadx v1.16.0

Environment overrides:
  IMAGE_REPO          Image repo/name. Default: px4-sih
  IMAGE_OUTPUT        Output mode: archive, local, or registry. Default: archive
  OUTPUT_DIR          Archive output directory. Default: dist/images
  CACHE_DIR           BuildKit local cache directory. Default: .buildx-cache/px4-sih
  DOCKERFILE          Dockerfile path. Default: Dockerfile.px4-sih
  PX4_BUILDER_IMAGE   PX4 builder image. Default: Dockerfile default
  RUNTIME_BASE_IMAGE  Runtime base image family. Default: Dockerfile default
  RUNTIME_TAG         Runtime base tag. Default: Dockerfile default
  PX4_REPO            PX4 git repository URL. Default: Dockerfile default
  PX4_CLONE_DEPTH     Shallow clone depth. Default: Dockerfile default
  PX4_SUBMODULE_PATHS Space-separated submodules to initialize. Default: Dockerfile default
  PX4_BUILD_TARGET    PX4 build target. Default: Dockerfile default
  PX4_BUILD_DIR       PX4 build output directory. Default: inferred from target
  PX4_JOBS            Parallel make jobs. Default: Dockerfile default
  ZSTD_LEVEL          zstd compression level for image layers and archives. Default: 3
  ZSTD_LONG           zstd --long window. Default: 27

Restore:
  zstd -dc dist/images/<archive>.tar.zst | docker load
EOF
}

if [[ $# -ne 2 ]]; then
    usage >&2
    exit 2
fi

model="$1"
version_or_ref="$2"

case "$model" in
    sihsim_quadx|sihsim_airplane|sihsim_hexa|sihsim_xvert|sihsim_standard_vtol|sihsim_rover_ackermann)
        ;;
    *)
        echo "Unsupported PX4 SIH model: $model" >&2
        echo "Expected one of: sihsim_quadx, sihsim_airplane, sihsim_hexa, sihsim_xvert, sihsim_standard_vtol, sihsim_rover_ackermann" >&2
        exit 2
        ;;
esac

if [[ "$version_or_ref" =~ ^[0-9]+([.][0-9A-Za-z._-]+)*$ ]]; then
    px4_ref="v${version_or_ref}"
    version="v${version_or_ref}"
else
    px4_ref="$version_or_ref"
    version="$version_or_ref"
fi

image_repo="${IMAGE_REPO:-px4-sih}"
image_output="${IMAGE_OUTPUT:-archive}"
dockerfile="${DOCKERFILE:-Dockerfile.px4-sih}"
output_dir="${OUTPUT_DIR:-dist/images}"
cache_dir="${CACHE_DIR:-.buildx-cache/px4-sih}"
zstd_level="${ZSTD_LEVEL:-3}"
zstd_long="${ZSTD_LONG:-27}"

safe_model="$(printf '%s' "$model" | tr '[:upper:]_' '[:lower:]-' | tr -c 'a-z0-9_.-' '-')"
safe_version="$(printf '%s' "$version" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_.-' '-')"
image_tag="${image_repo}:${safe_model}-${safe_version}"
archive="${output_dir}/${image_repo}-${safe_model}-${safe_version}.docker.tar.zst"

mkdir -p "$output_dir"

build_args=(
    --build-arg "PX4_REF=${px4_ref}"
    --build-arg "PX4_SIM_MODEL=${model}"
)

px4_build_target="${PX4_BUILD_TARGET:-}"
if [[ -z "$px4_build_target" ]]; then
    case "$px4_ref" in
        main|master)
            px4_build_target="px4_sitl_sih"
            ;;
        *)
            px4_build_target="px4_sitl"
            ;;
    esac
fi

px4_build_dir="${PX4_BUILD_DIR:-}"
if [[ -z "$px4_build_dir" ]]; then
    case "$px4_build_target" in
        px4_sitl)
            px4_build_dir="px4_sitl_default"
            ;;
        *)
            px4_build_dir="$px4_build_target"
            ;;
    esac
fi

build_args+=(
    --build-arg "PX4_BUILD_TARGET=${px4_build_target}"
    --build-arg "PX4_BUILD_DIR=${px4_build_dir}"
)

if [[ -n "${PX4_BUILDER_IMAGE:-}" ]]; then
    build_args+=(--build-arg "PX4_BUILDER_IMAGE=${PX4_BUILDER_IMAGE}")
fi
if [[ -n "${RUNTIME_BASE_IMAGE:-}" ]]; then
    build_args+=(--build-arg "RUNTIME_BASE_IMAGE=${RUNTIME_BASE_IMAGE}")
fi
if [[ -n "${RUNTIME_TAG:-}" ]]; then
    build_args+=(--build-arg "RUNTIME_TAG=${RUNTIME_TAG}")
fi
if [[ -n "${PX4_REPO:-}" ]]; then
    build_args+=(--build-arg "PX4_REPO=${PX4_REPO}")
fi
if [[ -n "${PX4_CLONE_DEPTH:-}" ]]; then
    build_args+=(--build-arg "PX4_CLONE_DEPTH=${PX4_CLONE_DEPTH}")
fi
if [[ -n "${PX4_SUBMODULE_PATHS:-}" ]]; then
    build_args+=(--build-arg "PX4_SUBMODULE_PATHS=${PX4_SUBMODULE_PATHS}")
fi
if [[ -n "${PX4_JOBS:-}" ]]; then
    build_args+=(--build-arg "PX4_JOBS=${PX4_JOBS}")
fi

cache_args=(
    --cache-to "type=local,dest=${cache_dir},mode=max"
)
if [[ -f "${cache_dir}/index.json" ]]; then
    cache_args=(--cache-from "type=local,src=${cache_dir}" "${cache_args[@]}")
fi

case "$image_output" in
    archive)
        output_args=(
            --output "type=docker,compression=zstd,compression-level=${zstd_level},force-compression=true"
        )
        ;;
    local)
        output_args=(
            --output "type=docker,compression=zstd,compression-level=${zstd_level},force-compression=true"
        )
        ;;
    registry)
        output_args=(
            --output "type=image,push=true,oci-mediatypes=true,compression=zstd,compression-level=${zstd_level},force-compression=true"
        )
        ;;
    *)
        echo "Unsupported IMAGE_OUTPUT: $image_output. Expected archive, local, or registry" >&2
        exit 2
        ;;
esac

echo "Building ${image_tag} from ${px4_ref} (${model}, ${px4_build_target} -> build/${px4_build_dir})"
docker buildx build -f "$dockerfile" \
    "${build_args[@]}" \
    "${cache_args[@]}" \
    -t "$image_tag" \
    "${output_args[@]}" .

if [[ "$image_output" == "registry" ]]; then
    echo "Pushed ${image_tag} with zstd-compressed OCI layers"
    exit 0
fi

if [[ "$image_output" == "local" ]]; then
    echo "Loaded ${image_tag} into the local Docker image store"
    exit 0
fi

zstd_args=(-T0 "-${zstd_level}" "--long=${zstd_long}" -f)
if [[ "$zstd_level" =~ ^[0-9]+$ ]] && (( zstd_level > 19 )); then
    zstd_args=(--ultra "${zstd_args[@]}")
fi

echo "Exporting ${archive}"
docker image save "$image_tag" | zstd "${zstd_args[@]}" -o "$archive"

echo "Wrote ${archive}"
