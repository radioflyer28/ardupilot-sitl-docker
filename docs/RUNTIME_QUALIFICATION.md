# Runtime Qualification

## Qualification layers

Live checks performed on 2026-10-16 UTC with Docker Engine 28.1.1 / Docker Desktop.
Three scopes are distinguished below: existing firmware images with mounted
helpers, newly built images using installed entrypoints, and Compose services
with host clients. Later sections add PX4 UDP and both JSBSim topologies.
The external ArduPilot checkout was not edited. Results are historical evidence
for the exact recorded images/helpers, not qualification of every rebuild.
Current usage lives in the runtime guides; older commands below may now exercise
newer defaults and do not recreate historical image IDs.

### Existing-image baseline

The first checks used **existing local images with then-current repository helpers
mounted read-only at `/qualification`**, without building firmware or images.

| Firmware environment | Existing image ID | Verified firmware identity |
| --- | --- | --- |
| `ardupilot-sitl:copter-4.6.3` | `sha256:5a7aacc0269d4c3d95464b30b5d80abf72a6b79146d14934c75f3871831ef8a3` | MAVLink version `0x040603ff` (4.6.3 release), custom version ASCII `92b0cd78`; pymavlink 2.4.49 |
| `px4-sih:sihsim-quadx-v1.16.0` | `sha256:1bc2dc61fb300a4a52ccd053339b6845c4f0f2bef951b6fe3989d1a6f22933b1` | PX4 Release 1.16.0, git `6ea3539157ca358c70a515878b77077af7d4611d` |

The images predate the managed-runtime changes. These results qualify the mounted
helpers against these firmware environments, **not newly packaged images** or
those images' installed entrypoints/health checks. The helper health command was
invoked explicitly. Bridge-isolated internal connections were tested, not host
port publication, cross-host routing or external flight dynamics.

## Reproduce without image builds

Requirements: Docker access, already-built image tags, Python 3 on the host,
and a host checkout visible to Docker bind mounts. Run from the repository root.
Current PX4 helpers require a pymavlink-equipped image such as the readiness image
below; old baseline PX4 images lack that dependency. To reproduce the original
process-only baseline instead, use the qualifier at commit `34a6d74` and its old tag.
The image users must be able to write the artifact directories (tested with the
default UID 1000). Choose a new/empty output directory each time.

```bash
python3 docker/qualify-runtime.py \
  --output artifacts/qualification-copter-4.6.3-final

python3 docker/qualify-runtime.py \
  --family px4 --image px4-sih:qualify-v1.16.0-ready \
  --output artifacts/qualification-px4-mounted-ready
```

The PX4 suite uses the existing ArduPilot image only as a pymavlink-equipped
client sharing PX4's network namespace (`--client-image` selects that client).
It does not launch a second autopilot in that client container.

The opt-in suite launches named `sitl-qualify-*` containers, makes assertions
against real firmware, and removes those containers on completion/failure. It
retains generated logs, run state and `report.json` under the ignored output
root. Reports include image IDs, source revision, helper hashes and observations.
They are generated evidence, not checked-in fixtures. The source revision can
have uncommitted fixes; helper hashes identify the tested code. Interruption of
the harness itself may require manual cleanup of its containers.

## Existing-image results: ArduPilot Copter 4.6.3

Passed in direct mode (`INSTANCE=0`, `SYSID=1`) and non-interactive MAVProxy mode
(`INSTANCE=1`, `SYSID=2`):

- Expected initialized autopilot heartbeat and managed readiness/health command.
- Startup upload and readback of all items in the checked-in mission (5), fence
  (4), and rally (1) examples, with independent mission types.
- Actual execution of `qualification-ready.lua`: a witness file is written in
  `work/`, proving more than file copying. The initial-state example is also
  staged; no flight/arming or airborne-pose correctness is claimed.
- Persisted `RTL_ALT=4321` across stop/resume and retained uploaded plans when
  plan selections are omitted on resume.
- Removed Lua selections disappear from the restaged `scripts/` directory.
- Fresh start restores `RTL_ALT=1500` and archives the prior `work/` directory.
- SIGTERM via `docker stop` exits 143, records `stopped`, and finishes in less
  than one second in observed runs (the suite enforces an 18-second upper bound).
