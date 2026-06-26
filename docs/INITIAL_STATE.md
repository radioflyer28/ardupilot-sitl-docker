# SITL Initial State

This note captures how to start ArduPilot SITL from a specific state, including
position, velocity, attitude, rates, mode, and mission context. It is based on
the local `./ardupilot` checkout and favors wrapper-level integration over
patching upstream ArduPilot.


## Summary

ArduPilot does not expose a single `sim_vehicle.py` argument for "start already
airborne with this complete state." The closest native mechanism is Lua
scripting:

- `libraries/AP_Scripting/examples/sim_arming_pos.lua` sets a simulated vehicle
  pose when the vehicle transitions from disarmed to armed.
- `sim:set_pose(...)` is the scripting binding that changes SITL position,
  attitude, velocity, and gyro rates.
- The binding requires `AHRS_EKF_TYPE=10`.
- ArduPilot's own QuadPlane autotests use this path for airborne recovery tests.

For this project, the recommended long-term shape is runtime Lua support in the
Docker wrapper:

- Copy scripts from `$SITL_CONFIG_DIR/scripts/` into the ArduPilot working
  `scripts/` directory before launching SITL.
- Add a singular `LUA_SCRIPT` runtime env var for mounting or selecting one
  specific Lua script outside a full config bundle.
- Keep initial-state config as runtime data, not a build-time image concern.


## What sim_vehicle.py Covers

`sim_vehicle.py` and the SITL binary already cover launch-time basics:

- home/origin via `--location`, `--custom-location`, or SITL `--home`
- vehicle and frame/model selection via `--vehicle`, `--frame`, and `--model`
- runtime default parameter layering via `--add-param-file`
- simulation speed via `--speedup`
- instance and system ID via `--instance` and `--sysid`
- simulation clock start via `--start-time`
- direct SITL binary arguments via `--sitl-instance-args`

These are useful for setting the scenario origin and model, but they do not set
a full dynamic airborne state by themselves.


## ArduPilot Pose Injection

The key Lua API is documented in:

```text
ardupilot/libraries/AP_Scripting/docs/docs.lua
```

Its signature is:

```lua
sim:set_pose(instance, loc, orient, velocity_bf, gyro_rads)
```

The docs describe:

- `instance`: `0` for the first vehicle
- `loc`: a `Location`
- `orient`: a `Quaternion`
- `velocity_bf`: body-frame velocity
- `gyro_rads`: body rates in rad/s
- requirement: `AHRS_EKF_TYPE=10`

The C++ implementation is in:

```text
ardupilot/libraries/SITL/SIM_Aircraft.cpp
```

It updates:

- direction cosine matrix from the quaternion
- earth-frame velocity
- location
- NED position relative to home
- smoothing position, rotation, velocity, and location
- gyro rates

It does not directly set acceleration.


## Existing sim_arming_pos.lua

ArduPilot ships:

```text
ardupilot/libraries/AP_Scripting/examples/sim_arming_pos.lua
```

The script creates a `SIM_APOS_` parameter table:

```text
SIM_APOS_ENABLE
SIM_APOS_POS_N
SIM_APOS_POS_E
SIM_APOS_POS_D
SIM_APOS_VEL_X
SIM_APOS_VEL_Y
SIM_APOS_VEL_Z
SIM_APOS_RLL
SIM_APOS_PIT
SIM_APOS_YAW
SIM_APOS_GX
SIM_APOS_GY
SIM_APOS_GZ
SIM_APOS_MODE
```

On the first armed update, it:

- converts roll, pitch, and yaw degrees into a quaternion
- builds a velocity vector from `SIM_APOS_VEL_X/Y/Z`
- offsets `ahrs:get_origin()` by `SIM_APOS_POS_N/E`
- adjusts altitude using `SIM_APOS_POS_D`
- converts `SIM_APOS_GX/GY/GZ` from deg/s to rad/s
- calls `sim:set_pose(0, loc, quat, vel, gyro)`
- calls `vehicle:set_mode(SIM_APOS_MODE)` when the mode is non-negative

This is proven by upstream autotests in:

```text
ardupilot/Tools/autotest/quadplane.py
```

Those tests install `sim_arming_pos.lua`, set `SCR_ENABLE=1`,
`AHRS_EKF_TYPE=10`, and `SIM_APOS_*`, then arm into airborne recovery states.


## State Field Notes

Position:

- `--custom-location=lat,lon,alt,heading` or SITL `--home` sets the base
  origin.
- `SIM_APOS_POS_N` and `SIM_APOS_POS_E` are meter offsets from the origin.
- `SIM_APOS_POS_D` is NED-style down. Negative values place the aircraft above
  the origin.

Velocity:

- `sim_arming_pos.lua` exposes `SIM_APOS_VEL_X/Y/Z`.
- The Lua docs call the `set_pose` argument body-frame velocity.
- The C++ implementation names the argument `velocity_ef`.
- The example script rotates its velocity vector before calling `set_pose`.
- Treat this as a convention to verify with a small SITL test before promising
  user-facing axis semantics.

Attitude:

- `SIM_APOS_RLL`, `SIM_APOS_PIT`, and `SIM_APOS_YAW` are degrees.

Rates:

- `SIM_APOS_GX`, `SIM_APOS_GY`, and `SIM_APOS_GZ` are deg/s in the example
  script and are converted to rad/s for `sim:set_pose`.

Acceleration:

