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
- Update `RESEARCH.md` and `DESIGN.md` when `.BIN`, `.tlog`, or other
  post-run analysis artifact decisions change.
- Update `FUTURE_WORK.md` when a future improvement is added, removed, or
  clarified.
- Update `CHANGELOG.md` when notable user-facing behavior, build/release flow,
  runtime configuration, or documentation structure changes.
- Update `SESSION_SUMMARY.md` when preserving chronological session context is
  useful.
- Keep docs concise and operational.


## Verification


## Child DOX Index

No child DOX files.
