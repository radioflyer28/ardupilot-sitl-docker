# Runtime Profiles and External Dynamics Integration

## Status and scope

Design direction and research handoff for future sessions, not an implemented
external-simulator interface. The repository has ArduPilot SITL and PX4 SIH
runtime paths; external adapters, simulator images and scenario orchestration
remain unimplemented and unqualified here. Host-only runtime tests are not live
firmware/FDM qualification. No image builds or external-runtime experiments were
performed for this design discussion.

Use this note for architecture, terminology, research implications and acceptance
criteria. [EXTERNAL_SIMULATORS.md](EXTERNAL_SIMULATORS.md) owns the simulator
catalog/support survey; [DESIGN.md](DESIGN.md) describes the current runtime;
[FUTURE_WORK.md](FUTURE_WORK.md) owns the actionable backlog.

## Four logical runtime profiles, not necessarily four images

The useful top-level matrix is autopilot family × dynamics placement:

| Profile | Autopilot | Dynamics | Repository status |
| --- | --- | --- | --- |
| ArduPilot / internal | ArduPilot SITL | Built-in SITL dynamics | Primary runtime path |
| ArduPilot / external | ArduPilot SITL configured for a named backend | Separate FDM/simulator plus compatible integration | Proposed; not qualified here |
| PX4 / internal | PX4 SITL with SIH | Internal SIH physics | Existing sibling runtime path |
| PX4 / external | PX4 SITL with required simulation modules | Separate FDM/simulator plus compatible integration | Proposed; not qualified here |

Use **runtime profile** for each logical combination. Internal/external describes
where physical dynamics execute relative to the autopilot, not whether a viewer
is present or which file configures the model. An external engine remains an
external backend even if deployment colocates it with the autopilot.

Distinguish these terms:

- **Image/build variant:** packaged executable, libraries and plugins.
- **Runtime service:** running process/container with its own lifecycle.
- **Backend adapter:** native launch, transport, mapping and lifecycle contract
  for an autopilot/backend pairing.
- **Scenario:** coordinated autopilot services, dynamics world(s), bridges,
  inputs, clocks, outputs and optional viewers/controllers.

Consequences:

- Four profiles do not mean four codebases, Dockerfiles or simultaneously running
  containers. Share validated configuration/state/lifecycle primitives.
- One ArduPilot image may support both internal and some external profiles if its
  prebuilt binaries include the needed support; verify each backend/release.
- Plan a PX4 external-simulation build/runtime variant rather than assuming the
  stripped SIH path can connect to external physics. It needs the appropriate
  modules, airframes, startup scripts and possibly simulator client libraries.
  Changing the SIH `MODEL` env var is not sufficient.
- There may be several external backend variants per autopilot. Four is a
  taxonomy, not a maximum package count or a promise of universal compatibility.

## Recommended service and packaging boundaries

```text
GCS / controller -- MAVLink --> autopilot service
                                    ^
                                    | actuators / sensors / simulation clock
                                    v
                              FDM / world service
                                    |
                              optional viewer
```

Keep one autopilot service per vehicle. Default to a separately built simulator
image and separately running FDM/world service, coordinated as one scenario.
Native integration requirements may justify colocated deployment; retain the
logical ownership boundary even then.

There are three responsibilities, not necessarily three containers:

| Responsibility | Default placement |
| --- | --- |
| Flight-control software and vehicle state | Autopilot service |
| Physics engine, world and sensor simulation | Simulator service |
| Protocol bridge/plugin and signal mappings | Where the native integration requires it |

A Gazebo plugin belongs with Gazebo; a PX4 bridge module compiled into PX4 belongs
with PX4. Only an independently executable bridge necessarily merits its own
service. Do not impose an extra network hop or a universal bridge container.