- `sim:set_pose` does not directly set acceleration.
- SITL derives acceleration from the next dynamics update.
- `SIM_SHOVE_X/Y/Z` and `SIM_TWIST_X/Y/Z` can apply temporary linear or
  rotational acceleration after launch, but they are disturbances rather than
  initial-state fields.
- If exact initial acceleration becomes required, the likely upstream change is
  a new or extended SITL scripting binding.

Flight mode:

- `vehicle:set_mode(...)` takes a numeric mode ID.
- Mode IDs are vehicle-specific.
- For example, Plane uses `CRUISE=7`, `AUTO=10`, `GUIDED=15`, `QLOITER=19`.
- Copter uses `AUTO=3`, `GUIDED=4`, `LOITER=5`; `7` is `CIRCLE`.
- A Docker-facing config should prefer symbolic names only if the wrapper owns
  a vehicle-specific mapping table.

Mission:

- Mission loading is separate from pose injection.
- Lua mission APIs include `mission:clear`, `mission:set_item`, and
  `mission:set_current_cmd`.
- ArduPilot ships `libraries/AP_Scripting/examples/mission-load.lua` for loading
  QGC WPL files.
- MAVProxy can load missions with `wp load`, but that path depends on MAVProxy
  being enabled or running externally.


## Docker Runtime Recommendation

Add first-class runtime Lua installation to the wrapper. The image should not
rebuild ArduPilot to change initial-state behavior.

Recommended bundle convention:

```text
SITL_CONFIG_DIR/
  vehicleinfo.json
  model.json
  params.parm
  scripts/
    initial-state.lua
    modules/
      optional-helper.lua
```

At container start, the wrapper should copy the mounted `scripts/` directory
into:

```text
/home/ardupilot/ardupilot/scripts/
```

This matches ArduPilot's SITL scripting behavior: scripts in the working
`scripts/` directory are automatically launched when scripting is enabled.

Recommended env var:

```text
LUA_SCRIPT
```

Semantics:

- Empty by default.
- Absolute paths are used as-is.
- Relative paths resolve under `SITL_CONFIG_DIR`.
- The selected file is copied into ArduPilot's working `scripts/` directory.
- `LUA_SCRIPT` is copied after `$SITL_CONFIG_DIR/scripts/`, so a specifically
  selected script can override a bundled script with the same basename.
- Missing files should fail fast with a concise launch error.

Why a separate env var is useful:

- It allows one-off experiments without creating a full config bundle.
- It makes a specific script visible in `docker run -e LUA_SCRIPT=...`.
- It avoids overloading `PARAM_FILE`, `MODEL`, or `vehicleinfo.json`.
- It keeps Lua behavior runtime-selectable for derived images and Compose
  stacks.


## Initial-State Script Recommendation

For a durable user-facing feature, prefer a project-owned
`initial-state.lua` over direct reliance on `SIM_APOS_*` params.

Reason:

- `SIM_APOS_*` params are created dynamically by `sim_arming_pos.lua`.
- Defaults files are loaded before Lua-created params necessarily exist.
- ArduPilot's defaults loader can ignore unknown params during early passes.
- Built-in params such as `SCR_ENABLE` and `AHRS_EKF_TYPE` are safe in defaults,
  but Lua-created params need careful ordering.

Better shape:

- A Docker-provided or bundle-provided Lua script reads an initial-state config
  file from `SITL_CONFIG_DIR`.
- The wrapper copies that script into `scripts/`.
- The wrapper layers only built-in params through `PARAM_FILE`, such as
  `SCR_ENABLE=1` and `AHRS_EKF_TYPE=10`.
- The state file carries position, velocity, attitude, rates, mode, trigger,
  and optional mission behavior.

Possible future config:

```json
{
  "trigger": "arm",
  "position_ned_m": { "north": 200, "east": 400, "down": -200 },
  "velocity_mps": { "x": 40, "y": 0, "z": 0, "frame": "body" },
  "attitude_deg": { "roll": 150, "pitch": -70, "yaw": 250 },
  "rates_dps": { "x": 0, "y": 0, "z": 0 },
  "mode": { "plane": "QLOITER" }
}
```

The trigger should default to `arm`, because that is the behavior proven by
ArduPilot's existing script and avoids starting the simulation in an airborne
state before the autopilot is ready.


## Practical Sequence Today

Without adding new wrapper support yet, the manual sequence is:

1. Mount or copy `sim_arming_pos.lua` into the container's ArduPilot `scripts/`
   directory.
2. Start SITL with scripting enabled and the sim AHRS backend:

   ```text
   SCR_ENABLE 1
   AHRS_EKF_TYPE 10
   ```

3. Restart SITL or restart scripting so the script registers `SIM_APOS_*`.
4. Set the `SIM_APOS_*` params over MAVLink.
5. Arm the vehicle.

For automation, this is clumsy. That is why wrapper-level Lua installation plus
a config-file-driven initial-state script is the preferred project direction.


## Open Questions

- Should first-class initial-state support use JSON, Lua table syntax, or a
  `.parm`-adjacent custom file?
- Should mode be numeric only, or should the wrapper support symbolic mode names
  per vehicle?
- Should mission loading live in the same initial-state feature, or remain a
  separate `MISSION_FILE` workflow?
- Do we need exact acceleration initialization, or are pose, rates, velocity,
  mode, and optional shove/twist disturbances enough?
- Should `LUA_SCRIPT` be singular only, or should a future `LUA_SCRIPT_DIR` or
  `LUA_SCRIPTS` be added after real usage appears?
