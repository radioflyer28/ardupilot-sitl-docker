# Runtime Plan Artifacts

This note captures how missions, geofences, rally points, initial state, and
other scenario artifacts should fit into runtime SITL config bundles,
especially when running many SITL containers at once.


## Summary

The project should treat each SITL container as owning one runtime config bundle.
That bundle should contain every artifact needed for that vehicle:

```text
configs/fleet/uav0/
  vehicleinfo.json
  model.json
  params.parm
  scripts/
    initial-state.lua
  missions/
    survey.waypoints
  fences/
    operating-area.json
  rally/
    recovery-points.json
```

For Docker Compose, each service should mount its own bundle at `/configs`.
Inside a container, fixed staging paths such as `missions/mission.waypoints` are
safe because each container has an isolated ArduPilot working tree. Avoid
designs that rely on shared global files, host-side mutable state, or one
container managing another container's plan artifacts.


## Current State

Implemented runtime artifacts:

- `MODEL`: optional `sim_vehicle.py --model` override.
- `PARAM_FILE`: optional `sim_vehicle.py --add-param-file` override.
- `LUA_SCRIPT`: optional single Lua script copied into the working `scripts/`
  directory.
- `$SITL_CONFIG_DIR/scripts/`: optional bundle scripts copied into the working
  `scripts/` directory.
- `MISSION_FILE`: optional QGC WPL 110 mission staged into the working
  `missions/` directory and loaded by the image-provided Lua script.
- `FENCE_FILE`: optional project-owned JSON geofence plan uploaded with
  `MAV_MISSION_TYPE_FENCE`.
- `RALLY_FILE`: optional project-owned JSON rally plan uploaded with
  `MAV_MISSION_TYPE_RALLY`.
- `PLAN_UPLOAD_MASTER`: optional MAVLink endpoint override for fence/rally
  uploads.
- `PLAN_UPLOAD_TIMEOUT`: upload timeout, default 60 seconds.

Implemented examples:

- `configs/examples/initial-state/`
- `configs/examples/mission/`
- `configs/examples/plan-artifacts/`


## Missions

Plain mission loading can use the Lua path because ArduPilot exposes mission
write APIs to scripting:

- `mission:clear()`
- `mission:set_item(index, item)`
- `mavlink_mission_item_int_t()`

This repo uses `MISSION_FILE` for QGC WPL 110 mission files. The wrapper
resolves the selected file relative to `SITL_CONFIG_DIR`, stages it into the
ArduPilot working tree, and installs `load-mission.lua`.

This path is intentionally independent of MAVProxy, so it works with
`NO_MAVPROXY=1`.


## Geofence And Rally Findings

MAVLink models mission, fence, and rally as separate mission-protocol plan
types using `mission_type`:

- `MAV_MISSION_TYPE_MISSION`
- `MAV_MISSION_TYPE_FENCE`
- `MAV_MISSION_TYPE_RALLY`

ArduPilot supports those plan types through separate C++ mission item protocol
handlers:

- `MissionItemProtocol_Waypoints`
- `MissionItemProtocol_Fence`
- `MissionItemProtocol_Rally`

The local ArduPilot checkout registers fence and rally handlers when the
vehicle supports them. Fence uploads accept commands such as:

- `MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION`
- `MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION`
- `MAV_CMD_NAV_FENCE_RETURN_POINT`
- `MAV_CMD_NAV_FENCE_CIRCLE_INCLUSION`
- `MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION`
- `MAV_CMD_NAV_FENCE_HOME_CIRCLE_INCLUSION`

Rally uploads accept `MAV_CMD_NAV_RALLY_POINT`.

Lua is not currently the right write path for fences and rally points. The
local scripting bindings expose fence status/read helpers and rally lookup, but
not APIs to replace stored fence or rally plans.

`QGC WPL 110` should also not be stretched to represent all plan artifacts. It
is useful for mission waypoints, but MAVLink documents it as not supporting
geofence or rally point information.


## Implemented Low-Level Knobs

Keep direct env vars for one-off SITL runs. They are useful for quick
experiments, CI smoke tests, and derived images that already know exactly which
artifact to mount:

```text
MISSION_FILE=
FENCE_FILE=
RALLY_FILE=
```

These mirror the existing path semantics:

- empty by default
- absolute paths used as-is
- relative paths resolved under `SITL_CONFIG_DIR`
- fail fast when the selected file does not exist
- stage or upload the artifact inside the container