- Killing the real `arducopter` process fails the managed run with exit 1 and
  `failed` status instead of leaving sim_vehicle sleeping indefinitely.

The mounted `arducopter-quad` bundle also starts successfully using the
process-local metadata overlay. Installed `vehicleinfo.py` SHA-256 remains
`5837b37d1649a44bb998391dcb911dfc8be16e3f02566ba025d3da399fbbf6c5`
before/after launch. A missing explicit bundle is rejected before creating a run
root. These checks cover the older Python-backed metadata implementation only.

The existing image emits optional MAVProxy ADS-B-module/terrain-download and
WSL-interface-probing warnings. They did not prevent the tested plan, telemetry
or lifecycle operations; this is not qualification of those optional modules.

## Existing-image results: PX4 SIH 1.16.0

Passed with `sihsim_quadx`, instance 0:

- Native startup completes; simulator reports lockstep; live local position
  becomes valid with advancing timestamps. This is a qualification observation,
  not a new runtime readiness guarantee.
- Explicit `SYSID=7` is observed in received MAVLink heartbeats after the startup
  hook fix. A subsequent fresh start with no SYSID uses native system ID 1.
- Set/save `MPC_XY_VEL_MAX=7.25`; resume restores it. Fresh returns it to 12 and
  archives previous state.
- SIGTERM exits 143 with `stopped` status, observed below one second.
- Killing the real `px4` process yields exit 137 and `failed` status.

These earlier PX4 helpers reported process-only `running`. Automatic
heartbeat readiness and mission/fence/rally initialization were absent in those
helpers; the newer readiness implementation is qualified separately below.

## Newly packaged images and JSON-backed compatibility

Built the current Dockerfiles under separate local qualification tags; existing
release tags were not replaced or pushed:

| Qualification image | Image ID | Firmware |
| --- | --- | --- |
| `ardupilot-sitl:qualify-c6a991d4` | `sha256:a084bb5b44b9489f8427d1bf18eaad9b5fe97791c1e30a4a415dfec74f1cffc8` | ArduCopter 4.8.0-dev, exact revision `c6a991d4aa91e3834af333c0061533aa1009b431` |
| `px4-sih:qualify-v1.16.0` | `sha256:77aabc69577c7be4145f2a62d30950fa6e39c9b7a23708c66390d1dbf2b65f83` | PX4 1.16.0, revision `6ea3539157ca358c70a515878b77077af7d4611d` |

Copter 4.7.2 still has Python-backed metadata. The JSON-backed check therefore
uses a **pinned development revision**, not a claimed stable JSON-backed release.
The built image has pymavlink 2.4.50 and reports MAVLink firmware `0x04080000`,
custom version ASCII `c6a991d4`.

Reproduce the builds from the repository root (cache imports are optional):

```bash
docker buildx build --progress plain --cache-from type=local,src=.buildx-cache \
  --build-arg ARDUPILOT_REF=c6a991d4aa91e3834af333c0061533aa1009b431 \
  --build-arg WAF_TARGET=copter --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:qualify-c6a991d4 --load -f Dockerfile .

docker buildx build --progress plain --cache-from type=local,src=.buildx-cache/px4-sih \
  --build-arg PX4_REF=v1.16.0 --build-arg PX4_BUILD_TARGET=px4_sitl \
  --build-arg PX4_BUILD_DIR=px4_sitl_default --build-arg PX4_JOBS=8 \
  -t px4-sih:qualify-v1.16.0 --load -f Dockerfile.px4-sih .
```

These commands pin autopilot source, not every apt/pip/base-image dependency.
Image IDs identify the actual tested packages; future rebuilds need not be
bit-identical. Existing PX4 firmware build layers were reused from cache.

Run the installed-image suites (PX4 uses the newer readiness image described below):

```bash
python3 docker/qualify-runtime.py --installed \
  --image ardupilot-sitl:qualify-c6a991d4 \
  --output artifacts/qualification-packaged-c6a991d4

python3 docker/qualify-runtime.py --installed --family px4 \
  --image px4-sih:qualify-v1.16.0-ready \
  --output artifacts/qualification-packaged-px4-ready
```

`--installed` does not override ENTRYPOINT or launch mounted runtime helpers;
only test inputs/clients come from the read-only checkout mount. Core installed
helper hashes were also compared with their source files and matched.