Package dependencies separately from small read-only scenario inputs. Pin a
compatible tuple of autopilot release, simulator version, bridge/plugin revision
and vehicle/world assets. Independent simulator images are preferable initially
to a complicated shared-image hierarchy. Both autopilot and simulator runtimes
should start prebuilt executables, not invoke upstream build-and-run targets.

For fleet scenarios:

- Use one simulator per shared world when vehicles need common collisions,
  environment or interactions; not automatically one FDM container per vehicle.
- Use independent worlds/FDM instances for genuinely independent experiments.
- Assign explicit simulator entity names, autopilot instances and MAVLink system
  IDs. These are different identities; host ports are another allocation domain.
- Sharing Gazebo as a platform does not prove that mixed ArduPilot/PX4 vehicles
  can safely share one clock/world. Qualify that combination independently.

## Backend capability contract

Add explicit adapters rather than restoring unrestricted upstream flag
forwarding. The future configuration needs autopilot family, dynamics placement,
a named backend and its specific model/configuration; the word `external` alone
is insufficient.

Each adapter should declare:

- Compatible binary/modules, bridge placement, releases and model formats.
- Native launch arguments and whether any upstream launcher would auto-start an
  unwanted duplicate simulator.
- Physics endpoints, connect/listen direction, discovery/partition requirements
  and supported network deployment modes.
- Actuator/sensor mappings, units, frames, rates and which component adds noise,
  bias, delay or failures.
- Clock ownership, timestep, speed control, pause/step and startup handshakes.
- Initial-state and trim capabilities, reset semantics and checkpoint support.
- Readiness/liveness observations, failure policy and bounded stop behavior.
- CPU/GPU/rendering needs, output/ground-truth capture and licensing constraints.

A future manifest should generate the existing native runtime interfaces, not
create an independent competing interpreter. Reject unsupported capabilities
rather than silently approximating them. Exact schema, env names, image names
and adapter API remain open until one integration is qualified.

## Research findings and design implications

### 1. Clock ownership, lockstep and readiness

PX4 documents that its Gazebo bridge updates PX4 time from Gazebo simulation
steps and that Gazebo lockstep cannot be disabled [S1]. ArduPilot's JSON interface
receives absolute physics timestamps and sends a requested frame rate that the
backend may handle differently [S2]. Do not treat these as interchangeable clock
contracts or infer one from the other.

Recommended design:

- A shared world's timestep and speedup are scenario/world settings, not
  independently conflicting per-vehicle settings.
- Use wall-clock deadlines for startup, network establishment and shutdown;
  simulation time for scenario events and simulated-duration assertions.
- Distinguish intentional pause, advancing simulation and an unexpected stall.
- Extend current process/heartbeat/plan readiness with backend link status,
  expected sensor updates and observable simulation-time progress.
- Avoid circular `depends_on` health gates: both sides may need to run before
  either handshake can complete. Define adapter-specific initialization phases.
- Test slow or failed vehicles in a shared lockstep world; do not assume other
  vehicles remain unaffected or promise throughput before measurement.

The target progression is processes started → transport connected → valid
sensor/time exchange → requested plans initialized → scenario ready. Exact
ordering, including paused startup, must follow the native integration. GCS
MAVLink connectivity alone does not establish a working physics link.

### 2. Reset, persistence and coordinated failure

Gazebo has a world reset API, but system/plugin reset behavior also participates
[S3]. ArduPilot JSON frame counters can identify an autopilot restart and
repeated frames can support reconnection [S2]. These mechanisms are not a
complete scenario reset/checkpoint protocol.

Separate three promises:

1. **Fresh scenario:** initialize both autopilot and physics from declared inputs.
2. **Persistent autopilot state:** retain selected files/parameters/plans while
   physics may start afresh. This is not restoring an airborne simulation.
3. **Checkpoint restore:** restore all relevant autopilot, physics, sensor,
   bridge and clock state. Unsupported until explicitly implemented and tested.

