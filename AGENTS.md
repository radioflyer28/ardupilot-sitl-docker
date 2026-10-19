# DOX Framework

DOX is a highly performant `AGENTS.md` hierarchy installed here.
Agents must follow DOX instructions across any edits.


## Core Contract

- `AGENTS.md` files are binding work contracts for their subtrees.
- Work products, source materials, instructions, records, assets, and durable
  docs must stay understandable from the nearest applicable `AGENTS.md` plus
  every parent `AGENTS.md` above it.


## Read Before Editing

1. Read the root `AGENTS.md`.
2. Identify every file or folder you expect to touch.
3. Walk from the repository root to each target path.
4. Read every `AGENTS.md` found along each route.
5. If a parent `AGENTS.md` lists a child `AGENTS.md` whose scope contains the
   path, read that child and continue from there.
6. Use the nearest `AGENTS.md` as the local contract and parent docs for
   repo-wide rules.
7. If docs conflict, the closer doc controls local work details, but no child
   doc may weaken DOX.

Do not rely on memory. Re-read the applicable DOX chain in the current session
before editing.


## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning `AGENTS.md` when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or
  quality
- `AGENTS.md` creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child
index changes. Update child docs when parent changes alter local rules. Remove
stale or contradictory text immediately. Small edits that do not change behavior
or contracts may leave docs unchanged, but the DOX pass still must happen.


## Hierarchy

- Root `AGENTS.md` is the DOX rail: project-wide instructions, global
  preferences, durable workflow rules, and the top-level Child DOX Index.
- Child `AGENTS.md` files own domain-specific instructions and their own Child
  DOX Index.
- Each parent explains what its direct children cover and what stays owned by
  the parent.
- The closer a doc is to the work, the more specific and practical it must be.


## Child Doc Shape

- Create a child `AGENTS.md` when a folder becomes a durable boundary with its
  own purpose, rules, responsibilities, workflow, materials, or quality
  standards.
- Work Guidance must reflect the current standards of the project or user
  instructions; if there are no specific standards or instructions yet, leave it
  empty.
- Verification must reflect an existing check; if no verification framework
  exists yet, leave it empty and update it when one exists.

Default section order:

- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index


## Style

- Keep docs concise, current, and operational.
- Document stable contracts, not diary entries.
- Put broad rules in parent docs and concrete details in child docs.
- Prefer direct bullets with explicit names.
- Do not duplicate rules across many files unless each scope needs a local
  version.
- Delete stale notes instead of explaining history.
- Trim obvious statements, repeated rules, misplaced detail, and warnings for
  risks that no longer exist.


## Project Contracts

- This repository builds and documents Docker images for pre-built SITL
  runtimes. ArduPilot SITL is the mature primary path; PX4 is a sibling family
  with SIH and experimental JSBSim paths. Runtime images run SITL; they do not
  rebuild the autopilot after startup.
- Treat `./ardupilot` as an external checkout. Do not edit it unless the user
  explicitly asks for upstream ArduPilot changes. It contains its own
  `AGENTS.md`.
- Keep generated or heavy artifacts out of git by default, including
  `.buildx-cache/`, `dist/images/`, `configs/generated-frames/`, and local
  `artifacts/` run directories.
- Managed autopilot runtimes own one vehicle and one writable run root. Keep read-only
  inputs separate from `work/` and archived `history/`; never clear an unowned
  nonempty directory. Shared fresh/resume semantics must not imply identical
  ArduPilot and PX4 readiness capabilities.
- Keep Dockerfile COPY sources and `.dockerignore` allowlists aligned when adding
  runtime helpers; packaging tests must exercise installed entrypoints, not only
  mounted source helpers.
- Keep checked-in config bundles small and example-oriented. Use
  `scripts/populate-config-bundles.py` for full generated catalogs.
- Keep the README user-facing. Put design rationale in `docs/DESIGN.md`,
  research indexes in `docs/RESEARCH.md`, future work in
  `docs/FUTURE_WORK.md`, release-facing history in `docs/CHANGELOG.md`, and
  session history in `docs/SESSION_SUMMARY.md`.