**ArduPilot passed:** both direct/MAVProxy modes, real plan upload/readback, Lua
execution, persisted plans/parameters, script removal, fresh archives, shutdown
and vehicle-crash handling. Each ready state was also checked against Docker's
installed HEALTHCHECK. The bundled frame uses the JSON-backed overlay without
changing either upstream metadata file; SHA-256 values before/after launch are:

- `vehicleinfo.py`: `cdeffa409a8821f7b05b3c4b96e55f0de0deb952ce24990701272500d10f0750`
- `vehicleinfo.json`: `9a860f414b2bb16298d283c6024b65b37b57a99bb085de8b56a4bb7a0ad8c32b`

The current suite uses `SIM_WIND_SPD=2.5` for persistence and expects 0 after fresh
start. This replaces the historical `RTL_ALT` probe above because the development
revision changed that parameter interface. No flight/airborne dynamics were tested.

**PX4 passed:** the installed default entrypoint, live SIH/position data, on-wire
SYSID 7 override/native SYSID 1, saved parameter resume, fresh archive/reset,
shutdown and binary-crash behavior. This earlier image has no automatic MAVLink
readiness or image HEALTHCHECK; its managed status is process-only `running`.
Newer PX4 helpers integrate verified readiness and require rebuilding the runtime
package; these older image IDs do not qualify that capability. Explicit
`bash` debug-command dispatch also passed for both image families.

Generated reports are in the output directories above; build logs are retained
locally under ignored `artifacts/qualification-builds/`.

## Compose and host-client qualification

The base `compose.sitl.yml` topology passed using the packaged development image.
A test-only [override](../docker/compose.qualification.yml) selects fresh/resume
per service without changing production topology. Run with a host Python that
already has pymavlink installed (the tested interpreter was `/usr/bin/python3.10`,
pymavlink 2.4.49):

```bash
python3 docker/qualify-compose.py --image ardupilot-sitl:qualify-c6a991d4 \
  --client-python /usr/bin/python3.10 \
  --output artifacts/qualification-compose-c6a991d4
```

Clients send GCS heartbeat traffic before waiting for vehicle telemetry, including
on MAVProxy tcpin outputs; the vehicle handshake remains bounded.
Cleanup errors fail qualification and are retained in the report, even when the
scenario assertions succeeded. Final success is printed only after cleanup.
The plan-readback client also compares commands, canonical frames, coordinates,
altitudes and parameters against independent fixture expectations, not just counts.
ArduPilot synthesizes mission item 0 from current home, which may still be unset
at managed readiness. Its coordinates/altitude are recorded, not compared to the
uploaded home row; this is not a GPS/home readiness check. Stored rows must match
native integer coordinates or the specific legacy float32 coordinate/scaling
conversion, within one integer unit, with centimeter altitude tolerances. This
accounts for legacy MISSION_REQUEST precision loss rather than applying a blanket
spatial tolerance.

The three host ports must be free. The checker creates a unique Compose project,
uses real host TCP clients (not a container sharing the vehicle network), and
retains commands/results in its output directory. Verified:

- All three containers become healthy via the installed health command.
- Published bindings are loopback-only: TCP 5760, 5770 and 5780 reach SYSIDs
  1, 2 and 3 respectively.
- Each service has a distinct named volume with working image-user permissions.
- Setting `SIM_WIND_SPD=2.5` succeeds through all three host connections.
- `down` retains volumes. Recreating containers in resume mode reuses those
  volumes and preserves the parameter in each vehicle.
- Fresh recreation resets the parameter to 0 and archives exactly one previous
  work directory per service.
- Final cleanup removes the test project's containers and volumes only; no
  qualification containers/volumes remained after the successful run.

The default Compose release tag was not changed. To run this qualified image
manually, set `ARDUPILOT_SITL_IMAGE=ardupilot-sitl:qualify-c6a991d4` explicitly.
PX4 host/bridge network deployment is not covered by the ArduPilot Compose result.

## PX4 verified readiness and plan initialization

A newer runtime package was built with cached PX4 v1.16.0 firmware (source
`6ea3539157ca358c70a515878b77077af7d4611d`), without replacing release tags:

- Image: `px4-sih:qualify-v1.16.0-ready`
- ID: `sha256:1ef96ee0b8a5a6b96cfe8046f1c168fca5110156dbf133ec62cb3603bdffd49a`
- Runtime: Python 3.10.12, pymavlink 2.4.50 in an isolated venv, binary wheels only.
- Installed supervisor, uploader, launch script and startup-hook hashes matched
  the source tested for that image; later relay changes are qualified below.

Build using the PX4 command above with the new tag, then reproduce qualification:

```bash
python3 docker/qualify-runtime.py --installed --family px4 \
  --image px4-sih:qualify-v1.16.0-ready \
  --output artifacts/qualification-px4-readiness-v1.16.0-documented
```

The installed entrypoint and Docker HEALTHCHECK passed. The private loopback UDP
link leaves the native GCS link available; a separate client still receives the
expected SYSID there. Verified cases:

1. Fresh SYSID 7 startup uploads and independently reads back 5 mission, 4 fence
   and 1 rally item, including coordinates, frames, commands, parameters and altitudes.
2. Resume with all plan selections omitted retains all three plans and saved
   `MPC_XY_VEL_MAX=7.25`.
3. Resume with explicit empty selections clears all three types, retaining the
   saved parameter.
4. Fresh restart archives prior work, restores the parameter default 12, leaves
   plans empty and uses native SYSID 1. Killing PX4 exits 137 with failed status.
5. A terrain-frame mission rejected by firmware with MISSION_RESULT 2 exits 1
   and never becomes ready.
6. An unused initialization endpoint times out and exits 1, not process-only ready.

Graceful stops exited 143 in under one second. Real SIH lockstep and valid local
position were also observed, separately from startup readiness. The mission file
is a protocol fixture, **not a flight-ready PX4 mission**: PX4 stores row 0 as a
normal item. Legacy coordinate requests quantize to float32; PX4 stores that value
as double, unlike ArduPilot's additional float32 integer scaling. Readback checks
permit these specific backend conversions, not arbitrary spatial tolerances.

The report and logs remain under the output directory above. Current mounted
helpers also passed Copter 4.6.3 direct/MAVProxy/bundle regression in
`artifacts/qualification-ardupilot-px4-uploader-regression/`. Older installed PX4
image IDs above remain process-only; they were not retroactively qualified for
the new readiness contract. No flight or network-fault resilience is implied.

## Localhost-default Compose qualification

The default host publications for both runtimes are localhost-only. The ArduPilot
Compose file retains its three TCP ports; `compose.px4-sih.yml` adds a bridge-mode
PX4 UDP endpoint. `SITL_BIND_ADDRESS` explicitly opts into LAN publication, with
no custom firewall configuration. Container-internal listener addresses are not
restricted in a way that breaks Docker forwarding.

PX4 was packaged under a new tag without replacing earlier qualification or
release tags:

- `px4-sih:qualify-v1.16.0-localhost`
- `sha256:89cdc26666132254089da6ee085bd63c12a2ce2152103d98928b3e288de90589`
- Installed runtime/uploader/hook/relay hashes match the tested source.

Reproduce with a host pymavlink Python and UDP port 18570 free:

```bash
python3 docker/qualify-compose.py --family px4 \
  --image px4-sih:qualify-v1.16.0-localhost \
  --client-python /usr/bin/python3.10 \
  --output artifacts/qualification-px4-localhost-compose
```

The checked-in Compose topology passed installed health and inspected publication
`127.0.0.1:18570` -> container `18670/udp`. Real host clients observed SYSID 1 and
set/read `MPC_XY_VEL_MAX=7.25`. A separate reconnected client used UDP source port
52317 after the first used 50530; both exchanged real vehicle data through the
relay. Named-volume down/resume retained the parameter; fresh recreation reset it
to 12 and archived prior work. Killing the relay stopped the managed vehicle with
exit 1 and failed status, rather than leaving it advertised healthy. Cleanup passed.

ArduPilot's three-service localhost TCP/state/volume suite also passed with the
new binding override and shared checker, recorded under
`artifacts/qualification-ardupilot-localhost-compose-regression/`.
Host-only tests separately exercise bidirectional relay bytes, client reconnection
and multiple active peers. CI configuration-only checks validate both localhost
and explicit all-interface publication for both Compose files; actual access from
another LAN machine is not qualified here. Passive UDP autodiscovery remains
available through the explicit native PX4 host-network alternative, not bridge mode.

## ArduCopter/JSBSim F450 qualification

