#!/usr/bin/env python3
"""Validate and upload mission, fence and rally artifacts through MAVLink."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
import socket
from pathlib import Path
import sys
import time
from typing import Any


class PlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlanItem:
    seq: int
    mission_type: str
    frame: str | int
    command: str | int
    params: tuple[float, float, float, float]
    lat: float
    lon: float
    alt: float
    current: int = 0
    autocontinue: int = 1


FENCE_TYPE_COMMANDS = {
    "polygon_inclusion": "MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION",
    "polygon_exclusion": "MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION",
    "circle_inclusion": "MAV_CMD_NAV_FENCE_CIRCLE_INCLUSION",
    "circle_exclusion": "MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION",
    "home_circle_inclusion": "MAV_CMD_NAV_FENCE_HOME_CIRCLE_INCLUSION",
    "return_point": "MAV_CMD_NAV_FENCE_RETURN_POINT",
}

FRAME_ALIASES = {
    "global": "MAV_FRAME_GLOBAL_INT",
    "global_int": "MAV_FRAME_GLOBAL_INT",
    "absolute": "MAV_FRAME_GLOBAL_INT",
    "relative": "MAV_FRAME_GLOBAL_RELATIVE_ALT_INT",
    "relative_alt": "MAV_FRAME_GLOBAL_RELATIVE_ALT_INT",
    "terrain": "MAV_FRAME_GLOBAL_TERRAIN_ALT_INT",
    "terrain_alt": "MAV_FRAME_GLOBAL_TERRAIN_ALT_INT",
}


def load_mavutil():
    os.environ.setdefault("MAVLINK20", "1")
    from pymavlink import mavutil  # pylint: disable=import-outside-toplevel

    return mavutil


def resolve_path(path: str, config_dir: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return config_dir / candidate


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("version", 1) != 1:
            raise PlanError(f"{path}: unsupported version (expected 1)")
        return data
    except OSError as exc:
        raise PlanError(f"{path}: could not read file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"{path}: invalid JSON: {exc}") from exc


def require_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlanError(f"{context}: expected an object")
    return value


def require_sequence(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise PlanError(f"{context}: expected a list")
    return value


def number(value: Any, context: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PlanError(f"{context}: expected a number") from exc
    if isinstance(value, bool) or not math.isfinite(result):
        raise PlanError(f"{context}: expected a finite number")
    return result


def required_number(obj: dict[str, Any], key: str, context: str) -> float:
    if key not in obj:
        raise PlanError(f"{context}: missing required field {key!r}")
    return number(obj[key], f"{context}.{key}")


def optional_number(obj: dict[str, Any], key: str, default: float, context: str) -> float:
    if key not in obj:
        return default
    return number(obj[key], f"{context}.{key}")


def normalize_type(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{context}: expected a non-empty string")
    return value.strip().lower().replace("-", "_")


def normalize_frame(value: Any, default: str, context: str) -> str | int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{context}: expected a frame string or integer")
    frame = value.strip()
    alias = FRAME_ALIASES.get(frame.lower().replace("-", "_"))
    if alias:
        return alias
    if frame.startswith("MAV_FRAME_"):
        return frame
    return f"MAV_FRAME_{frame.upper()}"


def raw_params(item: dict[str, Any], context: str) -> tuple[float, float, float, float]:
    if "params" in item:
        params = require_sequence(item["params"], f"{context}.params")
        if len(params) != 4:
            raise PlanError(f"{context}.params: expected exactly 4 values")
        return tuple(number(value, f"{context}.params[{idx}]") for idx, value in enumerate(params))  # type: ignore[return-value]

    return (
        optional_number(item, "param1", 0.0, context),
        optional_number(item, "param2", 0.0, context),
        optional_number(item, "param3", 0.0, context),
        optional_number(item, "param4", 0.0, context),
    )


def raw_command(value: Any, context: str) -> str | int:
    if isinstance(value, int):
        if isinstance(value, bool) or not 0 <= value <= 65535:
            raise PlanError(f"{context}: command must be an unsigned 16-bit integer")
        return value
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{context}: expected a command string or integer")
    command = value.strip()
    if command.startswith("MAV_CMD_"):
        return command
    return f"MAV_CMD_{command.upper()}"


def location_from(obj: dict[str, Any], context: str) -> tuple[float, float]:
    if "center" in obj:
        center = require_mapping(obj["center"], f"{context}.center")
        return (
            required_number(center, "lat", f"{context}.center"),
            required_number(center, "lon", f"{context}.center"),
        )
    return (
        required_number(obj, "lat", context),
        required_number(obj, "lon", context),
    )


def parse_raw_items(
    raw_items_value: Any,
    mission_type: str,
    default_frame: str,
    path: Path,
) -> list[PlanItem]:
    raw_items = require_sequence(raw_items_value, f"{path}.items")
    items = []
    for seq, raw in enumerate(raw_items):
        context = f"{path}.items[{seq}]"
        item = require_mapping(raw, context)
        if "command" not in item:
            raise PlanError(f"{context}: missing required field 'command'")
        items.append(
            PlanItem(
                seq=seq,
                mission_type=mission_type,
                frame=normalize_frame(item.get("frame"), default_frame, f"{context}.frame"),
                command=raw_command(item["command"], f"{context}.command"),
                params=raw_params(item, context),
                lat=required_number(item, "lat", context),
                lon=required_number(item, "lon", context),
                alt=optional_number(item, "alt", optional_number(item, "z", 0.0, context), context),
            )
        )
    return items


def parse_fence_file(path: Path) -> list[PlanItem]:
    data = load_json(path)
    if isinstance(data, dict) and "items" in data:
        return parse_raw_items(
            data["items"],
            "MAV_MISSION_TYPE_FENCE",
            "MAV_FRAME_GLOBAL_INT",
            path,
        )

    fences_value = data if isinstance(data, list) else require_mapping(data, str(path)).get("fences")
    fences = require_sequence(fences_value, f"{path}.fences")
    items: list[PlanItem] = []

    for fence_index, raw in enumerate(fences):
        context = f"{path}.fences[{fence_index}]"
        fence = require_mapping(raw, context)
        fence_type = normalize_type(fence.get("type"), f"{context}.type")
        command = FENCE_TYPE_COMMANDS.get(fence_type)
        if command is None:
            expected = ", ".join(sorted(FENCE_TYPE_COMMANDS))
            raise PlanError(f"{context}.type: unsupported fence type {fence_type!r}; expected one of: {expected}")

        if fence_type.startswith("polygon_"):
            points = require_sequence(fence.get("points"), f"{context}.points")
            if not 3 <= len(points) <= 255:
                raise PlanError(f"{context}.points: expected 3 to 255 polygon vertices")
            altitude = optional_number(fence, "alt", 0.0, context)
            for point_index, raw_point in enumerate(points):
                point_context = f"{context}.points[{point_index}]"
                point = require_mapping(raw_point, point_context)
                items.append(
                    PlanItem(
                        seq=len(items),
                        mission_type="MAV_MISSION_TYPE_FENCE",
                        frame=normalize_frame(fence.get("frame"), "MAV_FRAME_GLOBAL_INT", f"{context}.frame"),
                        command=command,
                        params=(float(len(points)), 0.0, 0.0, 0.0),
                        lat=required_number(point, "lat", point_context),
                        lon=required_number(point, "lon", point_context),
                        alt=optional_number(point, "alt", altitude, point_context),
                    )
                )
            continue

        if fence_type in {"circle_inclusion", "circle_exclusion"}:
            lat, lon = location_from(fence, context)
            radius = required_number(fence, "radius", context)
            altitude = optional_number(fence, "alt", 0.0, context)
        elif fence_type == "home_circle_inclusion":
            lat, lon = 0.0, 0.0
            radius = required_number(fence, "radius", context)
            altitude = 0.0
        else:
            lat, lon = location_from(fence, context)
            radius = 0.0
            altitude = optional_number(fence, "alt", 0.0, context)

        if fence_type.endswith("inclusion") or fence_type.endswith("exclusion"):
            if radius <= 0:
                raise PlanError(f"{context}.radius: must be positive")
        items.append(
            PlanItem(
                seq=len(items),
                mission_type="MAV_MISSION_TYPE_FENCE",
                frame=normalize_frame(fence.get("frame"), "MAV_FRAME_GLOBAL_INT", f"{context}.frame"),
                command=command,
                params=(radius, 0.0, 0.0, 0.0),
                lat=lat,
                lon=lon,
                alt=altitude,
            )
        )

    return items


def parse_rally_file(path: Path) -> list[PlanItem]:
    data = load_json(path)
    if isinstance(data, dict) and "items" in data:
        return parse_raw_items(
            data["items"],
            "MAV_MISSION_TYPE_RALLY",
            "MAV_FRAME_GLOBAL_RELATIVE_ALT_INT",
            path,
        )

    points_value = data if isinstance(data, list) else require_mapping(data, str(path)).get("points")
    points = require_sequence(points_value, f"{path}.points")
    items = []
    for seq, raw in enumerate(points):
        context = f"{path}.points[{seq}]"
        point = require_mapping(raw, context)
        items.append(
            PlanItem(
                seq=seq,
                mission_type="MAV_MISSION_TYPE_RALLY",
                frame=normalize_frame(point.get("frame"), "MAV_FRAME_GLOBAL_RELATIVE_ALT_INT", f"{context}.frame"),
                command="MAV_CMD_NAV_RALLY_POINT",
                params=(0.0, 0.0, 0.0, 0.0),
                lat=required_number(point, "lat", context),
                lon=required_number(point, "lon", context),
                alt=required_number(point, "alt", context),
            )
        )
    return items


def parse_mission_file(path: Path) -> list[PlanItem]:
    """Parse the complete WPL file before any vehicle state is touched."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "QGC WPL 110":
        raise PlanError(f"{path}: expected QGC WPL 110 header")
    items = []
    for line_number, line in enumerate(lines[1:], 2):
        if not line.strip():
            continue
        fields = line.split()
        context = f"{path}:{line_number}"
        if len(fields) != 12:
            raise PlanError(f"{context}: expected 12 fields")
        values = [number(v, context) for v in fields]
        for index in (0, 1, 2, 3, 11):
            if values[index] != int(values[index]):
                raise PlanError(f"{context}: field {index + 1} must be an integer")
        seq, current, frame, command = map(int, values[:4])
        if seq != len(items) or current not in (0, 1) or values[11] not in (0, 1):
            raise PlanError(f"{context}: invalid sequence/current/autocontinue")
        if not 0 <= command <= 65535:
            raise PlanError(f"{context}: command out of range")
        items.append(PlanItem(seq, "MAV_MISSION_TYPE_MISSION", frame, command,
                              tuple(values[4:8]), *values[8:11], current, int(values[11])))
    return items


