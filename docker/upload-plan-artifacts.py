#!/usr/bin/env python3
"""Upload runtime fence and rally artifacts through MAVLink mission protocol."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
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
            return json.load(f)
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
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PlanError(f"{context}: expected a number") from exc


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


def mav_value(mavlink: Any, value: str | int, context: str) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(getattr(mavlink, value))
    except AttributeError as exc:
        raise PlanError(f"{context}: unknown MAVLink constant {value}") from exc


def encode_item(master: Any, item: PlanItem, target_system: int, target_component: int) -> Any:
    mavlink = master.mav
    constants = load_mavutil().mavlink
    return mavlink.mission_item_int_encode(
        target_system,
        target_component,
        item.seq,
        mav_value(constants, item.frame, f"item {item.seq} frame"),
        mav_value(constants, item.command, f"item {item.seq} command"),
        0,
        0,
        item.params[0],
        item.params[1],
        item.params[2],
        item.params[3],
        int(round(item.lat * 1e7)),
        int(round(item.lon * 1e7)),
        item.alt,
        mav_value(constants, item.mission_type, f"item {item.seq} mission_type"),
    )


def connect(master_spec: str, timeout: float) -> tuple[Any, Any]:
    mavutil = load_mavutil()
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        connection = None
        try:
            connection = mavutil.mavlink_connection(
                master_spec,
                source_system=255,
                source_component=0,
                dialect="ardupilotmega",
            )
            heartbeat = connection.wait_heartbeat(timeout=1)
            if heartbeat is not None:
                return connection, heartbeat
        except Exception as exc:  # pymavlink raises several connection types
            last_error = exc
            if connection is not None:
                connection.close()
            time.sleep(0.5)

    detail = f": {last_error}" if last_error else ""
    raise PlanError(f"timed out waiting for MAVLink heartbeat on {master_spec}{detail}")


def upload_items(master: Any, heartbeat: Any, label: str, items: list[PlanItem], timeout: float) -> None:
    mavutil = load_mavutil()
    mavlink = mavutil.mavlink
    if not items:
        print(f"upload-plan-artifacts.py: {label}: no items to upload")
        return

    target_system = heartbeat.get_srcSystem()
    target_component = heartbeat.get_srcComponent()
    mission_type = mav_value(mavlink, items[0].mission_type, f"{label} mission_type")
    encoded = [encode_item(master, item, target_system, target_component) for item in items]

    print(f"upload-plan-artifacts.py: uploading {len(items)} {label} item(s)")
    master.mav.mission_count_send(target_system, target_component, len(encoded), mission_type)

    remaining = set(range(len(encoded)))
    deadline = time.monotonic() + timeout
    while remaining:
        if time.monotonic() > deadline:
            pending = ", ".join(str(seq) for seq in sorted(remaining))
            raise PlanError(f"{label}: timed out waiting for item request(s): {pending}")

        msg = master.recv_match(type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"], blocking=True, timeout=1)
        if msg is None:
            continue

        msg_type = msg.get_type()
        msg_mission_type = getattr(msg, "mission_type", mission_type)
        if msg_mission_type != mission_type:
            continue

        if msg_type == "MISSION_ACK":
            result = mavutil.mavlink.enums["MAV_MISSION_RESULT"].get(msg.type)
            result_name = result.name if result else str(msg.type)
            raise PlanError(f"{label}: received early MISSION_ACK {result_name}")

        seq = msg.seq
        if seq not in remaining:
            continue
        master.mav.send(encoded[seq])
        remaining.remove(seq)
        deadline = time.monotonic() + max(10.0, timeout / 4.0)

    ack_deadline = time.monotonic() + max(10.0, timeout / 4.0)
    while time.monotonic() < ack_deadline:
        msg = master.recv_match(type=["MISSION_ACK"], blocking=True, timeout=1)
        if msg is None:
            continue
        if getattr(msg, "mission_type", mission_type) != mission_type:
            continue
        if msg.type != mavlink.MAV_MISSION_ACCEPTED:
            result = mavlink.enums["MAV_MISSION_RESULT"].get(msg.type)
            result_name = result.name if result else str(msg.type)
            raise PlanError(f"{label}: upload failed: {result_name}")
        print(f"upload-plan-artifacts.py: uploaded {len(items)} {label} item(s)")
        return

    raise PlanError(f"{label}: timed out waiting for MISSION_ACK")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=os.environ.get("SITL_CONFIG_DIR") or "/configs")
    parser.add_argument("--master", default=os.environ.get("PLAN_UPLOAD_MASTER"))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("PLAN_UPLOAD_TIMEOUT") or 60))
    parser.add_argument("--fence", default=os.environ.get("FENCE_FILE"))
    parser.add_argument("--rally", default=os.environ.get("RALLY_FILE"))
    parser.add_argument("--dry-run", action="store_true", help="parse selected files without connecting to MAVLink")
    return parser.parse_args()


def selected_plans(args: argparse.Namespace) -> list[tuple[str, Path, list[PlanItem]]]:
    config_dir = Path(args.config_dir)
    plans = []
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
    return plans


def main() -> int:
    args = parse_args()
    try:
        plans = selected_plans(args)
        if not plans:
            return 0

        if args.dry_run:
            for label, path, items in plans:
                print(f"{path}: parsed {len(items)} {label} item(s)")
            return 0

        if not args.master:
            raise PlanError("PLAN_UPLOAD_MASTER was not set and no --master was provided")

        master, heartbeat = connect(args.master, args.timeout)
        try:
            for label, _path, items in plans:
                upload_items(master, heartbeat, label, items, args.timeout)
        finally:
            master.close()
    except PlanError as exc:
        print(f"upload-plan-artifacts.py: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
