# Design: Swappable ArduCopter Physics with JSBSim

## Status and decision

Implemented experimental backend: **unmodified ArduCopter 4.6.3 + JSBSim 1.3.3
F450 quad-X**, starting on the ground. Installed images passed normal-EKF takeoff,
hover, yaw, landing and coupled failure checks. This is not validation against a
real aircraft or support for arbitrary models/releases. Ordinary ArduPilot images
still default to internal dynamics; the dedicated combined image defaults to JSBSim. `docker/jsbsim_adapter.py` owns the adapter outside ArduPilot.
Both combined and optional split deployments passed installed flight checks;
local child failures and graceful shutdown were exercised separately. Exact
images, measurements and limits are recorded in
[RUNTIME_QUALIFICATION.md](RUNTIME_QUALIFICATION.md#combined-default-and-optional-split-deployment).

For the same model catalog with PX4, see [PX4 + JSBSim](PX4_JSBSIM.md).
The shared physics assets do not imply identical transport or sensor contracts.

Keep the custom adapter and aircraft assets in project-owned code outside the
external `ardupilot/` checkout. Start in this repository; a dedicated repository
can own independent releases later. An ArduPilot fork is not an expected
prerequisite. If qualification reveals a missing upstream capability, record the
blocker and obtain approval before proposing upstream modifications.

This note specializes [RUNTIME_PROFILES.md](RUNTIME_PROFILES.md). It owns the
ArduCopter/JSBSim design; [FUTURE_WORK.md](FUTURE_WORK.md) owns implementation
milestones. The implementation and usage are described below; qualification
claims must remain tied to the recorded tests, not inferred from this design.

## Running the experimental integration

Run commands from the repository root. Prerequisite: build/load `ardupilot-sitl:copter-4.6.3` using the existing release
build workflow. Default to one combined image without replacing that release tag:

```bash
docker buildx build --target combined --load -f Dockerfile.jsbsim \
  -t ardupilot-sitl:qualify-4.6.3-jsbsim-local .
docker compose -f compose.jsbsim.yml up -d --wait
# Connect only after startup initialization releases the direct TCP endpoint:
mavproxy.py --master=tcp:127.0.0.1:5760
# Always stop both coupled processes before a new scenario:
docker compose -f compose.jsbsim.yml down
```

The combined image layers project-owned helpers and an isolated
`/opt/jsbsim-venv` (JSBSim 1.3.3 and NumPy 2.2.6) onto prebuilt ArduPilot. It does
not modify/rebuild firmware or install physics dependencies into ArduPilot's
Python environment. Docker caches unchanged layers. Base/OS dependencies are not
claimed to be hermetically pinned. Retain JSBSim's LGPL notices and source references.

`compose.jsbsim.yml` starts one container. The existing supervisor launches both
ArduCopter and the adapter/JSBSim process, with physics UDP bound to loopback.
It stops/reaps both process groups on termination or either process failing.
Physics state, truth and model hashes live under autopilot `work/physics/`;
a fresh run archives both together. No shared status volume or external physics
network is required. Only TCP 5760 is published, on localhost by default. `SITL_PORT` changes
the host port; `SITL_BIND_ADDRESS` opts into LAN access. `LAT`, `LON`, `ALT` and
`DIR` are shared explicitly between physics and autopilot; altitude is metres
above sea level. The physical landing gear settles above the declared ground
altitude before exchange starts. The model does not reproduce terrain relief.

`DYNAMICS_BACKEND=jsbsim` (or `--dynamics jsbsim`) selects the managed adapter
contract. `JSBSIM_DEPLOYMENT=local` is the default managed topology; the combined
image also defaults `DYNAMICS_BACKEND=jsbsim`. `JSBSIM_PYTHON` selects the isolated
physics interpreter. Local mode owns its host/status paths and rejects external
overrides. Only ArduCopter/frame `quad`, instance 0, fresh state,
speed 1 and direct-motor quad-X models are currently supported. The generated final parameter
layer fixes quad-X motor mapping, PWM 1000–2000, 800 Hz exchange and the normal
EKF. Custom `MODEL`, Lua physical-state injection and resume are rejected.
Readiness requires advancing physics as well as autopilot initialization, not
merely a heartbeat. Local adapter exit is detected immediately by the supervisor.

To switch back, stop the JSBSim Compose project and run the existing
`compose.sitl.yml` workflow. Internal dynamics remain the default in ordinary
ArduPilot images and the split autopilot target. In the combined image, explicitly
use `--dynamics internal` or `DYNAMICS_BACKEND=internal` to skip the adapter. Changing the backend means restarting the scenario,
not transferring physical state between engines. Do not restart one side alone:
frame discontinuity fails the adapter and physics loss stops the autopilot.

Qualification commands:

```bash
python3 -m unittest discover -s docker -p 'test_*.py'
docker run --rm --entrypoint /opt/jsbsim-venv/bin/python3 \
  ardupilot-sitl:qualify-4.6.3-jsbsim-local /usr/local/bin/qualify-jsbsim-model.py
python3 docker/qualify-jsbsim.py --output artifacts/jsbsim-new-run
```

The live checker requires Docker and a host Python with pymavlink (default
`/usr/bin/python3.10`; override `--client-python`). It uses a unique Compose
project, verifies installed health/local publication, attempts a normal-EKF flight
and a simulator-death fault, retains logs/truth/state, and removes only its own
containers/volumes. Reports go into a new empty output directory. Model-only tests
are not flight qualification. `truth.jsonl` records state and motor PWM at 20 Hz;
`model-manifest.json` records physical asset hashes.

## Optional two-container deployment

Build independently packaged targets when separate updates/resource limits are
useful. The same adapter/model code is used in both topologies:

```bash
docker buildx build --target autopilot --load -f Dockerfile.jsbsim \
  -t ardupilot-sitl:qualify-4.6.3-jsbsim-split .
docker buildx build --target simulator --load -f Dockerfile.jsbsim \
  -t jsbsim:qualify-1.3.3-split .
docker compose -f compose.jsbsim-split.yml up -d --wait
# Stop both containers before a fresh scenario:
docker compose -f compose.jsbsim-split.yml down
```

The split Compose file sets `JSBSIM_DEPLOYMENT=external`, `JSBSIM_HOST=physics`
and `JSBSIM_STATUS_FILE=/physics/status.json`. It retains a private Docker network
and separate named volumes with a read-only status mount on the autopilot side.
The supervisor monitors status freshness; the simulator times out if actuator
progress stops. Hostnames resolve before launch, so simulator-first startup is
the supported Compose ordering. Never combine the local and split base files.
For catalogs, pair `compose.jsbsim-split.yml` with
`compose.jsbsim-split-models.yml`; only the physics container receives `/models`.
Use `qualify-jsbsim.py --deployment split` for split lifecycle/flight checks.
Both topologies keep localhost publication and explicit LAN opt-in.

## Multiple aircraft in a read-only model catalog

Build the combined image above, then export the same editable model assets used
by either topology:

```bash
mkdir -p artifacts/model-export
docker run --rm --user "$(id -u):$(id -g)" \
  --entrypoint /opt/jsbsim-venv/bin/python3 \
  -v "$PWD/artifacts/model-export:/export" ardupilot-sitl:qualify-4.6.3-jsbsim-local \
  /usr/local/bin/jsbsim_adapter.py --export-models /export/models
```

The export destination must not exist. It contains editable direct-motor F450
assets, shared engines, license notices and source provenance. Keep those notices
with redistributed copies. No large model catalog is checked into git.

```text
models/
  aircraft/
    F450/F450.xml          # plus Mass.xml, Metrics.xml, Propulsion.xml, Aero.xml, Gear.xml
    HeavyQuad/HeavyQuad.xml
    LightQuad/LightQuad.xml
  engine/                 # shared motor and propeller definitions
  systems/                # optional shared systems
```

Duplicate `aircraft/F450/` to create a variant and rename its `F450.xml` entry file
to match the new directory name (e.g. `HeavyQuad.xml`). Edit the variant's mass,
inertia, geometry, propulsion, aerodynamic and contact XML normally. For unique
motor/propeller definitions, copy and rename the shared engine files and update
that aircraft's references; editing a shared file affects every model using it.
Custom entry XML is preserved, not replaced by the packaged F450 composition.
Packaged F450 and a mounted 1.8 kg HeavyQuad variant passed the installed flight
suite; see [catalog qualification](RUNTIME_QUALIFICATION.md#read-only-jsbsim-model-catalogs)
for exact images and modified inertia values. Other variants need their own tests.

```bash
export JSBSIM_MODELS_DIR="$PWD/artifacts/model-export/models"
export JSBSIM_MODEL=HeavyQuad
docker compose -f compose.jsbsim.yml -f compose.jsbsim-models.yml up -d --wait
# Stop both sides before changing JSBSIM_MODEL or model files:
docker compose -f compose.jsbsim.yml -f compose.jsbsim-models.yml down
```

The override mounts the catalog read-only at `/models`; a missing host directory
fails rather than being silently created. `JSBSIM_MODEL` selects the same expected
model identity in the supervisor and adapter (in either topology). With no catalog, packaged F450 remains the
default; a missing name in an explicit catalog never falls back to packaged data.
Inputs must be separate from the owned physics run root. Selected aircraft and
shared engines/systems are copied to a private run snapshot and hashed.

The interface stays fixed: four engines in front-right, aft-left, front-left,
aft-right order, using `adapter/motor-0` through `adapter/motor-3` as normalized
0–1 inputs. Retain the exported direct-motor flight-control section and avoid a
second pilot controller or duplicate sensor noise. Native layout does not imply
arbitrary JSBSim aircraft are compatible: other rotor arrangements need a new
adapter contract. Custom gear geometry may need an appropriate ground-start setup;
the current initialization places the CG 0.5 ft above ground before settling.
Configuration/motor-count checks cannot validate rotor geometry, tuning or fidelity.
Changing a model does not rebuild or modify ArduPilot, but may require retuning
and separate flight qualification. Use `qualify-jsbsim.py --models-dir PATH --model
NAME` to exercise a variant against the existing flight acceptance tests.

## Why not the existing JSBSim connector?

The inspected ArduPilot JSBSim connector translates outputs into aileron,
elevator, rudder and throttle commands. It also launches JSBSim itself and uses
loopback control/data sockets. It is a fixed-wing-oriented integration, not a
ready-made independent-motor interface for ArduCopter.

Use ArduPilot's existing **JSON/UDP external-physics interface** instead. It sends
individual actuator PWM outputs and accepts timestamped simulated state/IMU
inputs. Our adapter maps these to/from JSBSim. This physics protocol is distinct
from the JSON-backed `vehicleinfo.json` aircraft metadata used by some releases.
Availability and behavior must be verified against the selected firmware binary;
no arbitrary-release compatibility is implied.

## Scope and meaning of swappable

Select three independent concepts:

- **Autopilot:** ArduCopter firmware and controller parameters.
- **Dynamics backend:** built-in physics or JSBSim via our adapter.
- **Aircraft model:** mass, inertia, rotor geometry, propulsion, aerodynamics,
  ground contact and the required signal mappings.

For the first release, swapping means **stop and restart a scenario** with a
validated backend/model selection. Keep the host controller's MAVLink interface
unchanged. Parameters may require backend-specific layers; the same controller
settings are not guaranteed to produce equivalent behavior in both engines.

Out of scope: in-flight engine replacement, arbitrary model compatibility,
checkpoint restoration, shared-world interactions, rendered sensors and fidelity
claims for a real aircraft. PX4 has a separate implemented adapter described in
[PX4_JSBSIM.md](PX4_JSBSIM.md). Ground-contact support is still
required for the initial takeoff/landing case.

## Architecture and ownership

```text
Host controller / GCS
        | existing MAVLink endpoint
        v
Combined container: supervisor
        |-- ArduCopter (prebuilt, unmodified firmware)
        |       | PWM outputs       ^ state / IMU / simulation time
        |       v                   |
        `-- Project-owned adapter + JSBSim + quad-X assets
            (separate process and isolated Python environment)
```

JSBSim's library bindings run inside the adapter process, which owns stepping
and model-property access. By default that process shares a container with the
autopilot; the optional split topology moves it into a simulator container without
changing the interface. A third bridge container is unnecessary.

Responsibilities:

- Autopilot runtime: configuration resolution, firmware, estimator/control,
  parameter/plan initialization, vehicle logs and owned run state.
- Adapter: JSON wire handling, PWM-to-motor mapping, JSBSim stepping,
  state/sensor conversion, input validation and physics-link observations.
- JSBSim/model: physical state, forces, moments, propulsion and ground contact.
- Scenario orchestration: compatible image/model selection, network wiring,
  coordinated startup/failure/shutdown and correlated run metadata.

Build dependencies and firmware ahead of runtime. Mount small model/config
inputs read-only. Local physics owns a nested run root at autopilot `work/physics/`,
archived together with the vehicle; split physics owns a separate volume. Keep
its outputs distinct from firmware files. Run one physics instance per vehicle.

## Proposed configuration seam

Expose backend selection through the managed resolver, not unrestricted upstream
argument passthrough. The following illustrates intent only; these keys are not
implemented and are not a finalized manifest schema:

```yaml
autopilot: arducopter
frame: quad-x
dynamics:
  backend: jsbsim                 # alternative: internal
  aircraft: qualified-quad-x      # placeholder, not a selected asset
  initial_conditions: ground-start.xml
```

Resolve a selection into pinned image/model identities, validated parameter
layers, native launch options, private physics endpoints and adapter settings.
Reject missing assets, incompatible frames, invalid rates and unsupported
capabilities before launching. Keep the current internal path usable without
JSBSim installed. Aircraft files remain native inspectable assets, not a new
project-defined aerodynamic format.

## Physics interface contract

| Concern | Required behavior |
| --- | --- |
| Motor inputs | Map actual ArduCopter output channels to the corresponding rotor, rotation direction and JSBSim property. Handle disarmed PWM, armed idle, range, saturation and motor response explicitly. Do not reinterpret motor outputs as roll/pitch/yaw commands or mix them a second time. |
| Physical model | Verify mass/inertia, rotor locations, thrust and reaction torque, drag and ground contact. Include motor lag where the model requires it. An engine supporting multirotors does not validate a particular asset. |
| Frames and units | Document JSBSim property frames/units and convert to ArduPilot's body and NED conventions. Verify gyro radians/second, acceleration metres/second squared, quaternion order and attitude direction. |
| Accelerometer | Derive the specific force expected by SITL, not simply kinematic acceleration. Verify gravity treatment with stationary-level, tilted and free-fall fixtures against the selected JSON implementation. |
| Position | Keep JSBSim geodetic state, the local NED origin, altitude reference and ArduPilot home/location consistent. |
| Sensors | Supply required state/IMU fields and identify how any additional sensors are derived. Assign noise/bias/latency ownership so the adapter and SITL do not apply them twice. Do not bypass the normal estimator with ground truth as a substitute for sensor validation. |
| Time | Use a fixed physics timestep and a documented actuator-update/substep policy compatible with the firmware loop rate. Return absolute simulation timestamps; never advance twice for a duplicate frame. |
| Wire behavior | Validate the selected JSON protocol's packet size, magic, channel count, frame counter, finite values and message framing. Define startup, dropped/repeated frame and restart behavior from pinned-source evidence. |

Start synchronized at normal speed. The adapter advances JSBSim; the scenario
sets one coherent timestep/speed policy. Do not promise pause, single-step or
accelerated operation until measured. Wall-clock startup/shutdown deadlines must
remain effective when simulation time stops.

## Lifecycle, readiness and persistence

1. Resolve and validate inputs; claim owned writable roots (nested physics root
   for local deployment, separate volume for split deployment).
2. Start the simulator listener and autopilot without circular health gates.
   Neither upstream tooling nor the wrapper should start a duplicate JSBSim.
3. Establish actuator/state exchange; verify expected model identity, finite
   sensor values and advancing simulation time.
4. Complete expected-autopilot heartbeat and selected-plan initialization using
   the existing runtime's supported ordering.
5. Advertise scenario readiness only when both the autopilot initialization and
   physics checks pass. A heartbeat alone does not prove external physics works.
6. Monitor required processes and physics progress. Bound unexpected stalls with
   wall-clock deadlines; distinguish intentional pause if later supported.
7. Stop the coupled scenario on a required process/link failure. Preserve failure
   metadata/logs and stop both sides within a bounded interval.

Initially support coordinated fresh physical starts. Retaining autopilot files
with `SITL_STATE=resume` is not restoring JSBSim's physical state or an airborne
checkpoint. Backend/model changes should require a fresh scenario initially;
reject ambiguous resume combinations rather than silently reuse incompatible
parameters/state. External initial conditions belong to JSBSim, not the existing
built-in-physics Lua pose injection. Airborne initialization and trim are later
capabilities.

Local deployment keeps physics traffic on loopback. Split deployment uses a
private user-defined Docker network; the resolver translates the physics service
hostname to an IPv4 address before launching ArduPilot. Autopilot-first/DNS-delay
startup remains unqualified.
Do not reuse or publish GCS/offboard ports for physics. Preserve localhost host
publications and explicit LAN opt-in without adding firewall prerequisites.

## Qualification and delivery gates

The roadmap follows these gates; define numerical tolerances and simulated test
durations before executing each experiment.

| Gate | Completion evidence |
| --- | --- |
| 1. Select and pin | ArduCopter binary/revision, JSBSim/bindings version and one quad-X asset revision with licensing/provenance reviewed. Verify JSON support and required per-motor properties. Record missing model capabilities before committing to an asset. |
| 2. Adapter correctness | Tests for wire parsing, duplicate/restart handling, channel order, rotor torque signs, unit/frame conversion, gravity/specific force and timestep/substeps. Compare known stationary and rotated states with expected values. |
| 3. Packaged coupling | Installed images exchange real PWM/state data; physics time advances. Start in both orders, reject malformed/stale data, stop either side and verify bounded failure/cleanup. Run two isolated scenarios without cross-traffic. |
| 4. Controlled flight | Record individual-motor force/moment responses, then takeoff, hover, controlled attitude/yaw response and landing with the normal estimator. Capture tracking errors, ground behavior and actuator saturation against declared limits. |
| 5. Swapping and repeatability | The same host controller can run internal and JSBSim scenarios via explicit backend selection. Repeat fresh runs within declared tolerances; reject unsupported resume. Record any necessary parameter differences, not assumed engine equivalence. |

Retain image digests, firmware/adapter/JSBSim revisions, aircraft/config hashes,
parameter layers, timestep, seeds, CPU/runtime context, achieved real-time factor,
JSBSim truth, autopilot estimates and actuator traces correlated by simulation
time. Store generated evidence under ignored `artifacts/` directories. Keep
lightweight adapter tests in PR CI; opt into JSBSim/image/live-flight qualification
separately. Host protocol/configuration, real-model and installed flight/failure
checks have passed for the recorded tuple. Startup in the opposite order,
transport-loss recovery and arbitrary model/parameter configurations remain
unqualified; these broader gates must not be inferred from one successful flight.

## Initial implementation selection

- Selected firmware: existing Copter 4.6.3 binary with JSON backend support.
  Installed coupled flight/lifecycle checks are recorded in
  [RUNTIME_QUALIFICATION.md](RUNTIME_QUALIFICATION.md); other releases remain unqualified.
- JSBSim Python bindings/data: pinned 1.3.3, distributed under the bundled LGPL
  license (retain package license notices and corresponding-source references).
  Upstream source: <https://github.com/JSBSim-Team/jsbsim/tree/v1.3.3>.
- Model: bundled F450, marked ALPHA upstream, 1.4 kg with four independent motor
  inputs. Treat it as an educational simulation model, not a validated DJI vehicle.
- The adapter copies assets into owned temporary storage and writes a project-owned
  model composition using format version 2.0. It retains metrics, mass, propulsion,
  ground reactions and aerodynamics, replacing the pilot controller with direct
  per-motor gains and excluding bundled sensor systems. This avoids the original
  version-3.0 warning, duplicate sensor-property ties and a second flight controller.
- Two 1600 Hz physics steps per 800 Hz actuator frame. A 400 Hz exchange reached
  EKF alignment but failed normal arming because the gyro rate must exceed 1.8x
  the 400 Hz controller loop; keep that safety check enabled. The advertised firmware
  rate is advisory and can converge during boot; the backend's returned timestamps
  define its fixed timestep. One peer, cached duplicate
  responses, fail on skipped/restarted frames. No resume or automatic link recovery.
- Model/data provenance and generated XML hashes are retained per run. Redistribution
  must retain JSBSim's package license; the adapter does not vendor these assets into git.

## Open qualification decisions

- Expand beyond the qualified hover/yaw/land flight and process-death cases to
  directional manoeuvres, transport interruption and opposite startup order.
  Other releases/assets are unqualified.
- Extend physical fidelity beyond force-direction/ground/free-fall checks;
  bundled F450 assets are not validation against real aircraft measurements.
- Confirm repeated runs and isolated scenarios meet declared tolerances.
- Decide whether independent adapter releases warrant a separate repository.
  Generalized manifests and arbitrary aircraft selection remain future work.

## Source evidence and limits

The local checkout inspected for this design is ArduPilot
`c6a991d4aa91e3834af333c0061533aa1009b431`, not a promise about every release:

- [Native JSBSim connector](https://github.com/ArduPilot/ardupilot/blob/c6a991d4aa91e3834af333c0061533aa1009b431/libraries/SITL/SIM_JSBSim.cpp):
  fixed-wing `send_servos` mapping, child launch and loopback sockets.
- [JSON protocol](https://github.com/ArduPilot/ardupilot/blob/c6a991d4aa91e3834af333c0061533aa1009b431/libraries/SITL/examples/JSON/readme.md)
  and [implementation](https://github.com/ArduPilot/ardupilot/blob/c6a991d4aa91e3834af333c0061533aa1009b431/libraries/SITL/SIM_JSON.cpp):
  individual PWM outputs, state fields, timestamps and frame handling.

Revalidate these contracts against the selected release. Broader backend sources
and engine/model fidelity limits are indexed in
[EXTERNAL_SIMULATORS.md](EXTERNAL_SIMULATORS.md) and
[RUNTIME_PROFILES.md](RUNTIME_PROFILES.md).