GLOBAL_FRAMES = {0, 3, 5, 6, 10, 11, "MAV_FRAME_GLOBAL", "MAV_FRAME_GLOBAL_INT",
                 "MAV_FRAME_GLOBAL_RELATIVE_ALT", "MAV_FRAME_GLOBAL_RELATIVE_ALT_INT",
                 "MAV_FRAME_GLOBAL_TERRAIN_ALT", "MAV_FRAME_GLOBAL_TERRAIN_ALT_INT"}


def validate_items(items, path):
    for item in items:
        if item.frame in GLOBAL_FRAMES:
            if not -90 <= item.lat <= 90 or not -180 <= item.lon <= 180:
                raise PlanError(f"{path}: item {item.seq}: latitude/longitude out of range")
        elif item.frame in (2, "MAV_FRAME_MISSION") and item.mission_type == "MAV_MISSION_TYPE_MISSION":
            if any(v != int(v) or not -(2**31) <= v < 2**31 for v in (item.lat, item.lon)):
                raise PlanError(f"{path}: item {item.seq}: mission-frame x/y must be int32")
        else:
            raise PlanError(f"{path}: item {item.seq}: unsupported frame {item.frame}")
    if len(items) > 65535:
        raise PlanError(f"{path}: too many items")


def mav_value(mavlink: Any, value: str | int, context: str) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(getattr(mavlink, value))
    except AttributeError as exc:
        raise PlanError(f"{context}: unknown MAVLink constant {value}") from exc