An experimental external-physics path passed installed-image qualification with
unmodified Copter 4.6.3 and JSBSim 1.3.3. The project-owned adapter uses ArduPilot's
JSON physics protocol, not its fixed-wing JSBSim connector. See
[ARDUCOPTER_JSBSIM.md](ARDUCOPTER_JSBSIM.md) for build/run instructions and the
project-owned direct-motor F450 composition.

Qualified image identities:

- Autopilot: `ardupilot-sitl:qualify-4.6.3-jsbsim`,
  `sha256:0b251c960ee24579f3224283da7071f923a89f431af824e534ec9cab39a1e171`.
- Simulator: `jsbsim:qualify-1.3.3-f450`,
  `sha256:ccfc58346fb03512657b26eb259830c2530c9c262361e91774bd15fbd9558d72`.
- Original Copter release tag was not replaced. Simulator dependencies include
  Python 3.12, JSBSim 1.3.3 and NumPy 2.2.6. Package license notices remain installed;
  generated model/config hashes are retained in each simulator run manifest.

Successful evidence:

- `artifacts/qualification-jsbsim-f450-800hz/report.json`: installed helper hashes,
  inspected localhost TCP publication, initialized physics-aware readiness and
  normal-EKF guided flight without force-arm or disabled arming checks.
- Takeoff target 5 m; 81 samples during the 10-second hover window reported
  altitude 4.986–5.001 m, maximum horizontal displacement from the hover-window
  origin 0.0143 m and maximum absolute roll/pitch 0.00435 rad. These are autopilot
  telemetry measurements, not real-aircraft accuracy claims. Independent JSBSim
  truth confirmed takeoff above 4 m and monotonically advancing simulation time.
- Commanded yaw to 90 degrees, landing and automatic disarm passed. Reported
  landed relative altitude was -0.027 m. Declared acceptance limits were altitude
  3–7 m, hover displacement under 4 m, absolute roll/pitch below 0.45 rad, at
  least 20 hover samples, yaw within 15 degrees and landed altitude below 0.5 m.
- Killing JSBSim invalidated autopilot readiness and stopped the autopilot with
  failed status/exit 1. `artifacts/qualification-jsbsim-f450-autopilot-loss/`
  independently passed the reverse direction: killing ArduCopter caused the
  adapter's actuator-progress deadline to fail and exit 1. This second project
  ran concurrently on a separate Docker network and host port 5960.
- `artifacts/jsbsim-model-800hz-check.json`: real-model stationary specific force,
  tilted free-fall/attitude, four individual rotor moment signs and collective
  climb checks. Host protocol/configuration regressions pass without JSBSim.
- `artifacts/qualification-jsbsim-f450-repeat/`: a second fresh installed flight
  passed on the same image digests, including physics-death shutdown. Its 77 hover
  samples also stayed at 4.986–5.001 m, with maximum hover-window displacement
  0.0143 m. Two successful runs do not establish deterministic outcomes.
- `artifacts/qualification-jsbsim-final-internal-regression/`: installed internal
  physics regression passed on the final qualified autopilot image. This is not
  an internal-versus-JSBSim flight comparison. All qualification projects cleaned
  up their containers and volumes.

Run the current combined-default checker into new empty directories (these
commands do not recreate the historical split image tuple above; see the later
combined/split section and runtime guide for current packaging):

```bash
python3 docker/qualify-jsbsim.py --output artifacts/jsbsim-flight-new
python3 docker/qualify-jsbsim.py --skip-flight --fault sitl --port 5960 \
  --output artifacts/jsbsim-autopilot-loss-new
```

Qualification exposed and fixed three integration assumptions: the older base
image needed updated shell entrypoints and an owned named-volume mount directory;
firmware's advertised actuator rate converges during boot rather than matching
`SIM_RATE_HZ` immediately; and a 400 Hz gyro exchange fails Copter's normal arming
rate check. The adapter now exchanges at 800 Hz with two 1600 Hz physics substeps,
keeping the 400 Hz controller and arming checks intact.

Scope remains one F450 model, flat ground start, instance 0 per isolated project,
fresh state and speed 1. Opposite startup order/DNS delay, transport-loss recovery,
custom model/parameter changes, directional flight manoeuvres, airborne starts,
checkpoint restore, cross-host physics and real-aircraft fidelity are unqualified.
The existing internal backend remains default. JSBSim backend selection is a
scenario restart, not a live state transfer; arbitrary models are not swappable.