Unlike `MISSION_FILE`, fence and rally are uploaded with MAVLink mission
protocol tooling after SITL is accepting MAVLink connections. The runtime image
includes a small Python helper that uses the ArduPilot Python environment and
pymavlink already present for SITL tooling.

The helper:

- connect to the container-local SITL MAVLink endpoint
- upload one artifact at a time with the proper `mission_type`
- use `MISSION_COUNT`, `MISSION_REQUEST_INT` / `MISSION_REQUEST`, and
  `MISSION_ACK`
- preserve mission, fence, and rally as independent plan types
- report concise errors with the artifact path, item sequence, and ack result

The implemented helper uses an explicit project-owned JSON format for fence and
rally examples before trying to parse every ground-station export format. JSON
keeps runtime dependencies low and makes generated Compose/fleet tooling
simpler.

When `NO_MAVPROXY=1`, the default upload endpoint is direct SITL TCP:
`tcp:127.0.0.1:$((5760 + INSTANCE * 10))`. When MAVProxy is enabled and
`PLAN_UPLOAD_MASTER` is unset, the wrapper adds a private in-container MAVProxy
`tcpin` output at `$((5761 + INSTANCE * 10))` and uploads through that.
Explicit `PLAN_UPLOAD_MASTER` values are used as-is.

For multi-SITL runs, do not expect users to manage every artifact through long
hand-written env blocks. Add a higher-level fleet/scenario layer that can expand
per-vehicle definitions into Compose services, mounts, ports, and env vars.


## Proposed Bundle Shape

A complete per-vehicle bundle should remain flat enough to inspect, but grouped
by artifact type:

```text
SITL_CONFIG_DIR/
  vehicleinfo.json
  params.parm
  model.json
  scripts/
    initial-state.lua
  missions/
    mission.waypoints
  fences/
    fence.json
  rally/
    rally.json
```

Suggested future env use:

```text
PARAM_FILE=params.parm
MISSION_FILE=missions/mission.waypoints
LUA_SCRIPT=scripts/initial-state.lua
FENCE_FILE=fences/fence.json
RALLY_FILE=rally/rally.json
```

These env vars are the low-level runtime interface. A future fleet manager
should generate them from a clearer per-vehicle config rather than asking users
to hand-maintain large Compose env blocks.


## One-Off Vs Fleet Configuration

Use direct env vars for a single vehicle or a quick override:

```bash
docker run ... \
  -e PARAM_FILE=params.parm \
  -e MISSION_FILE=missions/mission.waypoints \
  -e LUA_SCRIPT=scripts/initial-state.lua
```

Use a fleet/scenario definition for multiple vehicles. It should describe each
vehicle once, then generate Compose services and env vars:

```yaml
vehicles:
  - name: uav0
    image: ardupilot-sitl:copter-4.6.3
    bundle: ./configs/fleet/uav0
    instance: 0
    sysid: 1
    vehicle: ArduCopter
    frame: quad
    location: { lat: 37.1971467, lon: -80.5780381, alt: 618, heading: 55 }
    params: params.parm
    mission: missions/survey.waypoints
    initial_state: scripts/initial-state.lua
    fence: fences/operating-area.json
    rally: rally/recovery-points.json
```

The generated Compose service would mount `bundle` at `/configs`, set
container-local env vars, and publish the right ports for that vehicle. This
keeps the runtime image simple while making fleet launches repeatable.


## Multi-SITL Design Constraints

When running many vehicles:

- use one container per SITL instance
- mount one bundle per service at `/configs`
- keep `INSTANCE`, `SYSID`, ports, frame/model, params, mission, initial-state
  script, fence, and rally values service-local
- avoid host-global temp names and shared writable config files
- allow generated Compose files to reference bundle paths directly
- keep staged runtime files inside each container's ArduPilot working tree

This keeps fleet orchestration simple: a Compose builder can generate one
service per vehicle, each with its own mounted bundle and env block, rather than
trying to multiplex artifacts inside one container.


## Open Questions

- Which ground-station fence/rally export formats are worth importing alongside
  the project-owned JSON format?
- Should `MISSION_FILE` eventually move from Lua loading to the same Python
  uploader as fence/rally for consistency?
- Should mission/fence/rally upload be opt-in blocking startup, or should the
  container stay up and report upload failure through logs?
- Do we need a `SCENARIO_FILE` later that points to all artifacts for one
  vehicle, with env vars reserved as overrides?
