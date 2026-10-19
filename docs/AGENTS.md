# Documentation DOX


## Purpose

Owns durable project documentation beyond quick user commands.


## Ownership

- `DESIGN.md`: architecture, philosophy, trade-offs, and decision rationale.
- `RESEARCH.md`: index of research notes and investigation status.
- `INITIAL_STATE.md`: research and recommendations for SITL initial-state and
  runtime Lua support.
- `PLAN_ARTIFACTS.md`: research and recommendations for mission, fence, rally,
  and multi-SITL artifact organization.
- `PX4_SIH.md`: research and runtime design notes for the PX4 SIH sibling
  image.
- `PX4_JSBSIM.md`: experimental PX4/JSBSim build/run/catalog guide, simulator
  transport and sensor contracts, bridge reuse assessment and qualified limits.
- `EXTERNAL_SIMULATORS.md`: external physics and flight-dynamics simulator
  options for ArduPilot and PX4.
- `RUNTIME_PROFILES.md`: four-profile terminology, proposed external-dynamics
  architecture, capability contracts, research evidence and qualification plan.
- `ARDUCOPTER_JSBSIM.md`: experimental no-fork quad-X integration/usage, read-only
  multi-model catalogs and selection, adapter ownership,
  physics/lifecycle contracts and qualification gates; update for backend selection
  or implementation findings without presenting proposals as verified behavior.
- `RUNTIME_QUALIFICATION.md`: tested real-firmware environments, reproduction
  commands, observed results/fixes and unqualified boundaries.
- Runtime analysis log research currently lives in `RESEARCH.md` and
  `DESIGN.md` unless it grows into a dedicated note.
- `FUTURE_WORK.md`: action-oriented backlog and improvement ideas.
- `CHANGELOG.md`: release-facing summary of notable project changes, sourced
  from commit history and durable docs.
- `SESSION_SUMMARY.md`: chronological dev log for prompts, answers, and session
  context.


## Local Contracts

- Keep design rationale separate from backlog items.
- Keep `RESEARCH.md` as an index and routing doc, not a dumping ground for long
  research notes.
- Keep `CHANGELOG.md` release-facing and user-readable; keep chronological
  prompt/session details in `SESSION_SUMMARY.md`.
- Keep README-facing workflow details in `README.md`; link here for deeper
  rationale.


## Work Guidance

- Update `DESIGN.md` when project architecture, philosophy, or durable decisions
  change.
- Update `RESEARCH.md` when a research note is added, removed, renamed, or its
  status changes.
- Update `INITIAL_STATE.md` when ArduPilot SITL state-injection research,
  runtime Lua recommendations, or initial-state design decisions change.
- Update `PLAN_ARTIFACTS.md` when mission, fence, rally, scenario bundle, or
  multi-SITL artifact design decisions change.
- Update `PX4_SIH.md` when PX4 SIH build, runtime, networking, or env
  conventions change.
- Update `EXTERNAL_SIMULATORS.md` when external backend options, support
  status, or integration boundaries change.
- Update `RUNTIME_PROFILES.md` when runtime-profile boundaries, external backend
  design assumptions or qualification findings change. Distinguish proposals,
  upstream findings and locally verified capabilities; profiles are not a fixed
  image/container count.
- Update `RESEARCH.md` and `DESIGN.md` when `.BIN`, `.tlog`, or other
  post-run analysis artifact decisions change.
- Update `RUNTIME_QUALIFICATION.md` when live runtime checks establish new
  compatibility evidence or expose a defect. Separate mounted-helper results
  from installed-image qualification and retain exact firmware/image identities.
- Update `FUTURE_WORK.md` when a future improvement is added, removed, or
  clarified.
- Update `CHANGELOG.md` when notable user-facing behavior, build/release flow,
  runtime configuration, or documentation structure changes.
- Update `SESSION_SUMMARY.md` when preserving chronological session context is
  useful.
- Audit examples against build scripts, Dockerfiles, entrypoints and Compose:
  build/run tags must agree, release-specific targets must be explicit, and
  runtime-family scope must be visible. Check full workflows, not just feature links.
- Preserve historical results with exact identities; label superseded commands
  and defaults as historical rather than rewriting evidence as current behavior.
- Keep docs concise and operational.


## Verification


## Child DOX Index

No child DOX files.