def encode_item(master: Any, item: PlanItem, target_system: int, target_component: int, legacy=False) -> Any:
    constants = load_mavutil().mavlink
    frame = mav_value(constants, item.frame, f"item {item.seq} frame")
    global_frame = item.frame in GLOBAL_FRAMES
    if legacy:
        frame = {5: 0, 6: 3, 11: 10}.get(frame, frame)
        encode = master.mav.mission_item_encode
        x, y = item.lat, item.lon
    else:
        frame = {0: 5, 3: 6, 10: 11}.get(frame, frame)
        encode = master.mav.mission_item_int_encode
        scale = 1e7 if global_frame else 1
        x, y = int(round(item.lat * scale)), int(round(item.lon * scale))
    return encode(target_system, target_component, item.seq, frame,
                  mav_value(constants, item.command, f"item {item.seq} command"),
                  item.current, item.autocontinue, *item.params, x, y, item.alt,
                  mav_value(constants, item.mission_type, f"item {item.seq} mission_type"))


def connect(master_spec: str, timeout: float, target_system=1, target_component=1, expected_autopilot=None) -> tuple[Any, Any]:
    mavutil = load_mavutil()
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        connection = None
        keep = False
        previous_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(min(1.0, max(0.01, deadline - time.monotonic())))
            connection = mavutil.mavlink_connection(master_spec, source_system=255,
                                                   source_component=190, dialect="ardupilotmega", retries=1)
            while time.monotonic() < deadline:
                heartbeat = connection.wait_heartbeat(timeout=min(1.0, max(0.01, deadline - time.monotonic())))
                if heartbeat is None:
                    # Keep a healthy TCP connection open while the vehicle boots.
                    continue
                if (heartbeat.get_srcSystem() == target_system and heartbeat.get_srcComponent() == target_component
                        and heartbeat.autopilot != mavutil.mavlink.MAV_AUTOPILOT_INVALID
                        and (expected_autopilot is None or heartbeat.autopilot == expected_autopilot)
                        # ArduPilot sends heartbeats before mission storage init.
                        # UNINIT/BOOT/CALIBRATING must not trigger plan upload.
                        and heartbeat.system_status not in (0, 1, 2)):
                    keep = True
                    return connection, heartbeat
        except (OSError, ValueError) as exc:
            last_error = exc
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        finally:
            socket.setdefaulttimeout(previous_timeout)
            if connection is not None and not keep:
                connection.close()
    detail = f": {last_error}" if last_error else ""
    raise PlanError(f"timed out waiting for autopilot {target_system}/{target_component} on {master_spec}{detail}")