## Read-only JSBSim model catalogs

Catalog-capable images passed installed flight checks for both packaged F450 and
an independently named, read-only mounted `HeavyQuad` variant:

- `ardupilot-sitl:qualify-4.6.3-jsbsim-models`:
  `sha256:20b4af6104bcacedc373b1af948778b7e555bfa908a8c61bd85a148039c04529`.
- `jsbsim:qualify-1.3.3-models`:
  `sha256:92b8ce8ac6c5786374d27cabcf94aef49435c34ba07a41161e9758470ea0e5b8`.
- `artifacts/qualification-jsbsim-models-heavy/`: exported native catalog with
  both F450 and HeavyQuad present; selected HeavyQuad through `JSBSIM_MODEL`.
  Its mass was changed from 1.4 to 1.8 kg and inertias from
  0.0190/0.0190/0.0252 to 0.0244/0.0244/0.0324 kg m². JSBSim property inspection
  confirmed the distinct masses when selecting each name from the same catalog.
- `artifacts/qualification-jsbsim-models-default/`: no catalog mounted;
  packaged F450 remained the default. Both flights passed normal arming/EKF,
  takeoff, hover, yaw, landing, auto-disarm and simulator-death shutdown.
  Reported hover altitude was 4.987–5.001 m in both runs; this is not a claim of
  equivalent aircraft dynamics or deterministic results.
- Installed runtime helper hashes matched source. HeavyQuad's retained manifest
  identified `/models` as its source; all staged file hashes matched the original
  catalog after the run. The Compose override declares a read-only bind and
  disables automatic creation of a missing host directory. Test containers and
  volumes were cleaned up.
- 57 host regressions and all lightweight CI commands passed locally, including
  catalog Compose validation. GitHub execution is a separate check.

Use the catalog/export commands in [ARDUCOPTER_JSBSIM.md](ARDUCOPTER_JSBSIM.md).
Custom XML is preserved, selected by name and snapshotted per run. Four-engine
and direct-motor-input checks establish interface compatibility only; arbitrary
models, motor geometry and tuning are not qualified by these two examples.

## Combined default and optional split deployment

Both current topologies passed installed flight qualification with the same
adapter/model implementation. These tags leave the earlier qualification images
unchanged:

- Combined: `ardupilot-sitl:qualify-4.6.3-jsbsim-local`,
  `sha256:62b437603e47892b5eb57e99d0fbe53e781bfdbe0de5260fe128f31a8d1f3c30`.
- Split autopilot: `ardupilot-sitl:qualify-4.6.3-jsbsim-split`,
  `sha256:c78f62e6268226aae7db9c5fc839306ee0f0760c657fa76b4a01a1db49039ec6`.
- Split simulator: `jsbsim:qualify-1.3.3-split`,
  `sha256:04944fd39934dbd40b30bf0d7ee33f8c3de56ebe5cbed584810d48abffbaf2e0`.

Evidence under ignored `artifacts/`:

| Report directory | Passed checks |
| --- | --- |
| `qualification-jsbsim-local-flight` | Single-container F450 takeoff, hover, yaw, landing/disarm; killing the physics child fails and stops the combined runtime |
| `qualification-jsbsim-local-heavy-stop` | Read-only HeavyQuad catalog flight; graceful Compose stop records stopped status for supervisor and physics child |
| `qualification-jsbsim-local-autopilot-loss` | Killing the actual ArduCopter process fails the combined runtime and stops the physics child |
| `qualification-jsbsim-split-flight` | Optional two-container F450 flight and shutdown following simulator-container failure |

All runs verified installed helper hashes and localhost host publication; the
flight runs also verified progressing physics truth independently of telemetry.
All test containers and volumes were removed. The combined image's isolated
interpreter reported Python 3.12.3, `sys.prefix=/opt/jsbsim-venv`, and JSBSim 1.3.3.
Real-model tests and model export passed through that interpreter. Explicit
`--dynamics internal --validate` passed on the combined image; this is preflight,
not a new full internal-physics flight qualification.

61 host tests pass, including preserving the virtualenv interpreter symlink,
rejecting conflicting local/external settings before state creation, and archiving
nested physics truth with autopilot state. Both base topologies and read-only
catalog overrides pass Compose configuration checks. Dockerfile checks passed;
lightweight CI commands passed locally, not necessarily on GitHub.

