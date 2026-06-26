# Config Bundles DOX


## Purpose

Owns checked-in SITL config bundle examples and rules for generated frame
catalogs.


## Ownership

- `configs/frames/`: small checked-in examples only.
- `configs/generated-frames/`: ignored output from
  `scripts/populate-config-bundles.py`.
- `configs/README.md` and `configs/frames/MANIFEST.md`: user-facing guidance
  for bundle layout and generation.


## Local Contracts

- Each checked-in bundle must be directly mountable as `SITL_CONFIG_DIR`.
- Each bundle must include a local `vehicleinfo.json`.
- Relative paths inside bundle `vehicleinfo.json` should point to files in the
  same bundle directory.
- Do not check in full generated catalogs unless the user explicitly asks.


## Work Guidance

- Keep examples minimal and copyable.
- Prefer refreshing examples from `./ardupilot/Tools/autotest` rather than
  hand-inventing parameter files.
- If adding a generated catalog for local use, use ignored
  `configs/generated-frames/`.


## Verification

- Validate edited bundle JSON with `python3 -m json.tool <path>`.
- For checked-in examples, validate:
  - `configs/frames/arducopter-quad/vehicleinfo.json`
  - `configs/frames/arduplane-plane/vehicleinfo.json`
- When changing generation behavior, run `scripts/populate-config-bundles.py`
  with `--output` pointed at a temporary directory.


## Child DOX Index

No child DOX files.