def upload_items(master: Any, heartbeat: Any, label: str, items: list[PlanItem], timeout: float) -> None:
    mavlink = load_mavutil().mavlink
    target_system, target_component = heartbeat.get_srcSystem(), heartbeat.get_srcComponent()
    mission_type = mav_value(mavlink, "MAV_MISSION_TYPE_" + label.upper(), f"{label} mission_type")
    encoded = [encode_item(master, item, target_system, target_component) for item in items]
    remaining = set(range(len(items)))
    deadline = time.monotonic() + timeout
    retry_at = 0.0
    last_item = None
    print(f"upload-plan-artifacts.py: uploading {len(items)} {label} item(s)", flush=True)
    while time.monotonic() < deadline:
        if time.monotonic() >= retry_at:
            if last_item is None:
                master.mav.mission_count_send(target_system, target_component, len(items), mission_type)
            else:
                master.mav.send(last_item)
            retry_at = time.monotonic() + 1.0
        msg = master.recv_match(type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"],
                                blocking=True, timeout=min(0.5, max(0.01, deadline - time.monotonic())))
        if msg is None:
            continue
        if (msg.get_srcSystem() != target_system or msg.get_srcComponent() != target_component
                or getattr(msg, "mission_type", 0) != mission_type
                or getattr(msg, "target_system", 0) not in (0, master.source_system)
                or getattr(msg, "target_component", 0) not in (0, master.source_component)):
            continue
        if msg.get_type() == "MISSION_ACK":
            if msg.type != mavlink.MAV_MISSION_ACCEPTED:
                raise PlanError(f"{label}: upload rejected, MAV_MISSION_RESULT={msg.type}")
            if remaining:
                raise PlanError(f"{label}: accepted before all items were requested")
            print(f"upload-plan-artifacts.py: uploaded {len(items)} {label} item(s)", flush=True)
            return
        if not 0 <= msg.seq < len(items):
            raise PlanError(f"{label}: invalid requested sequence {msg.seq}")
        # Repeated requests are normal loss recovery, including after the last item.
        last_item = (encode_item(master, items[msg.seq], target_system, target_component, legacy=True)
                     if msg.get_type() == "MISSION_REQUEST" else encoded[msg.seq])
        master.mav.send(last_item)
        remaining.discard(msg.seq)
        retry_at = time.monotonic() + 1.0
    raise PlanError(f"{label}: upload timed out before accepted MISSION_ACK")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=os.environ.get("SITL_CONFIG_DIR") or "/configs")
    parser.add_argument("--master", default=os.environ.get("PLAN_UPLOAD_MASTER"))
    parser.add_argument("--timeout", type=float, default=os.environ.get("PLAN_UPLOAD_TIMEOUT") or "60")
    parser.add_argument("--mission", default=os.environ.get("MISSION_FILE"))
    parser.add_argument("--target-system", type=int, default=os.environ.get("SYSID") or "1")
    parser.add_argument("--target-component", type=int, default=1)
    parser.add_argument("--autopilot", choices=("ardupilot", "px4"), help="require the expected autopilot family")
    parser.add_argument("--wait-ready", action="store_true", help="verify target heartbeat even with no artifacts")
    parser.add_argument("--fence", default=os.environ.get("FENCE_FILE"))
    parser.add_argument("--rally", default=os.environ.get("RALLY_FILE"))
    parser.add_argument("--dry-run", action="store_true", help="parse selected files without connecting to MAVLink")
    return parser.parse_args()


