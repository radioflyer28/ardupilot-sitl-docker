#!/usr/bin/env python3
import argparse
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTOTEST = ROOT / "ardupilot" / "Tools" / "autotest"
VEHICLEINFO = AUTOTEST / "pysim" / "vehicleinfo.json"
DEFAULT_OUT_ROOT = ROOT / "configs" / "generated-frames"


def slug(value):
    value = value.replace("+", "plus")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value)
    return value.strip("-").lower() or "default"


def source_for(relative_path):
    return AUTOTEST / relative_path


def copy_asset(relative_path, dest_dir, copied):
    src = source_for(relative_path)
    if not src.is_file():
        raise FileNotFoundError(
            f"missing asset referenced by vehicleinfo.json: {relative_path}"
        )

    name = src.name
    if name in copied and copied[name] != relative_path:
        stem = slug(relative_path).replace("-", "_")
        suffix = Path(name).suffix
        name = f"{stem}{suffix}" if suffix and not stem.endswith(suffix) else stem

    shutil.copy2(src, dest_dir / name)
    copied[name] = relative_path
    return name


def normalize_model(model, dest_dir, copied):
    if not isinstance(model, str) or "@ROMFS/models/" not in model:
        return model

    prefix, relative_path = model.split("@ROMFS/", 1)
    return f"{prefix}{copy_asset(relative_path, dest_dir, copied)}"


def normalize_params(params, dest_dir, copied):
    if isinstance(params, str):
        return copy_asset(params, dest_dir, copied)
    if isinstance(params, list):
        return [copy_asset(param, dest_dir, copied) for param in params]
    return params


def write_manifest(rows, out_root):
    lines = [
        "Generated SITL Frame Bundles",
        "============================",
        "",
        "Each subdirectory is ready to mount as `SITL_CONFIG_DIR`.",
        "",
        "| Bundle | Vehicle | Frame | Copied assets |",
        "| --- | --- | --- | ---: |",
    ]
    for bundle_name, vehicle, frame, asset_count in sorted(rows):
        lines.append(f"| `{bundle_name}` | `{vehicle}` | `{frame}` | {asset_count} |")
    (out_root / "MANIFEST.md").write_text("\n".join(lines) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate mountable SITL config bundles from ArduPilot vehicleinfo.json."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help="Output directory. Default: configs/generated-frames",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    out_root = args.output
    if not out_root.is_absolute():
        out_root = ROOT / out_root

    vehicleinfo = json.loads(VEHICLEINFO.read_text())
    out_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for vehicle, vehicle_info in vehicleinfo.items():
        for frame, frame_info in vehicle_info.get("frames", {}).items():
            has_romfs_model = (
                isinstance(frame_info.get("model"), str)
                and "@ROMFS/models/" in frame_info.get("model")
            )
            has_params = frame_info.get("default_params_filename") not in (None, [])
            if not has_romfs_model and not has_params:
                continue

            bundle_name = f"{slug(vehicle)}-{slug(frame)}"
            dest_dir = out_root / bundle_name
            dest_dir.mkdir(parents=True, exist_ok=True)
            for existing in dest_dir.iterdir():
                if existing.is_file():
                    existing.unlink()

            copied = {}
            normalized_info = dict(frame_info)
            if "model" in normalized_info:
                normalized_info["model"] = normalize_model(
                    normalized_info["model"], dest_dir, copied
                )
            if "default_params_filename" in normalized_info:
                normalized_info["default_params_filename"] = normalize_params(
                    normalized_info["default_params_filename"], dest_dir, copied
                )

            bundle_vehicleinfo = {
                vehicle: {
                    "default_frame": frame,
                    "frames": {
                        frame: normalized_info,
                    },
                }
            }
            (dest_dir / "vehicleinfo.json").write_text(
                json.dumps(bundle_vehicleinfo, indent=2) + "\n"
            )
            rows.append((bundle_name, vehicle, frame, len(copied)))

    write_manifest(rows, out_root)
    try:
        display_path = out_root.relative_to(ROOT)
    except ValueError:
        display_path = out_root
    print(f"generated {len(rows)} bundles under {display_path}")


if __name__ == "__main__":
    main()
