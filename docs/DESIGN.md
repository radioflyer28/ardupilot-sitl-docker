# Design: SITL Docker Images

The project provides prebuilt, headless autopilot runtimes. ArduPilot SITL is the
primary path; PX4 SIH is a sibling with native PX4 conventions. Runtime startup
must not rebuild the autopilot or depend on an interactive developer terminal.

## Goals and boundaries

- One vehicle per autopilot container, with service-local identity, networking
  and inputs. A future external simulator service may own a multi-vehicle world.
- Native model, parameter and plan files remain inspectable, mountable inputs.
- Validate requested configuration before launch; never fall back silently.
- Keep source/config inputs separate from writable state and retained outputs.
- Keep checked-in bundles small; generate catalogs with
  `scripts/populate-config-bundles.py` into ignored `configs/generated-frames/`.
- Preserve explicit command/debug-shell entrypoints for advanced upstream use.
- Do not patch the external `./ardupilot` checkout.
- Build automation and fleet generation are separate from the single-vehicle
  runtime lifecycle.

## Runtime profile direction

Use four logical profiles: ArduPilot/internal, ArduPilot/external, PX4/internal
(SIH), and PX4/external. These are capability/deployment profiles, not a mandate
for four Dockerfiles, independent implementations or simultaneous containers.
ArduPilot internal dynamics and PX4 SIH are qualified runtime paths. The
ArduCopter/JSBSim F450 external path is experimental, with installed normal-EKF
hover/yaw/land and coupled process-failure checks passing for one pinned tuple;
see `RUNTIME_QUALIFICATION.md` for its narrower tested scope.

Default single-vehicle ArduCopter/JSBSim to one combined container, with separate
supervised processes and an isolated physics Python environment. Retain independent
simulator/autopilot images and explicit split Compose for deployment flexibility.
Shared-world simulators may still merit separate containers. Share primitives, but
qualify each autopilot/backend/version/model combination. One shared world may
serve several autopilot containers; an existing image may support more than one
profile, while external backends may require multiple build variants.

[RUNTIME_PROFILES.md](RUNTIME_PROFILES.md) records the proposed architecture,
research sources, clock/reset/state boundaries and experiments required before
freezing external adapter or scenario-manifest contracts.

The first experimental external pairing is ArduCopter with the JSBSim F450 quad-X model,
using ArduPilot's existing JSON physics interface and a project-owned adapter
outside the upstream checkout. Keep internal dynamics default and swap backends
by scenario restart, not in flight. [ARDUCOPTER_JSBSIM.md](ARDUCOPTER_JSBSIM.md)
owns the design, experimental usage, signal/lifecycle contracts and delivery gates.
A read-only native JSBSim catalog can hold multiple named quad-X variants with
shared engine assets. Select with `JSBSIM_MODEL`; preserve custom physical XML
and the same direct-motor interface. Selection support is distinct from model
qualification; packaged F450 remains the no-catalog default.

## Image architecture

Both Dockerfiles retain separate builder and runtime stages. The ArduPilot
builder prebuilds selected waf targets and prepares its Python environment;
only runtime dependencies, the prebuilt tree and helpers reach the runtime.
PX4 copies a prebuilt target and starts its `px4` binary without invoking make.

Build contracts:

- `ARDUPILOT_REF` accepts a tag, branch or exact commit through shallow fetch
  and detached checkout; raw commit IDs do not trigger a full-history clone.
- `WAF_TARGET` selects one ArduPilot target; empty selects `WAF_ALL_TARGETS`.
- `WAF_JOBS` controls build parallelism. BuildKit caches apt, pip, Gradle and
  ccache. Release scripts export zstd archives or publish compressed OCI layers.
- Generated catalogs, build caches and image archives stay out of git.
- PX4 model selection is runtime-only. Build target/directory defaults remain
  release-sensitive (`px4_sitl_sih` on newer main; `px4_sitl_default` for v1.16).
- PX4 initializes only selected SIH-relevant submodules, not external simulator
  stacks. See `PX4_SIH.md` for the version and dependency rationale.

## Runtime pipeline

```text
resolve → validate → lock run directory → prepare → launch
        → expected autopilot heartbeat → upload selected plans → ready
        → monitor processes → bounded shutdown → retain artifacts
```

