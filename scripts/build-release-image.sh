#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Build one ArduPilot SITL image for a vehicle release and export it as zstd.

Usage:
  scripts/build-release-image.sh <target> <version-or-ref>

Targets:
  copter    -> Copter-<version>
  plane     -> Plane-<version>
  rover     -> Rover-<version>
  sub       -> ArduSub-<version>

Examples:
  scripts/build-release-image.sh copter 4.6.0
  scripts/build-release-image.sh plane Plane-4.6.0
  WAF_JOBS=8 ZSTD_LEVEL=22 scripts/build-release-image.sh rover 4.6.0

Environment overrides:
  IMAGE_REPO       Image repo/name. Default: ardupilot-sitl
  OUTPUT_DIR       Archive output directory. Default: dist/images
  CACHE_DIR        BuildKit local cache directory. Default: .buildx-cache
  DOCKERFILE       Dockerfile path. Default: Dockerfile
  BASE_IMAGE       Builder/runtime base image. Default: Dockerfile default
  TAG              Builder/runtime base tag. Default: Dockerfile default
  WAF_JOBS         Waf parallel jobs. Default: Dockerfile default
  ZSTD_LEVEL       zstd compression level. Default: 9
  ZSTD_LONG        zstd --long window. Default: 27

Restore:
  zstd -dc dist/images/<archive>.tar.zst | docker load
EOF
}

if [[ $# -ne 2 ]]; then
    usage >&2
    exit 2
fi

target="$1"
version_or_ref="$2"

case "$target" in
    copter)
        ref_prefix="Copter"
        ;;
    plane)
        ref_prefix="Plane"
        ;;
    rover)
        ref_prefix="Rover"
        ;;
    sub)
        ref_prefix="ArduSub"
        ;;
    *)
        echo "Unsupported target: $target. Expected one of: copter, plane, rover, sub" >&2
        exit 2
        ;;
esac

if [[ "$version_or_ref" == *-* ]]; then
    ardupilot_ref="$version_or_ref"
    version="${version_or_ref#${ref_prefix}-}"
else
    version="$version_or_ref"
    ardupilot_ref="${ref_prefix}-${version}"
fi

image_repo="${IMAGE_REPO:-ardupilot-sitl}"
dockerfile="${DOCKERFILE:-Dockerfile}"
output_dir="${OUTPUT_DIR:-dist/images}"
cache_dir="${CACHE_DIR:-.buildx-cache}"
zstd_level="${ZSTD_LEVEL:-9}"
zstd_long="${ZSTD_LONG:-27}"

safe_version="$(printf '%s' "$version" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9_.-' '-')"
image_tag="${image_repo}:${target}-${version}"
archive="${output_dir}/${image_repo}-${target}-${safe_version}.docker.tar.zst"

mkdir -p "$output_dir"

build_args=(
    --build-arg "ARDUPILOT_REF=${ardupilot_ref}"
    --build-arg "WAF_TARGET=${target}"
)

if [[ -n "${BASE_IMAGE:-}" ]]; then
    build_args+=(--build-arg "BASE_IMAGE=${BASE_IMAGE}")
fi
if [[ -n "${TAG:-}" ]]; then
    build_args+=(--build-arg "TAG=${TAG}")
fi
if [[ -n "${WAF_JOBS:-}" ]]; then
    build_args+=(--build-arg "WAF_JOBS=${WAF_JOBS}")
fi

cache_args=(
    --cache-to "type=local,dest=${cache_dir},mode=max"
)
if [[ -f "${cache_dir}/index.json" ]]; then
    cache_args=(--cache-from "type=local,src=${cache_dir}" "${cache_args[@]}")
fi

echo "Building ${image_tag} from ${ardupilot_ref}"
docker buildx build -f "$dockerfile" \
    "${build_args[@]}" \
    "${cache_args[@]}" \
    -t "$image_tag" \
    --load .

zstd_args=(-T0 "-${zstd_level}" "--long=${zstd_long}" -f)
if [[ "$zstd_level" =~ ^[0-9]+$ ]] && (( zstd_level > 19 )); then
    zstd_args=(--ultra "${zstd_args[@]}")
fi

echo "Exporting ${archive}"
docker image save "$image_tag" | zstd "${zstd_args[@]}" -o "$archive"

echo "Wrote ${archive}"
