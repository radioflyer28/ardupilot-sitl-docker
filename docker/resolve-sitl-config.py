#!/usr/bin/env python3
import json
import os
import shutil
import sys


CONFIG_DIR = os.environ.get("SITL_CONFIG_DIR") or "/configs"
ARDUPILOT_DIR = os.getcwd()
VEHICLEINFO_DEST = os.path.join(
    ARDUPILOT_DIR, "Tools", "autotest", "pysim", "vehicleinfo.json"
)


def resolve_path(path, base_dir=CONFIG_DIR):
    if not path:
        return path
    if os.path.isabs(path) or path.startswith("@ROMFS/"):
        return path
    return os.path.join(base_dir, path)


def resolve_model(model, base_dir=CONFIG_DIR):
    if not model or ":" not in model:
        return model
    prefix, path = model.rsplit(":", 1)
    if not path.endswith(".json"):
        return model
    return f"{prefix}:{resolve_path(path, base_dir)}"


def print_arg(name, value):
    if value:
        print(name)
        print(value)


def find_vehicleinfo():
    explicit = os.environ.get("VEHICLEINFO_JSON")
    if explicit:
        return resolve_path(explicit)

    candidate = os.path.join(CONFIG_DIR, "vehicleinfo.json")
    if os.path.isfile(candidate):
        return candidate

    return None


def frame_info_from(data):
    vehicle = os.environ.get("VEHICLE") or "ArduCopter"
    frame = os.environ.get("FRAME") or data.get(vehicle, {}).get("default_frame")
    try:
        return data[vehicle]["frames"][frame]
    except KeyError as exc:
        raise SystemExit(
            f"Mounted vehicleinfo.json does not define vehicle={vehicle!r} frame={frame!r}"
        ) from exc


def emit_vehicleinfo_args(vehicleinfo_path):
    shutil.copyfile(vehicleinfo_path, VEHICLEINFO_DEST)

    with open(vehicleinfo_path, encoding="utf-8") as f:
        data = json.load(f)

    base_dir = os.path.dirname(vehicleinfo_path)
    frame_info = frame_info_from(data)

    if not os.environ.get("MODEL"):
        print_arg("--model", resolve_model(frame_info.get("model"), base_dir))

    if not os.environ.get("PARAM_FILE"):
        params = frame_info.get("default_params_filename")
        if isinstance(params, str):
            params = [params]
        elif params is None:
            params = []

        for param in params:
            print_arg("--add-param-file", resolve_path(param, base_dir))


def main():
    vehicleinfo_path = find_vehicleinfo()
    if vehicleinfo_path:
        if not os.path.isfile(vehicleinfo_path):
            raise SystemExit(f"VEHICLEINFO_JSON does not exist: {vehicleinfo_path}")
        emit_vehicleinfo_args(vehicleinfo_path)

    model = os.environ.get("MODEL")
    if model:
        print_arg("--model", resolve_model(model))

    param_file = os.environ.get("PARAM_FILE")
    if param_file:
        print_arg("--add-param-file", resolve_path(param_file))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"resolve-sitl-config.py: {exc}", file=sys.stderr)
        sys.exit(1)