The no-argument/dash-argument entrypoint invokes `/usr/local/bin/run-sitl.sh`.
An explicit command (such as `bash`) runs directly instead. The stable derived-
image interface is still `run-sitl.sh`, but it now delegates to a Python runner
rather than shell generated inside the Dockerfile.

Responsibilities:

- `sitl_config.py`: pure resolution, supported CLI parsing, scalar/file checks,
  ordered parameter layers and derived endpoints.
- `run-sitl.py`: preflight artifact parsing, staging, lifecycle and readiness.
- `launch-sitl.py`: process-local upstream `VehicleInfo` overlay and execution
  of the unmodified upstream `sim_vehicle.py`.
- `sitl-terminal.py`: upstream `SITL_RITW_TERMINAL` adapter; keeps actual vehicle
  output on container stdout/stderr and publishes vehicle process status.
- `run_state.py`: exclusive run-directory ownership, fresh/resume state, atomic
  status records, Linux subreaping and bounded process-group shutdown.
- `upload-plan-artifacts.py`: mission/fence/rally parsing and MAVLink protocol.

The upstream launcher still handles native frame behavior. The wrapper overlays
metadata in memory for compatibility with both older Python-backed and newer
JSON-backed `VehicleInfo`. It never overwrites installed upstream files. Bundle
parameter files are also passed explicitly because newer binaries use embedded
ROMFS defaults rather than the launcher's `default_params_filename`.

## Effective configuration

Scalar CLI options override env values. Bundle metadata fills model/frame
information; explicit `MODEL`/`--model` wins. Relative artifact references resolve
against `SITL_CONFIG_DIR`; model/default-param paths inside `vehicleinfo.json`
resolve against that file's directory.

Parameter precedence, last definition wins:

1. Native frame defaults.
2. Mounted bundle parameter files.
3. `PARAM_FILES` (ordered JSON array).
4. `PARAM_FILE` (singular convenience layer).
5. Repeated CLI `--add-param-file` options.

Unlike the earlier resolver, `PARAM_FILE` does not suppress bundle defaults.
`--validate` and `--print-effective-config` check the prebuilt binary, selected
inputs and complete plan syntax without staging files or launching a vehicle.
Runtime metadata records the effective settings, not an indiscriminate dump of
the container environment.

Unrestricted upstream flag forwarding is deliberately removed: frame, instance,
transport and run-directory overrides must not disagree with previously derived
settings. The managed parser accepts a documented subset and rejects unknown
flags, multiple-vehicle/peripheral launch and UDP transport. `PROXY`/`-m` accepts
only output, logfile and streamrate options. Advanced upstream operation is an
explicit debug-shell path outside managed guarantees.

## State and artifact ownership

ArduPilot run-root precedence is `--use-dir` / `SITL_RUN_DIR`, then
`ARTIFACTS_DIR/instance_<INSTANCE>`, then `/tmp/ardupilot-sitl/instance_<INSTANCE>`.
PX4 uses `PX4_RUN_DIR`, then the same artifact-parent convention, then
`/tmp/px4-sih/instance_<INSTANCE>`.

Each root contains:

- `work/`: current vehicle state, installed scripts and vehicle logs.
- `history/<id>/`: archived work directories from fresh starts.
- `status.json`: lifecycle state plus supervisor timestamp.
- ArduPilot additionally records `effective-config.json` and internal process
  monitor/temporary files.

Run roots must be empty or carry the runner's ownership marker. An exclusive
file lock prevents concurrent reuse. The runner rejects unowned nonempty roots
and symlinked managed directories rather than deleting user files.

`SITL_STATE=fresh` archives previous work before starting clean. `resume` reuses
persistent vehicle files; it is not an in-flight checkpoint or a restore of an
external FDM's physical state and clock. Both restage the entire managed `scripts/` directory; an explicit
`LUA_SCRIPT` overrides bundled scripts by basename. No stale scripts survive.
Logs and state remain inspectable after failure; history retention is manual.

ArduPilot `.BIN` files live in `work/logs/`. MAVProxy `.tlog` files come from
MAVProxy, with `--aircraft` available for a separate retained directory. Direct
mode does not produce `.tlog`; use an external logger if required. Writable bind
mounts must accommodate the image user. Compose uses per-service named volumes.

## Readiness and lifecycle

ArduPilot defaults to direct TCP (`NO_MAVPROXY=1`). Readiness requires:

- an initialized autopilot heartbeat from configured `SYSID`, component 1,
  beyond UNINIT/BOOT/CALIBRATING (boot heartbeats can precede mission storage);