Our current `SITL_STATE=resume` preserves vehicle files; it is not promise 3.
Prefer coordinated fresh starts initially. For tightly coupled scenarios, fail
or stop the scenario when a required component fails; do not independently
restart one side into an incompatible clock/state. Shared worlds need an explicit
policy for whether any vehicle failure stops the entire world.

### 3. Initial conditions, trim and state ownership

The external FDM should own physical position, attitude, velocity and rates.
Do not assume ArduPilot's current `sim:set_pose` Lua example can reposition an
external engine. Autopilot estimator initialization, arming and flight mode are
separate concerns and need an explicit sequence.

JSBSim's initial-condition class constructs consistent kinematic conditions but
does not itself trim the model [S4]. An airborne pose is not necessarily a steady,
trimmed flight state. Preserve separate configuration concepts for physical
initial conditions, optional backend trim, and autopilot initialization.

### 4. Container transport and isolation

PX4 supports separately launched Gazebo through standalone mode [S1]. ArduPilot
JSON uses binary actuator packets out and JSON physics data back over UDP [S2].
PX4's simulator MAVLink API and its Gazebo Transport bridge are distinct; SIH is
internal uORB-based physics [S5]. Sharing an FDM does not imply a shared protocol.

Gazebo discovery may need `GZ_PARTITION`, interface selection and relay settings.
`GZ_RELAY` addresses discovery, not unreachable advertised data endpoints; NAT can
still break the data path [S6]. Service DNS and a few published ports are not a
universal solution.

Start with a dedicated user-defined Docker network on one host. Validate two
simultaneous scenario partitions, native connect/listen roles and bidirectional
traffic. Keep physics transport separate from GCS/offboard endpoints. Publish
only necessary user-facing endpoints, on loopback by default. Cross-host/VPN
operation is a separately tested capability, not an automatic extension.

### 5. Signal correctness and sensor ownership

Make each conversion/mapping explicit:

- NED/ENU, body axes, quaternion ordering and rotation direction.
- AGL/MSL or other altitude reference, degrees/radians, SI/non-SI units.
- Acceleration/gravity conventions, sample timestamps and sensor update rates.
- Actuator channel ordering, PWM/normalized units, direction and saturation.
- Noise, bias, latency, dropouts and failures: which component applies each.

The ArduPilot JSON and PX4 simulator APIs expose different input contracts
[S2, S5]; JSBSim initial-condition properties include feet, feet/second and knots
[S4]. An exchanged packet is not proof of physically correct mapping. Avoid
adding sensor noise twice or bypassing the estimator with unintended ground
truth. Record FDM truth alongside autopilot estimates and actuator outputs.

### 6. Fidelity and repeatability

Select the integration according to the actual task: mission functionality,
controller tuning, estimator testing, performance prediction, or perception and
collision testing. These have different validation requirements.

Engine capability is not model validity. JSBSim explicitly describes its bundled
named-aircraft models as public-data approximations for educational/entertainment
use [S7]. Require appropriate evidence for the selected model and intended use.
Neither lockstep nor a fixed random seed alone proves deterministic outcomes.

Define repeatability tolerances before interpreting results. Record image digests,
autopilot/FDM/bridge revisions, model/world/config hashes, seeds, timestep,
sensor rates, requested/achieved real-time factor and relevant CPU/GPU/runtime
information. Keep FDM truth and autopilot outputs correlatable by simulation time.
Distinguish exact reproducibility from acceptable numerical/statistical agreement.

### 7. Rendering, resources and asset provenance

No GUI does not mean no rendering. Camera and other render-based sensors may
still require rendering infrastructure. Gazebo documents EGL headless rendering
with OGRE2, including GPU and software-rendering considerations [S8].

Separate deployment capabilities for dynamics-only, rendered sensors and an
optional interactive viewer. Measure CPU, memory, GPU use, sensor bandwidth and
achieved real-time factor under representative load. Do not treat rendering a
viewer as proof that an engine is supplying flight dynamics.