`compose.jsbsim.yml` now means combined deployment; use
`compose.jsbsim-split.yml` for the former split arrangement. Likewise use the
matching `*-models.yml` override. The live checker defaults to local mode; add
`--deployment split` for split images and `--fault stop` for graceful shutdown.
Earlier reports in this document retain their original image/topology scope.
These checks do not establish arbitrary-model fidelity or cross-host physics.

## PX4/JSBSim qualification

The project-owned PX4 simulator-MAVLink adapter shares the same JSBSim 1.3.3
F450/catalog model implementation as ArduCopter. Both topologies passed installed
normal-EKF takeoff, 10-second hover, commanded yaw/reposition, landing and normal
auto-disarm. No force-arm or disabled estimator/arming checks were used.

Qualified images:

- `px4-jsbsim:qualify-v1.16.0-local`:
  `sha256:2cf41c517d2845f4d5db7a0403507fa0518628a8949e526c6f66a4ddc2e7d8af`
- `px4-jsbsim:qualify-v1.16.0-split`:
  `sha256:24cb8895ca83bb130ca3cf73b139d964d47d757568a51cfd2dbcadea907b9be2`
- `px4-jsbsim:qualify-v1.16.0-physics`:
  `sha256:3bdebcfc831a3b420ad13d5d7ed824bc3555d38ddb7b519b31ec90852d44d47e`

The unchanged PX4 binary in the base and both derived autopilot images hashes to
`37b9ebd0d673d569fab18663f82aee74430b76f5d2a82f45e42c472d7b788599`.
The tested build directory is `px4_sitl_default`, not a stripped newer SIH target.
Installed helper hashes, localhost UDP publication and unpublished simulator TCP
were checked. The combined physics environment is isolated at `/opt/jsbsim-venv`.

Evidence beneath ignored `artifacts/`:

| Report | Passed scope |
| --- | --- |
| `qualification-px4-jsbsim-local-flight-final` | F450 flight; physics child death fails/stops combined run |
| `qualification-px4-jsbsim-split-flight-final` | F450 flight; simulator container death fails/stops PX4 |
| `qualification-px4-jsbsim-local-autopilot-loss-final` | PX4 binary death stops local physics |
| `qualification-px4-jsbsim-split-autopilot-loss-final` | PX4 container death stops external physics |
| `qualification-px4-jsbsim-heavy-stop-final` | Mounted HeavyQuad flight and combined graceful shutdown |
| `qualification-px4-jsbsim-split-heavy-stop-final` | Mounted HeavyQuad flight and clean stopped states for both split processes |
| `qualification-px4-jsbsim-split-stop-final` | Independent split ordered-stop regression |
| `qualification-px4-jsbsim-split-recreation` | Two down/up cycles retain volumes and re-establish healthy fresh runs |
| `qualification-px4-jsbsim-sysid-archive-final` | SYSID 17 initialization and fresh restart archiving vehicle/physics together |
| `qualification-px4-sih-jsbsim-regression-final` | Native SIH readiness, host reconnection, down/resume retention, fresh reset and relay-failure cleanup on the new autopilot target |
| `qualification-arducopter-px4-jsbsim-regression` | ArduCopter flight and physics-loss regression after shared supervisor/qualification changes |

F450 hover altitudes were 4.970–5.000 m across both topologies, with maximum
reported horizontal displacement about 0.035 m. HeavyQuad hover across both was
4.969–5.001 m with displacement about 0.035 m. HeavyQuad's 101 staged asset hashes
matched the read-only source catalog; real model loading confirmed 1.8 kg versus
F450's 1.4 kg. Installed force/sensor/motor-sign checks also passed separately
(`px4-jsbsim-installed-model-check-final.json`). These measurements establish scoped
operation, not real-aircraft fidelity or cross-run determinism.

The ArduCopter regression used a separate tag,
`ardupilot-sitl:qualify-4.6.3-jsbsim-px4-regression`, image
`sha256:230f279df587c43f0a72b8bc3e347cc475cbd2cf8a6e8bfd2d812c1bbfbe14ed`;
previous release and qualification tags were preserved.

