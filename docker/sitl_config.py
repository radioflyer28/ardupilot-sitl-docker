"""Side-effect-free configuration for the managed, single-vehicle SITL runner."""
from __future__ import annotations

import argparse
import copy
import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import shlex
import sys


class ConfigError(ValueError):
    pass


def finite(value, name, low=None, high=None):
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{name}: expected a number") from exc
    if not math.isfinite(number) or (low is not None and number < low) or (high is not None and number > high):
        raise ConfigError(f"{name}: out of range")
    return number


def integer(value, name, low, high):
    number = finite(value, name, low, high)
    if number != int(number):
        raise ConfigError(f"{name}: expected an integer")
    return int(number)


def file_path(value, base, name):
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{name}: expected a nonempty path string")
    path = Path(value)
    path = (base / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_file():
        raise ConfigError(f"{name}: file does not exist: {path}")
    # sim_vehicle uses comma-separated defaults and shell-based terminal helpers.
    if any(c in str(path) for c in "\n\r\0,"):
        raise ConfigError(f"{name}: unsupported character in path: {path}")
    return str(path)


def stock_vehicleinfo(root):
    path = root / "Tools/autotest/pysim/vehicleinfo.py"
    if not path.is_file():
        raise ConfigError(f"missing upstream vehicle info loader: {path}")
    spec = importlib.util.spec_from_file_location("sitl_stock_vehicleinfo", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
        return module.VehicleInfo().options
    finally:
        sys.dont_write_bytecode = previous


def merge_vehicleinfo(stock, overrides):
    result = copy.deepcopy(stock)
    for vehicle, data in overrides.items():
        if not isinstance(data, dict) or not isinstance(data.get("frames"), dict):
            raise ConfigError(f"vehicleinfo: {vehicle}: expected frames object")
        dest = result.setdefault(vehicle, {"frames": {}})
        for key, value in data.items():
            if key != "frames":
                dest[key] = value
        for frame, values in data["frames"].items():
            if not isinstance(values, dict):
                raise ConfigError(f"vehicleinfo: {vehicle}/{frame}: expected object")
            dest["frames"].setdefault(frame, {}).update(values)
    return result


def parser(env):
    p = argparse.ArgumentParser(description="Managed single-vehicle ArduPilot SITL (unsupported upstream flags are rejected)", allow_abbrev=False)
    p.add_argument("--validate", action="store_true")
    p.add_argument("--print-effective-config", action="store_true")
    p.add_argument("--healthcheck", action="store_true")
    p.add_argument("-v", "--vehicle", default=env.get("VEHICLE") or "ArduCopter")
    p.add_argument("-f", "--frame", default=env.get("FRAME") or None)
    p.add_argument("-I", "--instance", default=env.get("INSTANCE") or "0")
    p.add_argument("--sysid", default=env.get("SYSID") or "1")
    p.add_argument("--model", default=env.get("MODEL") or None)
    p.add_argument("--speedup", default=env.get("SPEEDUP") or "1")
    p.add_argument("--custom-location", default=",".join(env.get(k) or v for k, v in zip(("LAT", "LON", "ALT", "DIR"), ("37.1971467", "-80.5780381", "618", "55"))))
    p.add_argument("--use-dir", default=env.get("SITL_RUN_DIR") or None)
    p.add_argument("--state", choices=("fresh", "resume"), default=env.get("SITL_STATE") or "fresh")
    p.add_argument("-w", "--wipe-eeprom", action="store_true")
    p.add_argument("--no-rebuild", action="store_true", help="accepted for compatibility; rebuilding is always disabled")
    p.add_argument("--no-mavproxy", action="store_true", default=env.get("NO_MAVPROXY", "1") == "1")
    p.add_argument("-m", "--mavproxy-args", default=env.get("PROXY") or "")
    p.add_argument("--aircraft")
    p.add_argument("--start-time")
    p.add_argument("--add-param-file", action="append", default=[])
    return p


def resolve(argv=None, env=None):
    env = dict(os.environ if env is None else env)
    args = parser(env).parse_args(argv)
    instance = integer(args.instance, "INSTANCE", 0, 255)
    run_dir = Path(args.use_dir or (str(Path(env["ARTIFACTS_DIR"]) / f"instance_{instance}") if env.get("ARTIFACTS_DIR") else f"/tmp/ardupilot-sitl/instance_{instance}")).resolve()
    if args.healthcheck:
        health_file = Path(env.get("SITL_HEALTH_FILE") or "/tmp/ardupilot-sitl-active.json")
        if health_file.is_file():
            run_dir = Path(json.loads(health_file.read_text())["run_dir"])
        return {"healthcheck": True, "run_dir": str(run_dir)}
    if args.state not in ("fresh", "resume"):
        raise ConfigError("SITL_STATE must be fresh or resume")
    if env.get("NO_MAVPROXY", "1") not in ("0", "1"):
        raise ConfigError("NO_MAVPROXY must be 0 or 1")
    if args.wipe_eeprom and args.state == "resume":
        raise ConfigError("-w conflicts with --state resume")
    root = Path(env.get("ARDUPILOT_ROOT") or Path.home() / "ardupilot").resolve()
    config_dir = Path(env.get("SITL_CONFIG_DIR") or "/configs").resolve()
    stock = stock_vehicleinfo(root)
    selected = env.get("VEHICLEINFO_JSON")
    if not selected and (config_dir / "vehicleinfo.json").exists():
        selected = "vehicleinfo.json"
    overrides = {}
    bundle_path = None
    if selected:
        bundle_path = file_path(selected, config_dir, "VEHICLEINFO_JSON")
        try:
            overrides = json.loads(Path(bundle_path).read_text())
        except (ValueError, OSError) as exc:
            raise ConfigError(f"VEHICLEINFO_JSON: {exc}") from exc
        if not isinstance(overrides, dict):
            raise ConfigError("vehicleinfo: expected object")
    info = merge_vehicleinfo(stock, overrides)
    vehicle = args.vehicle
    if vehicle not in info:
        raise ConfigError(f"unknown vehicle: {vehicle}")
    frame = args.frame or info[vehicle].get("default_frame")
    if not isinstance(frame, str) or frame not in info[vehicle]["frames"]:
        raise ConfigError(f"unknown frame: {vehicle}/{frame}; provide a bundle entry for custom frames")
    frame_info = info[vehicle]["frames"][frame]
    if frame_info.get("periph_params_filename") or frame_info.get("periph_extra_args"):
        raise ConfigError("managed runtime supports one vehicle, not frame-launched peripherals")
    target = frame_info.get("waf_target") or info[vehicle]["frames"][info[vehicle]["default_frame"]].get("waf_target")
    if not target:
        raise ConfigError("frame has no waf_target")
    binary = Path(file_path(target, root / "build/sitl", "vehicle binary"))
    if not os.access(binary, os.X_OK):
        raise ConfigError(f"vehicle binary is not executable: {binary}")
    bundle_frame = overrides.get(vehicle, {}).get("frames", {}).get(frame, {})
    model = args.model or frame_info.get("model") or frame
    if not isinstance(model, str) or any(c in model for c in "\n\r\0"):
        raise ConfigError("MODEL must be a nonempty single-line string")
    model_file = None
    if ":" in model and model.endswith(".json"):
        prefix, path = model.rsplit(":", 1)
        base = config_dir if args.model else Path(bundle_path).parent if bundle_path else root / "Tools/autotest"
        model_file = file_path(path, base, "MODEL")
        model = prefix + ":" + model_file
        try:
            json.loads(Path(model.rsplit(":", 1)[1]).read_text())
        except ValueError as exc:
            raise ConfigError(f"MODEL: invalid JSON: {exc}") from exc
    params = bundle_frame.get("default_params_filename", [])
    if isinstance(params, str):
        params = [params]
    if not isinstance(params, list) or not all(isinstance(p, str) for p in params):
        raise ConfigError("default_params_filename must be a string or list of strings")
    params = [file_path(p, Path(bundle_path).parent, "bundle params") for p in params]
    if bundle_frame:
        # Old sim_vehicle releases consume these themselves; newer releases use
        # embedded defaults. Absolute paths work for both, without editing upstream.
        bundle_frame["default_params_filename"] = list(params)
    try:
        extra_files = json.loads(env.get("PARAM_FILES") or "[]")
    except ValueError as exc:
        raise ConfigError("PARAM_FILES must be a JSON array of paths") from exc
    if not isinstance(extra_files, list) or not all(isinstance(p, str) for p in extra_files):
        raise ConfigError("PARAM_FILES must be a JSON array of paths")
    if env.get("PARAM_FILE"):
        extra_files.append(env["PARAM_FILE"])
    extra_files.extend(args.add_param_file)
    params.extend(file_path(p, config_dir, "parameter file") for p in extra_files)
    scripts = config_dir / "scripts"
    if scripts.exists() and not scripts.is_dir():
        raise ConfigError(f"scripts is not a directory: {scripts}")
    lua = file_path(env["LUA_SCRIPT"], config_dir, "LUA_SCRIPT") if env.get("LUA_SCRIPT") else None
    location = args.custom_location.split(",")
    if len(location) != 4:
        raise ConfigError("--custom-location requires lat,lon,alt,heading")
    location = [finite(v, name, low, high) for v, name, low, high in zip(location, ("LAT", "LON", "ALT", "DIR"), (-90, -180, None, 0), (90, 180, None, 360))]
    if args.start_time:
        try:
            datetime.datetime.strptime(args.start_time, "%Y-%m-%d-%H:%M")
        except ValueError as exc:
            raise ConfigError("--start-time requires YYYY-MM-DD-HH:MM") from exc
    sysid = integer(args.sysid, "SYSID", 1, 255)
    timeout = finite(env.get("PLAN_UPLOAD_TIMEOUT") or 60, "PLAN_UPLOAD_TIMEOUT", 0.1)
    stop_timeout = finite(env.get("SITL_STOP_TIMEOUT") or 10, "SITL_STOP_TIMEOUT", 0.1, 300)
    speedup = finite(args.speedup, "SPEEDUP", 0.001)
    if args.no_mavproxy and (args.mavproxy_args or args.aircraft):
        raise ConfigError("PROXY/-m and --aircraft require NO_MAVPROXY=0")
    proxy_args = shlex.split(args.mavproxy_args)
    # sim_vehicle has a legacy string parser. Keep this surface unambiguous and
    # prevent abbreviated master/command options from bypassing managed settings.
    index = 0
    while index < len(proxy_args):
        option, separator, value = proxy_args[index].partition("=")
        if option not in ("--out", "--logfile", "--streamrate"):
            raise ConfigError(f"PROXY: managed runtime does not accept {option}; use --out, --logfile or --streamrate")
        if not separator:
            index += 1
            if index >= len(proxy_args):
                raise ConfigError(f"PROXY: {option} needs a value")
            value = proxy_args[index]
        if not value or any(c.isspace() or c in "'\"=" for c in value):
            raise ConfigError(f"PROXY: unsupported value for {option}")
        index += 1
    master = env.get("PLAN_UPLOAD_MASTER")
    if not master:
        port = 5760 + instance * 10 if args.no_mavproxy else 20000 + instance
        master = f"tcp:127.0.0.1:{port}"
        if not args.no_mavproxy:
            proxy_args.append(f"--out=tcpin:127.0.0.1:{port}")
    plan_paths = {k: file_path(env[k], config_dir, k) if env.get(k) else None for k in ("MISSION_FILE", "FENCE_FILE", "RALLY_FILE")}
    for source in [str(config_dir), str(scripts), str(binary), bundle_path, model_file, lua, *params, *plan_paths.values()]:
        if source and Path(source).resolve().is_relative_to(run_dir):
            raise ConfigError("configuration inputs must be outside the owned run directory")
    return {
        "version": 1, "validate": args.validate, "print_effective_config": args.print_effective_config,
        "root": str(root), "config_dir": str(config_dir), "run_dir": str(run_dir), "state": args.state,
        "vehicle": vehicle, "frame": frame, "model": model, "binary": str(binary),
        "instance": instance, "sysid": sysid, "location": location, "speedup": speedup,
        "params": params, "vehicleinfo_overrides": overrides, "vehicleinfo_path": bundle_path,
        "scripts": str(scripts) if scripts.is_dir() else None, "lua_script": lua,
        "no_mavproxy": args.no_mavproxy, "proxy_args": " ".join(proxy_args),
        "aircraft": str(Path(args.aircraft).resolve()) if args.aircraft else None,
        "start_time": args.start_time, "master": master, "timeout": timeout, "stop_timeout": stop_timeout,
        "plans": plan_paths,
        "health_file": env.get("SITL_HEALTH_FILE") or "/tmp/ardupilot-sitl-active.json",
    }


def sim_arguments(config, work):
    args = ["--no-rebuild", "--vehicle", config["vehicle"], "--frame", config["frame"],
            "--model", config["model"], "-I", str(config["instance"]), "--sysid", str(config["sysid"]),
            "--custom-location=" + ",".join(map(str, config["location"])),
            "--speedup", str(config["speedup"]), "--use-dir", str(work)]
    if config["state"] == "fresh":
        args.append("-w")
    if config["no_mavproxy"]:
        args.append("--no-mavproxy")
    elif config["proxy_args"]:
        args.extend(["-m", config["proxy_args"]])
    for path in config["params"]:
        args.extend(["--add-param-file", path])
    if config["aircraft"]:
        args.extend(["--aircraft", config["aircraft"]])
    if config["start_time"]:
        args.extend(["--start-time", config["start_time"]])
    return args
