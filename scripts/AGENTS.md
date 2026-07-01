# Scripts DOX


## Purpose

Owns repository helper scripts for release builds and config bundle generation.


## Ownership

- `build-release-image.sh`: builds one ArduPilot release image and either
  exports it as a zstd-compressed Docker archive or pushes an OCI image with
  zstd-compressed layers.
- `build-px4-sih-image.sh`: builds one PX4 SIH image for a selected model and
  PX4 release/ref, with the same archive/local/registry output modes and zstd
  compression behavior as the ArduPilot release script.
- `populate-config-bundles.py`: generates mountable SITL config bundles from
  the local ArduPilot checkout.


## Local Contracts

- Scripts should be runnable from the repository root.
- Generated catalogs default to ignored `configs/generated-frames/`.
- Release archives default to ignored `dist/images/`.
- Keep defaults conservative and document environment overrides in README.


## Work Guidance

- Shell scripts should use `set -euo pipefail`.
- Python scripts should use only standard-library dependencies unless there is
  a clear reason otherwise.
- Do not require network access in config-generation scripts.


## Verification

- Shell syntax:
  `bash -n scripts/build-release-image.sh scripts/build-px4-sih-image.sh`
- Python syntax:
  `python3 -m py_compile scripts/populate-config-bundles.py`
- Generator smoke test:
  `scripts/populate-config-bundles.py --output /tmp/generated-frames-test`


## Child DOX Index

No child DOX files.