Development probes exposed two integration contracts: a 400 Hz sensor exchange
must match PX4's IMU integration rate, and perfectly constant ideal sensors trigger
native stuck-sensor validation. Seeded white sensor noise resolved the latter;
noise-free truth is retained separately. The flight client also decodes PX4's
bytewise integer parameter representation rather than treating it as float-cast
ArduPilot parameter data. Split ordered shutdown exposed a TCP-EOF race: the
adapter now invalidates readiness immediately but allows up to its link timeout
for Compose's following stop signal. Without that signal it still fails on peer
loss. Final images above passed both failure directions and clean stop checks.

Reproduce with `docker/qualify-jsbsim.py --family px4`; add `--deployment split`,
`--models-dir`, `--model`, or `--fault physics|sitl|stop` as needed. See
[PX4_JSBSIM.md](PX4_JSBSIM.md) for build/run commands and restrictions. Other
releases, arbitrary aircraft, cross-host physics, real LAN clients, sensor fidelity,
transport interruption/reconnection and checkpoint restore remain unqualified.

## Defects exposed and fixed

1. **ArduPilot speedup argument:** the resolver emitted `1.0`, rejected by
   Copter 4.6.3's integer `sim_vehicle --speedup` parser. Resolve/emit positive
   integer multipliers and reject fractional values during preflight.
2. **Premature mission initialization:** an early boot heartbeat triggered
   `MISSION_COUNT` before mission storage initialization, receiving
   `MAV_MISSION_NO_SPACE` (4). A later upload succeeded unchanged. Wait past
   `MAV_STATE_UNINIT`, `BOOT` and `CALIBRATING` before uploading; do not retry
   arbitrary rejected plans as though every rejection were transient.
3. **MAVProxy stdin EOF:** interactive MAVProxy exited when container stdin was
   closed. Managed launches now add `--non-interactive` internally.
4. **PX4 explicit system ID overwritten:** v1.16 rcS applies `PX4_PARAM_*`, then
   resets MAV_SYS_ID to `INSTANCE+1`. A late parameter change did not change the
   already-started MAVLink sender identity. A narrow PATH-sourced
   `px4-rc.mavlink` hook reapplies the explicit ID before native links start,
   without modifying upstream files.

5. **Build context omitted helpers:** the old `.dockerignore` allowed only the
   removed/older helper names. Allow current Python/shell helpers and the PX4
   startup hook; regression-check local Dockerfile COPY sources against it.
6. **Pinned commit checkout:** shallow `git clone --branch` does not accept a
   raw commit ID and fell back to a full clone. Fetch the requested ref/commit
   shallowly and check out FETCH_HEAD detached, verified by the development build.

Host-only regression tests cover runtime/packaging seams in addition to the live suite.
The PX4 qualification harness also waits for estimator convergence rather than
incorrectly treating successful startup-script return as valid position.

## Supporting checks

- 71 host-only regression tests pass (`python3 -m unittest discover -s docker -p 'test_*.py'`).
- Python compilation, Bash syntax, the POSIX PX4 startup-hook syntax, Compose
  configuration, local Markdown links and `git diff --check` pass.
- Static `docker buildx build --check` completes for the runtime Dockerfiles. Actual
  package builds and installed-image/Compose qualification also pass as above.

## Remaining qualification boundaries

- Qualify a stable JSON-backed ArduPilot release when available; the current
  JSON-backed result is one pinned 4.8.0-dev revision, not all future releases.
- Extend vehicle/release coverage beyond Copter 4.6.3, the pinned Copter
  development revision and PX4 SIH quad 1.16.0. Revalidate the PX4 PATH hook when
  upstream startup changes. Old release images were tested with mounted helpers,
  not rebuilt under their original tags.
- Add fault tests for startup cancellation, stalled firmware and interrupted
  uploads, plus transport-loss/retry cases with real peers. Mocked protocol-loss
  tests are not measurements of real network resilience.
- Extend beyond the qualified PX4 localhost bridge client to real LAN peers,
  other platforms and offboard tools. External dynamics require the experiments in
  [RUNTIME_PROFILES.md](RUNTIME_PROFILES.md).

See [FUTURE_WORK.md](FUTURE_WORK.md) for the actionable backlog. Do not generalize
these results into a complete release matrix, physics validation, flight test
or checkpoint guarantee. Installed-image evidence applies only to the image IDs
listed above.
