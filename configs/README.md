SITL Runtime Config Bundles
===========================

Run commands from the repository root after building/loading the selected image.
These are ArduPilot internal-dynamics examples; PX4 does not consume
`vehicleinfo.json`, `.parm` files or Lua scripts. For shared JSBSim aircraft
catalogs, use the [ArduCopter](../docs/ARDUCOPTER_JSBSIM.md) or
[PX4](../docs/PX4_JSBSIM.md) guide instead.

Each frame bundle directory is ready to mount as `SITL_CONFIG_DIR`:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/frames/arducopter-quad:/configs:ro" \
  -e VEHICLE=ArduCopter \
  -e FRAME=quad \
  ardupilot-sitl:copter-4.6.3
```

The files here are copied from `./ardupilot/Tools/autotest` and flattened so
`vehicleinfo.json` can refer to model and parameter files in the same mounted
directory. Copy a bundle, edit the model JSON and `.parm` files, then mount the
copy at `/configs`.

Checked-in example bundles:

```text
frames/arducopter-quad  ArduCopter quad params
frames/arduplane-plane  ArduPlane plane params
```

Checked-in runtime examples:

```text
examples/initial-state  Lua initial-state script plus params that enable it
examples/mission        QGC WPL 110 mission uploaded before readiness
examples/plan-artifacts Fence and rally JSON plans plus helper params
```

Mount an example as `SITL_CONFIG_DIR` when you want to try it against a stock
ArduPilot frame.

Initial state:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/initial-state:/configs:ro" \
  -e PARAM_FILE=initial-state.parm \
  ardupilot-sitl:copter-4.6.3
```

Mission (MAVLink upload; Lua and `SCR_ENABLE` are not required):

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/mission:/configs:ro" \
  -e MISSION_FILE=missions/simple-copter.waypoints \
  ardupilot-sitl:copter-4.6.3
```

Fence and rally:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/plan-artifacts:/configs:ro" \
  -e PARAM_FILE=plan-artifacts.parm \
  -e FENCE_FILE=fences/simple-polygon.json \
  -e RALLY_FILE=rally/recovery-points.json \
  ardupilot-sitl:copter-4.6.3
```

The full generated catalog is intentionally not checked in. Generate it on
demand into ignored `configs/generated-frames/`; it contains one mountable
bundle per ArduPilot `vehicleinfo.json` frame that references local model or
parameter assets.

Regenerate the catalog after updating `./ardupilot`:

```bash
scripts/populate-config-bundles.py
```
