# Runtime Plan Artifacts

## Current contract

Each container owns one vehicle and one read-only input bundle. The managed
runner parses every selected artifact before launch, then uploads it after an
initialized heartbeat from the expected autopilot family, `SYSID` and component 1
(beyond UNINIT/BOOT/CALIBRATING). Boot heartbeats can precede mission storage
initialization. Readiness requires
accepted uploads for all selected plans.

| Setting | Input | MAVLink plan type |
| --- | --- | --- |
| `MISSION_FILE` | QGC WPL 110 | `MAV_MISSION_TYPE_MISSION` |
| `FENCE_FILE` | project-owned JSON | `MAV_MISSION_TYPE_FENCE` |
| `RALLY_FILE` | project-owned JSON | `MAV_MISSION_TYPE_RALLY` |

All relative paths resolve under `SITL_CONFIG_DIR`. Missing or malformed inputs
fail preflight. `MISSION_FILE` no longer installs a Lua loader or requires
`SCR_ENABLE`; Lua is reserved for user simulation behavior.

Example service-local bundle:

```text
/configs/
  vehicleinfo.json
  model.json
  params.parm
  scripts/initial-state.lua
  missions/survey.waypoints
  fences/operating-area.json
  rally/recovery-points.json
```

Selected valid empty plans (a WPL header with no rows or JSON with an empty
collection, not a zero-byte file) clear the corresponding plan type. Omitted plans do not
send a clear; `SITL_STATE=resume` may therefore retain an existing plan. Fresh
runs use a new work directory. Explicitly selected plans are re-uploaded even
on resume. Loading does not arm the vehicle, change flight mode or start a
mission.

## Input formats

WPL parsing checks the exact header, twelve fields per nonempty item row,
contiguous sequence numbers, current/autocontinue flags and numeric values.
Global, relative-altitude and terrain global frames are supported, along with
`MAV_FRAME_MISSION` for non-location command fields. Unsupported local frames
fail explicitly rather than being silently scaled as latitude/longitude.

Fence JSON supports polygon inclusion/exclusion, circle inclusion/exclusion,
home-circle inclusion and return points. Rally JSON supports location/altitude
points. Both also accept raw `items` with command, frame and parameters.
Version 1 is the supported object format (omitting version retains compatibility).
Numbers must be finite, geographic coordinates in range, circle radii positive,
and polygon vertex counts between 3 and 255.

Examples are in `configs/examples/mission/` and
`configs/examples/plan-artifacts/`. Dry-run parsing needs only standard Python:

```bash
python3 docker/upload-plan-artifacts.py --dry-run --config-dir configs/examples/mission \
  --mission missions/simple-copter.waypoints
python3 docker/upload-plan-artifacts.py --dry-run --config-dir configs/examples/plan-artifacts \
  --fence fences/simple-polygon.json --rally rally/recovery-points.json
```

Geometry validity, parameter compatibility and vehicle support are ultimately
checked by the autopilot; a syntactically valid input can still receive a
rejected upload ACK. Such rejection fails startup.

## Transport and retry behavior

ArduPilot direct mode uses `tcp:127.0.0.1:(5760 + INSTANCE * 10)`. This endpoint normally
supports one client: clients must wait until initialization releases it and the
container becomes healthy. With MAVProxy, the wrapper adds a private loopback
`tcpin` output at `20000 + INSTANCE`. `PLAN_UPLOAD_MASTER` can select an explicit
endpoint but cannot change the configured target identity.

PX4 uses a dedicated native UDP link: local `30000 + INSTANCE`, loopback peer
`31000 + INSTANCE`. Its initializer binds `udpin:127.0.0.1:<peer>` without
consuming the GCS/offboard endpoints. See [PX4 SIH](PX4_SIH.md#networking).

The uploader:

- Uses MAVLink 2 and source identity 255/190.
- Waits for the selected autopilot, ignoring unrelated/GCS heartbeats.
- Keeps the connection open while waiting for startup and closes it on failure.
- Uploads mission, fence and rally serially with independent mission types.
- Retries `MISSION_COUNT` and the last item when responses are lost.
- Answers repeated `MISSION_REQUEST_INT` and legacy `MISSION_REQUEST`, including
  requests for the last item while waiting for ACK.
- Filters responses by source, destination and mission type.
- Requires an accepted `MISSION_ACK` after all items were requested.
- Uses one overall `PLAN_UPLOAD_TIMEOUT` deadline for connection and uploads.

The runner independently enforces its startup deadline and monitors vehicle and
initializer processes. Upload failure tears down the run; retained state/logs
remain available for diagnosis. Across multiple plan types there is no atomic
vehicle-side transaction: a later upload failure can follow an earlier success.
The vehicle is not reported ready in that case.

## Why not Lua for mission preload?

ArduPilot Lua exposes `mission:clear`, `mission:set_item` and mission-item types,
but not corresponding fence/rally replacement APIs. The old Lua mission loader
also completed asynchronously and depended on scripting parameters. A shared
MAVLink preload path gives all three types observable completion, one timeout
and consistent failure semantics without changing upstream ArduPilot.

User Lua remains appropriate for pose injection, simulated sensors and other
runtime behavior. Its completion is not included in the plan-readiness signal.

## Fleet and manifest direction

A fleet layer should generate existing env vars, mounts and ports rather than
make services share mutable input/state. Keep one bundle and writable run root
per service.

For future manifests:

- Mission/fence/rally must choose exactly one file or inline representation.
- Normalize inline definitions into native files before invoking the runtime.
- Params may combine ordered files and a final inline override map.
- Reference Lua code as files; generate separate structured script config.
- Keep instance, system ID, image, home, model, outputs and endpoint allocation
  explicit and service-local.

PX4 now integrates the shared uploader through a dedicated native loopback UDP
link and expected-family heartbeat check. Plan command/frame semantics remain
firmware-specific; row 0 is a stored mission item on PX4, not synthesized home.

Open work includes importing common ground-station plan formats and expanding
release/transport qualification. Host-only regression tests validate the protocol
state machine but are not live autopilot qualification.