Check engine/plugin/asset redistribution rights and unattended/headless licensing
before packaging commercial backends. Pin and make assets locally available;
PX4's standalone helper can fetch models/worlds on first use [S1], which should
not become an invisible network dependency of a reproducible runtime.

## Qualification experiments before generalizing

Run these against one pinned autopilot/backend/model pairing. Preserve commands,
configuration and measured results; documentation findings are not test results.

| Investigation | Minimum experiment | Decision/evidence required |
| --- | --- | --- |
| Transport and isolation | Start in both orders; run two isolated scenarios; interrupt/reconnect the link | Supported topology, explicit endpoints, no cross-scenario traffic, bounded failure/recovery |
| Clock and lifecycle | Pause, single-step, accelerate, CPU-throttle and kill each component | Coherent time/sensor updates; pause versus stall distinction; no false ready or leaked processes |
| Reset and initialization | Fresh restart, persisted-autopilot restart, world reset and declared airborne start | Defined ownership/order, repeatable initial state, no stale clock/plan/sensor state; trim distinguished from pose |
| Signal, fidelity and cost | Stationary/rotated/translating cases, simple actuator response, repeat runs and sensor load | Verified units/axes/mappings, recorded truth/estimates, declared numerical tolerances and measured resource envelope |

Mixed-autopilot shared worlds, cross-host transport, checkpoint restoration and
larger fleets are later qualification targets. Keep unsupported claims explicit.

## Starting recommendation and unresolved decisions

- Evaluate JSBSim first if configurable fixed-wing dynamics is the immediate
  goal; PX4 support is community-supported and release compatibility matters.
- Evaluate modern Gazebo first if shared worlds, collisions, multi-vehicle
  interactions or rich sensors are the immediate goal.
- Prove one ArduPilot/backend pairing end-to-end, then add PX4 via its own native
  adapter. Do not build a universal abstraction before measuring the first path.

Before implementation, choose the initial use case, backend, vehicle model and
pinned versions; decide required fidelity, sensor set, initial-state behavior and
repeatability tolerances. Use experiment results to settle image variants,
network topology, shared-world failure policy and manifest capabilities.

## Sources and revalidation

Upstream documentation was consulted for the design discussion. Several links
track `main`/`master`; Gazebo API pages below are version-specific. They are
research evidence, not a tested compatibility matrix. Revalidate against the
chosen release tuple and retain pinned source references with experiment results.

- **S1:** [PX4 Gazebo simulation](https://docs.px4.io/main/en/sim_gazebo_gz/)
  — standalone launch, bridge-driven time, lockstep and model/world fetching.
- **S2:** [ArduPilot JSON protocol](https://github.com/ArduPilot/ardupilot/blob/master/libraries/SITL/examples/JSON/readme.md)
  — UDP packet directions, fields/units, timestamps, frame rates and counters.
- **S3:** [Gazebo Sim 10 reset](https://gazebosim.org/api/sim/10/reset_simulation.html)
  — world-control reset and system reset interfaces.
- **S4:** [JSBSim initial-condition API](https://jsbsim-team.github.io/jsbsim/classJSBSim_1_1FGInitialCondition.html)
  — initialization, units and the distinction from trim.
- **S5:** [PX4 simulation overview](https://docs.px4.io/main/en/simulation/)
  — simulator MAVLink API, Gazebo bridge and SIH distinctions.
- **S6:** [Gazebo Transport 14 relay](https://gazebosim.org/api/transport/14/relay.html)
  — discovery, bidirectional endpoint reachability and NAT limitations.
- **S7:** [JSBSim model guidance](https://jsbsim-team.github.io/jsbsim-reference-manual/user/)
  — provenance and limitations of bundled aircraft models.
- **S8:** [Gazebo 6 headless rendering](https://gazebosim.org/api/gazebo/6/headless_rendering.html)
  — EGL/OGRE2 and rendering resource requirements; verify current-release details.