- accepted uploads for every selected plan;
- a running vehicle and launcher process.

`PLAN_UPLOAD_TIMEOUT` bounds the entire initialization phase. Selected plan
failure fails the run, rather than leaving a partially initialized vehicle
advertised as healthy. Successful initialization does not guarantee arming, GPS,
EKF or user Lua readiness. Initial-state Lua triggered on arm is intentionally
outside startup readiness. Ongoing health checks verify fresh supervisor status
and process liveness, not continuous MAVLink heartbeat health.

The terminal adapter monitors the actual child instead of trusting
`sim_vehicle.py`'s indefinite no-MAVProxy wait. Either launcher or vehicle exit
fails the run. SIGINT/SIGTERM invalidate readiness and terminate owned process
groups; remaining processes are killed after `SITL_STOP_TIMEOUT`. Linux
subreaping collects detached upstream children. Compose adds `init: true` and a
stop grace period longer than the runner deadline.

PX4 shares state/process primitives and plan parsing/upload. Its startup hook adds
a dedicated UDP link with loopback peer (local `30000 + INSTANCE`, peer `31000 + INSTANCE`),
without consuming GCS/offboard links. The supervisor requires an initialized PX4
heartbeat with the expected identity and accepted selected plans before `ready`.
PX4 plan semantics and command/frame capabilities remain native and separately
qualified; matching ready labels do not imply identical flight capabilities.

## Networking and plan initialization

Host publications for both runtime families bind to loopback by default;
`SITL_BIND_ADDRESS` explicitly opts into LAN publication. PX4 bridge mode uses a
supervised UDP byte relay with a stable native peer, avoiding native UDP peer
pinning when host clients reconnect. Native host networking remains opt-in.
Remote exposure must be explicit;
these endpoints are not an authenticated remote management interface.

Direct SITL TCP normally has one client. The initializer temporarily owns it;
external clients must wait for health/readiness. For fan-out, enable MAVProxy or
use an external router. With in-container MAVProxy, the initializer uses a
private loopback TCP output at `20000 + INSTANCE`, away from SITL serial ports.
Managed MAVProxy starts non-interactively so closed container stdin is harmless.
`PLAN_UPLOAD_MASTER` overrides that endpoint but not the expected identity.

Instance, MAVLink system ID and host port allocation are distinct concepts.
Bridge-isolated containers can reuse an internal instance/port while publishing
different host ports. Host-networked PX4 instances need globally coordinated
instance-derived endpoints.

All plan types now use MAVLink: QGC WPL 110 for `MISSION_FILE`, project-owned
JSON for `FENCE_FILE` and `RALLY_FILE`. Parsing happens before launch. Uploads
honor retransmission requests, filter source/destination/type, retry boundedly
and require accepted ACKs. An explicitly empty plan clears its type; an omitted
plan does not issue a clear. No automatic arming or mission start is performed.
See `PLAN_ARTIFACTS.md` for protocol and file details.

Lua remains for user simulation behavior and initial-state injection, not for
mission preload. User scripts still require appropriate parameters such as
`SCR_ENABLE=1` and, for `sim:set_pose`, `AHRS_EKF_TYPE=10`.

## Future scenario layer

A future project-owned manifest/schema should generate this low-level interface,
not introduce an independent runtime interpreter. First stabilize and validate
one vehicle across supported autopilot releases.

The manifest should connect vehicle identity, home, speedup, image reference,
networking, retained outputs and native artifact references. Mission/fence/rally
may use a file or inline definitions, but exactly one form per artifact. Generate
inline data into native files. Params deliberately support ordered files plus a
final inline override map. Lua stays code in files; structured script config may
be generated separately.

Fleet manifests should expand to one Compose service per vehicle with independent
inputs, ports, state and logs. PX4 and ArduPilot adapters should emit their native
controls rather than disguise meaningful autopilot differences.

## Verification boundary

`docker/test_runtime.py` provides host-only resolution, staging, state, protocol
and fake-process lifecycle regression tests. These do not substitute for real
MAVLink/SITL tests against pinned releases. Image builds and live flight/runtime
qualification remain separate checks. The existing-image real-firmware results
and uncovered compatibility fixes are recorded in
[RUNTIME_QUALIFICATION.md](RUNTIME_QUALIFICATION.md); see `FUTURE_WORK.md` for
remaining release and installed-image coverage.