## Verification

Use the narrowest relevant checks. `.github/workflows/checks.yml` runs host-only
PR checks without firmware/image builds or live containers:

- Dockerfile edits: `docker buildx build --check -f Dockerfile .`
- Release script edits:
  `for script in scripts/*.sh; do bash -n "$script"; done`
- Python helper edits:
  `python3 -m py_compile scripts/populate-config-bundles.py docker/*.py`
- Runtime configuration/lifecycle/protocol edits:
  `python3 -m unittest discover -s docker -p 'test_*.py'` and
  `for script in docker/*.sh; do bash -n "$script"; done` and
  `for script in docker/px4-rc.*; do sh -n "$script"; done`
- Config bundle edits:
  `python3 -m json.tool configs/frames/arducopter-quad/vehicleinfo.json` and
  `python3 -m json.tool configs/frames/arduplane-plane/vehicleinfo.json`
- Compose edits: `docker compose -f compose.sitl.yml config` and
  `PX4_SIH_IMAGE=px4-sih:config-only docker compose -f compose.px4-sih.yml config`;
  external physics: `docker compose -f compose.jsbsim.yml config`.
- Live firmware/image/Compose qualification: use the opt-in commands and exact
  tested-version boundaries in `docs/RUNTIME_QUALIFICATION.md`.

Docker commands require Docker daemon access and may require escalation in
sandboxed environments.


## Closeout

1. Re-check changed paths against the DOX chain.
2. Update nearest owning docs and any affected parents or children.
3. Refresh every affected Child DOX Index.
4. Remove stale or contradictory text.
5. Run existing verification when relevant.
6. Report any docs intentionally left unchanged and why.


## User Preferences

- Deployment targets an office workstation and local LAN, never the public
  Internet. LAN reachability in PX4 host-network mode is intentional; do not
  impose firewall configuration as a runtime prerequisite for this deployment.
- Default host-facing Docker publications to localhost for both runtimes; keep
  LAN access an explicit `SITL_BIND_ADDRESS` opt-in. Preserve container-internal
  listeners needed for Docker forwarding rather than binding them to loopback.
- Preserve expected localhost and LAN client connectivity. Do not add security
  restrictions that break these connections or change bind/publication defaults
  without an explicit request; explain trade-offs instead of silently locking down.
- Default single-vehicle ArduCopter/JSBSim and PX4/JSBSim to one combined container with an
  isolated physics Python environment; retain the explicit two-container option.
  Share adapter/model logic and qualify both deployment lifecycles.
- Keep custom external-physics adapters in project-owned code outside
  `./ardupilot`; prefer existing upstream interfaces over an ArduPilot fork.
- Keep generated SITL/GCS telemetry and runtime state out of commits through
  `.gitignore`; preserve intentional parameter/config inputs under `configs/`.
- Keep the repo uncluttered. Prefer small checked-in examples plus generators
  for large derived catalogs. RE: scripts/populate-config-bundles.py


## Child DOX Index

- `.github/AGENTS.md`: lightweight GitHub Actions checks and automation constraints.
- `configs/AGENTS.md`: runtime SITL config bundles and generated catalog rules.
- `docker/AGENTS.md`: runtime configuration, lifecycle/state, artifact upload
  helpers and regression/live qualification tests.
- `docs/AGENTS.md`: design, research, backlog, and durable documentation rules.
- `scripts/AGENTS.md`: build/export and config generation scripts.

Root-owned files include `Dockerfile`, `Dockerfile.px4-sih`, `Dockerfile.jsbsim`,
`compose.jsbsim.yml`, `compose.jsbsim-models.yml`, `compose.jsbsim-split.yml`,
`compose.jsbsim-split-models.yml`, `README.md`,
`compose.sitl.yml`, `compose.px4-sih.yml`, `Dockerfile.px4-jsbsim`,
`compose.px4-jsbsim*.yml`, `env.list`, `.dockerignore`, and `.gitignore`.
