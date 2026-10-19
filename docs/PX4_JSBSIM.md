# PX4 + JSBSim

Experimental **unmodified PX4 1.16.0 + JSBSim 1.3.3 quad-X** integration.
Combined and split deployments passed normal-EKF takeoff, hover, yaw, landing
and coupled process-failure checks. A mounted HeavyQuad variant also passed
flight and clean shutdown in both topologies. These are scoped simulator checks, not validation
against real aircraft or support for arbitrary models/releases.

Default to one container. The adapter shares the existing ArduPilot `QuadX`
model/catalog implementation, but uses PX4 simulator MAVLink rather than
ArduPilot JSON. Neither upstream autopilot is modified. Exact images, evidence
and limits: [runtime qualification](RUNTIME_QUALIFICATION.md#px4jsbsim-qualification).

## Build and run: one container

The qualified local base is `px4-sih:qualify-v1.16.0-localhost`. To build your own
base without overwriting existing release tags:

```bash
IMAGE_OUTPUT=local IMAGE_REPO=px4-jsbsim-base \
  scripts/build-px4-sih-image.sh sihsim_quadx v1.16.0

docker buildx build --target combined --load -f Dockerfile.px4-jsbsim \
  --build-arg PX4_IMAGE=px4-jsbsim-base:sihsim-quadx-v1.16.0 \
  -t px4-jsbsim:qualify-v1.16.0-local .
docker compose -f compose.px4-jsbsim.yml up -d --wait
mavproxy.py --master=udpout:127.0.0.1:18570
# Stop containers; retain the named run volume.
docker compose -f compose.px4-jsbsim.yml down
```

The v1.16.0 base uses `px4_sitl_default`, which already contains
`simulator_mavlink`, `pwm_out_sim` and airframe `3010_jsbsim_quadrotor_x`.
The derived image layers project helpers and `/opt/jsbsim-venv` onto that
prebuilt firmware; it does not rebuild PX4. A differently configured or newer
SIH base may omit those modules and must be checked separately.

`PX4_JSBSIM_IMAGE` overrides the Compose image. `PX4_GCS_PORT` overrides host
UDP 18570. Publications default to localhost; set `SITL_BIND_ADDRESS` to a LAN
address or `0.0.0.0` for explicit LAN access. The simulator TCP link stays
unpublished and uses loopback in combined mode. No custom firewall rules are
required. Native GCS/offboard links and the private initialization link remain
separate from simulator traffic.

## Optional split deployment

```bash
docker buildx build --target autopilot --load -f Dockerfile.px4-jsbsim \
  --build-arg PX4_IMAGE=px4-jsbsim-base:sihsim-quadx-v1.16.0 \
  -t px4-jsbsim:qualify-v1.16.0-split .
docker buildx build --target simulator --load -f Dockerfile.px4-jsbsim \
  -t px4-jsbsim:qualify-v1.16.0-physics .
docker compose -f compose.px4-jsbsim-split.yml up -d --wait
docker compose -f compose.px4-jsbsim-split.yml down
```

`PX4_JSBSIM_IMAGE` and `PX4_JSBSIM_PHYSICS_IMAGE` override the two images.
PX4 connects to `physics:4560` on the Compose network. The physics run volume is
read-only in PX4; its status must match the expected protocol, model, home,
SYSID and physics-process identity. One physics process accepts one PX4 peer;
restart the whole scenario after transport loss or either process failing.

## Reuse or export a model catalog

The same native `aircraft/<name>/<name>.xml`, `engine/` and optional `systems/`
catalog works with [ArduCopter](ARDUCOPTER_JSBSIM.md). Mount it read-only and
select by name. To export a starter F450 catalog into a **new** destination:

```bash
mkdir -p artifacts
docker run --rm -v "$PWD/artifacts:/exports" \
  --entrypoint /opt/jsbsim-venv/bin/python3 px4-jsbsim:qualify-v1.16.0-local \
  /usr/local/bin/px4_jsbsim_adapter.py --export-models /exports/jsbsim-models

export JSBSIM_MODELS_DIR="$PWD/artifacts/jsbsim-models"
export JSBSIM_MODEL=F450
docker compose -f compose.px4-jsbsim.yml -f compose.px4-jsbsim-models.yml up -d --wait
docker compose -f compose.px4-jsbsim.yml -f compose.px4-jsbsim-models.yml down
```

For split mode, use `compose.px4-jsbsim-split.yml` plus
`compose.px4-jsbsim-split-models.yml`; only physics mounts `/models`.
An existing ArduCopter-exported catalog can be used directly. Keep asset license
notices and source provenance when editing or redistributing models.

Compatible models expose four normalized `adapter/motor-0..3` inputs in
FR/AL/FL/AR order, with vertical thrust and +/+/-/- propeller senses. PX4 rotor
positions are derived from loaded JSBSim geometry relative to its CG, not the
stock wide/asymmetric PX4 JSBSim quad geometry. The normalized allocation yaw
coefficient remains +/+/-/- 0.05; this is not measured motor calibration.

Changes to compatible mass, inertia, propulsion or geometry need a restart and
qualification, not adapter or firmware rebuilds. F450 is the packaged default;
HeavyQuad was a mounted test variant (1.8 kg versus 1.4 kg), not another bundled
aircraft. Catalog selection alone does not establish suitable tuning or fidelity.

## Configuration, state and readiness

- `DYNAMICS_BACKEND=jsbsim`: external physics; dedicated combined image default.
- `JSBSIM_DEPLOYMENT=local|external`: supervised local adapter or separate service.
- `JSBSIM_MODEL`, `JSBSIM_MODEL_DIR`: name and optional native catalog directory.
- `JSBSIM_SEED`: deterministic sensor-noise seed, default 0; not a whole-system
  determinism guarantee.
- `LAT`, `LON`, `ALT`, `DIR`: home and heading; PX4's `PX4_HOME_*` aliases take
  precedence for position. Current home limits are latitude (-60, 60), longitude
  [-180, 180], altitude [-500, 10000] metres and heading [0, 360] degrees.
- `SYSID`: identity shared by PX4 and the adapter. `INSTANCE=0`, `SPEEDUP=1` and
  `SITL_STATE=fresh` are required. Resume, airborne initialization and in-flight
  backend/model switching are unsupported.
- `PX4_RUN_DIR`: owned run root. Combined physics lives under `work/physics`,
  so fresh starts archive both physics truth and vehicle state together.
- `JSBSIM_HOST` and `JSBSIM_STATUS_FILE`: external deployment only. Managed
  startup owns `PX4_SIM_HOST*` and the staged parameter script.

The project-owned `px4-rc.simulator` PATH hook applies the final model-derived
rotor/motor configuration, SYSID, one IMU/magnetometer and `IMU_INTEG_RATE=400`
before native simulator startup. These contract parameters override conflicting
native/environment defaults; other PX4 parameters retain native behavior.
`effective-config.json` records the enforced values.

Readiness requires the expected initialized PX4 heartbeat, selected plans
acknowledged, and fresh matching physics progress. It is not an arming or
flight-feasibility guarantee. Adapter failure/staleness fails the managed run;
PX4 exit/disconnection invalidates physics readiness immediately. Physics allows
up to its five-second link timeout for an ordered Compose stop signal before
reporting peer loss as failure. Combined shutdown stops both owned process
groups with bounded waits. `down` preserves named volumes; `down --volumes`
explicitly deletes them.

Preflight without launching a vehicle:

```bash
docker run --rm px4-jsbsim:qualify-v1.16.0-local --validate
# Native SIH remains available in the same prebuilt runtime.
docker run --rm -e DYNAMICS_BACKEND=internal px4-jsbsim:qualify-v1.16.0-local --validate
```

Use the same `DYNAMICS_BACKEND=internal` override without `--validate` to run SIH.
Do not retain `MODEL=jsbsim_quadrotor_x` when switching. Ordinary SIH images and
the dedicated split autopilot target still default to internal physics.

## Timing, sensors and evidence

PX4 connects as a TCP client. The adapter sends sensors before actuator outputs
exist, then requires exact matching lockstep replies. Sensor exchange and IMU
integration both run at 400 Hz; each exchange advances four 1600 Hz JSBSim
substeps. GPS is 10 Hz, PX4 ground truth 50 Hz, and archived truth 20 Hz.

Sensor inputs include seeded white IMU/magnetometer/pressure noise, ideal GPS,
a home-location magnetic table and ISA pressure. Noise is separate from physics
truth and its standard deviations are recorded in `model-manifest.json`.
This is not a calibrated real-aircraft sensor/environment model. Normal PX4
estimator and arming/stuck-sensor checks remain enabled.

```bash
python3 -m unittest discover -s docker -p 'test_*.py'
python3 docker/qualify-jsbsim.py --family px4 --output artifacts/px4-jsbsim-local-check
python3 docker/qualify-jsbsim.py --family px4 --deployment split \
  --port 19571 --output artifacts/px4-jsbsim-split-check
```

Live checks require Docker and a host pymavlink interpreter (`--client-python`).
Use a new output directory. `--models-dir`/`--model` select a custom catalog;
`--fault physics|sitl|stop` selects failure/stop checks; `--skip-flight` explicitly
omits flight. Reports retain exact image IDs, helper hashes, truth and lifecycle
status, and remove only their own test project containers/volumes.

## Upstream bridge assessment and sources

PX4 1.16.0 pins the upstream bridge at
`68de2cc63ded9a0d6641d45e9eb3ed2b43454cba`. Its configurable actuator properties
could drive these models, but it owns a separate C++ JSBSim runtime, compile-time
asset root, `models/`/`Engines/` layout and sensor plugins. A thin project-owned
MAVLink adapter instead reuses our Python model/catalog, status and truth handling.
The upstream bridge is protocol evidence, not a patched dependency.

- [PX4 v1.16 simulator startup](https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/ROMFS/px4fmu_common/init.d-posix/px4-rc.mavlinksim)
- [PX4 v1.16 JSBSim quad airframe](https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/3010_jsbsim_quadrotor_x)
- [PX4 v1.16 simulator MAVLink implementation](https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/src/modules/simulation/simulator_mavlink/SimulatorMavlink.cpp)
- [Pinned bridge model, clock, transport and sensor code](https://github.com/PX4/px4-jsbsim-bridge/tree/68de2cc63ded9a0d6641d45e9eb3ed2b43454cba/src)
- [Pinned bridge build and dependencies](https://github.com/PX4/px4-jsbsim-bridge/blob/68de2cc63ded9a0d6641d45e9eb3ed2b43454cba/CMakeLists.txt)
