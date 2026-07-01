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
  runtimes. ArduPilot SITL is the mature primary path; PX4 SIH is a sibling
  runtime path. Keep runtime images focused on running SITL, not rebuilding the
  autopilot after startup.
- Treat `./ardupilot` as an external checkout. Do not edit it unless the user
  explicitly asks for upstream ArduPilot changes. It contains its own
  `AGENTS.md`.
- Keep generated or heavy artifacts out of git by default, including
  `.buildx-cache/`, `dist/images/`, and `configs/generated-frames/`.
- Keep checked-in config bundles small and example-oriented. Use
  `scripts/populate-config-bundles.py` for full generated catalogs.
- Keep the README user-facing. Put design rationale in `docs/DESIGN.md`,
  research indexes in `docs/RESEARCH.md`, future work in
  `docs/FUTURE_WORK.md`, release-facing history in `docs/CHANGELOG.md`, and
  session history in `docs/SESSION_SUMMARY.md`.


## Verification

Use the narrowest relevant checks:

- Dockerfile edits: `docker buildx build --check -f Dockerfile .`
- Release script edits:
  `bash -n scripts/build-release-image.sh scripts/build-px4-sih-image.sh`
- Python helper edits:
  `python3 -m py_compile scripts/populate-config-bundles.py docker/resolve-sitl-config.py`
- Config bundle edits:
  `python3 -m json.tool configs/frames/arducopter-quad/vehicleinfo.json` and
  `python3 -m json.tool configs/frames/arduplane-plane/vehicleinfo.json`
- Compose edits: `docker compose -f compose.sitl.yml config`

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

- Keep the repo uncluttered. Prefer small checked-in examples plus generators
  for large derived catalogs. RE: scripts/populate-config-bundles.py


## Child DOX Index

- `configs/AGENTS.md`: runtime SITL config bundles and generated catalog rules.
- `docker/AGENTS.md`: runtime config resolver and Docker helper code.
- `docs/AGENTS.md`: design, research, backlog, and durable documentation rules.
- `scripts/AGENTS.md`: build/export and config generation scripts.

Root-owned files include `Dockerfile`, `Dockerfile.px4-sih`, `README.md`,
`compose.sitl.yml`, `env.list`, `.dockerignore`, and `.gitignore`.
