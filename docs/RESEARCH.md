# Research

This file indexes research notes and investigations that inform the project.
Keep detailed writeups in dedicated docs when they are large enough to stand on
their own.

Research is not the same as design commitment. Once a recommendation becomes a
project decision, summarize the decision in `docs/DESIGN.md`. Once it becomes
planned work, track the action in `docs/FUTURE_WORK.md`.


## SITL Initial State

Status: runtime Lua support and a copyable initial-state script are
implemented; generated or externally mounted initial-state config is still
planned

Detailed note:

```text
docs/INITIAL_STATE.md
```

Summary:

ArduPilot SITL can be moved into an airborne or otherwise custom dynamic state
through Lua scripting. The native hook is `sim:set_pose(...)`, and the closest
upstream example is `libraries/AP_Scripting/examples/sim_arming_pos.lua`.

Key findings:

- `sim_vehicle.py` can set the home/origin, model, params, speed, instance,
  system ID, and start time, but not a complete airborne state by itself.
- `sim:set_pose(...)` can set position, velocity, attitude, and gyro rates.
- The pose injection path requires `AHRS_EKF_TYPE=10`.
- ArduPilot's own QuadPlane autotests use `sim_arming_pos.lua` for airborne
  recovery tests.
- Acceleration is not directly set by `sim:set_pose`; SITL derives it on later
  dynamics updates.
- Mission loading is separate and can be handled through Lua mission APIs,
  MAVLink, or MAVProxy.

Implemented recommendations:

- Support runtime Lua installation from `$SITL_CONFIG_DIR/scripts/`.
- Add a singular `LUA_SCRIPT` env var for selecting one explicit Lua script.
- Provide a copyable `initial-state.lua` example that calls `sim:set_pose` once
  by default when the vehicle arms.

Remaining recommendation:

- Prefer generated or externally mounted initial-state config over direct
  reliance on `SIM_APOS_*` params when scaling this beyond hand-edited example
  scripts, because those params are created dynamically by Lua.

Feeds:

- `docs/DESIGN.md`: runtime Lua and initial-state decisions.
- `docs/FUTURE_WORK.md`: first-class initial-state feature backlog item.