def selected_plans(args: argparse.Namespace) -> list[tuple[str, Path, list[PlanItem]]]:
    config_dir = Path(args.config_dir)
    plans = []
    if args.mission:
        mission_path = resolve_path(args.mission, config_dir)
        if not mission_path.is_file():
            raise PlanError(f"MISSION_FILE does not exist or is not a file: {mission_path}")
        plans.append(("mission", mission_path, parse_mission_file(mission_path)))
    if args.fence:
        fence_path = resolve_path(args.fence, config_dir)
        if not fence_path.is_file():
            raise PlanError(f"FENCE_FILE does not exist or is not a file: {fence_path}")
        plans.append(("fence", fence_path, parse_fence_file(fence_path)))
    if args.rally:
        rally_path = resolve_path(args.rally, config_dir)
        if not rally_path.is_file():
            raise PlanError(f"RALLY_FILE does not exist or is not a file: {rally_path}")
        plans.append(("rally", rally_path, parse_rally_file(rally_path)))
    for _label, path, items in plans:
        validate_items(items, path)
    return plans


def main() -> int:
    args = parse_args()
    try:
        plans = selected_plans(args)
        if not plans and not args.wait_ready:
            return 0
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise PlanError("timeout must be finite and positive")
        if not 1 <= args.target_system <= 255 or not 1 <= args.target_component <= 255:
            raise PlanError("target system and component must be between 1 and 255")

        if args.dry_run:
            for label, path, items in plans:
                print(f"{path}: parsed {len(items)} {label} item(s)")
            return 0

        if not args.master:
            raise PlanError("PLAN_UPLOAD_MASTER was not set and no --master was provided")

        deadline = time.monotonic() + args.timeout
        expected_autopilot = None
        if args.autopilot:
            constant = "MAV_AUTOPILOT_PX4" if args.autopilot == "px4" else "MAV_AUTOPILOT_ARDUPILOTMEGA"
            expected_autopilot = mav_value(load_mavutil().mavlink, constant, "autopilot")
        master, heartbeat = connect(args.master, args.timeout, args.target_system, args.target_component, expected_autopilot)
        try:
            for label, _path, items in plans:
                upload_items(master, heartbeat, label, items, max(0, deadline - time.monotonic()))
        finally:
            master.close()
    except (PlanError, OSError, ValueError, ImportError) as exc:
        print(f"upload-plan-artifacts.py: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
