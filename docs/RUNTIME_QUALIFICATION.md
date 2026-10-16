# Runtime Qualification

## Qualification layers

Live checks performed on 2026-10-16 UTC with Docker Engine 28.1.1 / Docker Desktop.
Three scopes are distinguished below: existing firmware images with mounted
helpers, newly built images using installed entrypoints, and Compose services
with host TCP clients. The external ArduPilot checkout was not edited.

### Existing-image baseline

The first checks used **existing local images with current repository helpers
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

Requirements: Docker access, the two existing image tags, Python 3 on the host,
and a host checkout visible to Docker bind mounts. Run from the repository root.
The image users must be able to write the artifact directories (tested with the
default UID 1000). Choose a new/empty output directory each time.

```bash
python3 docker/qualify-runtime.py \
  --output artifacts/qualification-copter-4.6.3-final

python3 docker/qualify-runtime.py \
  --family px4 --image px4-sih:sihsim-quadx-v1.16.0 \
  --output artifacts/qualification-px4-v1.16.0-final
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

The managed PX4 status intentionally remains process-only `running`. Automatic
heartbeat readiness and mission/fence/rally initialization are still absent.

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

Run the installed-image suites:

```bash
python3 docker/qualify-runtime.py --installed \
  --image ardupilot-sitl:qualify-c6a991d4 \
  --output artifacts/qualification-packaged-c6a991d4

python3 docker/qualify-runtime.py --installed --family px4 \
  --image px4-sih:qualify-v1.16.0 \
  --output artifacts/qualification-packaged-px4-v1.16.0
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
shutdown and binary-crash behavior. PX4 still has no automatic MAVLink readiness
or image HEALTHCHECK; its managed status is process-only `running`. Explicit
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

- 38 host-only regression tests pass (`python3 -m unittest discover -s docker -p 'test_*.py'`).
- Python compilation, Bash syntax, the POSIX PX4 startup-hook syntax, Compose
  configuration, local Markdown links and `git diff --check` pass.
- Static `docker buildx build --check` completes for both Dockerfiles. Actual
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
- Qualify PX4 bridge/host networking and implement its explicit initialization
  readiness separately. External dynamics require the experiments in
  [RUNTIME_PROFILES.md](RUNTIME_PROFILES.md).

See [FUTURE_WORK.md](FUTURE_WORK.md) for the actionable backlog. Do not generalize
these results into a complete release matrix, physics validation, flight test
or checkpoint guarantee. Installed-image evidence applies only to the image IDs
listed above.
