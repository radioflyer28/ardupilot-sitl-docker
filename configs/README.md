SITL Runtime Config Bundles
===========================

Each bundle directory is ready to mount as `SITL_CONFIG_DIR`:

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
examples/mission        QGC WPL 110 mission plus params that enable loading it
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

Mission:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/mission:/configs:ro" \
  -e PARAM_FILE=mission.parm \
  -e MISSION_FILE=missions/simple-copter.waypoints \
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
